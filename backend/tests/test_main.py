def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_endpoint(client):
    response = client.get("/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["schema"] == "ok"
    assert payload["checks"]["database"] == "ok"
    assert payload["checks"]["worker_heartbeat"] == "ok"


def test_missing_client_session_is_rejected(client):
    response = client.get("/api/documents")
    assert response.status_code == 400
    payload = response.json()
    assert "X-Client-Session" in payload["error"]
    assert payload["code"] == "INVALID_CLIENT_SESSION"
    assert payload["request_id"]
