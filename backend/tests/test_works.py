from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import add_catalogue_work, logged_in_client

CUSTOM_BOOK = {
    "media_type": "book",
    "title": "  My Self-Published Novel  ",
    "creators": ["A. Writer"],
    "genres": ["Fantasy"],
    "total_units": 320,
}


def test_creating_a_work_requires_login():
    response = TestClient(app).post("/works", json=CUSTOM_BOOK)

    assert response.status_code == 401


def test_custom_work_is_created_as_custom_and_trimmed():
    client = logged_in_client("livia@example.com")

    response = client.post("/works", json=CUSTOM_BOOK)

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "My Self-Published Novel"
    assert body["source"] == "custom"
    assert body["cover_url"] is None


def test_unknown_fields_are_rejected():
    client = logged_in_client("livia@example.com")

    response = client.post(
        "/works", json={**CUSTOM_BOOK, "created_by_user_id": None, "cover_url": "https://x.y/a.png"}
    )

    assert response.status_code == 422


def test_blank_title_and_oversized_lists_are_rejected():
    client = logged_in_client("livia@example.com")

    blank_title = client.post("/works", json={**CUSTOM_BOOK, "title": "   "})
    too_many_genres = client.post("/works", json={**CUSTOM_BOOK, "genres": ["g"] * 11})

    assert blank_title.status_code == 422
    assert too_many_genres.status_code == 422


def test_custom_works_are_private_to_their_creator():
    owner = logged_in_client("owner@example.com")
    other = logged_in_client("other@example.com")
    work_id = owner.post("/works", json=CUSTOM_BOOK).json()["id"]

    assert owner.get(f"/works/{work_id}").status_code == 200
    assert other.get(f"/works/{work_id}").status_code == 404


def test_catalogue_works_are_visible_to_everyone(db):
    work = add_catalogue_work(db)
    client = logged_in_client("livia@example.com")

    response = client.get(f"/works/{work.id}")

    assert response.status_code == 200
    assert response.json()["source"] == "open_library"
