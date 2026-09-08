# Linkr API — v0.1

A URL shortener. Owned by **DEV**. This document is the hand-off spec for
**DEVOPS** — everything you need to package, run, and deploy it without reading
the source.

## What it is

```
[ static web ]  ->  [ this API (FastAPI) ]  ->  [ PostgreSQL ]
```

Stateless API. **All state lives in Postgres** — no local disk writes, no
in-memory session state, no sticky sessions needed. Safe to run N replicas.

## Runtime

| | |
|---|---|
| Language | Python **3.12** — chosen to match the approved `python:3.12-slim` base (OPS #003). Verified to run on 3.11–3.13. |
| Server | `uvicorn` — the app is an ASGI app at `app.main:app` |
| Listens on | **8000**, bound to `0.0.0.0` (see start command). Nothing in the code hardcodes a port — uvicorn is told. Port 8000 is above 1024, so an unprivileged user can bind it. |
| Dependencies | `requirements.txt` (runtime) · `requirements-dev.txt` (tests + lint) |
| Data store | **PostgreSQL 16** (what we develop against). Nothing used is version-specific; 14+ will work. |
| Logs | stdout/stderr only — **no file handlers anywhere**, nothing written to disk. |

**Production start command:**

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` is not optional in a container: bound to `127.0.0.1` the process
is unreachable from outside it.

**Test command:**

```bash
pip install -r requirements-dev.txt && ruff check . && pytest
```

## Configuration

Everything is environment-driven, prefix `LINKR_`. Nothing is hardcoded.
See `.env.example`.

| Variable | Required | Default | Notes |
|---|---|---|---|
| `LINKR_DATABASE_URL` | **yes** | localhost dev URL | SQLAlchemy URL. Driver is **psycopg 3**, so the scheme is `postgresql+psycopg://` — not `postgresql://`. Contains the password → **treat as a secret**. |
| `LINKR_BASE_URL` | **yes** in staging/prod | `http://localhost:8000` | Public origin used to build the `short_url` we return. If this is wrong, we hand users links that don't resolve. |
| `LINKR_ENV` | no | `local` | `local` / `staging` / `prod`. Echoed on `/health`. |
| `LINKR_VERSION` | set it in the build | `0.1.0` | Echoed on `/health`. |
| `LINKR_GIT_SHA` | set it in the build | `unknown` | Echoed on `/health`. **Please wire this to the real commit SHA** — it's how we tell what's actually deployed. |
| `LINKR_LOG_LEVEL` | no | `info` | |
| `LINKR_CORS_ORIGINS` | only if web is on another origin | `*` | Comma-separated. Tighten this before prod. |
| `LINKR_CODE_LENGTH` | no | `7` | |
| `LINKR_DB_POOL_SIZE` | no | `5` | Per process. **`replicas × workers × pool_size` must stay under Postgres `max_connections`.** |

## Schema / migrations

v0.1 has one table, `links`. Create it with:

```bash
python -m app.initdb     # idempotent; waits up to 60s for Postgres first
```

Run this **as its own deploy step**, before the app starts — not from the app's
startup path. A failed migration should fail the deploy, not crash-loop the API.

> ⚠️ Known gap: `initdb` can `CREATE TABLE` but not `ALTER` — it stops being
> enough the moment we change a column. DEV-4 tracks replacing it with Alembic.
> Please build the pipeline's migration step so swapping the command later is a
> one-line change.

## Endpoints

### Operational

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | **Liveness.** Never touches the DB — returns 200 whenever the process is alive. Returns `{status, env, version, git_sha}`. Use for restart/liveness checks. |
| `GET` | `/ready` | **Readiness.** Runs `SELECT 1`. **200** when the DB answers, **503** when it doesn't. Use for load-balancer target groups and rollout gates. |

Using `/health` for the load balancer would route traffic to an instance that
can't reach Postgres. Using `/ready` for liveness would restart the API during a
database blip. Please use each for its own job.

`GET /docs` serves interactive OpenAPI docs; `GET /openapi.json` is the spec.

### Application

| Method | Path | Returns |
|---|---|---|
| `POST` | `/api/links` | `201` — body `{"url": "...", "code": "optional-vanity"}`. `400` reserved code · `409` code taken · `422` invalid URL |
| `GET` | `/api/links?limit=20&offset=0` | `200` — newest first |
| `GET` | `/api/links/{code}` | `200` / `404` |
| `DELETE` | `/api/links/{code}` | `204` / `404` |
| `GET` | `/api/stats` | `200` — `{total_links, total_hits}` |
| `GET` | `/{code}` | `307` redirect to the target, and increments the hit counter. `404` if unknown. |

**Routing note:** the API owns the top-level path `/{code}`. If you put the
static frontend and the API behind one proxy, unknown top-level paths must go to
the API, not to the frontend. Paths the API owns: `/api/*`, `/health`, `/ready`,
`/docs`, `/redoc`, `/openapi.json`, `/{code}`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest          # 12 tests, in-memory SQLite, no database needed
ruff check .
```

Both are green as of this hand-off. `pytest` needs **no** services, so it can be
the fast gate on every push.

To run the same suite against real Postgres — worth adding as a separate
integration stage once compose exists:

```bash
LINKR_TEST_DATABASE_URL=postgresql+psycopg://linkr:linkr@localhost:5432/linkr_test pytest
```

## Notes for containerization (for `DEVOPS-01`)

Everything below was **verified on this codebase**, not assumed. It exists so the
Dockerfile can be built once rather than debugged twice.

### What the runtime image actually needs

| Include | Leave out |
|---|---|
| `app/` | `tests/` |
| the installed dependencies from `requirements.txt` | `requirements-dev.txt` (pytest, httpx, ruff) |
| | `pyproject.toml` (test/lint config only) |
| | `.env.example` |

### No compiler, and no `libpq` system package

We depend on **`psycopg[binary]`**, whose wheel vendors its own libpq (verified:
the installed `psycopg_binary.libs/` contains a bundled `libpq`). So:

- no `gcc`/`build-essential` in the build stage,
- no `libpq5` / `libpq-dev` in the runtime stage,
- copying installed site-packages between stages is safe — nothing links against
  a system library that would be missing in the runtime layer.

If anyone ever switches to plain `psycopg` or `psycopg[c]`, **both** of those
come back. Please don't change that extra without telling DEV.

### Two env vars the image should set

**`PYTHONUNBUFFERED=1` — please set this. It is not cargo cult.** Verified
behaviour of our actual stack:

| stream | who writes there | buffering when not a TTY |
|---|---|---|
| `stderr` | our app logs, uvicorn startup/error logs | **line-buffered** — appears immediately |
| `stdout` | **uvicorn access logs** | **block-buffered (~8 KB)** |

So our own logs are fine either way, but **access logs can sit in a buffer and
are lost outright if the container is killed** — which is precisely when you most
want them. One env var closes it.

**`PYTHONDONTWRITEBYTECODE=1`** — stops Python writing `__pycache__` into the
image at runtime. Keeps the layer clean and removes the only write the process
ever attempts.

### Read-only root filesystem: confirmed compatible

Grepped the whole of `app/` for file writes — **there are none.** No `open()` for
writing, no `FileHandler`, no temp files, no local state; all state is in
Postgres and all logs go to stdout/stderr. With `PYTHONDONTWRITEBYTECODE=1` the
process needs **no writable path at all**.

That means OPS's Stage-2 `read-only rootfs` MUST costs us nothing and needs no
`tmpfs` mount. Same reasoning makes **distroless viable at Stage 2** — the app
never shells out.

### Probes

- **liveness** → `GET /health` (never touches the DB)
- **readiness / LB target group / deploy gate** → `GET /ready` (503 when the DB is down)

### Reproducibility caveat — read before you pin the build

`requirements.txt` pins our **9 direct** dependencies. It does **not** pin the
**21 transitive** ones underneath them (`starlette`, `anyio`, `h11`, `pydantic_core`,
`typing_extensions`, …). Two builds from the identical commit can therefore
resolve different transitive versions. Tracked as **`DEV-05`** — see the channel.

## What DEV has deliberately NOT built

These are yours, and we're not going to guess at them:

- Dockerfile / container image · docker-compose for local dev
- CI pipeline · image registry · deployment to any environment
- Reverse proxy / TLS · secret storage · backups
- Prometheus metrics endpoint — **ask us and we'll add it**; instrumenting the
  app is DEV work, deciding what to scrape is yours.
