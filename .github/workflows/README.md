# GitHub Actions Workflows

## CI Pipeline (`ci.yml`)

Comprehensive continuous integration pipeline that runs on:
- **Push to main branch**
- **Pull request creation/updates targeting main**

### Jobs

#### 1. **Test** (`test`)
- **Matrix**: Python 3.9, 3.10, 3.11, 3.12
- **OS**: Ubuntu Latest
- **Features**:
  - Dependency caching for faster builds
  - Full pytest suite with coverage
  - Coverage reporting to Codecov (Python 3.11 only)
  - All 57 tests including iterative taxonomy and LOCOMO conversation tests

#### 2. **Lint** (`lint`)
- **Python**: 3.11
- **Tools**:
  - **Black**: Code formatting checks
  - **Ruff**: Fast Python linting
  - **isort**: Import sorting validation
  - **Bandit**: Security vulnerability scanning
- **Caching**: Dependencies cached for faster execution

#### 3. **Examples** (`examples`)
- **Depends on**: test, lint jobs
- **Purpose**: Integration testing
- **Tests**:
  - Basic functionality (imports, taxonomy loading, classification)
  - Iterative taxonomy system validation
  - LOCOMO conversation data verification
  - Example scripts execution (if available)

#### 4. **Integration** (`integration`)
- **Runs on**: Pull requests only
- **Depends on**: test, lint jobs
- **Purpose**: PR-specific validation
- **Tests**:
  - Dedicated iterative taxonomy test suite
  - LOCOMO conversation test suite
  - Performance benchmarking (classification speed)
  - Ensures <10ms average classification time

### Performance Expectations

- **Classification Speed**: <10ms average (100 iterations)
- **Test Suite**: All 57 tests must pass
- **Coverage**: XML and terminal coverage reporting
- **Build Cache**: Efficient caching for dependencies

### Workflow Triggers

```yaml
on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]
```

The pipeline ensures code quality, functionality, and performance before any changes are merged to main.
