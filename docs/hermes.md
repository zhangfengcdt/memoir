# Hermes Plugin

Memoir ships a memory-provider plugin for [Hermes](https://github.com/NousResearch/hermes-agent), the Nous Research personal-assistant agent. Activate it and Hermes gains **versioned, semantic long-term memory**: a git-like store (branch / commit / merge) over a Prolly-tree with semantic paths and cryptographic provenance. Unlike vector-only backends (Mem0, Zep, Letta), every write is a commit you can inspect (`memoir log`), attribute (`memoir blame`), and time-travel.

The plugin lives in the repo at `plugins/hermes/`.

## How it fits Hermes

Hermes has a pluggable `MemoryProvider` slot — exactly one external provider is active at a time, selected by `memory.provider` in `~/.hermes/config.yaml`. The built-in `MEMORY.md` / `USER.md` layer stays active alongside it. Memoir fills that slot.

It is a **directory plugin**, not a pip/entry-point package: Hermes loads memory providers by scanning `$HERMES_HOME/plugins/<name>/`, so the plugin is installed as a directory there. It holds no memoir code in-process — it shells out to the `memoir` CLI over a stdlib-only subprocess bridge, so the Prolly-tree self-resolves concurrent (fire-and-forget) writes with no locking.

## Install

The plugin needs two things on the machine: the **plugin directory** in your Hermes home, and the **`memoir` CLI** reachable on `PATH`.

### 1. Install the memoir CLI

```bash
pip install memoir-ai        # or: pipx install memoir-ai / uv tool install memoir-ai
```

> The bridge resolves `memoir` on `PATH` first, falling back to a pinned `uvx --from memoir-ai==<pin> memoir` (then `uv tool run`) when it isn't installed. A direct install is faster (no warmup).

### 2. Install the plugin

**Via the Hermes CLI** (once the plugin is on the repo's default branch):

```bash
hermes plugins install zhangfengcdt/memoir/plugins/hermes
```

Hermes clones the repo, takes the `plugins/hermes` subdirectory, reads its `plugin.yaml` (`name: memoir`), and installs it to `~/.hermes/plugins/memoir/`.

**By copy** (works today, from a local checkout):

```bash
cp -r plugins/hermes ~/.hermes/plugins/memoir
rm -rf ~/.hermes/plugins/memoir/tests ~/.hermes/plugins/memoir/__pycache__
```

### 3. Activate it

```bash
hermes memory setup        # interactive picker — choose "memoir"
```

`hermes memory setup` writes `memory.provider: memoir` to `~/.hermes/config.yaml`. (You can also set that key by hand.) Activating memoir **displaces any other external provider** (`mem0`, `honcho`, …) — only one runs at a time.

The store is created automatically on first run at `<hermes_home>/memoir-store` (override with `store_path` in config). You'll need a provider API key in the Hermes environment — see [LLM backend](#llm-backend).

## What ships

| Component | Count | Role |
|---|---|---|
| Tools (model-facing) | 3 | `memoir_recall`, `memoir_remember`, `memoir_status` |
| Lifecycle hooks | 5 | Auto-capture, recall context, store mirroring |
| CLI subcommands | 2 | `hermes memoir status`, `hermes memoir ui` |

There are no in-chat slash commands — Hermes has no plugin slash-command mechanism for memory providers. The equivalents are the auto-capture hook plus the three tools the model invokes on its own.

## Tools

The model decides when to call these (guided by their descriptions and the injected system-prompt block); they are not typed by the user.

| Tool | Purpose |
|---|---|
| `memoir_recall` | Fetch stored facts about the user (preferences, people, schedule, standing instructions). LLM-free: `summarize` → batched `get`, ranked by lexical overlap with the query. |
| `memoir_remember` | Store an explicit durable fact. Classified into a semantic path and committed. Guarded against obvious secrets. |
| `memoir_status` | Store status: branch, commit count, memory count. |

## Lifecycle hooks

These are called by Hermes automatically — they don't depend on the model invoking a tool, so **capture is guaranteed** even if the model never calls `memoir_remember`.

| Hook | When | Purpose |
|---|---|---|
| `initialize` | agent startup | Derive + ensure the store, resolve the model, cache an overview. |
| `system_prompt_block` | prompt assembly | Inject recall guidance + a short store overview. |
| `sync_turn` | after every turn | Fire-and-forget `memoir capture --profile assistant` over the turn. |
| `on_pre_compress` / `on_session_end` | compression / session end | Capture the uncaptured message tail. |
| `on_memory_write` | built-in memory edit | Mirror Hermes's `MEMORY.md` / `USER.md` writes into versioned memoir paths. |

Capture runs on a background thread and never blocks the response. Writes are skipped for non-primary agent contexts (subagent / cron / flush) so they can't corrupt the user's representation.

## Configuration

Config lives in `<hermes_home>/memoir.json` (all keys optional). Set it via `hermes memory setup` or by hand.

| Key | Default | Meaning |
|---|---|---|
| `store_path` | `<hermes_home>/memoir-store` | Store location. |
| `capture` | `true` | Auto-capture facts from each turn. `false` disables the `sync_turn` / boundary capture; recall and tools still work. |
| `model` | host's selected model | Pin the LLM model for capture/classification. Empty = follow Hermes `model.default`. See [Model selection](#model-selection). |
| `base_url` | provider default | Custom provider endpoint (LLM gateway/proxy). Empty = call the provider directly. See [Routing through a proxy](#routing-through-a-proxy). |

Example — pin cheap Haiku for per-turn capture regardless of your chat model:

```json
{ "model": "claude-haiku-4-5" }
```

## Model selection

memoir resolves the capture/classification model in this order:

1. **`model` pin** in `memoir.json` — always wins.
2. **Host-selected model** — Hermes `model.default`, tracked across mid-session model switches (`on_turn_start`).
3. **memoir's built-in default** — `claude-haiku-4-5`.

So out of the box, capture runs on the *same model your Hermes session uses*. That can be expensive: if your session model is Opus, every per-turn extraction is an Opus call. Pin a cheaper model (e.g. `claude-haiku-4-5`) in `memoir.json` to decouple capture cost from your chat model.

### Which provider key is used?

memoir routes by **model name**, not by which keys are present — so setting both `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` is unambiguous:

| Model | Provider → key |
|---|---|
| `claude-*` / `anthropic/*` | Anthropic → `ANTHROPIC_API_KEY` |
| `gpt-*` | OpenAI → `OPENAI_API_KEY` |
| `gemini/*` | Gemini → `GEMINI_API_KEY` |
| `ollama/*`, or any model with `base_url` set | that endpoint (no key check) |

Each key is consulted only when a model of its provider is selected. memoir's default model is `claude-haiku-4-5` (Anthropic), so with no model specified anywhere it uses `ANTHROPIC_API_KEY`.

## LLM backend

The plugin drives memoir with its **litellm (direct provider API) backend only** — it **never** shells out to the `claude` CLI, even when a `claude` binary is on `PATH`. A Hermes host has its own configured provider, and a typical Hermes box has no Claude Code install.

memoir reads the provider credentials from the Hermes process environment (e.g. `ANTHROPIC_API_KEY` in `<hermes_home>/.env`). If the selected model's provider key is missing, capture **fails loudly** ("ANTHROPIC_API_KEY required") rather than silently switching backends.

Recall is LLM-free, so it works even without a provider key. Auto-capture and explicit `memoir_remember` classification do need one.

### Routing through a proxy

By default memoir calls the provider directly (e.g. `api.anthropic.com`) and does **not** route through any gateway Hermes itself uses — Hermes keeps its gateway/base-URL internal to its own client and never exports it to the environment. To send memoir's calls through a proxy/gateway too, set `base_url` in `memoir.json`:

```json
{ "base_url": "https://your-gateway/v1" }
```

The bridge exports this as `MEMOIR_LLM_BASE_URL`; the credential in the environment must be valid for that endpoint.

## Verify

```bash
hermes memory status            # provider: memoir
hermes memoir status            # store branch / commit count / memory count
memoir capture --help           # confirms the CLI on PATH has `capture`
```

End-to-end: start a Hermes session and state a durable fact ("from now on call me Captain; my dog Rex sees the vet every March"). Capture runs in the background (a few seconds), then:

```bash
memoir -s <hermes_home>/memoir-store summarize --depth 3     # captured paths
memoir -s <hermes_home>/memoir-store blame <path>            # provenance
```

In a new session, ask "what's my name?" — the agent should call `memoir_recall` and answer from memory.

## Environment variables

The bridge sets these for the memoir subprocess automatically from `memoir.json`; you normally don't set them by hand.

| Variable | Set from | Effect |
|---|---|---|
| `MEMOIR_LLM_BACKEND` | always `litellm` | Forces direct provider APIs; suppresses the claude-cli fallback. |
| `MEMOIR_LLM_MODEL` | resolved model | Model for capture/classification. |
| `MEMOIR_LLM_BASE_URL` | `base_url` config | Custom provider endpoint, when set. |

Provider keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, …) are inherited from the Hermes process environment — set them in `<hermes_home>/.env`.

## Manifest

`plugins/hermes/plugin.yaml`:

```yaml
name: memoir
version: 0.1.0
description: "Memoir — versioned, semantic long-term memory with git-like branch/commit/merge and cryptographic provenance. Shells out to the memoir CLI; no Python deps."
```

No `pip_dependencies`: the provider talks to the `memoir` CLI over a subprocess bridge (PATH `memoir`, else a pinned `uvx --from memoir-ai`).

## Limitations (v1)

- **Local store only.** Multi-device sync (the merge-based wedge) is future work; it needs a `memoir remote` story.
- **One external provider at a time.** Activating memoir displaces any other Hermes memory provider.

## See also

- [CLI](cli.md) — the underlying `memoir` commands the plugin wraps (including `capture`).
- [Claude Code](claude_code.md) — the coding-agent plugin (slash commands, hooks).
- [Architecture](architecture.md) — how memoir is structured under the hood.
