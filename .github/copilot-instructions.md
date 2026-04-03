# GitHub Copilot Instructions

Use `AGENTS.md` as the canonical source of project context.
Do not duplicate stack, tooling, architecture, or convention details here.

## Copilot defaults
- Read `AGENTS.md` before making suggestions or edits.
- Prefer small, focused changes over rewrites.
- Preserve public behavior unless the task explicitly requires a change.
- When code changes affect behavior, update or add tests.
- Reuse existing libraries and patterns before introducing new dependencies or abstractions.

## Safety rules
- Never hardcode secrets, API tokens, or credentials.
- Prefer environment variables and documented configuration files.
- Avoid logging or exposing sensitive user or service data.

## AI-doc maintenance
- Keep this file short and Copilot-specific.
- Put durable repository guidance in `AGENTS.md`.
- Keep `CLAUDE.md` as a symlink to `AGENTS.md`.
