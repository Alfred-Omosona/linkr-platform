"""Test fixtures.

By default the suite runs against in-memory SQLite so `pytest` works on a bare
machine with no database — that keeps the CI unit-test stage fast and
dependency-free.

To run the same suite against real Postgres (recommended as a separate
integration stage in CI once compose exists):

    LINKR_TEST_DATABASE_URL=postgresql+psycopg://linkr:linkr@localhost:5432/linkr_test pytest
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app

TEST_DATABASE_URL = os.getenv("LINKR_TEST_DATABASE_URL", "sqlite://")


@pytest.fixture()
def client():
    kwargs = {}
    if TEST_DATABASE_URL.startswith("sqlite"):
        # One shared in-memory database for the whole test, across threads.
        kwargs = {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }

    engine = create_engine(TEST_DATABASE_URL, **kwargs)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
