"""点赞接口（P5）。

真值在 `likes` 关联表（用户维度唯一），目标表的 likes 字段是冗余计数。
所有写操作都要求 GitHub 登录，未登录返回 401，前端据此提示去登录。
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from app.api.github_auth import require_github_user
from app.deps import get_session
from app.schemas import LikeIn, LikeOut
from app.services import like_service
from app.services.cache_invalidate import invalidate_cache

router = APIRouter(prefix="/api/likes", tags=["点赞"])

# 点赞会改动列表页展示的计数 → 按目标类型清对应缓存并触发实时刷新
TAG_BY_TARGET = {
    "chatter": "moments",
    "chatter_comment": "moments",
    "comment": "comments",
    "post": "posts",
}


@router.post("/toggle", response_model=LikeOut)
def toggle_like(data: LikeIn, request: Request, session: Session = Depends(get_session)):
    """点赞 / 取消点赞（幂等切换，需登录）。"""
    user = require_github_user(request, session)
    result = like_service.toggle(session, user, data.target_type, data.target_id)
    invalidate_cache([TAG_BY_TARGET.get(data.target_type, "all")])
    return result


@router.get("/mine")
def my_likes(
    request: Request,
    target_type: str = Query(..., description="chatter / comment / post"),
    session: Session = Depends(get_session),
):
    """当前用户在某类目标下点过赞的 id 列表（前端回填"我的点赞态"）。

    未登录返回空列表而不是 401：调用方（页面加载）不该因未登录报错。
    """
    from app.api.github_auth import get_github_user_optional

    user = get_github_user_optional(request, session)
    if user is None:
        return {"target_type": target_type, "ids": []}
    return {"target_type": target_type, "ids": like_service.liked_ids(session, user.id, target_type)}
