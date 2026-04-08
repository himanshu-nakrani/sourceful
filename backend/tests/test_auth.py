def test_signup_login_me_logout_flow(client):
    signup = client.post(
        "/api/auth/signup",
        json={"email": "user@example.com", "password": "strong-pass-123"},
    )
    assert signup.status_code == 201
    payload = signup.json()
    assert payload["email"] == "user@example.com"
    assert payload["role"] == "user"

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "user@example.com"

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200

    me_after = client.get("/api/auth/me")
    assert me_after.status_code == 401

    login = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "strong-pass-123"},
    )
    assert login.status_code == 200
    assert login.json()["email"] == "user@example.com"


def test_admin_user_list_and_update(client):
    admin = client.post(
        "/api/auth/signup",
        json={"email": "admin@example.com", "password": "strong-pass-123"},
    )
    assert admin.status_code == 201
    admin_user = admin.json()

    no_admin = client.get("/api/users")
    assert no_admin.status_code == 403

    client.post("/api/auth/logout")
    second = client.post(
        "/api/auth/signup",
        json={"email": "member@example.com", "password": "strong-pass-123"},
    )
    assert second.status_code == 201
    member = second.json()
    client.post("/api/auth/logout")

    # Promote admin directly for test setup.
    from backend.database import execute
    import asyncio

    asyncio.run(execute("UPDATE users SET role = 'admin' WHERE id = ?", (admin_user["id"],)))

    relogin = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "strong-pass-123"},
    )
    assert relogin.status_code == 200

    users = client.get("/api/users")
    assert users.status_code == 200
    assert len(users.json()["users"]) >= 2

    updated = client.patch(f"/api/users/{member['id']}", json={"is_active": False})
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False
