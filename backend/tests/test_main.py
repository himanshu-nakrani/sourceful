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
    assert response.status_code == 401
    payload = response.json()
    assert payload["error"] == "Authentication required. Provide auth token or X-Client-Session header."
    assert payload["code"] == "AUTH_REQUIRED"
    assert payload["request_id"]
