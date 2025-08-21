Quick Start Guide
=================

This guide will help you get started with Memoir in just a few minutes.

Installation
------------

Install Memoir using pip:

.. code-block:: bash

   pip install memoir

For development installation with all dependencies:

.. code-block:: bash

   pip install -e ".[dev]"

Basic Setup
-----------

1. **Set up your LLM** (using OpenAI as an example):

.. code-block:: python

   import os
   from langchain_openai import ChatOpenAI

   # Set your OpenAI API key
   os.environ["OPENAI_API_KEY"] = "your-api-key-here"

   # Create LLM instance
   llm = ChatOpenAI(
       model="gpt-4o-mini",
       temperature=0,
       max_tokens=500
   )

2. **Initialize the memory system components**:

.. code-block:: python

   from memoir.store.prolly_adapter import ProllyTreeStore
   from memoir.classifier.intelligent import IntelligentClassifier
   from memoir.search.intelligent import IntelligentSearchEngine
   from memoir import ProllyTreeMemoryStoreManager

   # Create storage layer
   store = ProllyTreeStore(
       path="./memory_store",
       enable_versioning=True
   )

   # Create intelligent classifier
   classifier = IntelligentClassifier(
       llm=llm,
       confidence_thresholds={
           "high": 0.8,
           "medium": 0.5,
           "low": 0.0
       }
   )

   # Create search engine
   search_engine = IntelligentSearchEngine(
       llm=llm,
       store=store
   )

   # Assemble memory manager
   memory_manager = ProllyTreeMemoryStoreManager(
       prolly_store=store,
       classifier=classifier,
       search_engine=search_engine
   )

Storing Memories
----------------

Store memories with automatic semantic classification:

.. code-block:: python

   # Store a simple memory
   await memory_manager.store_memory(
       content="My name is Sarah and I'm 32 years old",
       namespace="user123",
       auto_classify=True
   )

   # Store with metadata
   await memory_manager.store_memory(
       content="I work as a senior software engineer at TechCorp",
       namespace="user123",
       metadata={"source": "conversation", "confidence": 0.95},
       auto_classify=True
   )

The memories will be automatically classified to semantic paths like:
- ``profile.identity.name.first``
- ``profile.demographics.age``
- ``profile.professional.occupation.role``

Searching Memories
------------------

Search for memories using natural language queries:

.. code-block:: python

   # Simple search
   results = await memory_manager.search_memories(
       query="What is the user's name?",
       namespace="user123"
   )

   for result in results:
       print(f"Found: {result.content}")
       print(f"Path: {result.id}")

   # Search with limit
   results = await memory_manager.search_memories(
       query="Tell me about the user's work",
       namespace="user123",
       limit=5
   )

Version Control
---------------

Memoir provides Git-like version control for memories:

.. code-block:: python

   # Create a branch
   await memory_manager.create_branch("experiment")
   await memory_manager.checkout("experiment")

   # Make changes
   await memory_manager.store_memory(
       content="Testing new memory",
       namespace="user123"
   )

   # Commit changes
   commit_hash = await memory_manager.commit("Added test memory")

   # Switch back to main
   await memory_manager.checkout("main")

   # Merge changes
   await memory_manager.merge("experiment", into="main")

Search Engines
--------------

Memoir offers two search engine options:

**Intelligent Search** (LLM-powered, default):

.. code-block:: python

   from memoir.search.intelligent import IntelligentSearchEngine

   search_engine = IntelligentSearchEngine(llm=llm, store=store)

**Semantic Search** (keyword-based, faster):

.. code-block:: python

   from memoir.search.semantic import SemanticSearchEngine

   search_engine = SemanticSearchEngine(store=store)

Next Steps
----------

- Explore the :doc:`architecture` to understand the system design
- Check out :doc:`examples/basic_usage` for a complete working example
- Learn about :doc:`classification` strategies
- Understand :doc:`versioning` capabilities
