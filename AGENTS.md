# AGENTS.md — project rules for the agent

This file is loaded into the agent's system context per Codex CLI /
Claude Code semantics. Anything you put here is treated as a standing
instruction. Use it for: coding conventions, naming rules, "always do X
before Y", architecture decisions, libraries to prefer or avoid.

---

## Project conventions

- **Language**: User-facing strings default to Chinese unless the user
  switches the UI language to English. Use `t('key', zh, en)` from
  `frontend/src/i18n.ts` instead of hardcoding Chinese.
- **API style**: All new FastAPI routers live under `backend/app/api/`
  and are mounted in `backend/app/main.py` with the `/api` prefix.
- **State changes**: Anything that touches the DB schema needs a
  migration in `_migrate_*` in `storage/db.py` and idempotent guards.
- **Logging**: Use `_log = logging.getLogger(__name__)`; never `print`.

## Tooling boundary

- The agent is *not* allowed to call `git push` without an explicit
  user instruction in the current session.
- The agent should prefer `uvicorn --reload` style dev workflows over
  killing processes when iterating.
- MCP tools that perform destructive operations (delete file, wipe
  account) must go through the permission modal flow.

## Coding rules

- Keep changes focused - one commit = one coherent feature.
- Update tests under `backend/tests/` whenever you add a backend module
  with non-trivial logic.
- Update `frontend/src/i18n.ts` keys before adding new visible strings.

## What NOT to do

- Do not edit `backend/data/` (runtime DB), `frontend/dist/` (build),
  or `node_modules/`.
- Do not introduce new top-level dependencies without a brief note in
  the commit message.
