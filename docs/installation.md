# Installation

## Requirements

- Python 3.10 or higher
- Git (for versioning features)

## Basic Installation

Install Memoir using pip:

```bash
pip install memoir-ai
```

The distribution name on PyPI is `memoir-ai` (the `memoir` name was already taken). After install, the Python import is still `import memoir`.

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

### LLM features (`recall`, auto-classification in `remember`)

These commands route through `memoir.llm.get_llm()`, which uses
[`litellm`](https://docs.litellm.ai/) to talk to any provider. Install
the `[litellm]` extra to enable them:

```bash
pip install 'memoir-ai[litellm]'
```

Without this extra, `memoir new`, `connect`, `get`, `forget`, `branch`,
`checkout`, and `remember -p <path>` (with an explicit path) all work —
only the LLM-backed code paths raise `ImportError` at runtime.

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
