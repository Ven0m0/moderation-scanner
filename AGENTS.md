# 🤖 Project Information for AI Agents

Welcome to the **Account Scanner** project. This document provides essential context and instructions for AI assistants, utilizing progressive disclosure to prioritize critical information.

## 🎯 Quick Project Summary

This project is a multi-source account scanner that combines Reddit toxicity analysis (via Perspective API) with OSINT username enumeration (via Sherlock). It also includes a Discord bot for moderation.

- **Stack:** Python 3.11+, Async (httpx, asyncio), `discord.py`
- **Linting & Formatting:** Ruff
- **Type Checking:** Mypy
- **Testing:** Pytest

---

<details>
<summary><h2>🛠️ Development Setup & Tools</h2></summary>

### Key Commands (Makefile)
- `make check`: Runs formatting, linting, and type checking.
- `make format`: Formats code with Ruff.
- `make lint-fix`: Auto-fixes Ruff linting issues.
- `make type`: Runs Mypy type checking.
- `make test`: Runs Pytest suite.
- `make dev`: Installs development dependencies.

### Environment Management
- Uses `pip install -e ".[dev]"` for local dev installation.
- Relies on `pyproject.toml` for dependency configuration.
- We require type hinting for all newly written functions.

</details>

<details>
<summary><h2>📐 Code Architecture & Conventions</h2></summary>

### Architecture Notes
- The codebase uses asynchronous Python heavily (e.g., `asyncio`, `httpx` with http2). When making I/O bound requests, always use async/await.
- Keep dependencies updated but avoid introducing unnecessary ones.
- The Discord bot (`discord_bot.py`) uses `app_commands` for slash commands.
- The core scanner logic is in `account_scanner.py`.

### Coding Standards
1. **Typing:** Use strict type hints (`typing` module) wherever possible.
2. **Formatting:** Follow the Ruff configuration defined in `pyproject.toml`.
   - Line length: 100
   - Quote style: double
   - Indent style: space
3. **Error Handling:** Use `try/except` gracefully to handle API limits or failures.
4. **Docs:** Add docstrings to public classes and complex functions.

</details>

<details>
<summary><h2>🔐 Security & Performance</h2></summary>

- Avoid hardcoding secrets. Always use environment variables (see `.env.example`).
- Be mindful of rate limits when interacting with Reddit, Perspective API, and Sherlock.
- Ensure that the async event loop (`uvloop` where applicable) does not block.
- Run `make security` or `make audit` periodically.

</details>
