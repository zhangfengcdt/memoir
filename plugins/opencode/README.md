# Memoir OpenCode Plugin

OpenCode plugin for [Memoir](https://github.com/zhangfengcdt/memoir): git-versioned, taxonomy-structured memory for coding agents.

This is the OpenCode counterpart to the Claude Code and Codex Memoir plugins. It derives a per-project store under `~/.memoir/<path-slug>`, resolves the `memoir` CLI with `uvx` fallback, and exposes commands/tools for status, recall, remember, and UI launch.

## Store configuration

The plugin uses the same environment variable as the Claude Code plugin:

| Source | Description |
|---|---|
| plugin option `store` | Highest-priority override when the plugin is loaded from `plugin[]` |
| `MEMOIR_STORE` | Portable global/project override |
| auto-derived path | `~/.memoir/<slug>`, where slug = git root (or resolved cwd) with `/` and `.` replaced by `-`; all worktrees share one store |

Example when loading through `plugin[]`:

```jsonc
{
  "plugin": [
    ["file:///absolute/path/to/plugins/opencode/src/index.ts", { "store": "/custom/store/path" }]
  ]
}
```

For a portable config, prefer the auto-discovered plugin file plus `MEMOIR_STORE` if an override is needed.

## Development workflow

All plugin logic is in TypeScript — no bash helper scripts.

```bash
cd plugins/opencode
npm install
npm run build     # typecheck/emit dist for packaging
```

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/zhangfengcdt/memoir/main/plugins/opencode/install.sh | bash
```

Downloads, builds, and installs the plugin to `~/.config/opencode/plugins/memoir/`. Restart OpenCode afterwards.

## Memoir CLI resolution

The TypeScript plugin resolves Memoir in this order:

1. `memoir` on `PATH`
2. `uvx --from memoir-ai==<pin> memoir` — ephemeral, pinned
3. `uv tool run --from memoir-ai==<pin> memoir` — pinned fallback (older `uv` layouts)

Every command passes an explicit `-s <store>` so the project-side git repository and the Memoir store are kept separate.

## Commands

The plugin registers these OpenCode slash commands:

- `/memoir:status` — show status for the current project store, including project git branch metadata.
- `/memoir:ui` — launch or reopen the Memoir web UI.
- `/memoir:remember <memory>` — ask the agent to save an explicit durable memory with a semantic path.
- `/memoir:recall <topic>` — ask the agent to list and use relevant stored memories.
- `/memoir:onboard [--force]` — populate or refresh the project onboarding snapshot (`codebase:onboard` for git repos, `project:onboard` otherwise).

## Tools

The plugin exposes these tools to OpenCode agents:

- `memoir_status` — run the status helper.
- `memoir_remember` — save explicit content to one or more semantic paths; refuses secret-like content.
- `memoir_recall` — list memory keys via `summarize` for relevance selection.
- `memoir_get` — fetch selected exact keys after `memoir_recall`.

## Skills

This plugin does not require separate OpenCode skills. The workflow lives in plugin tools, slash command templates, and hooks.

## Hooks

The plugin registers seven OpenCode hooks, mirroring the Claude Code plugin's lifecycle:

| Hook | Claude Code analogue | Purpose |
|---|---|---|
| `config` | — | Registers slash commands |
| `command.execute.before` | — | Handles `/memoir:status` and `/memoir:ui` |
| `shell.env` | — | Injects `MEMOIR_STORE` into shell env |
| `tool.execute.after` | `Stop` (observation) | Accumulates per-tool metrics (`metrics.turn.<branch>`) and tracks file edits for code change audit (`metrics.code.<branch>`) |
| `chat.message` | `UserPromptSubmit` | Recall gate — checks every user message for intent that needs Memoir context; fires `experimental.chat.system.transform` one-shot |
| `experimental.chat.system.transform` | `UserPromptSubmit additionalContext` | Injects a recall instruction into the system prompt when the gate triggered |
| `dispose` | `SessionEnd` | Flushes any remaining code changes and metrics on shutdown |

### Recall gate logic (chat.message)

Every user message is checked through the same gate as Claude Code's `UserPromptSubmit`:

1. Explicit commands (`/recall`, `memoir:recall`) → **always fire** regardless of length
2. `< 10 chars` → skip (empty or noise)
3. Acknowledgements (`ok`, `thanks`, `sounds good`, …) → skip
4. `≥ 40 chars` + trigger pattern → fire
5. Trigger patterns: action verbs (`add`, `refactor`, `implement`…), question starts (`how`, `why`, `what`…), code blocks (`` ``` ``), code definitions (`def`, `class`…), memoir/recall keywords, file extensions (`.py`, `.ts`…), file paths (`src/components/`)

### Capture (tool.execute.after + chat.message + dispose)

File edits and tool metrics are collected during each assistant turn and flushed at the next user message (or at plugin shutdown):

- **`metrics.code.<branch>`** — replaced each flush: `Changed N block(s) across M file(s): file1, file2…`
- **`metrics.turn.<branch>`** — replaced each flush: `Tool1:calls:errors | Tool2:calls:errors | …`

This mirrors the Claude Code `Stop` hook's metrics and code change accumulation — without the LLM-based fact extraction (no transcript or `claude -p` access in the OpenCode plugin runtime).

## Notes

- Memory operations fail open where possible; plugin failures should not block coding.
- Do not store secrets. Save redacted rules or preferences instead.
- `MEMOIR_STORE` can override the derived project store path.
- Keep standard paths: plugin test copies live under OpenCode's normal plugin directory. Do not change OpenCode path configuration just for this plugin.
