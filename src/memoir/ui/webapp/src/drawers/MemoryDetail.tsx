import { useEffect, useMemo, useState } from "react";
import type { BlameEntry, Memory } from "../api/types";
import { api, MemoirApiError } from "../api/client";
import { useStore } from "../state/storeSlice";
import { useConfig } from "../state/configSlice";
import { useMemorySelection } from "../state/memorySelectionSlice";
import { useUI } from "../state/uiSlice";
import { relativeTimeFromISO } from "../lib/time";
import "./DrawerPanels.css";

interface MemoryDetailProps {
  memory: Memory;
}

/**
 * Memory editor mirroring v1's "Memory Details" popup:
 *   - FULL KEY + NAMESPACE rows with copy buttons
 *   - Editable content textarea (always live; Save commits via
 *     /api/update-memory which bypasses the LLM classifier)
 *   - "Or describe how to change it (uses an LLM)" textarea +
 *     Rewrite button → /api/rewrite-memory loads the proposed text
 *     back into the editor; the user reviews and saves.
 *   - TYPE (Leaf / Branch) + CONNECTIONS (sibling memories) at bottom
 *
 * Save records edit-source in the commit message:
 *   - "manual" if the user only typed
 *   - "llm" if the user accepted an AI rewrite verbatim
 *   - "llm+manual" if the user tweaked the LLM output before saving
 */
export default function MemoryDetail({ memory }: MemoryDetailProps) {
  const storePath = useStore((s) => s.storePath);
  const allMemories = useStore((s) => s.data?.memories ?? []);
  const writable = useConfig((s) => s.writable);
  const useLLM = useConfig((s) => s.useLLM);

  const [content, setContent] = useState(memory.content ?? "");
  const [instructions, setInstructions] = useState("");
  const [editSource, setEditSource] = useState<"manual" | "llm" | "llm+manual">(
    "manual",
  );
  const [saving, setSaving] = useState(false);
  const [rewriting, setRewriting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<"key" | "namespace" | null>(null);

  // Reset local edit state whenever the user picks a different memory.
  useEffect(() => {
    setContent(memory.content ?? "");
    setInstructions("");
    setEditSource("manual");
    setError(null);
  }, [memory.key]);

  const dirty = content !== (memory.content ?? "");

  const { type, connections } = useMemo(
    () => computeTaxonomyMeta(memory, allMemories),
    [memory, allMemories],
  );

  const onCopy = async (text: string, which: "key" | "namespace") => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(which);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

  const onSave = async () => {
    if (!storePath) return;
    setSaving(true);
    setError(null);
    try {
      await api.updateMemory(storePath, memory.path, content, {
        namespace: memory.namespace,
        editSource,
        instructions,
      });
      // Refresh the store so the rest of the UI sees the new content.
      await useStore.getState().refresh();
      // Reset the edit source for the next round.
      setEditSource("manual");
      setInstructions("");
    } catch (err) {
      setError(err instanceof MemoirApiError ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const onCancel = () => {
    setContent(memory.content ?? "");
    setInstructions("");
    setEditSource("manual");
    setError(null);
  };

  const onRewrite = async () => {
    if (!instructions.trim()) return;
    setRewriting(true);
    setError(null);
    try {
      const res = await api.rewriteMemory(content, instructions, memory.key);
      setContent(res.new_content);
      // Mark this edit as LLM-driven; if the user later tweaks the text
      // before saving, the textarea handler upgrades it to "llm+manual".
      setEditSource("llm");
    } catch (err) {
      setError(err instanceof MemoirApiError ? err.message : String(err));
    } finally {
      setRewriting(false);
    }
  };

  const onContentChange = (next: string) => {
    setContent(next);
    if (editSource === "llm") setEditSource("llm+manual");
  };

  return (
    <div className="drawer-panel memory-detail">
      {/* FULL KEY row with copy */}
      <section className="drawer-panel-section">
        <div className="memory-kv-row">
          <span className="memory-kv-label">Full key</span>
          <code className="memory-kv-value">{memory.key}</code>
          <button
            type="button"
            className="memory-copy-btn"
            onClick={() => onCopy(memory.key, "key")}
          >
            {copied === "key" ? "✓ Copied" : "Copy"}
          </button>
        </div>
        <div className="memory-kv-row">
          <span className="memory-kv-label">Namespace</span>
          <code className="memory-kv-value">{memory.namespace}</code>
          <button
            type="button"
            className="memory-copy-btn"
            onClick={() => onCopy(memory.namespace, "namespace")}
          >
            {copied === "namespace" ? "✓ Copied" : "Copy"}
          </button>
        </div>
      </section>

      {/* Editable content */}
      <section className="drawer-panel-section">
        <label className="memory-edit-label" htmlFor="memory-content-edit">
          Edit content for <code>{memory.key}</code>
        </label>
        <textarea
          id="memory-content-edit"
          className="memory-edit-textarea"
          value={content}
          onChange={(e) => onContentChange(e.target.value)}
          spellCheck
          rows={6}
          placeholder="(no textual content)"
        />
      </section>

      {/* LLM rewrite — only when the server was started with --usellm.
       * Without that flag the /api/rewrite-memory endpoint will fail,
       * so hiding the input is honest about what's available rather
       * than letting users type into a dead box. */}
      {useLLM && (
        <section className="drawer-panel-section">
          <label className="memory-edit-label" htmlFor="memory-rewrite-instructions">
            Or describe how to change it (uses an LLM):
          </label>
          <textarea
            id="memory-rewrite-instructions"
            className="memory-rewrite-textarea"
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            rows={2}
            placeholder="e.g. Make it more concise. / Add a note about the deadline. / Translate to French."
          />
          <div className="memory-rewrite-actions">
            <button
              type="button"
              className="memory-rewrite-btn"
              onClick={onRewrite}
              disabled={!instructions.trim() || rewriting}
            >
              {rewriting ? "Rewriting…" : "✨ Rewrite with AI"}
            </button>
          </div>
        </section>
      )}

      {error && (
        <p className="drawer-error">{error}</p>
      )}

      {/* Save / Cancel — Save is hidden in readonly mode because the
       * backend will reject /api/update-memory without --no-readonly. */}
      <section className="drawer-panel-section memory-action-row">
        {!writable && (
          <span
            className="memory-readonly-note"
            title="Server is in readonly mode (relaunch with --no-readonly to enable edits)"
          >
            readonly mode — edits disabled
          </span>
        )}
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={onCancel}
          disabled={!dirty || saving}
        >
          Cancel
        </button>
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={onSave}
          disabled={!dirty || saving || !writable}
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </section>

      {/* Meta footer */}
      <section className="drawer-panel-section memory-meta-footer">
        <div className="memory-meta-row">
          <span className="memory-meta-label">Type</span>
          <span className="memory-meta-value">{type}</span>
        </div>
        <div className="memory-meta-row">
          <span className="memory-meta-label">Connections</span>
          <span className="memory-meta-value">{connections}</span>
        </div>
      </section>

      {/* Commit history for this key — git-blame-style. Refetches when the
       * user picks a different memory; not auto-refreshed on save (the
       * Commits tab is the live picture). */}
      <HistorySection memory={memory} />

      {/* Related keys — sibling paths this content was co-saved under. Empty
       * for single-key memories. Each chip navigates the drawer to that key
       * via the same path the graph uses. */}
      <RelatedKeysSection memory={memory} />
    </div>
  );
}

function RelatedKeysSection({ memory }: { memory: Memory }) {
  const allMemories = useStore((s) => s.data?.memories ?? []);
  const select = useMemorySelection((s) => s.select);
  const pushPanel = useUI((s) => s.pushPanel);

  const related = useMemo(() => normalizeRelatedKeys(memory.value), [memory.value]);

  if (related.length === 0) return null;

  // Resolve each related path against the loaded memories so we can light
  // up dead chips when the linked memory isn't in the current view (e.g.,
  // namespace filter excludes it).
  const resolved = related.map((path) => ({
    path,
    target: allMemories.find(
      (m) => m.namespace === memory.namespace && m.path === path,
    ),
  }));

  const onChipClick = (target: Memory) => {
    select(target);
    pushPanel({ kind: "memory-detail", memory: target });
  };

  return (
    <section className="drawer-panel-section memory-related-keys">
      <div className="memory-related-keys-header">
        <span className="memory-meta-label">Related keys</span>
        <span className="memory-history-count">{related.length}</span>
      </div>
      <ul className="memory-related-keys-list">
        {resolved.map(({ path, target }) => (
          <li key={path}>
            <button
              type="button"
              className="memory-related-key-chip"
              disabled={!target}
              onClick={target ? () => onChipClick(target) : undefined}
              title={target ? path : `${path} (not loaded in current view)`}
            >
              {path}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function normalizeRelatedKeys(value: Record<string, unknown>): string[] {
  const raw = value?.related_keys;
  if (!Array.isArray(raw)) return [];
  return raw.filter((k): k is string => typeof k === "string" && k.length > 0);
}

function HistorySection({ memory }: { memory: Memory }) {
  const storePath = useStore((s) => s.storePath);
  const [entries, setEntries] = useState<BlameEntry[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!storePath) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .blame(storePath, memory.path, memory.namespace)
      .then((res) => {
        if (cancelled) return;
        setEntries(res.entries);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof MemoirApiError ? err.message : String(err));
        setEntries([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [storePath, memory.key, memory.namespace, memory.path]);

  return (
    <section className="drawer-panel-section memory-history">
      <div className="memory-history-header">
        <span className="memory-meta-label">History</span>
        {entries && entries.length > 0 && (
          <span className="memory-history-count">{entries.length}</span>
        )}
      </div>
      {loading && <p className="memory-history-empty">Loading…</p>}
      {!loading && error && <p className="drawer-error">{error}</p>}
      {!loading && !error && entries && entries.length === 0 && (
        <p className="memory-history-empty">No commit history yet.</p>
      )}
      {!loading && !error && entries && entries.length > 0 && (
        <ul className="memory-history-list">
          {entries.map((entry, idx) => (
            <li key={`${entry.commit}-${idx}`} className="memory-history-row">
              <code className="memory-history-sha" title={entry.commit}>
                {entry.commit}
              </code>
              <span className="memory-history-message" title={entry.message}>
                {entry.message || "(no message)"}
              </span>
              <span
                className="memory-history-meta"
                title={`${entry.author}${entry.date ? ` · ${entry.date}` : ""}`}
              >
                {shortAuthor(entry.author)}
                {entry.date && (
                  <>
                    {" · "}
                    {relativeTimeFromISO(entry.date)}
                  </>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// "Name <email>" → "Name". Falls back to the raw string when there's no name.
function shortAuthor(author: string): string {
  const lt = author.indexOf("<");
  if (lt > 0) return author.slice(0, lt).trim();
  return author;
}

function computeTaxonomyMeta(
  memory: Memory,
  allMemories: Memory[],
): { type: "Leaf" | "Branch"; connections: number } {
  // "Branch" = at least one other memory has this memory's path as a
  // prefix (e.g., memory at `workflow.coding`, others at
  // `workflow.coding.style`). Otherwise it's a Leaf.
  const sameNs = allMemories.filter(
    (m) => m.namespace === memory.namespace && m.key !== memory.key,
  );
  const childPrefix = `${memory.path}.`;
  const isBranch = sameNs.some((m) => m.path.startsWith(childPrefix));

  // Connections = siblings (memories under the immediate parent prefix,
  // not counting self) plus children we own. This matches the v1 popup's
  // intent: "how many other memories share my context".
  const dot = memory.path.lastIndexOf(".");
  const parentPrefix = dot < 0 ? "" : memory.path.slice(0, dot + 1); // "" for top-level
  const siblings = sameNs.filter(
    (m) => parentPrefix === "" || m.path.startsWith(parentPrefix),
  );
  return {
    type: isBranch ? "Branch" : "Leaf",
    connections: siblings.length,
  };
}
