# Linkr: platform engineering

Taking a small 3-tier app from "it runs on my laptop" to containerized, CI-built,
scanned for vulnerabilities, and deployed to the cloud with cost guardrails.
One reviewed change at a time.

**The app isn't the point.** Linkr is a plain URL shortener. The dev side built it
and handed it over as a finished v0.1. The work is everything around it: the
image, the pipeline, the infrastructure, the guardrails.

> **Status: the VM era is complete.** Everything in the table below is built,
> deployed and evidenced. Nothing in it is a plan. The next phase is the same
> platform on Kubernetes.

**What is proven, with numbers rather than adjectives:**

* A deploy takes **21 seconds**, of which 15.8s is the image pull. A rollback takes
  **6 seconds**, because the previous image is already on the host. Both were timed
  in a real drill on a live EC2 instance, not estimated. See [`RUNBOOK.md`](RUNBOOK.md).
* `/health` reports the **exact git SHA of the running build**, baked into the image
  at build time. A deploy cannot silently fail and still look healthy.
* The readiness alert has been **watched firing and clearing**, by stopping the
  database and putting it back. An alert nobody has seen fire is a belief.
* Staging is built and destroyed from code every session. Total AWS spend across
  the whole build is **under $5**, with the budget alarm created before the first
  resource existed.

---

## Architecture

```
                    ┌───────────────┐
   browser  ────────▶  web (static) │   4 files, no build step
                    │ index/app/css │   runtime config in config.js
                    └───────┬───────┘
                            │  JSON over HTTP
                    ┌───────▼───────┐
                    │ api (FastAPI) │   stateless · N replicas safe
                    │    :8000      │   /health · /ready · /{code} redirect
                    └───────┬───────┘
                            │  psycopg 3
                    ┌───────▼───────┐
                    │ PostgreSQL 16 │   all state lives here
                    └───────────────┘
```

`/health` just says the process is alive. It makes no external calls. `/ready`
runs `SELECT 1` and returns 503 when the database is unreachable. The load
balancer and the deploy gate read `/ready`. The restart policy reads `/health`.

If liveness checked the database too, one short DB blip would kill and restart a
perfectly healthy app. A small problem turns into an outage.

---

## Platform roadmap

| | Ticket | Deliverable |
|---|---|---|
| ✅ | `DEVOPS-00` | Public repo, LF-normalized, secret scanning + push protection |
| ✅ | `DEVOPS-01` | Multi-stage Dockerfile, `python:3.12-slim`, non-root UID 10001 |
| ✅ | `DEVOPS-02` | `docker compose` stack with healthchecks and a named volume |
| ✅ | `DEVOPS-03` | CI: ruff → pytest → build → Trivy scan → push to GHCR by git SHA |
| ✅ | `DEVOPS-06` | AWS cost guardrails **before** any resource exists |
| ✅ | `DEVOPS-10` | Terraform: EC2, security group, scoped IAM, IMDSv2 required, cost budget adopted with `import` |
| ✅ | `DEVOPS-04` | Deploy to AWS staging, verified end to end from outside the network |
| ✅ | `DEVOPS-11` | Prometheus, Grafana and blackbox probing. One alert, demonstrated firing and clearing |
| ✅ | `DEVOPS-12` | [`RUNBOOK.md`](RUNBOOK.md): deploy, verify, rollback and destroy, with measured timings |
| 🔄 | next | The same platform on Kubernetes |

Access to the staging host is **keyless**. There is no SSH key and no port 22
rule. Operators connect through SSM Session Manager, and the instance requires
IMDSv2.

Staging is ephemeral by design, so there is no permanent URL to click. The
evidence is the repository, the pipeline runs, and the runbook's measured
numbers, all of which outlive the environment.

---

## Standards this repo is built to

These aren't my preferences. They're the standards this work gets reviewed
against, and each one is here because of something specific it stops from going
wrong.

| Standard | What it stops |
|---|---|
| Images tagged by immutable **git SHA**, never `:latest` | "What's running in staging?" has no answer, and rollback becomes a guess |
| Containers run **non-root** at a high UID (10001) | Low UIDs collide with host accounts; root in a container is root on a mounted volume |
| **Multi-stage** builds, no compilers in the runtime layer | A build toolchain in a production image is attack surface you never use |
| Secrets never in image layers, `ENV` defaults, or `--build-arg` | Build args stay in image history, so `docker history` hands them to anyone who pulls |
| Config from **environment variables** only | Anything hardcoded to `localhost` can't work in a container |
| Logs to **stdout/stderr**, never a file | Containers are ephemeral, so a log file inside one dies with it |
| **LF line endings** enforced by `.gitattributes` | A CRLF shebang fails in a Linux container with a "no such file" error that names the wrong problem |
| Cost guardrails **before** the first resource | A sandbox that quietly bills is a sandbox that gets switched off |

Where these come from: Docker's official build best practices, the 12-Factor App,
and AWS Well-Architected.

---

## Layout

```
api/    FastAPI service, owned by the dev side, consumed here
web/    static frontend, 4 files, no build step
prs/    change descriptions that came with each hand-off
```

Platform artifacts (`Dockerfile`, `compose.yaml`, `.github/workflows/`) land as
their tickets close.

---

## Running it today

The app runs locally right now. The containerized path arrives with
`DEVOPS-01`/`DEVOPS-02`.

```bash
cd api
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # point LINKR_DATABASE_URL at your Postgres
python -m app.initdb          # idempotent; waits up to 60s for Postgres
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Tests need no database. They run against in-memory SQLite:

```bash
pip install -r requirements-dev.txt && ruff check . && pytest
```

Full config reference: [`api/README.md`](api/README.md).

---

## How this project is run

I run this like a real team would. A dev side hands the app over with a change
description. An ops side publishes the standards and reviews my work against
them. Every bit of platform work gets a ticket, a review, and an approval before
it ships.

I set that up myself, so the pressure is invented. The standards aren't. They're
what real teams enforce, and everything in this repo is real.

This is a portfolio project, not a job.

## License

MIT. See [LICENSE](LICENSE).
