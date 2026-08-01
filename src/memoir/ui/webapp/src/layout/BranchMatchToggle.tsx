import { useEffect, useState } from "react";
import { api, MemoirApiError } from "../api/client";
import { useStore } from "../state/storeSlice";

/**
 * Toggles the memoir-branch-follows-code-branch enforcement the Claude
 * Code / Codex plugin hooks apply (`auto_match_memoir_branch` in
 * `hooks/common.sh`). Mirrors `memoir branch-match on|off`; both read/write
 * the same per-store marker file, so the CLI, this button, and the hooks
 * always agree on the current state.
 */
export default function BranchMatchToggle() {
  const storePath = useStore((s) => s.storePath);
  const status = useStore((s) => s.status);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!storePath || status !== "connected") {
      setEnabled(null);
      return;
    }
    api
      .getBranchMatchConfig(storePath)
      .then((res) => {
        if (!cancelled) setEnabled(res.enabled);
      })
      .catch(() => {
        if (!cancelled) setEnabled(null);
      });
    return () => {
      cancelled = true;
    };
  }, [storePath, status]);

  if (!storePath || status !== "connected" || enabled === null) return null;

  const onClick = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.setBranchMatchConfig(storePath, !enabled);
      setEnabled(res.enabled);
    } catch (err) {
      setError(err instanceof MemoirApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      className="btn btn-ghost btn-sm"
      onClick={onClick}
      disabled={busy}
      aria-pressed={enabled}
      title={
        error
          ? `Failed: ${error}`
          : enabled
            ? "Branch auto-matching is ON — click to stop the memoir branch from following your code branch"
            : "Branch auto-matching is OFF — click to resume following your code branch"
      }
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M9 6a4 4 0 1 1 0 8" />
        <path d="M9 6v12" />
        <circle cx="18" cy="6" r="3" />
        <circle cx="6" cy="18" r="3" />
      </svg>
      <span>Auto-match {enabled ? "on" : "off"}</span>
    </button>
  );
}
