"""点赞服务（P5）：用户维度去重 + 目标表冗余计数同步。

设计要点：
- 真值在 `likes` 表（`user_id + target_type + target_id` 唯一约束），
  目标表（chatter / comment / post）上的 `likes` 字段只是**冗余计数**，
  列表页直接读它，避免每次 COUNT。
- 并发下靠唯一约束兜底：重复插入触发 IntegrityError 时回滚并返回"已点赞"状态，
  不会把计数 +2。
- 支持的目标类型：chatter（说说）/ comment（评论）/ post（文章）。
"""

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models import Chatter, ChatterComment, Comment, GitHubUser, Like, Post

SUPPORTED_TARGETS = ("chatter", "comment", "post", "chatter_comment")


def _get_target(session: Session, target_type: str, target_id: int):
    """取被点赞的目标对象（用于同步冗余计数）"""
    if target_type == "chatter":
        return session.get(Chatter, target_id)
    if target_type == "comment":
        return session.get(Comment, target_id)
    if target_type == "chatter_comment":
        return session.get(ChatterComment, target_id)
    if target_type == "post":
        return session.get(Post, target_id)
    return None


def is_liked(session: Session, user_id: int, target_type: str, target_id: int) -> bool:
    return (
        session.exec(
            select(Like).where(
                Like.user_id == user_id,
                Like.target_type == target_type,
                Like.target_id == target_id,
            )
        ).first()
        is not None
    )


def liked_ids(session: Session, user_id: int, target_type: str) -> list[int]:
    """当前用户在某一类目标下点过赞的 id 列表（前端用来回填"我的点赞态"）"""
    rows = session.exec(
        select(Like).where(Like.user_id == user_id, Like.target_type == target_type)
    ).all()
    return [row.target_id for row in rows]


def toggle(session: Session, user: GitHubUser, target_type: str, target_id: int) -> dict:
    """点赞/取消点赞（幂等切换），返回 {liked, likes}"""
    if target_type not in SUPPORTED_TARGETS:
        raise HTTPException(400, f"不支持的点赞目标：{target_type}")

    target = _get_target(session, target_type, target_id)
    if target is None:
        raise HTTPException(404, "点赞目标不存在")

    existing = session.exec(
        select(Like).where(
            Like.user_id == user.id,
            Like.target_type == target_type,
            Like.target_id == target_id,
        )
    ).first()

    if existing:
        session.delete(existing)
        target.likes = max(0, (target.likes or 0) - 1)
        liked = False
    else:
        session.add(Like(user_id=user.id, target_type=target_type, target_id=target_id))
        target.likes = (target.likes or 0) + 1
        liked = True

    session.add(target)
    try:
        session.commit()
    except IntegrityError:
        # 并发重复点赞：约束拦下，回滚后按"已点赞"返回，计数不重复加
        session.rollback()
        target = _get_target(session, target_type, target_id)
        return {"liked": True, "likes": getattr(target, "likes", 0) or 0}

    session.refresh(target)
    return {"liked": liked, "likes": getattr(target, "likes", 0) or 0}
