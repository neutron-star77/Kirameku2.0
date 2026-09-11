"""重置 Kirameku 后台 admin 密码
用法:
    venv/Scripts/python.exe reset_admin.py [新密码]
默认密码: admin123
"""
import sys

sys.path.insert(0, r"F:\AI\projects\Kirameku\Kirameku-backend")

from app.utils.auth import hash_password, verify_password
from app.models import User
from app.database import engine
from sqlmodel import Session, select

password = sys.argv[1] if len(sys.argv) > 1 else "admin123"
username = "admin"

with Session(engine) as session:
    user = session.exec(select(User).where(User.username == username)).first()
    if not user:
        print(f"[ERROR] 未找到用户: {username}")
        sys.exit(1)
    user.hashed_password = hash_password(password)
    session.add(user)
    session.commit()
    session.refresh(user)
    ok = verify_password(password, user.hashed_password)
    print(f"[OK] 已重置 {username} 的密码 -> {password}")
    print(f"[OK] 哈希写回校验: {ok}")
    print(f"[OK] 哈希前缀: {user.hashed_password[:20]}")