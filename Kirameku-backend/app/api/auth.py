from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlmodel import Session, select

from app.deps import get_session
from app.models import User, LoginLog
from app.schemas import LoginRequest
from app.config import ACCESS_TOKEN_EXPIRE_HOURS
from app.deps import get_current_user
from app.utils.auth import verify_password, create_token, hash_password

router = APIRouter(prefix="/api/auth", tags=["认证"])


def _client_ip(request: Request) -> str:
    """取真实客户端 IP：CF Tunnel 下优先 CF-Connecting-IP / X-Forwarded-For。"""
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


def _parse_ua(ua: str) -> tuple[str, str]:
    """从 User-Agent 粗解析 (操作系统, 浏览器)，不引第三方依赖。"""
    ua = ua or ""
    system = "未知"
    if "Windows NT 10.0" in ua:
        system = "Windows"
    elif "Windows" in ua:
        system = "Windows"
    elif "Android" in ua:
        system = "Android"
    elif "iPhone" in ua or "iPad" in ua or "iOS" in ua:
        system = "iOS"
    elif "Mac OS X" in ua or "Macintosh" in ua:
        system = "macOS"
    elif "Linux" in ua:
        system = "Linux"

    browser = "未知"
    if "Edg/" in ua:
        browser = "Edge"
    elif "Chrome/" in ua and "Chromium" not in ua:
        browser = "Chrome"
    elif "Firefox/" in ua:
        browser = "Firefox"
    elif "Safari/" in ua:
        browser = "Safari"
    return system, browser


def _write_login_log(session: Session, username: str, success: bool, request: Request) -> None:
    system, browser = _parse_ua(request.headers.get("user-agent", ""))
    log = LoginLog(
        username=username or "unknown",
        summary="账号密码登录成功" if success else "账号密码登录失败",
        ip=_client_ip(request),
        address="",
        system=system,
        browser=browser,
        success=success,
    )
    session.add(log)
    session.commit()


@router.post("/login")
def login(req: LoginRequest, request: Request, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == req.username)).first()
    if not user or not verify_password(req.password, user.hashed_password):
        # 失败也留痕（防爆破排查），再返回 401
        _write_login_log(session, req.username, False, request)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_token({"sub": user.username, "admin": user.is_admin})
    expires = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    _write_login_log(session, user.username, True, request)

    return {
        "code": 0,
        "message": "success",
        "data": {
            "accessToken": token,
            "refreshToken": token,
            "expires": expires.isoformat(),
            "avatar": user.avatar or "",
            "username": user.username,
            "nickname": user.nickname or user.username,
            "roles": ["admin"] if user.is_admin else [],
            "permissions": ["*:*:*"] if user.is_admin else [],
        },
    }


@router.post("/refresh-token")
def refresh_token(user: User = Depends(get_current_user)):
    """用仍有效的登录态换发新 access token（无状态 JWT，旧 token 自然到期）。"""
    token = create_token({"sub": user.username, "admin": user.is_admin})
    expires = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return {
        "code": 0,
        "message": "success",
        "data": {
            "accessToken": token,
            "refreshToken": token,
            "expires": expires.isoformat(),
        },
    }


@router.get("/me-logs")
def me_logs(
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """当前登录用户自己的安全（登录）日志，按时间倒序分页。"""
    stmt = select(LoginLog).where(LoginLog.username == user.username)
    total = len(session.exec(stmt).all())
    rows = session.exec(
        stmt.order_by(LoginLog.created_at.desc())
        .offset((page - 1) * pageSize)
        .limit(pageSize)
    ).all()
    return {
        "code": 0,
        "message": "success",
        "data": {
            "list": [
                {
                    "id": r.id,
                    "summary": r.summary,
                    "ip": r.ip,
                    "address": r.address,
                    "system": r.system,
                    "browser": r.browser,
                    "operatingTime": r.created_at.isoformat() if r.created_at else "",
                }
                for r in rows
            ],
            "total": total,
            "currentPage": page,
            "pageSize": pageSize,
        },
    }


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    db_user = user
    return {
        "code": 0,
        "message": "success",
        "data": {
            "avatar": db_user.avatar or "",
            "username": db_user.username,
            "nickname": db_user.nickname or db_user.username,
            "email": db_user.email or "",
            "description": db_user.bio or "",
            "phone": "",
            "roles": ["admin"] if db_user.is_admin else [],
            "permissions": ["*:*:*"] if db_user.is_admin else [],
        },
    }


@router.put("/me")
def update_me(
    data: dict,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    db_user = user
    if "nickname" in data:
        db_user.nickname = data["nickname"]
    if "email" in data:
        db_user.email = data["email"]
    if "bio" in data or "description" in data:
        db_user.bio = data.get("bio") or data.get("description") or ""
    if "avatar" in data:
        db_user.avatar = data["avatar"]
    db_user.updated_at = datetime.now()
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return {"code": 0, "message": "更新成功"}
