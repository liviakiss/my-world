import os
from pathlib import Path

from dotenv import dotenv_values

BACKEND_DIR = Path(__file__).resolve().parents[1]
_local_env = dotenv_values(BACKEND_DIR / ".env")

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or _local_env.get("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError("TEST_DATABASE_URL is not set. Tests never run against the real database.")
if TEST_DATABASE_URL == _local_env.get("DATABASE_URL"):
    raise RuntimeError("TEST_DATABASE_URL must point at a separate test database.")

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["ENVIRONMENT"] = "test"
os.environ["JWT_SECRET"] = "test-only-jwt-secret-that-is-long-enough-1234567890"
os.environ["IP_HASH_SECRET"] = "test-only-ip-hash-secret-that-is-long-enough-123456"
os.environ["COOKIE_SECURE"] = "false"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

import app.models  # noqa: E402, F401
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security.rate_limit import reset_rate_limits  # noqa: E402

@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    Base.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    yield


@pytest.fixture(autouse=True)
def clean_state():
    reset_rate_limits()
    yield
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()

