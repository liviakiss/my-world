from typing import Any

import httpx2

from app.catalogue.base import CatalogueError

MAX_RESPONSE_BYTES = 2_000_000
REQUEST_TIMEOUT = httpx2.Timeout(5.0)


def create_client(user_agent: str) -> httpx2.Client:
    return httpx2.Client(
        timeout=REQUEST_TIMEOUT,
        follow_redirects=False,
        headers={"User-Agent": user_agent, "Accept": "application/json"},
    )


def get_json(
    client: httpx2.Client,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    try:
        response = client.get(url, params=params, headers=headers)
    except httpx2.HTTPError as exc:
        raise CatalogueError(f"request failed: {type(exc).__name__}") from exc

    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise CatalogueError(f"unexpected status {response.status_code}")
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise CatalogueError("response too large")

    try:
        data = response.json()
    except ValueError as exc:
        raise CatalogueError("invalid JSON") from exc
    if not isinstance(data, dict):
        raise CatalogueError("unexpected JSON shape")
    return data
