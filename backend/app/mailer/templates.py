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


def mask_email(address: str) -> str:
    name, _, domain = address.partition("@")
    return f"{name[:1]}***@{domain}"


def password_reset(to: str, token: str) -> EmailMessage:
    return EmailMessage(
        to=to,
        subject="Reset your My World password",
        text=(
            "Someone asked to reset the password of your My World account.\n\n"
            "Choose a new password with this link (valid for 30 minutes, works once):\n"
            f"{_link('/reset-password', token)}\n\n"
            "If this was not you, ignore this email: your password stays the same."
            f"{SIGN_OFF}"
        ),
    )


def password_changed(to: str) -> EmailMessage:
    return EmailMessage(
        to=to,
        subject="Your My World password was changed",
        text=(
            "The password of your My World account was just changed.\n\n"
            "If this was you, nothing else to do. If it was not, reset your password "
            "right away with \"Forgot password\" on the login page."
            f"{SIGN_OFF}"
        ),
    )


def confirm_new_email(to: str, token: str) -> EmailMessage:
    return EmailMessage(
        to=to,
        subject="Confirm your new email for My World",
        text=(
            "You asked to use this address for your My World account.\n\n"
            "Confirm it with this link (valid for 1 hour):\n"
            f"{_link('/confirm-email-change', token)}\n\n"
            "If you did not ask for this, ignore this email."
            f"{SIGN_OFF}"
        ),
    )


def email_changed(to: str, new_address: str) -> EmailMessage:
    return EmailMessage(
        to=to,
        subject="Your My World email address was changed",
        text=(
            f"Your My World account now uses {mask_email(new_address)} instead of this address.\n\n"
            "If this was not you, reply to this email or contact us right away."
            f"{SIGN_OFF}"
        ),
    )


def account_deleted(to: str) -> EmailMessage:
    return EmailMessage(
        to=to,
        subject="Your My World account was deleted",
        text=(
            "Your My World account and everything on your shelf have been deleted.\n\n"
            "Thank you for using My World."
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
