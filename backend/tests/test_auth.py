"""
Test autenticazione — /auth/login + /auth/config.
"""
import pytest
from httpx import AsyncClient

from tests.conftest import USER_EMAIL, ADMIN_EMAIL
import app.excel_store as store
from app.excel_store import settings
from app.security import hash_password

pytestmark = pytest.mark.anyio


async def test_health(client: AsyncClient):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_auth_config(client: AsyncClient):
    r = await client.get("/auth/config")
    assert r.status_code == 200
    data = r.json()
    # AuthConfig usa "provider" (non "auth_provider")
    assert "provider" in data
    assert "entra_enabled" in data


async def test_backdoor_login_all_users(client: AsyncClient):
    """La backdoor con BACKDOOR_PASSWORD funziona per qualsiasi utente attivo."""
    backdoor_pwd = settings.backdoor_password
    r = await client.post(
        "/auth/login",
        data={"username": USER_EMAIL, "password": backdoor_pwd},
    )
    assert r.status_code == 200, r.text
    assert "access_token" in r.json()


async def test_wrong_password(client: AsyncClient):
    r = await client.post(
        "/auth/login",
        data={"username": USER_EMAIL, "password": "wrong-password-xyz"},
    )
    assert r.status_code == 401


async def test_unknown_user(client: AsyncClient):
    r = await client.post(
        "/auth/login",
        data={"username": "nobody@example.com", "password": "whatever"},
    )
    assert r.status_code == 401


async def test_inactive_user(client: AsyncClient):
    """Utente con is_active=NO non può fare login."""
    store.STORE["users"][USER_EMAIL]["is_active"] = "NO"
    backdoor_pwd = settings.backdoor_password
    r = await client.post(
        "/auth/login",
        data={"username": USER_EMAIL, "password": backdoor_pwd},
    )
    assert r.status_code == 401


async def test_protected_endpoint_no_token(client: AsyncClient):
    r = await client.get("/cv/me")
    assert r.status_code == 401


async def test_protected_endpoint_with_token(user_client: AsyncClient):
    r = await user_client.get("/cv/me")
    assert r.status_code == 200
