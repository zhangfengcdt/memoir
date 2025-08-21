Installation
============

Requirements
------------

- Python 3.9 or higher
- Git (for versioning features)

Basic Installation
------------------

Install Memoir using pip:

.. code-block:: bash

   pip install memoir

Development Installation
------------------------

For development or contributing to Memoir:

.. code-block:: bash

   # Clone the repository
   git clone https://github.com/yourusername/memoir.git
   cd memoir

   # Install in development mode with all dependencies
   pip install -e ".[dev,docs]"

   # Install pre-commit hooks
   make pre-commit

Optional Dependencies
---------------------

**LLM Providers** (choose one or more):

.. code-block:: bash

   # OpenAI GPT models
   pip install langchain-openai

   # Anthropic Claude models
   pip install langchain-anthropic

   # Local LLMs via Ollama
   pip install langchain-ollama

**Additional Features**:

.. code-block:: bash

   # For LOCOMO dataset evaluation
   pip install rich

   # For performance benchmarking
   pip install pytest-benchmark

Environment Setup
-----------------

Set up your environment variables:

.. code-block:: bash

   # For OpenAI
   export OPENAI_API_KEY="your-openai-api-key"

   # For Anthropic
   export ANTHROPIC_API_KEY="your-anthropic-api-key"

Verification
------------

Test your installation:

.. code-block:: python

   import memoir
   print(f"Memoir version: {memoir.__version__}")

   # Test basic components
   from memoir import ProllyTreeStore, SemanticClassifier
   print("✓ Installation successful!")

Docker Installation
-------------------

Run Memoir in a Docker container:

.. code-block:: bash

   # Build the Docker image
   docker build -t memoir .

   # Run with mounted data directory
   docker run -v $(pwd)/data:/app/data memoir

Troubleshooting
---------------

**Common Issues**:

1. **Git not found**: Install Git for version control features
2. **LLM errors**: Ensure API keys are set correctly
3. **Permission errors**: Use virtual environments

For more help, see our `troubleshooting guide <troubleshooting.html>`_ or
`open an issue <https://github.com/yourusername/memoir/issues>`_.

ReadTheDocs Setup (Optional)
-----------------------------

The project includes ReadTheDocs configuration for easy documentation hosting:

.. code-block:: yaml

   # .readthedocs.yml is already configured
   version: 2
   build:
     os: ubuntu-22.04
     tools:
       python: "3.11"
   sphinx:
     configuration: docs/conf.py

**To set up ReadTheDocs:**

1. **For Public Repositories:**
   - Connect your GitHub repo to `ReadTheDocs <https://readthedocs.org>`_
   - Documentation will build automatically on commits

2. **For Private Repositories:**
   - Use `ReadTheDocs for Business <https://readthedocs.com>`_
   - Or build documentation locally with ``make docs``

**Local Documentation Building:**

.. code-block:: bash

   # Build documentation locally
   make docs
   
   # Start live reload development server
   make docs-live
   
   # Clean build artifacts
   make docs-clean
