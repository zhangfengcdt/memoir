# Memoir Classifier Theory & Architecture

## Executive Summary

The Memoir project implements two distinct classifier approaches for mapping memories to semantic taxonomy paths:

1. **SemanticClassifier**: A high-performance, cache-optimized classifier using LLM-based classification with pattern matching fallbacks
2. **IntelligentClassifier**: An advanced multi-stage classifier with memory-worthiness detection, confidence-based expansion, and specialized event extraction

Both classifiers serve different use cases and represent different points on the performance-accuracy spectrum.

## Core Problem Statement

Traditional AI memory systems suffer from:

- **Opaque Storage**: UUID-based keys with no semantic meaning
- **Expensive Search**: O(n) vector similarity search for every query
- **No History**: Lack of version control or audit trails
- **Flat Structure**: No hierarchical organization of related memories

Memoir solves this by introducing a **semantic taxonomy** where memories are classified into human-readable hierarchical paths like `profile.professional.skills.python` instead of opaque identifiers.

## Classification Philosophy

### Key Paradigm Shift
```mermaid
flowchart TB
    subgraph Trad[Traditional]
        direction LR
        t1[uuid-1234] --> t2[expensive vector search] --> t3[no history]
    end
    subgraph Mem[Memoir]
        direction LR
        m1[profile.professional.skills.python] --> m2["O(log n) lookup"] --> m3[full versioning]
    end
```

The classification system transforms unstructured memory content into structured taxonomy paths, enabling:

- **Deterministic Retrieval**: Direct path lookups instead of similarity search
- **Hierarchical Organization**: Natural grouping of related memories
- **Human Interpretability**: Paths that make sense to developers and users

## Architecture Overview

### 1. SemanticClassifier

#### Design Goals
- **Low Latency**: Sub-second classification with aggressive caching
- **High Throughput**: Batch processing capabilities
- **Flexibility**: Works with any taxonomy implementing `TaxonomyInterface`
- **Robustness**: Graceful fallbacks for failed classifications

#### Algorithm & Implementation

##### Stage 1: Cache Lookup (1-5ms)
```python
cache_key = sha256(memory_content + context)
if cache_key in cache:
    return cached_result  # Instant return
```

##### Stage 2: LLM Classification (100-500ms)
The classifier constructs a sophisticated prompt that includes:

1. **Taxonomy Structure**: Hierarchical presentation of available paths
   - Groups paths by top-level category
   - Shows example paths per category (limited to prevent prompt overflow)
   - Indicates total path count for context

2. **Few-Shot Examples**: Dynamically generated based on available taxonomy
   - Covers diverse categories (personal, professional, preferences)
   - Shows confidence scoring patterns
   - Demonstrates reasoning format

3. **Classification Guidelines**:
   - Match to MOST SPECIFIC appropriate path
   - Consider semantic meaning and context
   - Avoid overly generic paths
   - Confidence scoring rubric (0.0-1.0)

##### Stage 3: Advanced Taxonomy Integration
For taxonomies implementing `AdvancedTaxonomyInterface`:
```python
if isinstance(taxonomy, AdvancedTaxonomyInterface):
    selected_path, confidence = taxonomy.select_path_with_fallback(
        classification_result, memory_content, metadata
    )
```

This enables:

- **Smart Fallbacks**: Using 'other' categories when uncertain
- **Expansion Tracking**: Recording patterns for taxonomy growth
- **Confidence Boosting**: Leveraging historical classification data

##### Stage 4: Path Validation & Correction
```python
if not is_valid_path(suggested_path):
    # Progressive fallback strategy
    path = find_closest_valid_path(suggested_path)
```

Fallback hierarchy:

1. Try progressively shorter paths (removing last segment)
2. Use configured fallback path if valid
3. Find any valid path in the same top-level category
4. Ultimate fallback to first available path

#### Performance Characteristics
- **Cache Hit**: 1-5ms
- **Cache Miss**: 100-500ms (LLM dependent)
- **Memory Usage**: O(cache_size) bounded by configuration
- **Batch Processing**: Linear scaling with parallel LLM calls

### 2. IntelligentClassifier

#### Design Goals
- **Memory Worthiness**: Filter out non-memorable content
- **Multi-Label Classification**: Support content spanning multiple categories
- **Event Extraction**: Detect profile updates, timeline events, location references
- **Dynamic Expansion**: Suggest new taxonomy branches for novel content
- **Confidence-Based Actions**: Different behaviors based on certainty levels

#### Algorithm & Implementation

##### Stage 1: Memory Worthiness Detection
The classifier first determines if content should be stored at all:

```python
Skip if:

- Transient information (greetings, weather)
- General conversation without specifics
- Below confidence threshold

Store if:

- Personal preferences, facts, skills
- Relationships, goals, experiences
- Meets minimum confidence threshold
```

##### Stage 2: Multi-Path Classification
Unlike SemanticClassifier's single-path approach, IntelligentClassifier supports multi-label classification with strict rules:

```python
Multiple paths allowed ONLY when:

1. Content spans DIFFERENT top-level categories
2. Maximum 2 paths
3. Each path represents distinct information

Example:
"My colleague John loves machine learning"
→ entity.people.mentioned.colleagues (ENTITY category)
→ topics.technology.artificial_intelligence (TOPICS category)
```

##### Stage 3: Specialized Event Extraction

**Profile Updates**:
```python
Detects definitive facts that replace previous information:

- "I'm 25 years old" → profile.personal.identity.age.current
- "I work at Google" → profile.professional.current.company.name
```

**Timeline Events**:
```python
Extracts temporal events with date calculation:

- "Yesterday was my first day" (session: 2023-03-15)
  → date: "20230314", description: "first day at new job"
```

**Location Events**:
```python
Captures geographic references:

- "The support group in Los Angeles"
  → location: "Los Angeles", description: "support group attendance"
```

##### Stage 4: Confidence-Based Actions

```python
HIGH confidence (>0.8):
  → Direct classification to suggested path

MEDIUM confidence (0.6-0.8):
  → Classify but consider alternatives

LOW confidence (<0.6):
  → Trigger expansion decision:
     - EXPAND: Create new subcategories
     - USE_PARENT: Move to more general category
     - SKIP: Don't store
```

##### Stage 5: Dynamic Taxonomy Expansion
When confidence is low, the classifier can suggest taxonomy expansion:

```python
if confidence < threshold and content is specialized:
    suggest_expansion(
        parent_path="knowledge.music",
        new_categories=["piano", "composition", "theory"]
    )
```

Expansion follows hierarchical depth rules:

- Add ONE intermediate level at a time
- Use general-to-specific progression
- Maximum recommended depth: 4 levels

#### Key Implementation Details

##### Simplified Taxonomy for Prompts
To reduce prompt size, IntelligentClassifier uses a simplified taxonomy:
```python
class PresetTaxonomy:
    # Only multi-level paths (2+ levels) are valid
    # Single-level categories are forbidden
```

This enforces proper hierarchical classification and prevents shallow categorization.

##### JSON Response Parsing with Repair
The classifier includes sophisticated JSON repair logic:
```python
def _fix_common_json_issues(json_str):
    # Remove comments
    # Fix trailing commas
    # Add missing quotes
    # Handle array formatting
```

This ensures robustness against LLM formatting inconsistencies.

##### Validation and Fallback Logic
```python
Path validation hierarchy:

1. Check if path exists in taxonomy
2. Accept new top-level categories (for expansion)
3. Find valid parent paths
4. Enforce minimum 2-level depth
5. Apply domain-specific fallbacks
```

## Comparative Analysis

### SemanticClassifier vs IntelligentClassifier

| Aspect | SemanticClassifier | IntelligentClassifier |
|--------|-------------------|----------------------|
| **Primary Use Case** | High-performance classification | Comprehensive memory processing |
| **Classification Speed** | 1-5ms (cached), 100-500ms (uncached) | 200-1000ms (always uses LLM) |
| **Multi-Label Support** | No (single path) | Yes (max 2 paths, different categories) |
| **Memory Filtering** | No | Yes (worthiness detection) |
| **Event Extraction** | No | Yes (profile, timeline, location) |
| **Dynamic Expansion** | Via AdvancedTaxonomyInterface | Built-in with confidence thresholds |
| **Caching** | Aggressive SHA-256 based | No caching |
| **Prompt Complexity** | Moderate (~2K tokens) | High (~4K tokens) |
| **Taxonomy Size** | Full taxonomy | Simplified preset |
| **Fallback Strategy** | Progressive path shortening | Confidence-based actions |

### When to Use Which

**Use SemanticClassifier when:**
- High throughput is critical
- Classification latency must be minimized
- Working with stable, well-defined taxonomies
- Caching can provide significant benefits
- Single-path classification is sufficient

**Use IntelligentClassifier when:**
- Memory quality filtering is important
- Multi-aspect content needs multiple labels
- Event extraction is required
- Taxonomy needs to grow dynamically
- Confidence-based decisions are needed

## Advanced Features

### 1. Classification Hints (SemanticClassifier)
When using iterative taxonomies, the classifier can leverage historical patterns:
```python
hints = taxonomy.get_classification_hints(memory_content)
if hint_path matches classification:
    boost_confidence(+0.1)
```

### 2. Expansion Tracking (IntelligentClassifier)
The classifier tracks pending expansions:
```python
pending_expansions[parent_path].append({
    "content": content,
    "suggested_expansion": new_categories
})
if len(pending) >= threshold:
    trigger_expansion(parent_path)
```

### 3. Context-Aware Classification
Both classifiers support contextual information:

- User ID, Session ID
- Conversation history
- Available memory paths
- Temporal context

### 4. Batch Processing (SemanticClassifier)
Efficient batch classification with cache benefits:
```python
results = classifier.batch_classify(memories, shared_context)
# Later classifications benefit from earlier cache entries
```

## Performance Optimization Strategies

### 1. Caching Strategy (SemanticClassifier)
- **Key Generation**: SHA-256 hash of content + context
- **Cache Size**: Configurable, default 10,000 entries
- **Hit Rate**: Typically 60-80% in production
- **Memory Bound**: O(cache_size * avg_result_size)

### 2. Prompt Optimization
- **Path Limiting**: Show only MAX_PROMPT_PATHS to prevent overflow
- **Example Selection**: Dynamic generation based on available paths
- **Category Grouping**: Hierarchical presentation for clarity

### 3. Fallback Performance
- **Progressive Matching**: O(path_depth) for validation
- **Domain Defaults**: Pre-computed fallbacks per category
- **Early Termination**: Stop at first valid match

## Future Enhancements

### Planned Improvements

1. **Hybrid Classification**: Combine both classifiers for optimal performance
   - Use SemanticClassifier for initial fast classification
   - Fall back to IntelligentClassifier for low-confidence cases

2. **Embedding-Based Pre-filtering**:
   - Use embeddings to narrow taxonomy search space
   - Reduce LLM prompt size for large taxonomies

3. **Adaptive Thresholds**:
   - Learn optimal confidence thresholds per category
   - Adjust based on classification success rates

4. **Streaming Classification**:
   - Process content in chunks for long documents
   - Maintain context across chunks

5. **Multi-Model Ensemble**:
   - Use multiple LLMs for consensus
   - Combine fast local models with powerful cloud models

## Conclusion

The dual-classifier architecture in Memoir represents a sophisticated approach to semantic memory classification. By offering both a high-performance cached classifier (SemanticClassifier) and a comprehensive intelligent classifier (IntelligentClassifier), the system provides flexibility for different use cases while maintaining the core benefit of semantic, hierarchical memory organization.

The key innovation lies not just in using LLMs for classification, but in the careful orchestration of caching, validation, fallbacks, and specialized processing that makes the system both performant and robust in production environments.
