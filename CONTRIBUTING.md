# Contributing to Account Scanner

Thank you for your interest in contributing to the Account Scanner project! This guide will help you get started with development and ensure your contributions align with the project's standards.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Code Standards](#code-standards)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Project Architecture](#project-architecture)
- [Common Tasks](#common-tasks)

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Git
- Basic understanding of async/await Python
- Familiarity with Discord.py (for bot contributions)

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:

```bash
git clone https://github.com/YOUR_USERNAME/moderation-scanner.git
cd moderation-scanner
```

3. Add the upstream repository:

```bash
git remote add upstream https://github.com/ORIGINAL_OWNER/moderation-scanner.git
```

## Development Setup

### Install Dependencies

```bash
# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install package in editable mode with dev dependencies
pip install -e ".[dev]"

# Install Sherlock (optional, for OSINT features)
pip install sherlock-project
```

### Development Dependencies

The `[dev]` extras include:
- `ruff` - Fast Python linter and formatter
- `mypy` - Static type checker
- `pytest` - Testing framework
- `pytest-cov` - Test coverage plugin
- `pytest-asyncio` - Async test support
- `pre-commit` - Git pre-commit hooks

### Environment Configuration

Create a `.env` file for local development (never commit this file):

```bash
# Discord Bot
DISCORD_BOT_TOKEN=your_token_here

# Reddit API
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USER_AGENT=account-scanner-dev/1.0

# Google Perspective API
PERSPECTIVE_API_KEY=your_api_key

# Optional: Admin features
ADMIN_USER_IDS=123456789,987654321
LOG_CHANNEL_ID=123456789
```

Load environment variables:

```bash
export $(cat .env | xargs)
```

### Pre-commit Hooks (Recommended)

Set up pre-commit hooks to automatically check code before committing:

```bash
pre-commit install
```

This will run ruff formatting, linting, and mypy type checking before each commit.

## Code Standards

### Python Style Guide

We follow modern Python best practices:

- **PEP 8** with some modifications (enforced by ruff)
- **Type hints** required for all functions and methods
- **Docstrings** required for all public classes, methods, and functions
- **Line length**: 100 characters maximum
- **Imports**: Use absolute imports, grouped and sorted

### Code Formatting

Use ruff for formatting:

```bash
# Format all files
ruff format .

# Format specific file
ruff format account_scanner.py
```

### Linting

Fix linting issues with ruff:

```bash
# Check for issues
ruff check .

# Auto-fix issues
ruff check --fix .
```

### Type Checking

Run mypy to check type hints:

```bash
# Check all files
mypy account_scanner.py discord_bot.py

# Check with strict mode
mypy --strict account_scanner.py
```

### Docstring Format

We use Google-style docstrings:

```python
def analyze_text(text: str, threshold: float = 0.7) -> dict[str, float]:
    """Analyze text for toxicity using Perspective API.

    This function sends text to Google's Perspective API and returns
    toxicity scores for various attributes.

    Args:
        text: The text content to analyze.
        threshold: Minimum score to flag as toxic. Default: 0.7.

    Returns:
        Dict mapping attribute names to scores (0-1):
            - TOXICITY: Overall rudeness/disrespect
            - INSULT: Personal attacks
            - PROFANITY: Swear words

    Raises:
        ValueError: If text is empty or threshold is invalid.
        APIError: If Perspective API request fails.

    Example:
        >>> scores = analyze_text("This is great!")
        >>> print(scores['TOXICITY'])
        0.12
    """
    pass
```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_scanner.py

# Run specific test
pytest tests/test_scanner.py::test_rate_limiter

# Run with coverage
pytest --cov=account_scanner --cov-report=html
```

### Writing Tests

- Place tests in `tests/` directory
- Name test files `test_*.py`
- Use descriptive test function names
- Test both success and failure cases
- Mock external API calls

Example test:

```python
import pytest
from account_scanner import ScanConfig, RateLimiter

@pytest.mark.asyncio
async def test_rate_limiter():
    """Test that rate limiter delays requests appropriately."""
    limiter = RateLimiter(rate_per_min=60.0)

    start = time.time()
    await limiter.wait()
    await limiter.wait()
    elapsed = time.time() - start

    # Should take at least 1 second for 60 requests/min
    assert elapsed >= 1.0
```

### Test Coverage

Aim for:
- **80%+ overall coverage**
- **100% coverage for critical paths** (API interactions, scanning logic)
- Test edge cases and error handling

## Pull Request Process

### Before Submitting

1. **Update from upstream**:

```bash
git fetch upstream
git rebase upstream/main
```

2. **Run all checks**:

```bash
# Format code
ruff format .

# Check linting
ruff check .

# Type check
mypy account_scanner.py discord_bot.py

# Run tests
pytest
```

3. **Update documentation** if you:
   - Added new features or functions
   - Changed public APIs
   - Modified configuration options

### Commit Messages

Write clear, descriptive commit messages:

```
Add rate limiting to Perspective API requests

- Implement RateLimiter class with token bucket algorithm
- Add rate_per_min parameter to ScanConfig
- Update RedditScanner to use rate limiter
- Add tests for rate limiting functionality

Closes #123
```

Format:
- **First line**: Summary (50 chars or less)
- **Blank line**
- **Body**: Detailed explanation (wrap at 72 chars)
- **Reference issues**: Use "Closes #123" or "Fixes #123"

### Creating a Pull Request

1. Push your branch to your fork:

```bash
git push origin feature/your-feature-name
```

2. Open a pull request on GitHub

3. Fill out the PR template:
   - **Description**: What does this PR do?
   - **Motivation**: Why is this change needed?
   - **Testing**: How did you test this?
   - **Checklist**: Complete all items

4. Wait for review and address feedback

### PR Checklist

- [ ] Code follows project style guidelines
- [ ] All tests pass
- [ ] Added tests for new functionality
- [ ] Updated documentation (README, docstrings)
- [ ] Ran ruff format and ruff check
- [ ] Ran mypy type checking
- [ ] Updated changelog.md (for notable changes)
- [ ] No secrets or credentials in code

## Project Architecture

### Core Components

**account_scanner.py**
- `ScanConfig`: Dataclass for configuration
- `RateLimiter`: API rate limiting
- `SherlockScanner`: OSINT username enumeration
- `RedditScanner`: Reddit + Perspective API toxicity analysis
- `ScannerAPI`: High-level library interface

**discord_bot.py**
- `BotConfig`: Environment variable configuration
- Bot commands: scan, health, help, shutdown
- Discord.py integration with permissions and cooldowns

### Key Design Principles

1. **Async-first**: All I/O operations use async/await
2. **Type safety**: Comprehensive type hints throughout
3. **Error handling**: Graceful degradation, log errors
4. **Rate limiting**: Respect API quotas
5. **Separation of concerns**: Clear module boundaries
6. **Configuration**: Environment variables + dataclasses

### Adding New Features

#### Adding a New Toxicity Attribute

1. Update `ATTRIBUTES` constant in `account_scanner.py`
2. Update docstrings mentioning attribute lists
3. Update README toxicity attributes section
4. Add tests for the new attribute

#### Adding a New Discord Command

1. Add command function in `discord_bot.py`
2. Add docstring with usage examples
3. Add permission checks/cooldowns if needed
4. Update `!help` command output
5. Update README and DEPLOYMENT.md

#### Adding API Integrations

1. Create new scanner class (e.g., `TwitterScanner`)
2. Implement async methods with error handling
3. Add rate limiting
4. Add configuration to `ScanConfig`
5. Integrate into `ScannerAPI.scan_user()`
6. Add comprehensive tests

## Common Tasks

### Testing Locally

```bash
# Test CLI
python account_scanner.py testuser --mode sherlock --verbose

# Test Discord bot (requires valid token)
python discord_bot.py
```

### Debugging

Enable verbose logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Use the `--verbose` flag for CLI:

```bash
python account_scanner.py user --verbose
```

### Building Docker Image

```bash
# Build image
docker build -t account-scanner .

# Run container
docker run -e DISCORD_BOT_TOKEN=$DISCORD_BOT_TOKEN account-scanner
```

### Updating Dependencies

```bash
# Update specific package
pip install --upgrade package-name

# Update all packages from pyproject.toml (careful!)
pip install --upgrade -e ".[dev]"
```

## Questions or Issues?

- **Bugs**: Open an issue with reproduction steps
- **Features**: Open an issue with use case description
- **Questions**: Check existing issues or open a discussion
- **Security**: Email maintainers directly (don't open public issue)

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow
- Follow the project's technical standards

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (MIT License).

---

Thank you for contributing to Account Scanner! Your efforts help make moderation tools better for everyone.
