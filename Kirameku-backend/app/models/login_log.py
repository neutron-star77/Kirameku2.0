from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field


class LoginLog(SQLModel, table=True):
    """登录/安全日志（后台「账号设置-安全日志」用）。

    每次用户名密码登录尝试都记一条（成功/失败），me-logs 接口按用户名查自己的。
    UA 在写入时解析成 system/browser，避免前端再引依赖；address（归属地）留空，
    需要时可接 IP 库。
    """

    __tablename__ = "login_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(max_length=50, index=True)
    summary: str = Field(default="", max_length=200)
    ip: str = Field(default="", max_length=45)
    address: str = Field(default="", max_length=100)
    system: str = Field(default="", max_length=100)
    browser: str = Field(default="", max_length=100)
    success: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=datetime.now, index=True)
