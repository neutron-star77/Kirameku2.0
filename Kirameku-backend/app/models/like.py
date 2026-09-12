from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint


class Like(SQLModel, table=True):
    """点赞关联表（P5）。

    一行 = 某个 GitHub 用户对某个目标的一次点赞，靠
    `uq_likes_user_target` 唯一约束天然防重复（并发下也安全）。

    - `target_type`：`chatter`（说说）/ `comment`（评论）/ `post`（文章）
    - `target_id`：对应目标表的主键
    - 目标表上的 `likes` 字段仍保留为**冗余计数**，方便列表页直接读；
      真值以本表行数为准，需要重算时按 (target_type, target_id) 聚合即可。

    表名用复数 `likes`：`like` 是 SQL 关键字，裸 SQL 里必须加引号，容易踩坑。
    """

    __tablename__ = "likes"
    __table_args__ = (
        UniqueConstraint("user_id", "target_type", "target_id", name="uq_likes_user_target"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="github_user.id", index=True)
    target_type: str = Field(max_length=20, index=True)
    target_id: int = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.now)
