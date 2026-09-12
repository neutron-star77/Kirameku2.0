"""likes 表 + 评论多态（P5）

Revision ID: 0002_likes_comments
Revises: 0001_baseline
Create Date: 2026-09-12

内容：
1. `comment` 加 `target_type` / `target_id`（多态关联：post / chatter / album），
   用 post_id 回填历史数据，然后放开 post_id 的非空约束；
2. 新建 `likes` 关联表（user_id + target_type + target_id 唯一）用于点赞防刷。

生产库此前已 `alembic stamp head`，本迁移用 `alembic upgrade head` 应用。
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_likes_comments"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- 1) 评论多态 ----
    op.add_column(
        "comment",
        sa.Column("target_type", sa.String(20), nullable=False, server_default="post"),
    )
    op.add_column(
        "comment",
        sa.Column("target_id", sa.Integer(), nullable=False, server_default="0"),
    )
    # 历史数据回填：老评论都是文章评论
    op.execute("UPDATE comment SET target_id = post_id WHERE target_id = 0 AND post_id IS NOT NULL")
    # 回填完成后去掉 target_id 的默认值，避免"忘了传 target_id 就静默写成 0"
    op.execute("ALTER TABLE comment ALTER COLUMN target_id DROP DEFAULT")
    op.alter_column("comment", "post_id", existing_type=sa.Integer(), nullable=True)
    op.create_index("ix_comment_target", "comment", ["target_type", "target_id"])

    # ---- 2) 点赞关联表 ----
    op.create_table(
        "likes",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("github_user.id"), nullable=False),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "target_type", "target_id", name="uq_likes_user_target"),
    )
    op.create_index("ix_likes_user_id", "likes", ["user_id"])
    op.create_index("ix_likes_target_type", "likes", ["target_type"])
    op.create_index("ix_likes_target_id", "likes", ["target_id"])


def downgrade() -> None:
    op.drop_index("ix_likes_target_id", table_name="likes")
    op.drop_index("ix_likes_target_type", table_name="likes")
    op.drop_index("ix_likes_user_id", table_name="likes")
    op.drop_table("likes")

    op.execute("UPDATE comment SET post_id = target_id WHERE post_id IS NULL AND target_type = 'post'")
    op.drop_index("ix_comment_target", table_name="comment")
    op.alter_column("comment", "post_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("comment", "target_id")
    op.drop_column("comment", "target_type")
