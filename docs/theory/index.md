# Theory Documentation

Deep technical analysis and theoretical foundations of Memoir's core components.

These documents provide comprehensive explanations of the algorithms, design decisions, and architectural patterns used throughout the Memoir system.

## Component Theory

```{toctree}
:maxdepth: 2

classifier
search
memento
```

## Overview

The theory documentation explores three fundamental aspects of Memoir:

### Classifier Theory
Detailed analysis of the two classifier approaches (SemanticClassifier and IntelligentClassifier), including their algorithms, performance characteristics, and use cases.

- **SemanticClassifier**: High-performance, cache-optimized classification with pattern matching fallbacks
- **IntelligentClassifier**: Advanced multi-stage classification with memory-worthiness detection and event extraction

### Search Theory
In-depth exploration of the search engines (SemanticSearchEngine and IntelligentSearchEngine), covering keyword matching, LLM-powered path selection, and performance optimizations.

- **SemanticSearchEngine**: Fast keyword-based search with relevance scoring (16-75ms)
- **IntelligentSearchEngine**: LLM-powered semantic understanding and path selection (215-570ms)

### Memento Theory
Comprehensive examination of the memento pattern implementation for ProfileMemento, TimelineMemento, and LocationMemento, explaining dimensional memory organization.

- **ProfileMemento**: Identity and biographical information with replacement semantics
- **TimelineMemento**: Chronological event organization by date
- **LocationMemento**: Spatial memory management with geographic normalization

## Key Insights

- **Performance vs Accuracy Trade-offs**: Each component offers multiple implementations optimized for different use cases
- **Hierarchical Organization**: Leveraging semantic paths for O(log n) operations instead of O(n) vector searches
- **Dimensional Separation**: Organizing memories along natural human cognitive dimensions (identity, time, space)
- **Git-like Versioning**: Bringing version control concepts to AI memory management

## Performance Benchmarks

| Component | Fast Implementation | Intelligent Implementation |
|-----------|-------------------|---------------------------|
| **Classifier** | 1-5ms (cached) | 200-1000ms (LLM) |
| **Search** | 16-75ms (keyword) | 215-570ms (LLM) |
| **Storage** | 20-30ms | 20-30ms |

## Architecture Benefits

1. **10-50x faster search** than traditional vector approaches
2. **Transparent, interpretable** ranking mechanisms
3. **Flexible trade-offs** between speed and understanding
4. **Hierarchical exploration** of memory spaces
