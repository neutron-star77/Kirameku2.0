from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import Session, select

from app.api.github_auth import get_github_user_optional, require_github_user
from app.deps import get_session, get_current_user
from app.models import User
from app.schemas import CommentCreate, CommentOut, CommentAdminUpdate, LikeOut
from app.services import comment_service, like_service
from app.services.cache_invalidate import invalidate_cache
from app.utils.auth import decode_token

router = APIRouter(prefix="/api/comments", tags=["评论"])

# 评论写操作会影响内容页缓存与评论列表缓存 → 一并失效（并触发 P4 实时广播）
TAG_BY_TARGET = {"post": "posts", "chatter": "moments", "album": "albums"}


def _client_ip(request: Request) -> str:
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not ip:
        ip = request.headers.get("x-real-ip", "")
    if not ip:
        ip = request.client.host if request.client else ""
    return ip


def _require_admin_token(request: Request, session: Session) -> None:
    """后台（Vue admin）走的是用户名密码 JWT，这里手动校验管理员身份。

    与 `get_current_user` 的区别：那里用 `Depends(HTTPBearer)`，在"两种身份二选一"
    的路由里没法直接用，所以显式解析一次。
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "未登录")
    payload = decode_token(auth[7:])
    username = payload.get("sub")
    user = session.exec(select(User).where(User.username == username)).first() if username else None
    if not user or not user.is_admin:
        raise HTTPException(403, "只有作者本人或管理员可以删除")


# ---- 公开接口 ----

@router.get("", response_model=list[CommentOut])
def get_comments(
    target_type: str = Query("post", description="post / chatter / album"),
    target_id: int = Query(..., ge=1),
    session: Session = Depends(get_session),
):
    """按多态目标取评论（P5）。例：/api/comments?target_type=chatter&target_id=3"""
    return comment_service.get_comments(session, target_type, target_id)


@router.get("/post/{post_id}", response_model=list[CommentOut])
def get_post_comments(post_id: int, session: Session = Depends(get_session)):
    """旧接口兼容：文章维度评论"""
    return comment_service.get_comments_by_post(session, post_id)


@router.post("", response_model=CommentOut)
def create_comment(
    data: CommentCreate,
    request: Request,
    session: Session = Depends(get_session),
):
    """发评论 / 回复（需 GitHub 登录）。target_type + target_id 定位内容。"""
    user = get_github_user_optional(request, session)
    target_type, target_id = comment_service.resolve_target(data)
    created = comment_service.create_comment(session, data, user, _client_ip(request))
    invalidate_cache(["comments", TAG_BY_TARGET.get(target_type, "all")])
    return created


# ---- 管理/作者接口 ----

@router.get("/admin")
def admin_list_comments(
    status: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
    _: dict = Depends(get_current_user),
):
    return comment_service.get_comments_admin(session, status, page, size)


@router.put("/{comment_id}/status")
def update_comment_status(
    comment_id: int,
    data: CommentAdminUpdate,
    session: Session = Depends(get_session),
    _: dict = Depends(get_current_user),
):
    return comment_service.update_comment_status(session, comment_id, data.status)


@router.post("/{comment_id}/like", response_model=LikeOut)
def like_comment(comment_id: int, request: Request, session: Session = Depends(get_session)):
    """兼容旧接口：确保"已点赞"（已点过则不重复计数）。新代码请用 /api/likes/toggle。"""
    user = require_github_user(request, session)
    if like_service.is_liked(session, user.id, "comment", comment_id):
        comment = comment_service.get_comments_by_id(session, comment_id)
        return {"liked": True, "likes": comment["likes"]}
    result = like_service.toggle(session, user, "comment", comment_id)
    invalidate_cache(["comments"])
    return result


@router.post("/{comment_id}/unlike", response_model=LikeOut)
def unlike_comment(comment_id: int, request: Request, session: Session = Depends(get_session)):
    """兼容旧接口：确保"未点赞"。"""
    user = require_github_user(request, session)
    if not like_service.is_liked(session, user.id, "comment", comment_id):
        comment = comment_service.get_comments_by_id(session, comment_id)
        return {"liked": False, "likes": comment["likes"]}
    result = like_service.toggle(session, user, "comment", comment_id)
    invalidate_cache(["comments"])
    return result


@router.delete("/{comment_id}")
def delete_comment(
    comment_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    """删除评论：作者本人可删自己的；后台管理员带管理端 token 也可删。"""
    gh_user = get_github_user_optional(request, session)
    if gh_user is not None:
        comment_service.delete_comment(session, comment_id, github_user=gh_user)
    else:
        _require_admin_token(request, session)
        comment_service.delete_comment(session, comment_id)
    invalidate_cache(["comments"])
    return {"ok": True}
