"""P5 回归测试：点赞实名去重（likes 表）+ 评论多态（post / chatter / album）。

覆盖点：
1. 点赞必须登录；重复点赞不会重复计数（真值在 likes 唯一约束上）。
2. 「我的点赞态」接口可按目标类型回填。
3. 评论必须登录；目标用 target_type + target_id，post_id 只在 post 维度同步。
4. 楼中楼回复挂到 parent；跨目标回复被拒。
5. 删除评论：作者本人可删；他人 403；管理员（用户名 JWT）可删。
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_p5.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
from jose import jwt
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from app.config import ALGORITHM, SECRET_KEY
from app.database import engine
from app.main import app
from app.models import Chatter, GitHubUser, Like, User
from app.utils.auth import create_token, hash_password


@pytest.fixture(scope="module")
def client():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        if s.get(Chatter, 1) is None:
            s.add(Chatter(id=1, content="hello world", status="published"))
            s.commit()
    with TestClient(app) as c:
        yield c
    engine.dispose()
    if os.path.exists("_test_p5.db"):
        os.remove("_test_p5.db")


def _mk_github_user(github_id: int, login: str) -> int:
    with Session(engine) as s:
        user = GitHubUser(github_id=github_id, login=login, avatar="", bio="")
        s.add(user)
        s.commit()
        s.refresh(user)
        return user.id


def _gh_token(user_id: int, login: str) -> str:
    return jwt.encode(
        {"sub": str(user_id), "login": login, "type": "github"}, SECRET_KEY, algorithm=ALGORITHM
    )


@pytest.fixture(scope="module")
def gh(client):
    uid = _mk_github_user(1001, "tester")
    return {"id": uid, "headers": {"Authorization": f"Bearer {_gh_token(uid, 'tester')}"}}


@pytest.fixture(scope="module")
def other_gh(client):
    uid = _mk_github_user(1002, "stranger")
    return {"id": uid, "headers": {"Authorization": f"Bearer {_gh_token(uid, 'stranger')}"}}


@pytest.fixture(scope="module")
def admin_headers(client):
    with Session(engine) as s:
        if s.exec(select(User).where(User.username == "p5admin")).first() is None:
            s.add(User(username="p5admin", hashed_password=hash_password("pwd"), is_admin=True))
            s.commit()
    return {"Authorization": f"Bearer {create_token({'sub': 'p5admin', 'admin': True})}"}


# ---------------- 点赞 ----------------

def test_like_requires_login(client):
    r = client.post("/api/likes/toggle", json={"target_type": "chatter", "target_id": 1})
    assert r.status_code == 401


def test_like_rejects_unknown_target(client, gh):
    r = client.post(
        "/api/likes/toggle",
        json={"target_type": "nope", "target_id": 1},
        headers=gh["headers"],
    )
    assert r.status_code == 400


def test_like_toggle_is_idempotent(client, gh):
    url = "/api/likes/toggle"
    body = {"target_type": "chatter", "target_id": 1}

    first = client.post(url, json=body, headers=gh["headers"]).json()
    assert first == {"liked": True, "likes": 1}

    # 再点一次 = 取消，而不是把计数加成 2
    second = client.post(url, json=body, headers=gh["headers"]).json()
    assert second == {"liked": False, "likes": 0}

    third = client.post(url, json=body, headers=gh["headers"]).json()
    assert third == {"liked": True, "likes": 1}

    # 真值表里只有一行（唯一约束生效）
    with Session(engine) as s:
        rows = s.exec(
            select(Like).where(Like.target_type == "chatter", Like.target_id == 1)
        ).all()
        assert len(rows) == 1


def test_my_likes_returns_ids(client, gh):
    r = client.get("/api/likes/mine?target_type=chatter", headers=gh["headers"])
    assert r.status_code == 200
    assert r.json()["ids"] == [1]

    # 未登录不报错，返回空列表
    r2 = client.get("/api/likes/mine?target_type=chatter")
    assert r2.status_code == 200
    assert r2.json()["ids"] == []


# ---------------- 评论多态 ----------------

def test_comment_requires_login(client):
    r = client.post(
        "/api/comments",
        json={"target_type": "chatter", "target_id": 1, "content": "hi"},
    )
    assert r.status_code == 401


def test_create_and_list_polymorphic_comment(client, gh):
    r = client.post(
        "/api/comments",
        json={"target_type": "chatter", "target_id": 1, "content": "第一条说说评论"},
        headers=gh["headers"],
    )
    assert r.status_code == 200
    data = r.json()
    assert data["target_type"] == "chatter" and data["target_id"] == 1
    assert data["post_id"] is None  # 非文章维度不同步 post_id

    listed = client.get("/api/comments?target_type=chatter&target_id=1").json()
    assert len(listed) == 1 and listed[0]["content"] == "第一条说说评论"

    # 回复（楼中楼）
    reply = client.post(
        "/api/comments",
        json={
            "target_type": "chatter",
            "target_id": 1,
            "parent_id": data["id"],
            "content": "回复一下",
        },
        headers=gh["headers"],
    )
    assert reply.status_code == 200

    listed2 = client.get("/api/comments?target_type=chatter&target_id=1").json()
    assert len(listed2) == 1
    assert len(listed2[0]["replies"]) == 1
    assert listed2[0]["replies"][0]["content"] == "回复一下"

    # 跨目标回复要被拒
    bad = client.post(
        "/api/comments",
        json={
            "target_type": "post",
            "target_id": 999,
            "parent_id": data["id"],
            "content": "乱回复",
        },
        headers=gh["headers"],
    )
    assert bad.status_code == 400


def test_comment_target_required(client, gh):
    r = client.post("/api/comments", json={"content": "没有目标"}, headers=gh["headers"])
    assert r.status_code == 400


def test_delete_comment_permissions(client, gh, other_gh, admin_headers):
    created = client.post(
        "/api/comments",
        json={"target_type": "chatter", "target_id": 1, "content": "待删除"},
        headers=gh["headers"],
    ).json()

    # 别人不能删
    assert client.delete(f"/api/comments/{created['id']}", headers=other_gh["headers"]).status_code == 403
    # 未登录不能删
    assert client.delete(f"/api/comments/{created['id']}").status_code == 401
    # 作者本人可删
    assert client.delete(f"/api/comments/{created['id']}", headers=gh["headers"]).status_code == 200


def test_admin_can_delete_others_comment(client, gh, admin_headers):
    created = client.post(
        "/api/comments",
        json={"target_type": "chatter", "target_id": 1, "content": "管理员删我"},
        headers=gh["headers"],
    ).json()
    assert client.delete(f"/api/comments/{created['id']}", headers=admin_headers).status_code == 200
