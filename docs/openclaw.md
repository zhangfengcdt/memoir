# OpenClaw Plugin

Memoir ships a memory plugin for [OpenClaw](https://github.com/openclaw/openclaw), the personal-assistant gateway. Activate it and OpenClaw gains **versioned, semantic long-term memory**: a git-like store (branch / commit / merge) over a Prolly-tree with semantic paths and cryptographic provenance. Unlike vector-only backends (Mem0, Zep, Letta), every write is a commit you can inspect (`memoir log`), attribute (`memoir blame`), and time-travel — and each conversation is isolated by default, so a side chat never pollutes your global profile.

The plugin lives in its **own repository**: [`zhangfengcdt/openclaw-memoir`](https://github.com/zhangfengcdt/openclaw-memoir) (OpenClaw's `plugins install` for git sources expects the plugin at the repo root). It is the OpenClaw counterpart of the in-repo [Hermes plugin](hermes.md) and shares its conventions.

## How it fits OpenClaw

OpenClaw has a single-select **memory slot** (`plugins.slots.memory`, default `memory-core`). Installing this plugin claims that slot with `memory-memoir`. It holds no memoir code in-process — it shells out to the `memoir` CLI over a zero-dependency subprocess bridge, so the Prolly-tree self-resolves concurrent (fire-and-forget) writes with no locking.

It registers through OpenClaw's native seams: `registerTool` (model-facing tools), `registerMemoryCapability` (memory-guidance prompt section + disabling the MEMORY.md flush), `api.on(...)` hooks (capture + recall), `registerCommand` (the in-chat `/memoir`), and `registerCli` (`openclaw memoir …`).

## Install

You need three things: the **`memoir` CLI**, the **plugin** in the memory slot, and a **provider key + capture model** in the plugin's config (OpenClaw keeps its own keys in a secret store and does not export them to subprocesses — see [Model & API key](#model-api-key)).

### 1. Install the memoir CLI

```bash
pip install memoir-ai        # or: pipx install memoir-ai / uv tool install memoir-ai
```

> The bridge resolves `memoir` on `PATH` first, falling back to a pinned `uvx --from memoir-ai==<pin> memoir` (then `uv tool run`) when it isn't installed.

### 2. Install the plugin

```bash
# from the git repo root (no subdir form — the plugin is a root-level repo)
openclaw plugins install https://github.com/zhangfengcdt/openclaw-memoir

# …or link a local checkout while developing
openclaw plugins install --link /path/to/openclaw-memoir
```

Installing auto-switches the memory slot to `memory-memoir` (you'll see *"Exclusive slot 'memory' switched from 'memory-core' to 'memory-memoir'"*). To set it by hand:

```bash
openclaw config set plugins.slots.memory memory-memoir
```

### 3. Allow conversation access (for auto-capture)

Non-bundled plugins must opt in before their hooks can read conversation content:

```bash
openclaw config set plugins.entries.memory-memoir.hooks.allowConversationAccess true
```

Without this the tools and `/memoir` still work, but automatic capture and recall-injection are disabled.

### 4. Restart the gateway

```bash
systemctl --user restart openclaw-gateway      # or: openclaw gateway restart
```

The store is created automatically on first use under OpenClaw's state dir (see [Store location](#store-location)).

## What ships

| Component | Count | Role |
|---|---|---|
| Tools (model-facing) | 4 | `memoir_recall`, `memoir_remember`, `memoir_forget`, `memoir_status` |
| Lifecycle hooks | 4 | Auto-capture, recall-context injection, store bootstrap |
| Memory capability | 1 | Tool-aware guidance section; disables the MEMORY.md flush |
| In-chat command | 1 | `/memoir …` |
| CLI subcommands | 2 | `openclaw memoir status`, `openclaw memoir ui` |

## Tools

The model decides when to call these (guided by the memory-guidance prompt section). They are exposed to the agent **only when its tool profile allows memory tools** — see [Tool exposure](#tool-exposure).

| Tool | Purpose |
|---|---|
| `memoir_recall` | Fetch stored facts about the user (preferences, people, commitments, decisions). LLM-free: `summarize --depth 3` → batched `get`; `metrics.*` excluded. |
| `memoir_remember` | Store an explicit durable fact. Routed through `memoir capture` so the taxonomy classifier picks a valid semantic path (never a guessed key); guarded against obvious secrets. |
| `memoir_forget` | Delete a fact by its exact taxonomy path (find it with `memoir_recall` first). Pre-checks existence so a wrong path can't create a no-op delete; prior versions stay in git history. |
| `memoir_status` | Store status: branch, memory count, scope. |

## Automatic behavior

These don't depend on the model invoking a tool, so the memory loop works even when the tools are filtered out of the agent's profile:

| Hook | When | Purpose |
|---|---|---|
| `session_start` | new session | Ensure the store exists. |
| `before_prompt_build` | prompt assembly | Inject a `<memoir-memory>` block of relevant facts (passive recall). |
| `agent_end` | after every turn | Fire-and-forget `memoir capture --profile assistant` over the turn. |
| `before_compaction` | before summarization | Capture the message tail before it's discarded. |

Capture runs in the background and never blocks the reply. The memory-capability `promptBuilder` adds a short guidance line that names `memoir_recall` / `memoir_remember` **only when those tools are actually exposed** — otherwise it points the user at `/memoir`.

## The `/memoir` command

An in-chat command (not a tool, so it's never filtered by the tool profile):

```
/memoir status
/memoir recall [query]
/memoir remember <fact>
/memoir forget <key>
/memoir branch [name]      # versioning: diverge a timeline
/memoir checkout <name>
/memoir sync               # promote the current branch into main
```

## CLI

```bash
openclaw memoir status     # branch / memory count / scope
openclaw memoir ui         # open the memoir web UI for the store
```

## Configuration

Config lives under `plugins.entries.memory-memoir.config.*` (set with `openclaw config set …`). All keys optional.

| Key | Default | Meaning |
|---|---|---|
| `store` | `<state-dir>/memoir/<agent>` | Store path override. |
| `capture` | `true` | Auto-capture facts from each turn. |
| `recall` | `true` | Inject the memory overview into the prompt. |
| `scope` | `profile` | Isolation: `profile` (per-agent — shared across all that agent's sessions, the default), `chat` (per-conversation), `off` (one shared store). Recall always also reads the shared `default` namespace. See [Scoped memory](#scoped-memory). |
| `model` | — | Model for capture/remember extraction. **Required** in practice — see below. |
| `apiKey` | — | Provider API key for capture extraction. **Required** — see below. |
| `baseUrl` | — | Custom provider endpoint (proxy). Sets `MEMOIR_LLM_BASE_URL`. |

```bash
openclaw config set plugins.entries.memory-memoir.config.model  anthropic/claude-haiku-4-5
openclaw config set plugins.entries.memory-memoir.config.apiKey  "$ANTHROPIC_API_KEY"
```

## Model & API key

Capture/remember run an extraction step through memoir's litellm client. Two things matter:

**1. The key must be in the plugin config.** OpenClaw authenticates providers through its own secret store and does **not** export `ANTHROPIC_API_KEY` (etc.) into subprocesses. So memoir — a separate process — can't see it unless you provide it via `apiKey`. The plugin routes it to the right env var based on the model:

| Model | Provider → key |
|---|---|
| `claude-*` / `anthropic/*` | Anthropic → `ANTHROPIC_API_KEY` |
| `gpt-*` / `openai/*` | OpenAI → `OPENAI_API_KEY` |
| `gemini*` | Gemini → `GEMINI_API_KEY` |

**2. The model must support `temperature=0`.** memoir's extraction uses `temperature=0` for determinism. Reasoning models that force `temperature=1` (e.g. `claude-opus-4-8`) will fail capture with an `UnsupportedParamsError`. Use a standard model — `anthropic/claude-haiku-4-5` is ideal for background extraction (fast and cheap), and decouples capture cost from whatever model your chats run on.

Recall is LLM-free, so it works with no key. Only capture and explicit `memoir_remember` need one.

## Tool exposure

OpenClaw filters each agent's toolset by its **tools profile** (`tools.profile`). The `coding` profile is an allowlist that strips memory tools (it would strip `memory-core`'s tools too) — so on a coding-configured gateway the `memoir_*` tools won't appear in the model's tool list, even though they registered fine. To expose them, use a profile that includes memory tools:

```bash
openclaw config set tools.profile full     # or any profile that includes memory tools
systemctl --user restart openclaw-gateway
```

Either way, **auto-capture, passive recall injection, and the `/memoir` command don't depend on the tool profile** — they keep working under `coding`. The tools only add on-demand recall/remember/forget for the model.

## Storage model

OpenClaw maps onto memoir on **two axes**: an **agent** selects the *store* (a whole Prolly-tree), and the **scope** setting selects the *namespace* (a partition inside that store).

**Store ← agent**

```
<state-dir>/memoir/<agentId>
```

- `<state-dir>` = `OPENCLAW_STATE_DIR`, else `~/.openclaw` — so it follows `--profile` / `--dev` (e.g. `~/.openclaw-work/memoir/…`). See [Store location](#store-location).
- `<agentId>` = the conversation's agent (recovered from the `agent:<id>:<session>` session key), default `main`. Each agent gets a **separate tree**.
- Override the whole path with the `store` config or `MEMOIR_STORE`.

**Namespace ← scope** (details in [Scoped memory](#scoped-memory))

| `scope` | Namespace | One namespace per… |
|---|---|---|
| `profile` (default) | `profile-<agentId>` | agent (all its sessions) |
| `chat` | `chat-<sessionKey>` | conversation / launch |
| `off` | `default` | the whole store |

Two namespaces always exist alongside the scope one: **`default`** (shared facts — recall reads `scope ⊕ default`) and **`taxonomy`** (memoir's built-in path taxonomy, not user data — it's the "8 memories" you see on a fresh store).

The axes compose: **agent → tree, scope → partition**. Under the default `scope=profile` the store and namespace both key on the agent (1:1); the namespace layer only fans out under `scope=chat`.

```
~/.openclaw/memoir/main            # agent "main"        (store)
  ├── profile-main                 # scope=profile       (your facts)
  ├── default                      # shared across scopes
  └── taxonomy                     # built-in
~/.openclaw/memoir/research        # a second agent  →   separate store
```

## Scoped memory

By default memory is shared across all of an agent's sessions, so the assistant remembers you across launches. **OpenClaw mints a new session id per TUI launch**, so `chat` scope would isolate every launch (no cross-session continuity) — opt into it only when you genuinely want per-conversation separation. Set `scope` to change the granularity:

| `scope` | Each scope is… | Namespace |
|---|---|---|
| `profile` (default) | an agent (all its sessions) | `profile-<agentId>` |
| `chat` | a single conversation/launch | `chat-<sessionKey>` |
| `off` | one shared store | `default` |

Captures and `memoir_remember` write to the scope's namespace; `memoir_recall` reads the scope namespace **⊕** `default`, so global facts are visible everywhere but a scoped fact never leaks into another scope (default-deny, not an injection-time filter). Scoping uses memoir **namespaces** (parallel partitions) — distinct from branches.

### What lands in `default`?

Every write (auto-capture, `memoir_remember`, `/memoir remember`) targets the **scope namespace**, which is `default` *only* when `scope=off`:

| `scope` | Writes land in | Does `default` fill up? |
|---|---|---|
| `off` | `default` | ✅ everything |
| `profile` (default) | `profile-<agentId>` | ❌ nothing automatic |
| `chat` | `chat-<sessionKey>` | ❌ nothing automatic |

So under the default `profile` scope, **nothing the plugin writes goes to `default`** — it stays empty. `default` is the cross-scope *shared/read* layer (recall always merges it in); it only fills when you run `scope=off`, or write to it deliberately:

```bash
memoir -s ~/.openclaw/memoir/<agent> remember "<fact>" -p <path> -n default
```

(So if you want a fact visible in *every* scope while running `profile`/`chat`, put it in `default` by hand.)

## Store location

The store is anchored under OpenClaw's state dir, mirroring OpenClaw's own resolution: `OPENCLAW_STATE_DIR` if set, else `<HOME>/.openclaw`. So it **follows `--profile` / `--dev` isolation** — `--profile work` puts the store under `~/.openclaw-work/memoir/<agent>`. Default:

```
~/.openclaw/memoir/<agent>          # e.g. ~/.openclaw/memoir/main
```

Override with the `store` config or `MEMOIR_STORE`.

## Versioning

OpenClaw has no conversation-fork event, so (unlike Hermes) there's no automatic fork→branch mapping. Per-chat **scoping** covers the isolation case; for divergent, mergeable timelines use the manual branch commands:

```
/memoir branch <name>      # diverge off main
/memoir checkout <name>
/memoir sync               # additively merge the current branch back into main
```

## Verify

```bash
openclaw memoir status                                   # branch / memory count / scope
memoir -s ~/.openclaw/memoir/main summarize --depth 3    # captured paths
memoir -s ~/.openclaw/memoir/main blame <path>           # provenance
```

End-to-end: in a chat, state a durable fact ("remember my daughter Mia has piano on Tuesdays"). Capture runs in the background (a few seconds); `summarize` then shows it under a sensible path. A debug trace of capture attempts is written to `<store>/.git/memoir-openclaw-events.log`.

## Parity with the Hermes plugin

This plugin mirrors the [Hermes provider](hermes.md): the same tools, capture/recall flow, secret guard, model routing, per-chat scoping, `/memoir` command, and CLI. The differences come from OpenClaw's API:

- **No session-fork event** → manual `/memoir branch | checkout | sync` instead of automatic fork→branch.
- **Provider key in config** (`apiKey`) → OpenClaw doesn't export keys to subprocesses, where Hermes inherits them from its process environment.
- **Tool-profile filtering** can hide the tools (the `coding` profile); the passive path always works.

## Limitations (v1)

- **Local store only.** Multi-device sync (the merge-based wedge) is future work.
- **Capture needs a config key + a `temperature=0`-capable model** (see [Model & API key](#model-api-key)).
- **One memory provider at a time.** Claiming the slot displaces `memory-core`.

## See also

- [Hermes](hermes.md) — the in-repo personal-assistant counterpart.
- [CLI](cli.md) — the underlying `memoir` commands the plugin wraps (including `capture`).
- [Architecture](architecture.md) — how memoir is structured under the hood.
