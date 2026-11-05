from fastapi.testclient import TestClient

TEST_PASSWORD = "correct-horse-battery-staple"


def signup(client: TestClient, email: str, password: str = TEST_PASSWORD):
    return client.post("/auth/signup", json={"email": email, "password": password})


def login(client: TestClient, email: str, password: str = TEST_PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})
