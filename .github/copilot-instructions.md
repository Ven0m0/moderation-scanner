# GitHub Copilot Instructions

Use `/home/runner/work/moderation-scanner/moderation-scanner/AGENTS.md` as the canonical source of project context.
Do not duplicate stack, tooling, architecture, or convention details here.

## Copilot defaults
- Read `/home/runner/work/moderation-scanner/moderation-scanner/AGENTS.md` before making suggestions or edits.
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
- Put durable repository guidance in `/home/runner/work/moderation-scanner/moderation-scanner/AGENTS.md`.
- Keep `/home/runner/work/moderation-scanner/moderation-scanner/CLAUDE.md` as a symlink to `/home/runner/work/moderation-scanner/moderation-scanner/AGENTS.md`.
