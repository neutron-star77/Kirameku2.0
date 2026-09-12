from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Comment(SQLModel, table=True):
    """评论（P5 起支持多态关联）。

    - 早期只有文章评论 → `post_id`
    - 现改为多态：`target_type`（post / chatter / album）+ `target_id`
    - `post_id` 保留但可空，仅作历史兼容（新代码一律写 target_*）
    """

    __tablename__ = "comment"

    id: Optional[int] = Field(default=None, primary_key=True)
    post_id: Optional[int] = Field(default=None, foreign_key="post.id", index=True)
    target_type: str = Field(default="post", max_length=20, index=True)
    target_id: int = Field(default=0, index=True)
    parent_id: Optional[int] = Field(default=None, foreign_key="comment.id")
    github_user_id: Optional[int] = Field(default=None, foreign_key="github_user.id", index=True)
    content: str
    likes: int = Field(default=0)
    ip: str = Field(default="", max_length=45)
    status: str = Field(default="pending", max_length=20, index=True)
    created_at: datetime = Field(default_factory=datetime.now)
