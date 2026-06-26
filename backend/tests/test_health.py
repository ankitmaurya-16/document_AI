def test_health_ok(client):
    rv = client.get("/api/v1/health")
    assert rv.status_code == 200


def test_request_id_echoed(client):
    rv = client.get("/api/v1/health", headers={"X-Request-ID": "abc-123"})
    assert rv.headers.get("X-Request-ID") == "abc-123"
