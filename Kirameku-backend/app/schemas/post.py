from datetime import datetime
from pydantic import BaseModel


class PostCreate(BaseModel):
    title: str
    slug: str
    description: str = ""
    content: str = ""
    cover: str = ""
    category_id: int | None = None
    tags: list[str] = []
    status: str = "draft"
    is_pinned: bool = False
    reading_time: int = 0
    word_count: int = 0
    font_id: int | None = None


class PostUpdate(BaseModel):
    title: str | None = None
    slug: str | None = None
    description: str | None = None
    content: str | None = None
    cover: str | None = None
    category_id: int | None = None
    tags: list[str] | None = None
    status: str | None = None
    is_pinned: bool | None = None
    reading_time: int | None = None
    word_count: int | None = None
    font_id: int | None = None


class PostOut(BaseModel):
    id: int
    title: str
    slug: str
    description: str
    cover: str
    category: str = ""
    tags: list[str] = []
    status: str
    is_pinned: bool
    views: int
    likes: int
    word_count: int
    reading_time: int
    font_id: int | None = None
    font_name: str = ""
    font_family: str = ""
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PostDetail(PostOut):
    content: str
