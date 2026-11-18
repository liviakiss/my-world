from datetime import date
from urllib.parse import quote

from app.config import settings
from app.mailer.sender import EmailMessage
from app.models import NotificationKind

SIGN_OFF = "\n\n— My World: Track & Finish"


def _one_line(text: str, max_length: int = 150) -> str:
    return " ".join(text.split())[:max_length]


def _link(path: str, token: str) -> str:
    return f"{settings.frontend_url}{path}?token={quote(token)}"


def verify_email(to: str, token: str) -> EmailMessage:
    return EmailMessage(
        to=to,
        subject="Confirm your email for My World",
        text=(
            "Welcome to My World!\n\n"
            "Confirm your email address with this link (valid for 24 hours):\n"
            f"{_link('/verify-email', token)}\n\n"
            "If you did not sign up, you can ignore this email."
            f"{SIGN_OFF}"
        ),
    )


def signup_attempt_for_existing_account(to: str) -> EmailMessage:
    return EmailMessage(
        to=to,
        subject="Someone tried to sign up with your email",
        text=(
            "Someone just tried to create a My World account with this email address, "
            "but you already have one.\n\n"
            "If this was you, simply log in. If you forgot your password, "
            "use \"Forgot password\" on the login page.\n\n"
            "If it was not you, no action is needed: your account is unchanged."
            f"{SIGN_OFF}"
        ),
    )


def _when(release_date: date) -> str:
    return release_date.strftime("%A, %d %B %Y")


def release_reminder(
    to: str, kind: NotificationKind, title: str, label: str, release_date: date
) -> EmailMessage:
    title = _one_line(title)
    label = _one_line(label)
    subjects = {
        NotificationKind.ANNOUNCED: f"New date: {title} — {label}",
        NotificationKind.DAY_BEFORE: f"Tomorrow: {title} — {label}",
        NotificationKind.RELEASE_DAY: f"Out today: {title} — {label}",
    }
    intros = {
        NotificationKind.ANNOUNCED: f"A release date was announced for {title}.",
        NotificationKind.DAY_BEFORE: f"{title} has something new coming tomorrow.",
        NotificationKind.RELEASE_DAY: f"{title} has something new out today!",
    }
    return EmailMessage(
        to=to,
        subject=_one_line(subjects[kind], 200),
        text=(
            f"{intros[kind]}\n\n"
            f"{label}\n{_when(release_date)}\n\n"
            "You get this because you follow it on My World. "
            "You can turn reminders off in your notification settings."
            f"{SIGN_OFF}"
        ),
    )
