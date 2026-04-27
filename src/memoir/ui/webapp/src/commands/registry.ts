import { useStore } from "../state/storeSlice";
import { useUI } from "../state/uiSlice";
import { useSelection } from "../state/selectionSlice";
import { api, MemoirApiError } from "../api/client";

/**
 * Tag flags surfaced as small badges on the command-reference cards.
 * Mirrors v1's READONLY pill plus a couple of extra signals we now have.
 */
export type CommandTag = "readonly" | "mutating" | "llm" | "selection";

/** Category grouping shown as section headers in the Command Reference. */
export type CommandCategory =
  | "core"
  | "navigation"
  | "selection"
  | "ui"
  | "system";

export interface CommandDef {
  name: string;
  aliases: string[];
  summary: string;
  usage: string;
  category: CommandCategory;
  tags: CommandTag[];
  /** Optional longer-form help shown in the reference modal, beneath summary. */
  longDescription?: string;
  run: (args: string[]) => void | Promise<void>;
}

const registry: Map<string, CommandDef> = new Map();

function register(def: CommandDef) {
  registry.set(def.name, def);
  for (const alias of def.aliases) registry.set(alias, def);
}

// ---------- Core operations ----------

register({
  name: "connect",
  aliases: ["con", "conn"],
  summary: "Connect to a memoir store on disk",
  usage: "/connect <path>",
  category: "core",
  tags: ["readonly"],
  longDescription:
    "Reads the store at <path>, populates Commits + Tree + Graph, and announces in the history.",
  async run(args) {
    const path = args.join(" ").trim();
    if (!path) {
      useStore.getState().pushHistory({
        input: "/connect",
        level: "warning",
        lines: ["Missing path. Usage: /connect <path>"],
      });
      return;
    }
    await useStore.getState().connect(path);
  },
});

register({
  name: "disconnect",
  aliases: [],
  summary: "Drop the current store connection",
  usage: "/disconnect",
  category: "core",
  tags: [],
  run() {
    useStore.getState().disconnect();
  },
});

register({
  name: "refresh",
  aliases: ["r", "ref"],
  summary: "Re-read the currently connected store",
  usage: "/refresh",
  category: "core",
  tags: ["readonly"],
  async run() {
    await useStore.getState().refresh();
  },
});

register({
  name: "status",
  aliases: ["s"],
  summary: "Show connection status + store summary",
  usage: "/status",
  category: "core",
  tags: ["readonly"],
  run() {
    const s = useStore.getState();
    if (!s.storePath) {
      s.pushHistory({
        input: "/status",
        level: "info",
        lines: ["No store connected. Run /connect <path>."],
      });
      return;
    }
    const d = s.data;
    const lines = [
      `path     ${s.storePath}`,
      `status   ${s.status}${s.error ? ` — ${s.error}` : ""}`,
    ];
    if (d) {
      lines.push(
        `branch   ${d.current_branch}  (of ${d.branches.length}: ${d.branches.join(", ")})`,
        `commits  ${d.commits.length}`,
        `memories ${d.total_memories}`,
      );
    }
    s.pushHistory({ input: "/status", level: "info", lines });
  },
});

// ---------- Navigation ----------

register({
  name: "commits",
  aliases: ["log"],
  summary: "Switch to the Commits view",
  usage: "/commits",
  category: "navigation",
  tags: [],
  run() {
    useUI.getState().setActiveView("commits");
    useStore.getState().pushHistory({
      input: "/commits",
      level: "info",
      lines: ["Switched to Commits view."],
    });
  },
});

register({
  name: "outline",
  aliases: ["tree"],
  summary: "Switch to the Outline (taxonomy) view",
  usage: "/outline",
  category: "navigation",
  tags: [],
  run() {
    useUI.getState().setActiveView("tree");
    useStore.getState().pushHistory({
      input: "/outline",
      level: "info",
      lines: ["Switched to Outline view."],
    });
  },
});

register({
  name: "map",
  aliases: ["graph"],
  summary: "Switch to the Map view (taxonomy force-directed graph)",
  usage: "/map",
  category: "navigation",
  tags: [],
  run() {
    useUI.getState().setActiveView("graph");
    useStore.getState().pushHistory({
      input: "/map",
      level: "info",
      lines: ["Switched to Map view. Drag to pan, scroll to zoom."],
    });
  },
});

register({
  name: "timeline",
  aliases: ["tl"],
  summary: "Switch to the Timeline view",
  usage: "/timeline",
  category: "navigation",
  tags: [],
  run() {
    useUI.getState().setActiveView("timeline");
    useStore.getState().pushHistory({
      input: "/timeline",
      level: "info",
      lines: ["Switched to Timeline view."],
    });
  },
});

register({
  name: "places",
  aliases: ["locations"],
  summary: "Switch to the Places view",
  usage: "/places",
  category: "navigation",
  tags: [],
  run() {
    useUI.getState().setActiveView("places");
    useStore.getState().pushHistory({
      input: "/places",
      level: "info",
      lines: ["Switched to Places view."],
    });
  },
});

// ---------- Selection ----------

register({
  name: "diff",
  aliases: ["d"],
  summary: "Show a range diff between two commits",
  usage: "/diff [from] [to]",
  category: "selection",
  tags: ["readonly", "selection"],
  longDescription:
    "With no args, uses the two most recently shift-clicked commits. With explicit hashes, jumps directly.",
  run(args) {
    let fromHash: string | undefined = args[0];
    let toHash: string | undefined = args[1];

    if (!fromHash || !toHash) {
      const selected = Array.from(useSelection.getState().selectedHashes);
      if (selected.length < 2) {
        useStore.getState().pushHistory({
          input: "/diff",
          level: "warning",
          lines: [
            "Need two commit hashes (or two selected commits).",
            "Usage: /diff <from> <to>, or shift-click two commits first.",
          ],
        });
        return;
      }
      [fromHash, toHash] = selected;
    }

    useUI.getState().pushPanel({
      kind: "range-diff",
      fromHash,
      toHash,
    });
    useStore.getState().pushHistory({
      input: `/diff ${fromHash.slice(0, 7)} ${toHash.slice(0, 7)}`,
      level: "info",
      lines: [`Showing diff ${fromHash.slice(0, 7)} → ${toHash.slice(0, 7)} in drawer.`],
    });
  },
});

register({
  name: "deselect",
  aliases: [],
  summary: "Clear commit / memory selection",
  usage: "/deselect",
  category: "selection",
  tags: ["selection"],
  run() {
    useSelection.getState().clear();
    useStore.getState().pushHistory({
      input: "/deselect",
      level: "info",
      lines: ["Selection cleared."],
    });
  },
});

// ---------- UI / system ----------

register({
  name: "stats",
  aliases: ["statistics"],
  summary: "Open the statistics modal for the connected store",
  usage: "/stats",
  category: "ui",
  tags: ["readonly"],
  run() {
    if (!useStore.getState().storePath) {
      useStore.getState().pushHistory({
        input: "/stats",
        level: "warning",
        lines: ["Connect a store first: /connect <path>"],
      });
      return;
    }
    useUI.getState().openStats();
  },
});

register({
  name: "help",
  aliases: ["h", "?"],
  summary: "Open the command reference",
  usage: "/help [command]",
  category: "ui",
  tags: [],
  longDescription:
    "With no args, opens the full command reference modal. With a command name, prints that one's signature into the history log.",
  run(args) {
    const target = args[0];
    const s = useStore.getState();
    if (target) {
      // Single-command lookup keeps the legacy text behavior — useful when
      // typing `/help connect` to remind yourself of one signature.
      const def = registry.get(target.replace(/^\//, ""));
      if (!def) {
        s.pushHistory({
          input: `/help ${target}`,
          level: "warning",
          lines: [`Unknown command: ${target}`],
        });
        return;
      }
      s.pushHistory({
        input: `/help ${target}`,
        level: "info",
        lines: [
          `${def.usage}`,
          `  ${def.summary}`,
          def.aliases.length > 0 ? `  aliases: ${def.aliases.join(", ")}` : "",
        ].filter(Boolean),
      });
      return;
    }
    useUI.getState().openHelp();
  },
});

register({
  name: "clear",
  aliases: [],
  summary: "Clear command history",
  usage: "/clear",
  category: "system",
  tags: [],
  run() {
    useStore.getState().clearHistory();
  },
});

// ====================================================================
// V1-parity commands.
//
// The helpers below follow a tight shape: capture store path → call API
// → push a one-or-two-line summary into history. Errors are normalised
// through ``pushError``. Anything that needs a richer side panel
// (proof / blame / range-diff) routes through useUI.pushPanel into the
// drawer; everything else just lives in the command log.
// ====================================================================

function requireStorePath(input: string): string | null {
  const path = useStore.getState().storePath;
  if (!path) {
    useStore.getState().pushHistory({
      input,
      level: "warning",
      lines: ["Connect a store first: /connect <path>"],
    });
    return null;
  }
  return path;
}

function pushError(input: string, err: unknown): void {
  const message = err instanceof MemoirApiError ? err.message : String(err);
  useStore.getState().pushHistory({ input, level: "error", lines: [message] });
}

// ---------- Memory store creation ----------

register({
  name: "new",
  aliases: ["create"],
  summary: "Create a new memory store at <path>",
  usage: "/new <path>",
  category: "core",
  tags: ["mutating"],
  longDescription:
    "Initialises a git repo at the given path and connects to it as a memoir store.",
  async run(args) {
    const target = args.join(" ").trim();
    const input = `/new ${target}`;
    if (!target) {
      useStore.getState().pushHistory({
        input: "/new",
        level: "warning",
        lines: ["Missing path. Usage: /new <path>"],
      });
      return;
    }
    try {
      const res = await api.newStore(target);
      useStore.getState().pushHistory({
        input,
        level: "success",
        lines: [res.message ?? `Created store at ${target}`],
      });
      // Auto-connect to the freshly-created store.
      await useStore.getState().connect(res.path ?? target);
    } catch (err) {
      pushError(input, err);
    }
  },
});

// ---------- Memory operations ----------

register({
  name: "remember",
  aliases: ["rem"],
  summary: "Capture content as a new memory (LLM classifies the path)",
  usage: "/remember <content>",
  category: "core",
  tags: ["mutating", "llm"],
  longDescription:
    "Sends the text to the backend's intelligent classifier, which assigns a semantic path and stores it. Requires the server to have been started with --usellm.",
  async run(args) {
    const content = args.join(" ").trim();
    const input = `/remember ${content.slice(0, 40)}${content.length > 40 ? "…" : ""}`;
    if (!content) {
      useStore.getState().pushHistory({
        input: "/remember",
        level: "warning",
        lines: ["Missing content. Usage: /remember <text>"],
      });
      return;
    }
    const path = requireStorePath(input);
    if (!path) return;
    try {
      const res = await api.remember(path, content);
      const key = (res as Record<string, unknown>).key as string | undefined;
      const ns = (res as Record<string, unknown>).namespace as string | undefined;
      useStore.getState().pushHistory({
        input,
        level: "success",
        lines: [
          key
            ? `Stored ${ns ?? "default"}:${key}`
            : "Memory stored.",
          "Run /refresh to update the views.",
        ],
      });
      await useStore.getState().refresh();
    } catch (err) {
      pushError(input, err);
    }
  },
});

register({
  name: "forget",
  aliases: ["del"],
  summary: "Delete a memory by key",
  usage: "/forget <key> [namespace]",
  category: "core",
  tags: ["mutating"],
  longDescription:
    "Removes the memory at the given key. Optional namespace defaults to ``default``.",
  async run(args) {
    const key = args[0];
    const namespace = args[1] ?? "default";
    const input = `/forget ${key ?? ""}`;
    if (!key) {
      useStore.getState().pushHistory({
        input: "/forget",
        level: "warning",
        lines: ["Missing key. Usage: /forget <key> [namespace]"],
      });
      return;
    }
    const path = requireStorePath(input);
    if (!path) return;
    try {
      await api.forget(path, key, namespace);
      useStore.getState().pushHistory({
        input,
        level: "success",
        lines: [`Forgot ${namespace}:${key}`],
      });
      await useStore.getState().refresh();
    } catch (err) {
      pushError(input, err);
    }
  },
});

register({
  name: "recall",
  aliases: ["search"],
  summary: "Search memories with natural language (LLM)",
  usage: "/recall <query>",
  category: "core",
  tags: ["readonly", "llm"],
  longDescription:
    "Runs the intelligent search engine against the connected store and prints the top hits.",
  async run(args) {
    const query = args.join(" ").trim();
    const input = `/recall ${query.slice(0, 40)}${query.length > 40 ? "…" : ""}`;
    if (!query) {
      useStore.getState().pushHistory({
        input: "/recall",
        level: "warning",
        lines: ["Missing query. Usage: /recall <text>"],
      });
      return;
    }
    const path = requireStorePath(input);
    if (!path) return;
    try {
      const res = await api.recall(path, query);
      const lines: string[] = [];
      const memories = (res as Record<string, unknown>).memories;
      if (Array.isArray(memories) && memories.length > 0) {
        for (const m of memories.slice(0, 10)) {
          const r = m as Record<string, unknown>;
          const path = (r.path ?? r.key ?? "?") as string;
          const content = (r.content ?? "") as string;
          const snippet = content.split("\n")[0].slice(0, 80);
          lines.push(`${path}  ${snippet}`);
        }
      } else {
        lines.push("No memories matched.");
      }
      useStore.getState().pushHistory({
        input,
        level: "info",
        lines,
      });
    } catch (err) {
      pushError(input, err);
    }
  },
});

register({
  name: "summarize",
  aliases: ["sum"],
  summary: "Generate a summary of memories (LLM)",
  usage: "/summarize [type]",
  category: "core",
  tags: ["readonly", "llm"],
  longDescription:
    "Type can be all (default), taxonomy, timeline, places, or keys <pattern>.",
  async run(args) {
    const type = args[0] ?? "all";
    const pattern = args[0] === "keys" ? args.slice(1).join(" ") : undefined;
    const input = `/summarize ${type}${pattern ? " " + pattern : ""}`;
    const path = requireStorePath(input);
    if (!path) return;
    try {
      const res = await api.summarize(path, { type, pattern });
      const summary =
        (res as Record<string, unknown>).summary ??
        (res as Record<string, unknown>).result ??
        JSON.stringify(res);
      useStore.getState().pushHistory({
        input,
        level: "info",
        lines: typeof summary === "string" ? summary.split("\n") : [String(summary)],
      });
    } catch (err) {
      pushError(input, err);
    }
  },
});

// ---------- Crypto ----------

register({
  name: "proof",
  aliases: [],
  summary: "Generate a cryptographic proof for a memory key",
  usage: "/proof <key> [namespace]",
  category: "core",
  tags: ["readonly"],
  async run(args) {
    const key = args[0];
    const namespace = args[1] ?? "default";
    const input = `/proof ${key ?? ""}`;
    if (!key) {
      useStore.getState().pushHistory({
        input: "/proof",
        level: "warning",
        lines: ["Missing key. Usage: /proof <key> [namespace]"],
      });
      return;
    }
    const path = requireStorePath(input);
    if (!path) return;
    try {
      const res = await api.proof(path, key, namespace);
      const r = res as Record<string, unknown>;
      const proof = (r.proof ?? "") as string;
      useStore.getState().pushHistory({
        input,
        level: "success",
        lines: [
          `key       ${namespace}:${key}`,
          `proof     ${proof.slice(0, 60)}${proof.length > 60 ? "…" : ""}`,
          `size      ${(r.proof_size ?? "?")} bytes`,
          "Use /verify to confirm.",
        ],
      });
    } catch (err) {
      pushError(input, err);
    }
  },
});

register({
  name: "verify",
  aliases: [],
  summary: "Verify a memory proof",
  usage: "/verify <key> <proof> [namespace]",
  category: "core",
  tags: ["readonly"],
  longDescription:
    "Verifies the supplied proof against the current value of <key>. Returns valid/invalid.",
  async run(args) {
    const key = args[0];
    const proof = args[1];
    const namespace = args[2] ?? "default";
    const input = `/verify ${key ?? ""}`;
    if (!key || !proof) {
      useStore.getState().pushHistory({
        input: "/verify",
        level: "warning",
        lines: ["Usage: /verify <key> <proof> [namespace]"],
      });
      return;
    }
    const path = requireStorePath(input);
    if (!path) return;
    try {
      const res = await api.verify(path, key, proof, namespace);
      const valid = (res as Record<string, unknown>).valid;
      useStore.getState().pushHistory({
        input,
        level: valid ? "success" : "error",
        lines: [valid ? "Proof is valid." : "Proof is invalid."],
      });
    } catch (err) {
      pushError(input, err);
    }
  },
});

register({
  name: "blame",
  aliases: [],
  summary: "Show blame-like history for a memory key",
  usage: "/blame <key> [namespace]",
  category: "core",
  tags: ["readonly"],
  async run(args) {
    const key = args[0];
    const namespace = args[1] ?? "default";
    const input = `/blame ${key ?? ""}`;
    if (!key) {
      useStore.getState().pushHistory({
        input: "/blame",
        level: "warning",
        lines: ["Missing key. Usage: /blame <key> [namespace]"],
      });
      return;
    }
    const path = requireStorePath(input);
    if (!path) return;
    try {
      const res = await api.blame(path, key, namespace);
      const r = res as Record<string, unknown>;
      const history = r.history;
      const lines: string[] = [];
      if (Array.isArray(history)) {
        for (const entry of history.slice(0, 12)) {
          const e = entry as Record<string, unknown>;
          lines.push(
            `${(e.short_hash ?? "").toString().padEnd(8)} ${e.author ?? ""}  ${(e.message ?? "").toString().slice(0, 60)}`,
          );
        }
      }
      useStore.getState().pushHistory({
        input,
        level: "info",
        lines: lines.length > 0 ? lines : ["No history found."],
      });
    } catch (err) {
      pushError(input, err);
    }
  },
});

// ---------- Branch ops ----------

register({
  name: "branches",
  aliases: [],
  summary: "Open the Sync Branches modal",
  usage: "/branches",
  category: "core",
  tags: ["readonly"],
  longDescription:
    "Lists every local branch with its ahead-count vs the default branch, and offers Merge / Delete actions per row.",
  run() {
    if (!requireStorePath("/branches")) return;
    useUI.getState().openBranches();
  },
});

register({
  name: "branch",
  aliases: ["br"],
  summary: "Manage branches: list / create <name> / delete <name>",
  usage: "/branch <list|create|delete> [name]",
  category: "core",
  tags: ["mutating"],
  longDescription:
    "/branch list = same as /branches. /branch create <name> creates from HEAD. /branch delete <name> deletes (cannot delete the current branch).",
  async run(args) {
    const sub = (args[0] ?? "list").toLowerCase();
    const name = args[1];
    const input = `/branch ${sub}${name ? " " + name : ""}`;
    const path = requireStorePath(input);
    if (!path) return;
    try {
      if (sub === "list") {
        const res = await api.branches(path);
        useStore.getState().pushHistory({
          input,
          level: "info",
          lines: [
            `current  ${res.current}`,
            `branches ${res.branches.join(", ")}`,
          ],
        });
        return;
      }
      if (sub === "create") {
        if (!name) {
          useStore.getState().pushHistory({
            input,
            level: "warning",
            lines: ["Missing name. Usage: /branch create <name>"],
          });
          return;
        }
        const res = await api.createBranch(path, name);
        useStore.getState().pushHistory({
          input,
          level: "success",
          lines: [res.message ?? `Created branch ${name}`],
        });
        await useStore.getState().refresh();
        return;
      }
      if (sub === "delete") {
        if (!name) {
          useStore.getState().pushHistory({
            input,
            level: "warning",
            lines: ["Missing name. Usage: /branch delete <name>"],
          });
          return;
        }
        const res = await api.deleteBranch(path, name);
        useStore.getState().pushHistory({
          input,
          level: "success",
          lines: [res.message ?? `Deleted branch ${name}`],
        });
        await useStore.getState().refresh();
        return;
      }
      useStore.getState().pushHistory({
        input,
        level: "warning",
        lines: [`Unknown subcommand: ${sub}. Use list / create / delete.`],
      });
    } catch (err) {
      pushError(input, err);
    }
  },
});

register({
  name: "checkout",
  aliases: ["co"],
  summary: "Switch branches or commits",
  usage: "/checkout <branch-or-commit>",
  category: "core",
  tags: ["mutating"],
  async run(args) {
    const target = args[0];
    const input = `/checkout ${target ?? ""}`;
    if (!target) {
      useStore.getState().pushHistory({
        input: "/checkout",
        level: "warning",
        lines: ["Missing target. Usage: /checkout <branch>"],
      });
      return;
    }
    const path = requireStorePath(input);
    if (!path) return;
    try {
      const res = await api.checkout(path, target);
      useStore.getState().pushHistory({
        input,
        level: "success",
        lines: [res.message ?? `On ${res.current_branch}`],
      });
      await useStore.getState().refresh();
    } catch (err) {
      pushError(input, err);
    }
  },
});

register({
  name: "merge",
  aliases: [],
  summary: "Merge a branch into the current branch",
  usage: "/merge <source-branch>",
  category: "core",
  tags: ["mutating"],
  async run(args) {
    const source = args[0];
    const input = `/merge ${source ?? ""}`;
    if (!source) {
      useStore.getState().pushHistory({
        input: "/merge",
        level: "warning",
        lines: ["Missing source. Usage: /merge <branch>"],
      });
      return;
    }
    const path = requireStorePath(input);
    if (!path) return;
    try {
      const res = await api.mergeBranch(path, source);
      useStore.getState().pushHistory({
        input,
        level: res.conflict ? "warning" : "success",
        lines: [res.message ?? `Merged ${source}`],
      });
      await useStore.getState().refresh();
    } catch (err) {
      pushError(input, err);
    }
  },
});

register({
  name: "time-travel",
  aliases: ["tt"],
  summary: "Travel to a specific commit (creates a branch)",
  usage: "/time-travel <commit>",
  category: "core",
  tags: ["mutating"],
  longDescription:
    "Equivalent to checking out a commit on a fresh branch named travel-<short>.",
  async run(args) {
    const commit = args[0];
    const input = `/time-travel ${commit ?? ""}`;
    if (!commit) {
      useStore.getState().pushHistory({
        input: "/time-travel",
        level: "warning",
        lines: ["Missing commit. Usage: /time-travel <commit>"],
      });
      return;
    }
    const path = requireStorePath(input);
    if (!path) return;
    try {
      const branchName = `travel-${commit.slice(0, 7)}`;
      const res = await api.checkout(path, commit, branchName);
      useStore.getState().pushHistory({
        input,
        level: "success",
        lines: [res.message ?? `Travelled to ${commit} on ${branchName}`],
      });
      await useStore.getState().refresh();
    } catch (err) {
      pushError(input, err);
    }
  },
});

// ---------- Info commands (no API call required) ----------

register({
  name: "demo",
  aliases: [],
  summary: "Show notes about demo data and seeding",
  usage: "/demo",
  category: "ui",
  tags: [],
  run() {
    useStore.getState().pushHistory({
      input: "/demo",
      level: "info",
      lines: [
        "memoir's UI doesn't ship demo data anymore — connect to a real store with /connect <path>.",
        "Quick way to seed one:",
        "  memoir new /tmp/demo",
        "  memoir remember 'Prefer async-first in Python' --store /tmp/demo",
      ],
    });
  },
});

register({
  name: "repo",
  aliases: [],
  summary: "Show repository info for the connected store",
  usage: "/repo",
  category: "ui",
  tags: ["readonly"],
  run() {
    const input = "/repo";
    const s = useStore.getState();
    if (!s.storePath) {
      requireStorePath(input);
      return;
    }
    const d = s.data;
    const lines = [
      `path     ${s.storePath}`,
      `branch   ${d?.current_branch ?? "?"}`,
      `branches ${(d?.branches ?? []).join(", ") || "(none)"}`,
      `commits  ${d?.commits.length ?? 0}`,
      `memories ${d?.total_memories ?? 0}`,
    ];
    s.pushHistory({ input, level: "info", lines });
  },
});

register({
  name: "code",
  aliases: [],
  summary: "Show Python integration snippet",
  usage: "/code",
  category: "ui",
  tags: [],
  run() {
    useStore.getState().pushHistory({
      input: "/code",
      level: "info",
      lines: [
        "# Python integration",
        "from memoir.services.memory_service import MemoryService",
        "svc = MemoryService('/path/to/store')",
        "await svc.remember('Prefer async-first', namespace='default')",
        "results = await svc.recall('coding style')",
        "",
        "# CLI",
        "memoir new /tmp/demo",
        "memoir remember 'foo bar' --store /tmp/demo",
        "memoir recall 'foo' --store /tmp/demo",
      ],
    });
  },
});

register({
  name: "location",
  aliases: ["loc"],
  summary: "Switch to the Places view (alias)",
  usage: "/location",
  category: "navigation",
  tags: [],
  longDescription:
    "v1 used /location to manage location mementos. v2 routes you to the Places view; capture coordinates via the backend's /api/location POST endpoint.",
  run() {
    useUI.getState().setActiveView("places");
    useStore.getState().pushHistory({
      input: "/location",
      level: "info",
      lines: ["Switched to Places view."],
    });
  },
});

// ---------- Placeholders (parity stubs — backend support not yet wired) ----------

const PLACEHOLDERS: { name: string; aliases?: string[]; usage: string; summary: string }[] = [
  { name: "import", usage: "/import <file>", summary: "Import conversations from JSON or TXT (planned)" },
  { name: "eval", usage: "/eval <file>", summary: "Evaluate recall hit rate (planned)" },
  { name: "organize", usage: "/organize <path>", summary: "Reorganise taxonomy under a path (planned)" },
  { name: "inspect", usage: "/inspect <path>", summary: "Deep-dive a memory path (planned)" },
  { name: "benchmark", usage: "/benchmark", summary: "Run search/storage benchmarks (planned)" },
  { name: "export", usage: "/export <format>", summary: "Export memories to JSON/CSV (planned)" },
  { name: "compare-stores", usage: "/compare-stores <p1> <p2>", summary: "Compare two memory stores (planned)" },
  { name: "replay", usage: "/replay <session>", summary: "Replay a memory session (planned)" },
  { name: "template", usage: "/template <type>", summary: "Generate prompt templates (planned)" },
];

for (const p of PLACEHOLDERS) {
  register({
    name: p.name,
    aliases: p.aliases ?? [],
    summary: p.summary,
    usage: p.usage,
    category: "system",
    tags: [],
    longDescription:
      "Reserved for parity with v1's command list. Run it now and you'll get a 'planned' notice — not yet wired to a backend implementation.",
    run() {
      useStore.getState().pushHistory({
        input: `/${p.name}`,
        level: "warning",
        lines: [
          `${p.name}: planned but not yet wired up.`,
          "Track parity progress at https://github.com/zhangfengcdt/memoir/issues",
        ],
      });
    },
  });
}

// ------------------------------------------------------------------ parser

export interface ParsedCommand {
  name: string;
  args: string[];
}

export function parseCommand(input: string): ParsedCommand | null {
  const trimmed = input.trim();
  if (!trimmed) return null;
  const body = trimmed.startsWith("/") ? trimmed.slice(1) : trimmed;
  const [name, ...args] = body.split(/\s+/);
  return { name, args };
}

export async function dispatch(input: string): Promise<void> {
  const parsed = parseCommand(input);
  if (!parsed) return;
  const def = registry.get(parsed.name);
  if (!def) {
    useStore.getState().pushHistory({
      input: `/${parsed.name}`,
      level: "error",
      lines: [`Unknown command: /${parsed.name}. Try /help.`],
    });
    return;
  }
  await def.run(parsed.args);
}

export function commandNames(): string[] {
  const seen = new Set<string>();
  for (const def of registry.values()) seen.add(def.name);
  return Array.from(seen).sort();
}

/**
 * Snapshot the registry as a deduplicated list of canonical commands —
 * the help modal renders from this. Sorted by category-then-name so
 * navigation (Core → Navigation → Selection → UI → System) is stable.
 */
export function listCommands(): CommandDef[] {
  const seen = new Set<string>();
  const out: CommandDef[] = [];
  for (const def of registry.values()) {
    if (seen.has(def.name)) continue;
    seen.add(def.name);
    out.push(def);
  }
  const order: CommandCategory[] = [
    "core",
    "navigation",
    "selection",
    "ui",
    "system",
  ];
  out.sort((a, b) => {
    const ca = order.indexOf(a.category) - order.indexOf(b.category);
    return ca !== 0 ? ca : a.name.localeCompare(b.name);
  });
  return out;
}

export function categoryLabel(c: CommandCategory): string {
  switch (c) {
    case "core":
      return "Core operations";
    case "navigation":
      return "Navigation";
    case "selection":
      return "Selection";
    case "ui":
      return "UI";
    case "system":
      return "System";
  }
}

export function tagLabel(tag: CommandTag): string {
  switch (tag) {
    case "readonly":
      return "READONLY";
    case "mutating":
      return "MUTATING";
    case "llm":
      return "LLM";
    case "selection":
      return "SELECTION";
  }
}
