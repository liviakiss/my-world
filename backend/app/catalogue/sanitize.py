import re
from datetime import date
from urllib.parse import urlsplit

HTML_TAG = re.compile(r"<[^>]*>")
WHITESPACE = re.compile(r"\s+")
YEAR = re.compile(r"\b(\d{4})\b")
URL_MAX_LENGTH = 1000


def clean_line(value: object, max_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = WHITESPACE.sub(" ", HTML_TAG.sub(" ", value)).strip()
    return text[:max_length] or None


def clean_text(value: object, max_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = HTML_TAG.sub("", value)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:max_length] or None


def clean_list(values: object, max_items: int = 10, max_length: int = 200) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    for value in values:
        item = clean_line(value, max_length)
        if item and item not in cleaned:
            cleaned.append(item)
        if len(cleaned) == max_items:
            break
    return cleaned


def positive_int(value: object, maximum: int = 100_000) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 < value <= maximum else None


def safe_https_url(url: str, allowed_hosts: set[str]) -> str | None:
    if len(url) > URL_MAX_LENGTH:
        return None
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in allowed_hosts:
        return None
    return url


def parse_iso_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_year(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        year = value
    elif isinstance(value, str) and (match := YEAR.search(value)):
        year = int(match.group(1))
    else:
        return None
    return year if 1000 <= year <= 2100 else None
