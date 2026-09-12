import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session
from jose import jwt

from app.deps import get_session
from app.config import GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, SECRET_KEY, ALGORITHM
from app.models.github_user import GitHubUser

router = APIRouter(prefix="/api/auth/github", tags=["GitHub 登录"])

# 前端地址（登录成功后跳转）
# 注意：默认值曾误指向模板作者的站点 boke.hiromu.top；NAS 容器已用环境变量覆盖，
# 这里同步修正默认值，避免裸跑（本地/新环境）时把用户跳到别人的站。
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "https://neutronstar.fun")


@router.get("/login")
def github_login():
    """跳转到 GitHub 授权页"""
    if not GITHUB_CLIENT_ID:
        raise HTTPException(500, "未配置 GITHUB_CLIENT_ID")
    url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&scope=read:user"
    )
    return RedirectResponse(url)


@router.get("/callback")
def github_callback(
    code: str,
    request: Request,
    session: Session = Depends(get_session),
):
    """GitHub 回调：用 code 换 token → 获取用户信息 → 生成 JWT"""
    # 1. code 换 access_token
    token_resp = httpx.post(
        "https://github.com/login/oauth/access_token",
        json={
            "client_id": GITHUB_CLIENT_ID,
            "client_secret": GITHUB_CLIENT_SECRET,
            "code": code,
        },
        headers={"Accept": "application/json"},
        timeout=10,
    )
    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(400, "GitHub 授权失败")

    # 2. 获取用户信息
    user_resp = httpx.get(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        timeout=10,
    )
    if user_resp.status_code != 200:
        raise HTTPException(400, "获取 GitHub 用户信息失败")
    gh_user = user_resp.json()

    # 3. 查找或创建 github_user
    existing = session.exec(
        __import__("sqlmodel", fromlist=["select"]).select(GitHubUser).where(
            GitHubUser.github_id == gh_user["id"]
        )
    ).first()

    if existing:
        existing.login = gh_user["login"]
        existing.avatar = gh_user.get("avatar_url", "")
        existing.bio = gh_user.get("bio") or ""
        session.add(existing)
        session.commit()
        session.refresh(existing)
        db_user = existing
    else:
        db_user = GitHubUser(
            github_id=gh_user["id"],
            login=gh_user["login"],
            avatar=gh_user.get("avatar_url", ""),
            bio=gh_user.get("bio") or "",
        )
        session.add(db_user)
        session.commit()
        session.refresh(db_user)

    # 4. 签发 JWT
    token = jwt.encode(
        {"sub": str(db_user.id), "login": db_user.login, "type": "github"},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    # 5. 重定向回前端统一回调页，把 token 带上（通过 query param）
    redirect_url = f"{FRONTEND_ORIGIN}/auth/callback?token={token}"
    return RedirectResponse(redirect_url)


@router.get("/me")
def get_me(
    request: Request,
    session: Session = Depends(get_session),
):
    """获取当前登录的 GitHub 用户信息"""
    user = _get_github_user(request, session)
    return {
        "id": user.id,
        "login": user.login,
        "avatar": user.avatar,
        "bio": user.bio,
    }


def _get_github_user(request: Request, session: Session) -> GitHubUser:
    """从 Authorization header 解析 JWT，返回 GitHubUser"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "未登录")
    token = auth[7:]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except Exception:
        raise HTTPException(401, "登录已过期，请重新登录")
    user = session.get(GitHubUser, user_id)
    if not user:
        raise HTTPException(401, "用户不存在")
    return user


def get_github_user_optional(request: Request, session: Session) -> GitHubUser | None:
    """可选登录：未登录返回 None"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        token = auth[7:]
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
        return session.get(GitHubUser, user_id)
    except Exception:
        return None


def require_github_user(request: Request, session: Session) -> GitHubUser:
    """必须登录（P5 点赞等写操作）：未登录/过期直接 401，前端据此提示去登录。"""
    user = get_github_user_optional(request, session)
    if user is None:
        raise HTTPException(401, "请先登录 GitHub")
    return user
