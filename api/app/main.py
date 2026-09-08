"""Linkr API — URL shortener.

Owned by DEV. Packaging, runtime, and deployment belong to DEVOPS: this module
never assumes a port, a hostname, a container, or a cloud.

Operational endpoints:
  GET /health  — liveness. Never touches the database. Use for restart checks.
  GET /ready   — readiness. Hits the DB; returns 503 when it can't. Use for LB
                 target-group health checks and rollout gates.
"""

import logging
import secrets
import string
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Path, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Link
from .schemas import HealthOut, LinkCreate, LinkOut, StatsOut

settings = get_settings()

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("linkr")

ALPHABET = string.ascii_letters + string.digits

# Paths the router owns — a vanity code can never shadow one of these.
RESERVED_CODES = {
    "api", "health", "ready", "docs", "redoc", "openapi.json",
    "metrics", "static", "favicon.ico", "robots.txt",
}

MAX_CODE_ATTEMPTS = 5


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(
        "linkr starting env=%s version=%s git_sha=%s",
        settings.env, settings.version, settings.git_sha,
    )
    yield
    log.info("linkr shutting down")


app = FastAPI(
    title="Linkr API",
    version=settings.version,
    description="A small URL shortener. 3-tier demo: static web -> this API -> Postgres.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


def _to_out(link: Link) -> LinkOut:
    return LinkOut(
        code=link.code,
        short_url=f"{settings.base_url.rstrip('/')}/{link.code}",
        target_url=link.target_url,
        hits=link.hits,
        created_at=link.created_at,
        last_hit_at=link.last_hit_at,
    )


def _new_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(settings.code_length))


# --------------------------------------------------------------------------
# Operational endpoints
# --------------------------------------------------------------------------

@app.get("/health", response_model=HealthOut, tags=["ops"])
def health() -> HealthOut:
    """Liveness. Deliberately does NOT touch the database."""
    return HealthOut(
        status="ok",
        env=settings.env,
        version=settings.version,
        git_sha=settings.git_sha,
    )


@app.get("/ready", tags=["ops"])
def ready(db: Session = Depends(get_db)) -> dict[str, str]:
    """Readiness. 200 only when the database answers."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        log.exception("readiness check failed: database unreachable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        ) from exc
    return {"status": "ready"}


# --------------------------------------------------------------------------
# Link management
# --------------------------------------------------------------------------

@app.post("/api/links", response_model=LinkOut, status_code=201, tags=["links"])
def create_link(payload: LinkCreate, db: Session = Depends(get_db)) -> LinkOut:
    target = str(payload.url)

    if payload.code:
        if payload.code.lower() in RESERVED_CODES:
            raise HTTPException(status_code=400, detail="that code is reserved")
        link = Link(code=payload.code, target_url=target)
        db.add(link)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            # A taken code is a normal outcome, not an internal fault — don't
            # chain the driver error into the response.
            raise HTTPException(
                status_code=409, detail="that code is already taken"
            ) from None
        db.refresh(link)
        log.info("created vanity link code=%s", link.code)
        return _to_out(link)

    # Generated code: collide-and-retry rather than pre-checking, so two
    # concurrent writers can't both "win" the same free code.
    for attempt in range(MAX_CODE_ATTEMPTS):
        link = Link(code=_new_code(), target_url=target)
        db.add(link)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            log.warning("short code collision (attempt %d)", attempt + 1)
            continue
        db.refresh(link)
        log.info("created link code=%s", link.code)
        return _to_out(link)

    log.error("gave up generating a unique code after %d attempts", MAX_CODE_ATTEMPTS)
    raise HTTPException(status_code=500, detail="could not allocate a short code")


@app.get("/api/links", response_model=list[LinkOut], tags=["links"])
def list_links(
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[LinkOut]:
    rows = db.scalars(
        select(Link).order_by(Link.created_at.desc(), Link.id.desc())
        .limit(limit).offset(offset)
    ).all()
    return [_to_out(r) for r in rows]


@app.get("/api/links/{code}", response_model=LinkOut, tags=["links"])
def get_link(code: str, db: Session = Depends(get_db)) -> LinkOut:
    link = db.scalar(select(Link).where(Link.code == code))
    if link is None:
        raise HTTPException(status_code=404, detail="unknown short code")
    return _to_out(link)


@app.delete("/api/links/{code}", status_code=204, tags=["links"])
def delete_link(code: str, db: Session = Depends(get_db)) -> None:
    result = db.execute(
        delete(Link).where(Link.code == code).execution_options(synchronize_session=False)
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="unknown short code")
    log.info("deleted link code=%s", code)


@app.get("/api/stats", response_model=StatsOut, tags=["links"])
def stats(db: Session = Depends(get_db)) -> StatsOut:
    total_links = db.scalar(select(func.count(Link.id))) or 0
    total_hits = db.scalar(select(func.coalesce(func.sum(Link.hits), 0))) or 0
    return StatsOut(total_links=int(total_links), total_hits=int(total_hits))


# --------------------------------------------------------------------------
# The redirect. Registered LAST so it can never shadow a real route.
# --------------------------------------------------------------------------

@app.get("/{code}", include_in_schema=False, tags=["links"])
def follow(
    code: str = Path(pattern=r"^[A-Za-z0-9_-]{1,32}$"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Resolve a short code and bump its counter in one statement."""
    target = db.execute(
        update(Link)
        .where(Link.code == code)
        .values(hits=Link.hits + 1, last_hit_at=func.now())
        .returning(Link.target_url)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()
    db.commit()

    if target is None:
        raise HTTPException(status_code=404, detail="unknown short code")

    # 307, not 301 — a cached permanent redirect makes a link impossible to fix.
    return RedirectResponse(url=target, status_code=307)
