# 🤖 GitHub Copilot Project Context

Welcome to **Account Scanner**. This context document provides essential instructions to guide Copilot’s code suggestions.

## 🎯 Quick Project Summary

This project integrates Reddit toxicity analysis (Perspective API) with OSINT username enumeration (Sherlock). It also features a Discord bot for moderation.

- **Stack:** Python 3.11+, Async (`httpx`, `asyncio`), `discord.py`
- **Linting & Formatting:** Ruff
- **Type Checking:** Mypy
- **Testing:** Pytest

---

<details>
<summary><h2>🛠️ Development Setup & Guidelines</h2></summary>

### Key Commands (Makefile)
- `make check`: Formatting, linting, type checking.
- `make format`: Auto-format code.
- `make lint-fix`: Auto-fix Ruff lint issues.
- `make type`: Mypy type check.
- `make test`: Pytest suite.
- `make dev`: Install dev dependencies.

### Environment Management
- Uses `pip install -e ".[dev]"` for local dev installation.
- Relies on `pyproject.toml` for dependency configuration.
- We require type hinting for all newly written functions.

</details>

<details>
<summary><h2>📐 Code Architecture & Conventions</h2></summary>

### Architecture Notes
- The codebase heavily utilizes asynchronous Python (e.g., `asyncio`, `httpx` with http2). When making I/O bound requests, generate async code.
- Keep dependencies updated but avoid introducing unnecessary ones.
- The Discord bot (`discord_bot.py`) uses `app_commands` for slash commands.
- The core scanner logic is in `account_scanner.py`.

### Coding Standards
1. **Typing:** Provide strict type hints for variables, parameters, and return types.
2. **Formatting:** Follow the Ruff configuration defined in `pyproject.toml`.
   - Line length: 100
   - Quote style: double
   - Indent style: space
3. **Error Handling:** Generate `try/except` gracefully to handle API rate limits or failures.
4. **Docs:** Add docstrings to public classes and complex functions.

</details>

<details>
<summary><h2>🔐 Security & Performance Tips</h2></summary>

- Do not suggest hardcoded secrets. Instead, suggest pulling them from environment variables (e.g., `os.getenv()`).
- Always use asynchronous sleep (`asyncio.sleep()`) over blocking `time.sleep()`.
- Ensure generated code handles concurrent limits effectively using semaphores if making high-volume API requests.

</details>
