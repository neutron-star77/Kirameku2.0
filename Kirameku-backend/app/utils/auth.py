from datetime import datetime, timedelta, timezone
import bcrypt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlmodel import Session, select

from app.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_HOURS
from app.database import get_session
from app.models import User

security = HTTPBearer()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_token(data: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode({**data, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="无效的令牌")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: Session = Depends(get_session),
) -> User:
    """解析 JWT 并落库校验：用户必须存在，且必须是管理员。

    仅凭签名有效就放行会让「已删除用户 / 非管理员」也能调用写接口。
    """
    payload = decode_token(credentials.credentials)
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="无效的令牌")

    user = session.exec(select(User).where(User.username == username)).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """语义化别名：写接口统一依赖它。"""
    return user
