# Contributing to UniMatch

Thank you for your interest in contributing to UniMatch! This document provides guidelines for contributors to ensure a smooth collaboration process.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Submitting Pull Requests](#submitting-pull-requests)
- [Issue Guidelines](#issue-guidelines)

---

## Prerequisites

Before contributing, ensure you have the following installed:

- **Python 3.12+** - For running the service layer and API
- **Git** - For version control
- **GitHub account** - For submitting pull requests
- **Code editor** - VS Code, PyCharm, or similar

### Optional Tools

- **Docker** - For containerized deployment (future)
- **Node.js 18+** - For frontend development (future)

---

## Getting Started

### 1. Fork the Repository

1. Visit the [UniMatch repository](https://github.com/Mabotse-Mosima/UniMatch-University-Application-System)
2. Click the **Fork** button in the top-right corner
3. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/UniMatch-University-Application-System.git
   cd UniMatch-University-Application-System
   ```

### 2. Set Up Development Environment

```bash
# Create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# Install all dependencies
pip install -r requirements.txt
```

### 3. Run Tests

Verify your setup by running the full suite from the repository root:

```bash
python -m pytest tests/ -v
# Expected: 81 tests, all pass
```

---

## Development Workflow

### 1. Pick an Issue

- Browse issues labeled [`good-first-issue`](https://github.com/Mabotse-Mosima/UniMatch-University-Application-System/issues?q=is%3Aissue+is%3Aopen+label%3Agood-first-issue) for beginner-friendly tasks
- Check [`feature-request`](https://github.com/Mabotse-Mosima/UniMatch-University-Application-System/issues?q=is%3Aissue+is%3Aopen+label%3Afeature-request) for enhancement ideas
- Comment on the issue to claim it (avoid duplicate work)

### 2. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
```

### 3. Make Changes

- Write code following [Coding Standards](#coding-standards)
- Add tests for new functionality
- Update documentation as needed

### 4. Test Your Changes

```bash
# Run relevant tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest --cov=.
```

### 5. Commit Changes

```bash
git add .
git commit -m "Brief description of changes"
```

Follow commit message conventions:
- Use present tense: "Add feature" not "Added feature"
- Be specific: "Add learner profile validation" not "Add stuff"
- Reference issues: "Fix #123 - Add APS calculation"

### 6. Push and Create Pull Request

```bash
git push origin feature/your-feature-name
```

Then visit GitHub to create a Pull Request.

---

## Coding Standards

### Python Code Style

- Follow **PEP 8** guidelines
- Use **4 spaces** for indentation (no tabs)
- Maximum line length: **88 characters**
- Use meaningful variable and function names
- Add docstrings to functions and classes

### Example:

```python
def calculate_aps(marks: list[int]) -> int:
    """
    Calculate APS score from subject marks.
    
    Args:
        marks: List of subject marks (0-100)
        
    Returns:
        APS score based on NSC 7-point scale
        
    Raises:
        ValueError: If marks are outside valid range
    """
    if not all(0 <= mark <= 100 for mark in marks):
        raise ValueError("Marks must be between 0 and 100")
    # Implementation...
```

### Documentation

- Update **README.md** for user-facing changes
- Add comments for complex logic
- Keep documentation in sync with code changes

### Git Conventions

- One feature/fix per commit
- Squash related commits before PR
- Write clear, descriptive commit messages

---

## Testing

### Test Requirements

- All new features must include tests
- Maintain test coverage above 80%
- Tests must pass before PR merge

### Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/services/test_services.py -v

# Run with coverage
python -m pytest --cov=. --cov-report=html
```

### Test Structure

```
tests/
├── conftest.py                    # Root conftest (sets pythonpath)
├── test_domain_entities.py        # Domain entity tests
├── services/
│   └── test_services.py           # Service layer unit tests
└── api/
    └── test_api.py                # API integration tests (httpx TestClient)
```

---

## Submitting Pull Requests

### PR Checklist

Before submitting, ensure:

- [ ] Code follows [Coding Standards](#coding-standards)
- [ ] Tests pass locally
- [ ] New features include tests
- [ ] Documentation is updated
- [ ] Commit messages are clear
- [ ] PR description explains the change

### PR Template

```markdown
## Description
Brief description of what this PR does.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Related Issues
Fixes #(issue number)

## Testing
Describe how you tested this change.

## Checklist
- [ ] Tests pass
- [ ] Documentation updated
- [ ] No breaking changes (or documented)
```

### Review Process

1. Automated CI/CD checks must pass
2. At least one maintainer approval required
3. Address review feedback promptly
4. Keep PRs focused and small

---

## Issue Guidelines

### Reporting Bugs

Use the bug report template:

```markdown
**Description**
Clear description of the bug

**Steps to Reproduce**
1. Go to...
2. Click on...
3. See error

**Expected Behavior**
What should happen

**Actual Behavior**
What actually happens

**Environment**
- OS: [e.g., Windows 10]
- Python version: [e.g., 3.11]
```

### Feature Requests

Use the feature request template:

```markdown
**Problem Description**
What problem does this solve?

**Proposed Solution**
How should it work?

**Alternatives**
What alternatives did you consider?

**Additional Context**
Screenshots, examples, etc.
```

### Issue Labels

- `good-first-issue` - Suitable for newcomers
- `feature-request` - Enhancement ideas
- `bug` - Bug reports
- `documentation` - Documentation improvements
- `enhancement` - Code improvements

---

## Getting Help

- **GitHub Issues**: For bug reports and feature requests
- **Discussions**: For questions and general discussion
- **Email**: christinah@example.com (replace with actual contact)

---

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Welcome newcomers and help them learn
- Assume good intentions

---

## Recognition

Contributors will be acknowledged in the project's CONTRIBUTORS.md file.

Thank you for contributing to UniMatch! 🎓

---

## Quick-Start Checklist for New Contributors

If you just want to jump straight in, here is the minimum you need:

```bash
# 1. Fork and clone
git clone https://github.com/YOUR_USERNAME/UniMatch-University-Application-System.git
cd UniMatch-University-Application-System

# 2. Install all dependencies
pip install -r requirements.txt

# 3. Run the full test suite from the repo root (should show 81 passing)
python -m pytest tests/ -v

# 4. Start the API and open Swagger UI
uvicorn unimatch.main:app --reload
# → http://localhost:8000/docs
```

## Known Setup Gotchas

- Always run tests and the application from the **repository root**, not from a subdirectory.
- The application is installed as the `unimatch` package under `src/`. The `pythonpath`
  setting in `pyproject.toml` configures this automatically for pytest.
- Use your own virtual environment (`python -m venv .venv`). Do not reuse any `.venv`
  that may have been left in historical subdirectories.
