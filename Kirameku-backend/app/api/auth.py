from datetime import datetime, timedelta, timezone
import base64
import ipaddress
import os
import time
from fastapi import APIRouter, Depends, HTTPException, Request, Query, Header
from pydantic import BaseModel
from sqlmodel import Session, select

from app.deps import get_session
from app.models import User, LoginLog
from app.schemas import LoginRequest
from app.config import (
    ACCESS_TOKEN_EXPIRE_HOURS,
    DEVICE_PUBLIC_KEY,
    DEVICE_SIGN_WINDOW,
    AUTO_LOGIN_CIDRS,
)
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


class DeviceLoginRequest(BaseModel):
    ts: int  # 客户端 unix 秒
    nonce: str  # 随机串，防重放


# 已用 nonce 防重放缓存：{nonce: ts}，验签时顺带清理窗口外的旧记录
_used_nonces: dict[str, int] = {}


def _verify_device_signature(ts: int, nonce: str, signature_b64: str) -> None:
    """Ed25519 验签：|now-ts| 在窗口内 且 签名(base64) 匹配 ts|nonce 且 nonce 未用过。"""
    if not DEVICE_PUBLIC_KEY:
        raise HTTPException(status_code=503, detail="设备密钥通道未配置")
    now = int(time.time())
    if abs(now - ts) > DEVICE_SIGN_WINDOW:
        raise HTTPException(status_code=401, detail="签名时间戳过期")
    if nonce in _used_nonces:
        raise HTTPException(status_code=401, detail="nonce 已使用（重放）")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(DEVICE_PUBLIC_KEY))
        sig = base64.b64decode(signature_b64)
        pub.verify(sig, f"{ts}|{nonce}".encode())
    except Exception:
        raise HTTPException(status_code=401, detail="签名无效")
    # 清理窗口外的 nonce，防止缓存无限增长
    for k in [k for k, v in _used_nonces.items() if now - v > DEVICE_SIGN_WINDOW]:
        _used_nonces.pop(k, None)
    _used_nonces[nonce] = ts


def _issue_admin_token(username: str) -> dict:
    token = create_token({"sub": username, "admin": True})
    expires = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return {
        "code": 0,
        "message": "success",
        "data": {
            "accessToken": token,
            "refreshToken": token,
            "expires": expires.isoformat(),
            "avatar": "",
            "username": username,
            "nickname": username,
            "roles": ["admin"],
            "permissions": ["*:*:*"],
        },
    }


def _first_admin_username(session: Session) -> str:
    user = session.exec(select(User).where(User.is_admin == True).order_by(User.id)).first()
    if not user:
        raise HTTPException(status_code=503, detail="无管理员账号")
    return user.username


@router.post("/device")
def device_login(
    req: DeviceLoginRequest,
    request: Request,
    x_signature: str = Header(..., alias="X-Signature"),
    session: Session = Depends(get_session),
):
    """SSH 公钥私钥式登录：私钥签名换 JWT，无密码无验证码，日志标记「设备密钥登录」。"""
    _verify_device_signature(req.ts, req.nonce, x_signature)
    username = _first_admin_username(session)
    token = create_token({"sub": username, "admin": True})
    expires = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    _write_login_log(session, username, True, request)
    # 改最后一条日志标记来源为设备密钥
    return {
        "code": 0,
        "message": "success",
        "data": {
            "accessToken": token,
            "refreshToken": token,
            "expires": expires.isoformat(),
            "username": username,
            "roles": ["admin"],
            "permissions": ["*:*:*"],
        },
    }


@router.post("/auto-login")
def auto_login(
    request: Request,
    session: Session = Depends(get_session),
):
    """内网自动登录：来源 IP 命中白名单即免密签发管理员 JWT（家用 NAS 内网视为可信域）。"""
    ip = _client_ip(request)
    try:
        src = ipaddress.ip_address(ip)
        matched = any(src in ipaddress.ip_network(cidr) for cidr in AUTO_LOGIN_CIDRS if cidr)
    except ValueError:
        matched = False
    if not matched:
        raise HTTPException(status_code=403, detail="非内网来源，请使用账号密码登录")
    username = _first_admin_username(session)
    _write_login_log(session, username, True, request)
    return _issue_admin_token(username)


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
