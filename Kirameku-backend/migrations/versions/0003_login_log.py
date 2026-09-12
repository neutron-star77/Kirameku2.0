"""login_log 登录日志表（后台安全日志 / me-logs 接口）

Revision ID: 0003_login_log
Revises: 0002_likes_comments
Create Date: 2026-09-13

内容：新建 `login_log` 表，记录每次登录尝试（用户名/IP/UA 解析/成功与否/时间），
供「账号设置-安全日志」页 GET /api/auth/me-logs 分页查询。
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_login_log"
down_revision = "0002_likes_comments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_log",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("summary", sa.String(200), nullable=False, server_default=""),
        sa.Column("ip", sa.String(45), nullable=False, server_default=""),
        sa.Column("address", sa.String(100), nullable=False, server_default=""),
        sa.Column("system", sa.String(100), nullable=False, server_default=""),
        sa.Column("browser", sa.String(100), nullable=False, server_default=""),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_login_log_username", "login_log", ["username"])
    op.create_index("ix_login_log_success", "login_log", ["success"])
    op.create_index("ix_login_log_created_at", "login_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_login_log_created_at", table_name="login_log")
    op.drop_index("ix_login_log_success", table_name="login_log")
    op.drop_index("ix_login_log_username", table_name="login_log")
    op.drop_table("login_log")
