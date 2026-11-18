import pytest
from pydantic import ValidationError

from app.config import Settings

BASE = {
    "database_url": "postgresql+psycopg://u:p@h/db",
    "jwt_secret": "j" * 40,
    "ip_hash_secret": "i" * 40,
}


def test_production_refuses_to_start_without_real_email():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production", email_provider="console", **BASE)


def test_resend_needs_an_api_key():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, email_provider="resend", **BASE)
