from tests.helpers import login


def test_login_is_rate_limited_per_client(client):
    responses = [login(client, f"user{i}@example.com") for i in range(11)]

    assert all(r.status_code == 401 for r in responses[:10])
    assert responses[10].status_code == 429
    assert int(responses[10].headers["Retry-After"]) > 0


def test_signup_is_rate_limited_per_client(client):
    statuses = [
        client.post(
            "/auth/signup", json={"email": f"user{i}@example.com", "password": "x" * 12}
        ).status_code
        for i in range(6)
    ]

    assert statuses[:5] == [202] * 5
    assert statuses[5] == 429
