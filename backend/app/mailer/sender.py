import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import httpx2

from app.catalogue.http import create_client
from app.config import settings

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"


class EmailError(Exception):
    pass


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None: ...


class ConsoleEmailSender:
    def send(self, message: EmailMessage) -> None:
        logger.info("Email to %s\nSubject: %s\n\n%s", message.to, message.subject, message.text)


class ResendEmailSender:
    def __init__(self, client: httpx2.Client, api_key: str, sender: str) -> None:
        self.client = client
        self.sender = sender
        self._auth = {"Authorization": f"Bearer {api_key}"}

    def send(self, message: EmailMessage) -> None:
        payload = {
            "from": self.sender,
            "to": [message.to],
            "subject": message.subject,
            "text": message.text,
        }
        try:
            response = self.client.post(RESEND_URL, json=payload, headers=self._auth)
        except httpx2.HTTPError as exc:
            raise EmailError(f"request failed: {type(exc).__name__}") from exc
        if response.status_code >= 300:
            raise EmailError(f"unexpected status {response.status_code}")


@lru_cache
def get_email_sender() -> EmailSender:
    if settings.email_provider == "resend" and settings.resend_api_key is not None:
        client = create_client(settings.catalogue_user_agent)
        return ResendEmailSender(client, settings.resend_api_key.get_secret_value(), settings.email_from)
    return ConsoleEmailSender()


def send_quietly(sender: EmailSender, message: EmailMessage) -> None:
    try:
        sender.send(message)
    except EmailError as exc:
        logger.warning("Email could not be sent: %s", exc)
