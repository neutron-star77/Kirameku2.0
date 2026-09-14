"""font_asset 字体资源表 + post.font_id（文章级选字体，P 字体内嵌）

Revision ID: 0004_font_asset
Revises: 0003_login_log
Create Date: 2026-09-14

内容：
1. 新建 `font_asset` 表：开源古文字体（霞鹜文楷/思源等）元数据 + woff2 二进制
   （file_data BYTEA）入库，公开 API 下发渲染；
2. `post` 加 `font_id` 可空外键：后台写文章可选字体，未选保持不变（默认字体）。

注意：应用启动时 `init_db()` 的 `create_all` 会先建新表，请先跑本迁移再重启容器
（或接受 create_all 建表后执行 `alembic stamp 0004_font_asset`，见坑大全 6.3.16）。
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_font_asset"
down_revision = "0003_login_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "font_asset",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("family", sa.String(128), nullable=False, unique=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="cjk"),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="400"),
        sa.Column("license_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("license_url", sa.String(300), nullable=False, server_default=""),
        sa.Column("file_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("mime_type", sa.String(64), nullable=False, server_default="font/woff2"),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("file_data", sa.LargeBinary(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_font_asset_role", "font_asset", ["role"])

    op.add_column("post", sa.Column("font_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_post_font_id", "post", "font_asset", ["font_id"], ["id"])
    op.create_index("ix_post_font_id", "post", ["font_id"])


def downgrade() -> None:
    op.drop_index("ix_post_font_id", table_name="post")
    op.drop_constraint("fk_post_font_id", "post", type_="foreignkey")
    op.drop_column("post", "font_id")

    op.drop_index("ix_font_asset_role", table_name="font_asset")
    op.drop_table("font_asset")