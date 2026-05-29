"""Canonical derivation of anonymous owner scopes.

Fix #5: anonymous clients are scoped by the ``X-Client-Session`` header. The
raw header value is HMAC-signed so the resulting ``owner_id`` is deterministic
for a given header but cannot be guessed or forged by another client who does
not know the signing secret.

This module is the single source of truth for that derivation so routers,
services, migrations, and tests never reconstruct the ``anon:`` scope by hand.
"""

from __future__ import annotations

import hashlib
import hmac

from backend.settings import settings

ANON_PREFIX = "anon:"


def _resolve_anon_secret() -> bytes:
    """Resolve the HMAC secret used to sign anonymous session scopes.

    Order of preference:
    1. ``ANON_SESSION_SECRET`` — the dedicated, stable secret (required in
       production so anon scoping is isolated from admin-password rotation).
    2. ``DEFAULT_SUPERUSER_PASSWORD`` — local-dev/SQLite fallback only, so the
       app keeps working out of the box without extra config.

    There is intentionally no baked-in constant fallback: a shared default key
    would let any misconfigured deployment forge anonymous scopes. In
    production (``DATABASE_URL`` set) a dedicated secret is mandatory.
    """
    if settings.anon_session_secret:
        return settings.anon_session_secret.encode("utf-8")
    if settings.using_postgres:
        raise RuntimeError(
            "ANON_SESSION_SECRET must be set when DATABASE_URL is configured. "
            "It signs anonymous session scopes and must be a dedicated, stable "
            "secret independent of the superuser password."
        )
    if settings.default_superuser_password:
        return settings.default_superuser_password.encode("utf-8")
    raise RuntimeError(
        "Set ANON_SESSION_SECRET (or DEFAULT_SUPERUSER_PASSWORD for local dev) "
        "to sign anonymous session scopes."
    )


_ANON_SESSION_SECRET = _resolve_anon_secret()


def sign_client_session(client_session: str) -> str:
    """Return the 24-char HMAC digest for a raw X-Client-Session value."""
    return hmac.new(
        _ANON_SESSION_SECRET, client_session.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:24]


def anon_owner_id(client_session: str) -> str:
    """Derive the anonymous ``owner_id`` for a raw X-Client-Session value."""
    return f"{ANON_PREFIX}{sign_client_session(client_session)}"
