import { useStore } from "../state/storeSlice";
import { useUI } from "../state/uiSlice";
import { useSelection } from "../state/selectionSlice";

export interface CommandDef {
  name: string;
  aliases: string[];
  summary: string;
  usage: string;
  run: (args: string[]) => void | Promise<void>;
}

// Internal — declared here so `/help` can enumerate itself without circular
// imports. Each command closes over the Zustand store (getState).
const registry: Map<string, CommandDef> = new Map();

function register(def: CommandDef) {
  registry.set(def.name, def);
  for (const alias of def.aliases) registry.set(alias, def);
}

register({
  name: "connect",
  aliases: ["con"],
  summary: "Connect to a memoir store on disk",
  usage: "/connect <path>",
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
  name: "refresh",
  aliases: ["r"],
  summary: "Re-read the currently connected store",
  usage: "/refresh",
  async run() {
    await useStore.getState().refresh();
  },
});

register({
  name: "status",
  aliases: ["s"],
  summary: "Show connection status + store summary",
  usage: "/status",
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

register({
  name: "disconnect",
  aliases: [],
  summary: "Drop the current store connection",
  usage: "/disconnect",
  run() {
    useStore.getState().disconnect();
  },
});

register({
  name: "help",
  aliases: ["h", "?"],
  summary: "List available commands",
  usage: "/help [command]",
  run(args) {
    const target = args[0];
    const s = useStore.getState();
    if (target) {
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
    // List uniques — the registry holds both canonical names and aliases.
    const seen = new Set<string>();
    const lines: string[] = [];
    for (const def of registry.values()) {
      if (seen.has(def.name)) continue;
      seen.add(def.name);
      lines.push(`${def.usage.padEnd(22)} — ${def.summary}`);
    }
    s.pushHistory({ input: "/help", level: "info", lines });
  },
});

register({
  name: "clear",
  aliases: [],
  summary: "Clear command history",
  usage: "/clear",
  run() {
    useStore.getState().clearHistory();
  },
});

register({
  name: "commits",
  aliases: ["log"],
  summary: "Switch to the Commits view",
  usage: "/commits",
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
  name: "tree",
  aliases: [],
  summary: "Switch to the Tree view",
  usage: "/tree",
  run() {
    useUI.getState().setActiveView("tree");
    useStore.getState().pushHistory({
      input: "/tree",
      level: "info",
      lines: ["Switched to Tree view (placeholder until Phase 4)."],
    });
  },
});

register({
  name: "graph",
  aliases: [],
  summary: "Switch to the Graph view",
  usage: "/graph",
  run() {
    useUI.getState().setActiveView("graph");
    useStore.getState().pushHistory({
      input: "/graph",
      level: "info",
      lines: ["Switched to Graph view. Drag to pan, scroll to zoom."],
    });
  },
});

register({
  name: "deselect",
  aliases: [],
  summary: "Clear commit selection",
  usage: "/deselect",
  run() {
    useSelection.getState().clear();
    useStore.getState().pushHistory({
      input: "/deselect",
      level: "info",
      lines: ["Selection cleared."],
    });
  },
});

register({
  name: "diff",
  aliases: [],
  summary: "Show a range diff between selected commits",
  usage: "/diff [from] [to]",
  run(args) {
    let fromHash: string | undefined = args[0];
    let toHash: string | undefined = args[1];

    if (!fromHash || !toHash) {
      // Derive endpoints from the current commit selection. Sorted
      // alphabetically by hash — the direction doesn't matter semantically,
      // the backend handles either order.
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
