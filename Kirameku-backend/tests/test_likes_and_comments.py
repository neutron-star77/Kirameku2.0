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
from app.models import Chatter, ChatterComment, GitHubUser, Like, User
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


# ---------------- 后台列表（按内容类型过滤 + 带 target 信息）----------------

def test_admin_list_requires_admin(client):
    assert client.get("/api/comments/admin").status_code in (401, 403)


def test_admin_list_filters_by_target_and_returns_target_info(client, gh, admin_headers):
    """后台评论列表要能按 post / chatter / album 分开看，并带上所属内容标题。"""
    chatter_comment = client.post(
        "/api/comments",
        json={"target_type": "chatter", "target_id": 1, "content": "后台过滤用-说说"},
        headers=gh["headers"],
    ).json()
    post_comment = client.post(
        "/api/comments",
        json={"target_type": "post", "target_id": 999, "content": "后台过滤用-文章"},
        headers=gh["headers"],
    ).json()

    only_chatter = client.get(
        "/api/comments/admin?target_type=chatter", headers=admin_headers
    ).json()
    ids = [item["id"] for item in only_chatter]
    assert chatter_comment["id"] in ids
    assert post_comment["id"] not in ids
    # target 信息（说说的内容摘要 + 前台链接）
    target = next(item["target"] for item in only_chatter if item["id"] == chatter_comment["id"])
    assert target["type"] == "chatter"
    assert target["url"] == "/moments"
    assert target["title"]

    only_post = client.get("/api/comments/admin?target_type=post", headers=admin_headers).json()
    post_targets = [item["target"]["type"] for item in only_post]
    assert post_targets and set(post_targets) == {"post"}

    # 收尾：删掉两条测试评论
    assert client.delete(f"/api/comments/{chatter_comment['id']}", headers=admin_headers).status_code == 200
    assert client.delete(f"/api/comments/{post_comment['id']}", headers=admin_headers).status_code == 200


def test_chatter_admin_list_has_target(client, gh, admin_headers):
    """说说评论走独立表，后台列表也要带 target 信息。"""
    created = client.post(
        "/api/chatters/comments",
        json={"chatter_id": 1, "content": "说说评论-后台列表"},
        headers=gh["headers"],
    ).json()

    rows = client.get("/api/chatters/comments/admin", headers=admin_headers).json()
    row = next(item for item in rows if item["id"] == created["id"])
    assert row["target"]["type"] == "chatter"
    assert row["target"]["id"] == 1

    # 删除时应连带子回复并回退 comments_count
    reply = client.post(
        "/api/chatters/comments",
        json={"chatter_id": 1, "parent_id": created["id"], "content": "子回复"},
        headers=gh["headers"],
    ).json()
    assert reply["parent_id"] == created["id"]
    assert client.delete(
        f"/api/chatters/comments/{created['id']}", headers=admin_headers
    ).status_code == 200

    with Session(engine) as s:
        assert s.get(ChatterComment, reply["id"]) is None
        chatter = s.get(Chatter, 1)
        assert chatter.comments_count == 0
