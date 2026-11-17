import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.models import DataSource, Entry, EntryStatus, MediaType, Work

TEST_PASSWORD = "correct-horse-battery-staple"


def signup(client: TestClient, email: str, password: str = TEST_PASSWORD):
    return client.post("/auth/signup", json={"email": email, "password": password})


def login(client: TestClient, email: str, password: str = TEST_PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def logged_in_client(email: str) -> TestClient:
    client = TestClient(app)
    signup(client, email)
    login(client, email)
    return client


def add_catalogue_work(
    db, title: str = "A Public Book", media_type: MediaType = MediaType.BOOK, total_units=None
) -> Work:
    work = Work(
        title=title,
        media_type=media_type,
        total_units=total_units,
        source=DataSource.OPEN_LIBRARY,
        external_id=uuid.uuid4().hex,
    )
    db.add(work)
    db.commit()
    return work


def current_user_id(client: TestClient) -> uuid.UUID:
    return uuid.UUID(client.get("/auth/me").json()["id"])


def add_entry(db, user_id: uuid.UUID, work: Work, status: EntryStatus, **fields) -> Entry:
    entry = Entry(user_id=user_id, work_id=work.id, status=status, **fields)
    db.add(entry)
    db.commit()
    return entry
