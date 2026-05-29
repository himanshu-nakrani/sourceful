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


def test_default_superuser_seeded(client):
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin123"},
    )
    assert login.status_code == 200
    payload = login.json()
    assert payload["email"] == "admin@example.com"
    assert payload["role"] == "admin"


def test_admin_user_list_and_update(client):
    admin = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin123"},
    )
    assert admin.status_code == 200
    second = client.post(
        "/api/auth/signup",
        json={"email": "member@example.com", "password": "strong-pass-123"},
    )
    assert second.status_code == 201
    member = second.json()
    client.post("/api/auth/logout")

    relogin = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin123"},
    )
    assert relogin.status_code == 200

    users = client.get("/api/users")
    assert users.status_code == 200
    assert len(users.json()["users"]) >= 2

    updated = client.patch(f"/api/users/{member['id']}", json={"is_active": False})
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False

    superuser = next(
        user for user in users.json()["users"] if user["email"] == "admin@example.com"
    )
    protected = client.patch(f"/api/users/{superuser['id']}", json={"role": "user"})
    assert protected.status_code == 400


def test_oauth_creates_new_user(client):
    """OAuth login for a brand-new email creates an oauth_no_password user."""
    import asyncio

    from backend.auth import authenticate_or_create_oauth_user

    user = asyncio.run(authenticate_or_create_oauth_user("fresh-oauth@example.com"))
    assert user is not None
    assert user["email"] == "fresh-oauth@example.com"


def test_oauth_allows_existing_oauth_account(client):
    """A second OAuth login for the same email returns the same user."""
    import asyncio

    from backend.auth import authenticate_or_create_oauth_user

    first = asyncio.run(authenticate_or_create_oauth_user("repeat-oauth@example.com"))
    second = asyncio.run(authenticate_or_create_oauth_user("repeat-oauth@example.com"))
    assert first["id"] == second["id"]


def test_oauth_rejects_password_account_with_conflict(client):
    """Fix #3: OAuth must not merge into a local-password account."""
    import asyncio

    import pytest

    from backend.auth import authenticate_or_create_oauth_user, create_user

    asyncio.run(create_user("haspassword@example.com", "strong-pass-123"))
    with pytest.raises(ValueError) as exc:
        asyncio.run(authenticate_or_create_oauth_user("haspassword@example.com"))
    assert str(exc.value) == "OAUTH_ACCOUNT_CONFLICT"


def test_oauth_disabled_account_reports_disabled(client):
    """A disabled account must raise ACCOUNT_DISABLED, not the conflict code."""
    import asyncio

    import pytest

    from backend.auth import authenticate_or_create_oauth_user
    from backend.database import execute

    # Seed a disabled OAuth account (no real password set).
    asyncio.run(authenticate_or_create_oauth_user("disabled-oauth@example.com"))
    asyncio.run(
        execute(
            "UPDATE users SET is_active = 0 WHERE email = ?",
            ("disabled-oauth@example.com",),
        )
    )
    with pytest.raises(ValueError) as exc:
        asyncio.run(authenticate_or_create_oauth_user("disabled-oauth@example.com"))
    assert str(exc.value) == "ACCOUNT_DISABLED"
