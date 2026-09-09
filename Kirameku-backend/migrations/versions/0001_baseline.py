"""baseline

现有库由 SQLModel.metadata.create_all 建立（见 app.database.init_db）。
本迁移只是基线锚点，不重复建表；部署后执行 `alembic stamp head` 对齐版本，
之后的模型变更一律用 `alembic revision --autogenerate` 生成。

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-09
"""

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
