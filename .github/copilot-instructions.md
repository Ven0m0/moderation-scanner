# 🤖 GitHub Copilot Instructions

> Canonical, up-to-date project context (stack, tools, commands, conventions, architecture, etc.) lives in `AGENTS.md`. Do not restate or override it here.

## How Copilot should use this repository

- When you need project context, first open and read `AGENTS.md` and follow the guidance there.
- Treat `AGENTS.md` as the single source of truth for technologies, commands, and coding conventions.
- Prefer suggesting changes that stay consistent with the patterns and examples documented in `AGENTS.md`.

## Suggestions & completions

- Prefer small, focused edits over large rewrites unless explicitly requested.
- Preserve existing public APIs and behaviour unless the user explicitly asks to change them.
- When adding dependencies or tools, keep them minimal and explain why they are needed.
- Where tests exist, update or add tests alongside code changes.

## Security & safety

- Never suggest hard-coded secrets or tokens; use environment variables and configuration instead.
- Avoid sending or logging sensitive data (tokens, passwords, PII) unless explicitly required and documented.
