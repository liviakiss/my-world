import re
import uuid

from fastapi.testclient import TestClient

from app.mailer.sender import EmailError, EmailMessage
from app.main import app
from app.models import DataSource, Entry, EntryStatus, MediaType, User, Work

TEST_PASSWORD = "correct-horse-battery-staple"
TOKEN_IN_LINK = re.compile(r"token=([A-Za-z0-9_%-]+)")


class FakeEmailSender:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[EmailMessage] = []
        self.fail = fail

    def send(self, message: EmailMessage) -> None:
        if self.fail:
            raise EmailError("provider down")
        self.sent.append(message)

    def to(self, address: str) -> list[EmailMessage]:
        return [message for message in self.sent if message.to == address]


def token_from(message: EmailMessage) -> str:
    match = TOKEN_IN_LINK.search(message.text)
    assert match is not None, "no link with a token in this email"
    return match.group(1)


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


def mark_verified(db, email: str) -> None:
    user = db.query(User).filter(User.email == email).one()
    user.is_email_verified = True
    db.commit()
