# Docker smoke test — memoir Hermes plugin

A throwaway container that installs Hermes + the memoir plugin from scratch and
verifies the plugin end-to-end. Useful for confirming the `owner/repo/subdir`
install path, the provider/tools/slash-command wiring, and real auto-capture in
a clean environment (no dependence on your local `~/.hermes`).

## Build

```bash
docker build -t hermes-memoir-test plugins/docker-tests/hermes
```

This installs `hermes-agent` from `main`, `memoir-ai` from PyPI, then runs the
real install path:

```
hermes plugins install zhangfengcdt/memoir/plugins/hermes
```

and activates it (`memory.provider: memoir`, `plugins.enabled: [memoir]`).

> **Why Hermes from `main`?** The subdir-aware `hermes plugins install
> owner/repo/subdir` postdates the `0.16.0` release. On released Hermes the
> install form is `cp -r plugins/hermes ~/.hermes/plugins/memoir` instead. Pin
> `--build-arg HERMES_REF=<tag>` once a release includes it.

Build args: `HERMES_REF` (default `main`), `MEMOIR_AI_VERSION` (default
`0.2.3`), `MEMOIR_PLUGIN` (default `zhangfengcdt/memoir/plugins/hermes`).

## Run the smoke test

```bash
docker run --rm \
  -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  -v "$PWD/plugins/docker-tests/hermes/test.sh:/test.sh:ro" \
  hermes-memoir-test bash /test.sh
```

`test.sh` checks:

1. Hermes + memoir versions.
2. `hermes memory status` — provider installed / available / active.
3. Provider loads via Hermes's own loaders; the 5 tools are exposed; the
   `/memoir` slash command is registered; `/memoir status` runs.
4. **Real auto-capture** (`memoir capture`) — the only step that calls an LLM,
   so it needs `ANTHROPIC_API_KEY`. Extracts durable facts from a sample turn.
5. The captured facts are present in the store.

Only step 4 needs the API key; the rest run offline. Drop into the image to
poke around interactively:

```bash
docker run --rm -it -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" hermes-memoir-test bash
```
