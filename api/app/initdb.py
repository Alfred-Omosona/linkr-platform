"""Create the schema. Idempotent — safe to run on every deploy.

    python -m app.initdb

Waits for Postgres to accept connections before doing anything, so it can be
used as an init container / pre-deploy job without racing the database.

NOTE FOR DEVOPS: this is a v0.1 stopgap. It creates tables but cannot ALTER
them, so it stops being enough the moment we change a column. DEV-4 tracks
replacing it with Alembic; please wire the migration step into the pipeline as
its own stage (not into the app's startup) so a failed migration fails the
deploy instead of crash-looping the app.
"""

import logging
import sys
import time

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .db import Base, engine
from .models import Link  # noqa: F401 — imported so it registers on Base.metadata

log = logging.getLogger("linkr.initdb")

WAIT_SECONDS = 60
RETRY_DELAY = 2


def wait_for_db(timeout: int = WAIT_SECONDS) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            log.info("database is accepting connections")
            return
        except SQLAlchemyError as exc:
            last_error = exc
            log.info("database not ready yet, retrying in %ss", RETRY_DELAY)
            time.sleep(RETRY_DELAY)
    raise SystemExit(f"database not reachable after {timeout}s: {last_error}")


def main() -> None:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
    wait_for_db()
    Base.metadata.create_all(engine)
    log.info("schema is up to date")


if __name__ == "__main__":
    sys.exit(main())
