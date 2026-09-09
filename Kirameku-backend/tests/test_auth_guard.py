"""T0 加固：管理端写接口的鉴权必须落库校验。

历史事件：get_current_user 只解 JWT 不查库，导致
「签名有效但用户已删除 / 非管理员」也能调用写接口。
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_guard.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from app.database import engine
from app.main import app
from app.models import User
from app.utils.auth import create_token, hash_password


@pytest.fixture(scope="module")
def client():
    SQLModel.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c
    engine.dispose()
    if os.path.exists("_test_guard.db"):
        os.remove("_test_guard.db")


def _mk_user(username: str, is_admin: bool) -> None:
    with Session(engine) as s:
        existing = s.get(User, username)
        if existing is None:
            s.add(
                User(
                    username=username,
                    hashed_password=hash_password("pwd"),
                    is_admin=is_admin,
                )
            )
            s.commit()


@pytest.fixture(scope="module")
def admin_token(client):
    _mk_user("admin01", True)
    return create_token({"sub": "admin01", "admin": True})


@pytest.fixture(scope="module")
def plain_token(client):
    _mk_user("plain01", False)
    return create_token({"sub": "plain01", "admin": False})


def test_missing_token_rejected(client):
    r = client.get("/api/auth/me")
    assert r.status_code in (401, 403)


def test_invalid_signature_rejected(client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.token"})
    assert r.status_code == 401


def test_token_of_deleted_user_rejected(client):
    """签名有效，但库里没这个用户 → 必须 401。"""
    token = create_token({"sub": "ghost-user", "admin": True})
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_non_admin_rejected(client, plain_token):
    """签名有效且用户存在，但不是管理员 → 必须 403。"""
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {plain_token}"})
    assert r.status_code == 403


def test_admin_allowed(client, admin_token):
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert r.json()["data"]["username"] == "admin01"


def test_visitor_delete_requires_auth(client):
    """访客删除接口历史上完全没鉴权。"""
    r = client.delete("/api/visitors/1")
    assert r.status_code in (401, 403)

    r = client.delete("/api/visitors")
    assert r.status_code in (401, 403)


def test_visitor_delete_allowed_for_admin(client, admin_token):
    r = client.delete("/api/visitors/1", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
