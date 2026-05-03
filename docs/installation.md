# Installation

## Requirements

- Python 3.10 or higher
- Git (for versioning features)

## Basic Installation

Pick one — they all install the same `memoir` CLI.

### Recommended: `uv`

If you don't already have `uv`, install it first (one-line, no Python required):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then either install memoir as a tool, or just run it on demand via `uvx`:

```bash
# Persistent install (recommended for daily use)
uv tool install memoir-ai

# OR — try without installing (one-shot, ephemeral venv)
uvx --from memoir-ai memoir --help
```

`uv` is significantly faster than `pip` and isolates the CLI from your project Python environments. **If you have `uv`, you do not need to `pip install memoir-ai`** — the Claude Code plugin's auto-fallback also uses `uvx --from memoir-ai memoir` transparently when the bare `memoir` binary isn't on PATH.

### Alternative: `pipx`

```bash
pipx install memoir-ai
```

### Universal fallback: `pip`

```bash
pip install memoir-ai
```

The distribution name on PyPI is `memoir-ai` (the `memoir` name was already taken). After install, the Python import is still `import memoir` and the CLI command is `memoir`.

## Development Installation

For development or contributing to Memoir:

```bash
# Clone the repository
git clone https://github.com/zhangfengcdt/memoir.git
cd memoir

# Install in development mode with all dependencies
pip install -e ".[dev,docs]"

# Install pre-commit hooks
make pre-commit
```

## Optional Dependencies

As of **v0.1.7**, [`litellm`](https://docs.litellm.ai/) (the LLM router
used by `recall` and auto-classification in `remember`) is a **default
dependency** — `pip install memoir-ai` is enough for both LLM-backed
and direct-path commands.

If you don't need LLM features and want to trim the install footprint,
`pip uninstall litellm` after install — memoir's other features
(`-p` paths, `get`, `forget`, `branch`, `checkout`, etc.) keep working
because the import is lazy. The `[litellm]` extra is preserved as a
no-op alias for backward-compat scripts.

### Other extras

```bash
pip install 'memoir-ai[tui]'         # Terminal UI (textual-based)
pip install 'memoir-ai[langmem]'     # ProllyTreeMemoryStoreManager (LangMem drop-in)
pip install 'memoir-ai[all]'         # tui + langmem + litellm
```

## Environment Setup

Memoir's CLI defaults to **Anthropic Claude (`claude-haiku-4-5`)** for
LLM-backed commands as of v0.1.6. Set the corresponding key:

```bash
# Default — Anthropic (Haiku)
export ANTHROPIC_API_KEY="your-anthropic-api-key"

# OR if you want to keep using OpenAI (memoir's default before v0.1.6)
export OPENAI_API_KEY="your-openai-api-key"
export MEMOIR_LLM_MODEL="gpt-4o-mini"   # or pass --model gpt-4o-mini per call
```

Resolution order for the model used by `recall` / `remember` (no `-p`):

1. `--model <name>` flag on the command (highest priority)
2. `MEMOIR_LLM_MODEL` env var
3. `claude-haiku-4-5` default

The same env var also drives the UI's default model (`memoir ui --usellm`).

## Verification

Test your installation:

```python
import memoir
print(f"Memoir version: {memoir.__version__}")

# Test basic components
from memoir import ProllyTreeStore, SemanticClassifier
print("Installation successful!")
```

## Docker Installation

Run Memoir in a Docker container:

```bash
# Build the Docker image
docker build -t memoir .

# Run with mounted data directory
docker run -v $(pwd)/data:/app/data memoir
```

## Troubleshooting

**Common Issues**:

1. **Git not found**: Install Git for version control features
2. **LLM errors**: Ensure API keys are set correctly
3. **Permission errors**: Use virtual environments

For more help, see the [FAQ](faq.md) or
[open an issue](https://github.com/zhangfengcdt/memoir/issues).

## Building the Docs Locally

The site is built with [mkdocs-material](https://squidfunk.github.io/mkdocs-material/). After `pip install -e ".[docs]"`:

```bash
# Build the static site into ./site
make docs

# Start the live-reload dev server
make docs-live

# Clean the build output
make docs-clean
```
