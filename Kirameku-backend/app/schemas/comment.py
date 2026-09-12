from datetime import datetime
from pydantic import BaseModel


class GitHubUserOut(BaseModel):
    id: int
    login: str
    avatar: str
    bio: str


class CommentCreate(BaseModel):
    """评论创建入参。

    新代码用 `target_type`（post/chatter/album）+ `target_id`；
    只传 `post_id` 的老调用方仍然可用（服务层会归一成 post 维度）。
    """

    post_id: int | None = None
    target_type: str | None = None
    target_id: int | None = None
    parent_id: int | None = None
    content: str


class CommentOut(BaseModel):
    id: int
    post_id: int | None = None
    target_type: str = "post"
    target_id: int = 0
    parent_id: int | None
    content: str
    likes: int = 0
    status: str
    created_at: datetime
    github_user: GitHubUserOut | None = None
    replies: list["CommentOut"] = []


# ---- 点赞（P5：用户维度去重，真值在 likes 表，目标表 likes 字段为冗余计数）----

class LikeIn(BaseModel):
    """点赞/取消点赞入参：target_type = chatter / comment / post"""

    target_type: str
    target_id: int


class LikeOut(BaseModel):
    liked: bool
    likes: int


class CommentAdminUpdate(BaseModel):
    status: str  # approved / rejected


# 留言板/杂谈
class MessageCreate(BaseModel):
    content: str
    parent_id: int | None = None


class MessageOut(BaseModel):
    id: int
    github_user_id: int | None
    parent_id: int | None
    content: str
    ip: str = ""
    status: str
    likes: int
    created_at: datetime
    github_user: GitHubUserOut | None = None
    replies: list["MessageOut"] = []


class MessageAdminUpdate(BaseModel):
    status: str
