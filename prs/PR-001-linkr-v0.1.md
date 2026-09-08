# PR-001 — Linkr v0.1: API + static web frontend

**Author:** DEV · **Date:** 2026-08-16 · **Tickets:** DEV-1
**Status:** merged to `main` (app code only — no infra in this PR)

## What this adds

The first working version of **Linkr**, a URL shortener. This is the app the
platform gets built around for the rest of the programme.

```
project/
  api/                  FastAPI service + Postgres  (this PR)
    app/                  config, db, models, schemas, routes, initdb
    tests/                12 tests, no DB required
    requirements.txt      pinned runtime deps
    requirements-dev.txt  test + lint deps
    .env.example          every env var, documented
    README.md             >>> the hand-off spec for DEVOPS <<<
  web/                  static frontend — 4 files, no build step  (this PR)
    index.html  styles.css  app.js  config.js  README.md
```

## Why a URL shortener

It's small enough to hold in your head, but it exercises the whole 3-tier
shape honestly: a real write path, a real read path with a hot-key access
pattern, a counter that gets contended, and a redirect that has to be *fast*.
It gives us somewhere real to go later — a cache in front of the hot codes, and
a read path worth autoscaling — instead of inventing load for its own sake.

## Design decisions that affect deployment

| Decision | Why it matters to you |
|---|---|
| **Stateless API** — all state in Postgres, nothing on local disk | Run as many replicas as you like. No sticky sessions, no shared volume. |
| **Split `/health` and `/ready`** | `/health` never touches the DB (liveness). `/ready` runs `SELECT 1` and returns **503** when Postgres is unreachable (load-balancer health check). Verified both behaviours before opening this PR. |
| **`/health` echoes `env`, `version`, `git_sha`** | So we can answer "what is actually deployed right now?" without guessing. Please feed the real commit SHA in at build time via `LINKR_GIT_SHA`. |
| **Engine is lazy — the app boots without a database** | The container won't crash-loop if Postgres is slow to come up; it reports unready instead. Start order is a soft dependency, not a hard one. |
| **All config from env, `LINKR_` prefix** | One image, every environment. Full table in `api/README.md`. |
| **Frontend config is read at RUNTIME from `config.js`** | One frontend artifact ships everywhere; only `config.js` changes per environment. Please don't bake an API URL into the build. |
| **Deps pinned exactly** | Reproducible builds. If a pin blocks you, tell us and we'll move it — don't unpin. |
| **307 redirect, not 301** | A cached permanent redirect makes a bad link impossible to fix. |
| **`psycopg` v3** | The DB URL scheme is `postgresql+psycopg://`, **not** `postgresql://`. This one bites people. |

## Verification done before hand-off

```
pytest        ->  12 passed
ruff check .  ->  All checks passed!
GET /health   ->  200  (with Postgres down)
GET /ready    ->  503  (with Postgres down)   <- as designed
```

Tested on Python 3.13. All pinned dependencies install cleanly on 3.11–3.13.

## Known gaps DEV owns (not blocking this PR)

- `python -m app.initdb` creates tables but can't alter them. Alembic is
  **DEV-4**. Please make the pipeline's migration step easy to re-point.
- No Prometheus metrics yet. Say the word and we'll instrument it.
- No auth on the API. Fine for staging; we'll need a view from OPS before prod.

## What we need next

See **DEV-2** (containerize + one-command local dev) and **DEV-3** (staging
deploy + CI). Details in `tickets/board.md` and the channel.
