Basic Usage
===========

This guide walks through the basic usage patterns of Memoir, demonstrating the clean layered architecture and proper dependency injection.

Complete Example
----------------

Here's a complete example showing how to set up and use Memoir:

.. code-block:: python

   import asyncio
   import os
   import tempfile
   from langchain_openai import ChatOpenAI

   from memoir import ProllyTreeMemoryStoreManager
   from memoir.classifier.intelligent import IntelligentClassifier
   from memoir.search.intelligent import IntelligentSearchEngine
   from memoir.taxonomy.taxonomy_presets import TaxonomyVersion

   async def main():
       # 1. Set up LLM
       llm = ChatOpenAI(
           model="gpt-4o-mini",
           temperature=0,
           max_tokens=500
       )

       # 2. Create components in dependency order

       # Step 1: Storage layer (pure storage, no business logic)
       from memoir.store.prolly_adapter import ProllyTreeStore

       prolly_store = ProllyTreeStore(
           path="/tmp/memory_store",
           enable_versioning=True,
           cache_size=10000
       )

       # Step 2: Classification layer (depends on LLM)
       classifier = IntelligentClassifier(
           llm=llm,
           taxonomy_version=TaxonomyVersion.GENERAL,
           confidence_thresholds={
               "high": 0.8,   # High confidence - store immediately
               "medium": 0.5, # Medium confidence - good memories
               "low": 0.0     # Low threshold - reject below this
           }
       )

       # Step 3: Search engine (depends on LLM + store)
       search_engine = IntelligentSearchEngine(
           llm=llm,
           store=prolly_store
       )

       # Step 4: Memory manager (orchestrates all components)
       memory_manager = ProllyTreeMemoryStoreManager(
           prolly_store=prolly_store,
           classifier=classifier,
           search_engine=search_engine,
           enable_versioning=True
       )

       # 3. Store memories with semantic classification
       user_id = "user123"

       memories_to_store = [
           "My name is Sarah Johnson and I'm 32 years old.",
           "I work as a senior software engineer at TechCorp in San Francisco.",
           "I prefer dark mode in all my development environments.",
           "My primary programming language is Python, but I also use JavaScript.",
           "I drink coffee every morning, specifically a double espresso with oat milk.",
           "I have 8 years of experience in machine learning and data science.",
           "My favorite IDE is VS Code with the Monokai Pro theme.",
           "I graduated from Stanford University with a Computer Science degree in 2014.",
       ]

       for memory_text in memories_to_store:
           semantic_key = await memory_manager.store_memory(
               content=memory_text,
               namespace=user_id,
               metadata={"source": "demo"},
               auto_classify=True
           )
           print(f"Stored: {memory_text[:40]}...")
           print(f"Path: {semantic_key}")

       # 4. Search for memories
       queries = [
           "What is the user's name and age?",
           "Where does the user work and what is their role?",
           "What are the user's IDE and theme preferences?",
           "What does the user drink in the morning?",
       ]

       for query in queries:
           results = await memory_manager.search_memories(
               query=query,
               namespace=user_id,
               limit=5
           )

           print(f"\\nQuery: '{query}'")
           if results:
               best_result = results[0]
               print(f"Found: {best_result.content}")
               print(f"Path: {best_result.id}")
           else:
               print("No matches found")

   if __name__ == "__main__":
       asyncio.run(main())

Key Concepts
------------

**1. Dependency Injection Pattern**

Memoir follows a clean dependency injection pattern where each layer depends only on the layers below it:

.. code-block:: text

   Memory Manager
        ↓
   ┌─────────┬──────────────┬─────────────┐
   │ Storage │ Classification │   Search    │
   │ Layer   │     Layer      │  Engine     │
   └─────────┴──────────────┴─────────────┘

This design enables:

- **Testability**: Each component can be tested in isolation
- **Flexibility**: Swap implementations without changing other layers
- **Maintainability**: Clear separation of concerns

**2. Semantic Path Classification**

Instead of random UUIDs, memories are stored at meaningful semantic paths:

.. code-block:: python

   # Input: "My name is Sarah Johnson"
   # Classification: profile.identity.name.full
   # Storage: Aggregated with other name-related memories

**3. Memory Aggregation**

Related memories are automatically grouped together:

.. code-block:: python

   # Multiple memories about work:
   await memory_manager.store_memory("I work at TechCorp", user_id)
   await memory_manager.store_memory("I'm a senior engineer", user_id)
   await memory_manager.store_memory("I've been there 3 years", user_id)

   # Result: All aggregated at profile.professional.occupation

Component Configuration
-----------------------

**Storage Configuration**

.. code-block:: python

   store = ProllyTreeStore(
       path="./memory_store",      # Storage directory
       enable_versioning=True,      # Git-like versioning
       cache_size=10000            # Memory cache size
   )

**Classifier Configuration**

.. code-block:: python

   # Balanced configuration
   classifier = IntelligentClassifier(
       llm=llm,
       taxonomy_version=TaxonomyVersion.GENERAL,
       confidence_thresholds={
           "high": 0.8,    # Store immediately
           "medium": 0.5,  # Good memories
           "low": 0.0      # Minimum threshold
       },
       min_items_for_expansion=2  # Taxonomy growth threshold
   )

   # Conservative configuration (less storage)
   classifier = IntelligentClassifier(
       llm=llm,
       confidence_thresholds={
           "high": 0.9,
           "medium": 0.7,
           "low": 0.5      # Higher threshold = more selective
       }
   )

**Search Engine Options**

.. code-block:: python

   # Fast keyword-based search (0.1-1ms)
   from memoir.search.semantic import SemanticSearchEngine
   search_engine = SemanticSearchEngine(store=store)

   # Intelligent LLM-powered search (100-500ms)
   from memoir.search.intelligent import IntelligentSearchEngine
   search_engine = IntelligentSearchEngine(llm=llm, store=store)

Search Patterns
---------------

**Basic Search**

.. code-block:: python

   results = await memory_manager.search_memories(
       query="user's job",
       namespace="user123"
   )

**Advanced Search with Filters**

.. code-block:: python

   results = await memory_manager.search_memories(
       query="programming languages",
       namespace="user123",
       limit=10,
       filter={"confidence": {"$gte": 0.7}}
   )

**Batch Queries**

.. code-block:: python

   queries = [
       "What's the user's name?",
       "Where do they work?",
       "What are their skills?"
   ]

   for query in queries:
       results = await memory_manager.search_memories(query, namespace="user123")
       # Process results...

Version Control Operations
--------------------------

**Commit Control**

Memoir provides fine-grained control over when commits happen:

.. code-block:: python

   # Traditional auto-commit (default, backward compatible)
   store = ProllyTreeStore(path="./store", auto_commit=True)
   await store.store_memory_async(namespace, content, key)  # Commits immediately

   # Batch commit control
   store = ProllyTreeStore(path="./store", auto_commit=False)
   await store.store_memory_async(namespace, content1, key1)
   await store.store_memory_async(namespace, content2, key2)
   commit_hash = store.commit("Batch of related memories")

   # Memory manager batch control
   store.auto_commit = False  # Set on the underlying store
   memory_manager = ProllyTreeMemoryStoreManager(prolly_store=store)
   await memory_manager.store_memory(content1, namespace)
   await memory_manager.store_memory(content2, namespace)
   commit_hash = memory_manager.store_commit("Logical batch description")

**Branching**

.. code-block:: python

   # Create experimental branch
   await memory_manager.create_branch("experiment")
   await memory_manager.checkout("experiment")

   # Make changes
   await memory_manager.store_memory("Experimental data", "user123")

   # Commit changes
   commit_hash = await memory_manager.commit("Added experimental data")

**Merging**

.. code-block:: python

   # Switch back to main
   await memory_manager.checkout("main")

   # Merge changes
   await memory_manager.merge("experiment", into="main")

**Time Travel**

.. code-block:: python

   # Search at specific commit
   historical_results = await memory_manager.search_memories(
       query="user data",
       namespace="user123",
       at_commit=commit_hash
   )

Error Handling
--------------

.. code-block:: python

   try:
       await memory_manager.store_memory(content, namespace)
   except ClassificationError as e:
       # Handle classification failures
       logger.warning(f"Classification failed: {e}")
       # Perhaps store with manual classification

   except StorageError as e:
       # Handle storage failures
       logger.error(f"Storage failed: {e}")
       # Retry or fallback strategy

Performance Tips
----------------

1. **Choose the Right Search Engine**:
   - Use ``SemanticSearchEngine`` for fast, simple queries
   - Use ``IntelligentSearchEngine`` for complex, contextual queries

2. **Tune Confidence Thresholds**:
   - Lower thresholds = more memories stored
   - Higher thresholds = higher quality, fewer memories

3. **Batch Operations**:
   - Store multiple memories in sequence for better performance
   - Use transactions for atomic operations

4. **Cache Configuration**:
   - Increase cache size for frequently accessed memories
   - Monitor memory usage vs. performance trade-offs

Next Steps
----------

- Explore the :doc:`architecture` for deeper understanding
- See the :doc:`examples` for advanced usage patterns
- Check the :doc:`faq` for common questions
- Visit the :doc:`api/memoir` for complete API reference
