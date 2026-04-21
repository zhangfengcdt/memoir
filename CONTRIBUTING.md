# Contributing to LangMem-ProllyTree

Thank you for your interest in contributing to LangMem-ProllyTree! This document provides guidelines and information for contributors.

## 🚀 Quick Start for Contributors

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/yourusername/langmem-prollytree.git
   cd langmem-prollytree
   ```

2. **Set up development environment**
   ```bash
   make setup
   ```

3. **Run tests to ensure everything works**
   ```bash
   make test
   ```

4. **Run the full CI pipeline locally**
   ```bash
   make ci
   ```

## 🎯 Areas Where We Need Help

### High Priority
- **Semantic taxonomy expansion**: Add new categories and paths
- **Classification accuracy**: Improve semantic path assignment
- **Performance optimization**: Make search and storage even faster
- **Documentation**: Examples, tutorials, and API docs

### Medium Priority
- **Multi-language support**: Expand beyond English taxonomy
- **Advanced search**: New search strategies and ranking algorithms
- **Integration examples**: More frameworks beyond LangGraph
- **Benchmarking**: Comprehensive performance testing

### Low Priority
- **Visualization tools**: Memory organization and search visualization
- **CLI tools**: Command-line interface for memory management
- **Export/import**: Additional formats and integrations

## 🛠️ Development Setup

### Prerequisites
- Python 3.10+
- Git
- Make (for convenience commands)

### Installation
```bash
# Clone your fork
git clone https://github.com/yourusername/langmem-prollytree.git
cd langmem-prollytree

# Set up development environment
make install-dev

# Install pre-commit hooks
make pre-commit
```

### Running Tests
```bash
# Basic tests
make test

# Tests with coverage
make test-cov

# Performance benchmarks
make benchmark

# Run examples
make examples
```

## 📝 Coding Standards

We maintain high code quality standards:

### Code Formatting
- **Black** for code formatting
- **isort** for import sorting
- **Ruff** for linting

```bash
# Format code
make format

# Check formatting
make lint
```

### Type Checking
- **MyPy** for static type checking
```bash
make type-check
```

### Security
- **Bandit** for security linting
- **Safety** for dependency vulnerability checking
```bash
make security
```

### Performance Requirements
All contributions must maintain or improve performance:

- **Memory search**: Must remain <10ms p95
- **Memory storage**: Must remain <50ms p95
- **Classification**: Must remain <10ms p95
- **No degradation**: No >10% performance regression

## 🧪 Testing Requirements

### Test Coverage
- New features require >90% test coverage
- Bug fixes require tests that demonstrate the fix
- Performance changes require benchmarks

### Test Categories
```bash
# Unit tests
pytest tests/test_*.py

# Integration tests
pytest tests/test_integration.py

# Performance tests
python examples/performance_benchmark.py
```

## 📋 Pull Request Process

### 1. Before You Start
- Check existing issues and PRs to avoid duplication
- Create an issue for substantial changes
- Fork the repository and create a feature branch

### 2. Making Changes
```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Make your changes
# ...

# Run local CI
make ci

# Commit with clear messages
git commit -m "feat: add semantic search optimization

- Improved hierarchical search performance by 20%
- Added new taxonomy paths for technical skills
- Updated benchmarks to reflect improvements"
```

### 3. Submitting PR
- Fill out the PR template completely
- Include performance impact assessment
- Add tests for new functionality
- Update documentation if needed

### 4. PR Review Process
- Automated CI checks must pass
- Code review by maintainers
- Performance benchmarks review
- Final approval and merge

## 🏗️ Architecture Guide

### Core Components

1. **Semantic Taxonomy** (`taxonomy/semantic_taxonomy.py`)
   - Fixed hierarchy of ~800 paths
   - Category organization
   - Path validation and navigation

2. **Classification Engine** (`taxonomy/semantic_classifier.py`)
   - Fast keyword-based classification
   - LLM fallback for complex cases
   - Caching and optimization

3. **Hierarchical Search** (`search/hierarchical_search.py`)
   - Multiple search strategies
   - Relevance scoring
   - Performance optimization

4. **ProllyTree Adapter** (`core/prolly_adapter.py`)
   - BaseStore interface implementation
   - Versioning capabilities
   - Storage optimization

5. **Memory Manager** (`core/memory_manager.py`)
   - High-level API
   - LangMem compatibility
   - Performance metrics

### Design Principles

- **Performance First**: All changes must consider performance impact
- **Backward Compatibility**: Maintain API compatibility when possible
- **Semantic Clarity**: Taxonomy changes should improve classification
- **Production Ready**: Code must be robust and well-tested

## 🔧 Adding New Features

### Semantic Taxonomy Expansion
```python
# In taxonomy/semantic_taxonomy.py
"new_category": {
    "subcategory": {
        "specific_area": ["item1", "item2", "item3"]
    }
}
```

### New Search Strategy
```python
# In search/hierarchical_search.py
async def _search_your_strategy(self, namespace: str, search_paths: List[str]):
    # Implement your search logic
    # Return List[SearchResult]
    pass
```

### Classification Improvements
```python
# In taxonomy/semantic_classifier.py
def _build_keyword_index(self):
    # Add new keyword mappings
    self.keyword_map["your_keyword"] = ["taxonomy.path"]
```

## 🐛 Bug Reports

### High Quality Bug Reports Include:
- **Clear description** of the issue
- **Reproduction steps** with minimal code example
- **Expected vs actual behavior**
- **Environment details** (Python version, OS, dependencies)
- **Performance impact** if applicable

### Bug Report Template
Use the GitHub issue template for bug reports.

## 💡 Feature Requests

### Good Feature Requests Include:
- **Clear use case** and motivation
- **Proposed API** or interface
- **Performance considerations**
- **Implementation ideas** (if you have them)

### Feature Request Template
Use the GitHub issue template for feature requests.

## 📊 Performance Contributions

### Benchmarking
```bash
# Run comprehensive benchmarks
make benchmark

# Run with custom parameters
cd examples
python performance_benchmark.py --num-memories 1000 --num-searches 500
```

### Performance Requirements
- **No Regression**: New features must not slow existing functionality
- **Measurable Improvement**: Performance optimizations should show >5% improvement
- **Documentation**: Include benchmark results in PR description

## 🔒 Security Guidelines

### Security Review Process
- All PRs automatically scanned for security issues
- No hardcoded secrets or credentials
- Validate all external inputs
- Follow secure coding practices

### Reporting Security Issues
Please report security vulnerabilities privately to the maintainers.

## 📚 Documentation

### Documentation Standards
- **Clear examples** for all public APIs
- **Performance notes** for optimization features
- **Migration guides** for breaking changes
- **Comprehensive README** updates

### Building Docs
```bash
make docs
```

## 🤝 Code Review Guidelines

### As a Reviewer
- **Be constructive** and specific in feedback
- **Focus on code quality**, performance, and maintainability
- **Test the changes** locally when possible
- **Check performance impact** with benchmarks

### As a Contributor
- **Respond promptly** to review feedback
- **Ask questions** if feedback is unclear
- **Update PR** based on feedback
- **Be patient** during the review process

## 🏆 Recognition

Contributors are recognized in several ways:
- **GitHub contributors** section
- **Release notes** for significant contributions
- **Maintainer invitation** for consistent contributors
- **Conference speaking** opportunities for major contributions

## 📞 Getting Help

- **GitHub Issues**: For bugs and feature requests
- **GitHub Discussions**: For questions and general discussion
- **Discord/Slack**: Real-time chat (if available)
- **Email**: Direct contact with maintainers (for sensitive issues)

## 📜 License

By contributing, you agree that your contributions will be licensed under the same MIT License that covers the project.

---

**Thank you for contributing to LangMem-ProllyTree!** 🚀

Together, we're building the next generation of AI memory systems with revolutionary performance improvements.
