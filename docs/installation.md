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

**LLM Providers** (choose one or more):

```bash
# OpenAI GPT models
pip install langchain-openai

# Anthropic Claude models
pip install langchain-anthropic

# Local LLMs via Ollama
pip install langchain-ollama
```

**Additional Features**:

```bash
# For LOCOMO dataset evaluation
pip install rich

# For performance benchmarking
pip install pytest-benchmark
```

## Environment Setup

Set up your environment variables:

```bash
# For OpenAI
export OPENAI_API_KEY="your-openai-api-key"

# For Anthropic
export ANTHROPIC_API_KEY="your-anthropic-api-key"
```

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
