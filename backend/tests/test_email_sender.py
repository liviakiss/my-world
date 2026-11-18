import json

import httpx2
import pytest

from app.mailer.sender import EmailError, EmailMessage, ResendEmailSender

MESSAGE = EmailMessage(to="fan@example.com", subject="Hello", text="Body")


def sender_with(status: int, seen: list[httpx2.Request]) -> ResendEmailSender:
    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(status, json={"id": "abc"})

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    return ResendEmailSender(client, api_key="re_secret", sender="My World <hello@example.com>")


def test_resend_receives_the_message_with_the_key_in_a_header():
    seen: list[httpx2.Request] = []

    sender_with(200, seen).send(MESSAGE)

    request = seen[0]
    assert request.headers["Authorization"] == "Bearer re_secret"
    assert "re_secret" not in str(request.url)
    assert json.loads(request.content) == {
        "from": "My World <hello@example.com>",
        "to": ["fan@example.com"],
        "subject": "Hello",
        "text": "Body",
    }


def test_provider_errors_become_email_errors():
    with pytest.raises(EmailError):
        sender_with(500, []).send(MESSAGE)
