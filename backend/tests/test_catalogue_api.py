from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.catalogue.base import CatalogueError, CatalogueItem
from app.catalogue.registry import Catalogue, get_catalogue
from app.main import app
from app.models import DataSource, DatePrecision, MediaType
from tests.helpers import logged_in_client

HOBBIT = CatalogueItem(
    source=DataSource.OPEN_LIBRARY,
    external_id="OL262758W",
    media_type=MediaType.BOOK,
    title="The Hobbit",
    creators=["J.R.R. Tolkien"],
    total_units=310,
    release_date=date(1937, 1, 1),
    release_date_precision=DatePrecision.YEAR,
)


class FakeAdapter:
    source = DataSource.OPEN_LIBRARY

    def __init__(self) -> None:
        self.fetch_calls = 0
        self.fail = False

    def search(self, query: str, media_type: MediaType) -> list[CatalogueItem]:
        if self.fail:
            raise CatalogueError("upstream down: secret internal detail")
        return [HOBBIT]

    def fetch(self, external_id: str, media_type: MediaType) -> CatalogueItem | None:
        self.fetch_calls += 1
        return HOBBIT if external_id == HOBBIT.external_id else None


@pytest.fixture
def fake_adapter():
    adapter = FakeAdapter()
    app.dependency_overrides[get_catalogue] = lambda: Catalogue({MediaType.BOOK: adapter})
    yield adapter
    app.dependency_overrides.pop(get_catalogue, None)


def import_hobbit(client):
    return client.post(
        "/catalogue/import", json={"media_type": "book", "external_id": HOBBIT.external_id}
    )


def test_search_requires_login(fake_adapter):
    response = TestClient(app).get("/catalogue/search", params={"q": "hobbit", "media_type": "book"})

    assert response.status_code == 401


def test_search_returns_results(fake_adapter):
    client = logged_in_client("livia@example.com")

    response = client.get("/catalogue/search", params={"q": "hobbit", "media_type": "book"})

    assert response.status_code == 200
    assert response.json()[0]["title"] == "The Hobbit"
    assert response.json()[0]["release_year"] == 1937


def test_search_query_length_is_limited(fake_adapter):
    client = logged_in_client("livia@example.com")

    too_short = client.get("/catalogue/search", params={"q": "h", "media_type": "book"})
    too_long = client.get("/catalogue/search", params={"q": "h" * 101, "media_type": "book"})

    assert too_short.status_code == too_long.status_code == 422


def test_unconfigured_media_type_returns_503(fake_adapter):
    client = logged_in_client("livia@example.com")

    response = client.get("/catalogue/search", params={"q": "frieren", "media_type": "anime"})

    assert response.status_code == 503


def test_upstream_failure_returns_generic_502(fake_adapter):
    fake_adapter.fail = True
    client = logged_in_client("livia@example.com")

    response = client.get("/catalogue/search", params={"q": "hobbit", "media_type": "book"})

    assert response.status_code == 502
    assert "secret internal detail" not in response.text


def test_import_caches_the_work_and_shares_it(fake_adapter):
    first_user = logged_in_client("first@example.com")
    second_user = logged_in_client("second@example.com")

    first = import_hobbit(first_user)
    second = import_hobbit(second_user)

    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["source"] == "open_library"
    assert fake_adapter.fetch_calls == 1


def test_imported_work_can_be_added_to_the_shelf(fake_adapter):
    client = logged_in_client("livia@example.com")
    work_id = import_hobbit(client).json()["id"]

    response = client.post("/entries", json={"work_id": work_id, "status": "in_progress"})

    assert response.status_code == 201
    assert response.json()["work"]["total_units"] == 310


def test_import_unknown_id_returns_404(fake_adapter):
    client = logged_in_client("livia@example.com")

    response = client.post(
        "/catalogue/import", json={"media_type": "book", "external_id": "OL999999999W"}
    )

    assert response.status_code == 404
