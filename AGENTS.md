# AGENTS.md

Canonical AI-agent guidance for this repository.
`CLAUDE.md` must remain a symlink to this file.

## Project snapshot
- Project: Account Scanner / moderation-scanner
- Runtime: Python 3.13+
- Core stack: `asyncio`, `httpx[http2]`, `asyncpraw`, `discord.py`, `orjson`, `aiofiles`
- Quality tools: Ruff, Mypy (strict), Pytest, pytest-asyncio
- Package entry points: `account-scanner` -> `account_scanner:main`, `scanner-bot` -> `discord_bot:main`

## Repository map
- `account_scanner.py`: main scanning pipeline, CLI entry point, cache/rate-limit helpers
- `discord_bot.py`: Discord bot bootstrap and config validation
- `cogs/`: bot command cogs
- `tests/`: primary test suite
- `test_*.py`: additional root-level pytest files
- `docs/`: user and contributor docs
- `pyproject.toml`: dependencies and tool configuration
- `Makefile`: common development commands

## Setup and validation
- Install dev dependencies: `pip install -e ".[dev]"`
- Format: `make format`
- Format check: `make format-check`
- Lint: `make lint`
- Type check: `make type`
- Combined quality checks: `make check`
- Tests: `make test` for the Makefile wrapper, or `pytest -v --tb=short` when you need failures to stop automation because `make test` ends with `|| true`

## Coding expectations
- Keep changes small and targeted; preserve existing public behavior unless the task requires change.
- Prefer async patterns for I/O-bound work; do not block the event loop.
- Add type hints to new or modified Python functions; the repo uses `mypy` strict mode.
- Follow Ruff formatting defaults from `pyproject.toml` (100-char line length, double quotes, sorted imports).
- Add or update tests when behavior changes.
- Match existing module structure instead of introducing new abstractions unless needed.

## Testing notes
- Pytest collects `test_*.py` from both `tests/` and the repository root.
- Async tests use `pytest-asyncio` with `asyncio_mode = "auto"`.
- When test failures need a real exit code, run `pytest` directly instead of relying on `make test`.

## Security and operations
- Never hardcode tokens, API keys, or secrets; use environment variables and documented config files.
- Be careful with Reddit, Perspective API, Discord, and Sherlock rate limits and network failures.
- Avoid logging sensitive identifiers or credentials.
- Prefer existing dependencies; add new ones only when necessary and justified.

## Agent workflow
- Read this file before making changes.
- Use `AGENTS.md` as the canonical project context.
- Keep `.github/copilot-instructions.md` brief and Copilot-specific.
- If AI guidance changes, update this file first and keep `CLAUDE.md` as a symlink to it.
