"""评论服务（P5 起支持多态目标）。

历史：只有文章评论（`post_id`）。
现在：统一用 `target_type` + `target_id`（post / chatter / album），
`post_id` 仅在 target_type == "post" 时同步一份，便于旧接口继续工作。

读取时组装两层结构：根评论 + `replies`（楼中楼）。当前只做两层，
再深的回复会被挂到其 parent 的 replies 下（前端按同一层级渲染）。
"""

from urllib.parse import quote

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import Album, Chatter, Comment, GitHubUser, Post
from app.schemas import CommentCreate

SUPPORTED_TARGETS = ("post", "chatter", "album")


def _snippet(text: str, length: int = 40) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= length else f"{text[:length]}…"


def target_info(session: Session, target_type: str, target_id: int) -> dict:
    """评论所属内容的信息（后台列表用：显示标题 + 可点回前台）。

    只做单条查询，后台列表页 size 有限（默认 20），不会造成明显 N+1。
    """
    if target_type == "post":
        post = session.get(Post, target_id)
        return {
            "type": "post",
            "id": target_id,
            "title": post.title if post else None,
            "url": f"/posts/{quote(post.slug)}" if post else None,
        }
    if target_type == "chatter":
        chatter = session.get(Chatter, target_id)
        return {
            "type": "chatter",
            "id": target_id,
            "title": _snippet(chatter.content) if chatter else None,
            "url": "/moments",
        }
    if target_type == "album":
        album = session.get(Album, target_id)
        return {
            "type": "album",
            "id": target_id,
            "title": album.title if album else None,
            "url": "/albums",
        }
    return {"type": target_type, "id": target_id, "title": None, "url": None}


def _comment_to_dict(
    session: Session,
    c: Comment,
    include_ip: bool = False,
    fetch_replies: bool = False,
) -> dict:
    gh_user = session.get(GitHubUser, c.github_user_id) if c.github_user_id else None
    d = {
        "id": c.id,
        "post_id": c.post_id,
        "target_type": c.target_type,
        "target_id": c.target_id,
        "parent_id": c.parent_id,
        "content": c.content,
        "likes": c.likes,
        "status": c.status,
        "created_at": c.created_at,
        "github_user": {
            "id": gh_user.id,
            "login": gh_user.login,
            "avatar": gh_user.avatar,
            "bio": gh_user.bio,
        } if gh_user else None,
        "replies": [],
    }
    if include_ip:
        d["ip"] = c.ip
    if fetch_replies:
        replies = list(
            session.exec(
                select(Comment)
                .where(Comment.parent_id == c.id)
                .order_by(Comment.created_at)
            ).all()
        )
        d["replies"] = [
            _comment_to_dict(session, r, include_ip=include_ip, fetch_replies=True) for r in replies
        ]
    return d


def resolve_target(data: CommentCreate) -> tuple[str, int]:
    """把 (target_type, target_id) 与历史的 post_id 归一成一个目标。"""
    target_type = (getattr(data, "target_type", None) or "post").strip() or "post"
    if target_type not in SUPPORTED_TARGETS:
        raise HTTPException(400, f"不支持的评论目标：{target_type}")

    target_id = getattr(data, "target_id", None)
    if target_id is None:
        target_id = getattr(data, "post_id", None)
    if target_id is None:
        raise HTTPException(400, "缺少评论目标（target_type + target_id）")
    return target_type, int(target_id)


def get_comments(session: Session, target_type: str, target_id: int) -> list[dict]:
    """某个目标（文章/说说/相册）下的已通过评论，组装成 根+楼中楼 两层。"""
    if target_type not in SUPPORTED_TARGETS:
        raise HTTPException(400, f"不支持的评论目标：{target_type}")

    rows = list(
        session.exec(
            select(Comment)
            .where(
                Comment.target_type == target_type,
                Comment.target_id == target_id,
                Comment.status == "approved",
            )
            .order_by(Comment.created_at.asc())
        ).all()
    )
    id_map: dict[int, dict] = {c.id: _comment_to_dict(session, c) for c in rows}
    roots: list[dict] = []
    for c in rows:
        d = id_map[c.id]
        if c.parent_id and c.parent_id in id_map:
            id_map[c.parent_id]["replies"].append(d)
        else:
            roots.append(d)
    return roots


def get_comments_by_post(session: Session, post_id: int) -> list[dict]:
    """旧接口兼容：文章维度评论"""
    return get_comments(session, "post", post_id)


def get_comments_by_id(session: Session, comment_id: int) -> dict:
    """取单条评论（点赞兼容接口需要读当前计数）"""
    comment = session.get(Comment, comment_id)
    if not comment:
        raise HTTPException(404, "评论不存在")
    return _comment_to_dict(session, comment)


def get_comments_admin(
    session: Session,
    status: str | None = None,
    target_type: str | None = None,
    page: int = 1,
    size: int = 20,
) -> list[dict]:
    """后台评论列表（根评论 + 嵌套回复）。

    - `status`：按审核状态过滤
    - `target_type`：按所属内容类型过滤（post / chatter / album）
      —— 评论表现在是多态的，后台需要能分类型查看
    """
    q = select(Comment).where(Comment.parent_id.is_(None))
    if status:
        q = q.where(Comment.status == status)
    if target_type:
        q = q.where(Comment.target_type == target_type)
    q = q.order_by(Comment.created_at.desc())
    q = q.offset((page - 1) * size).limit(size)
    rows = list(session.exec(q).all())

    items: list[dict] = []
    for c in rows:
        d = _comment_to_dict(session, c, include_ip=True, fetch_replies=True)
        # 后台需要知道这条评论挂在哪个内容下（标题 + 可点回前台）
        d["target"] = target_info(session, c.target_type, c.target_id)
        items.append(d)
    return items


def create_comment(
    session: Session,
    data: CommentCreate,
    github_user: GitHubUser | None = None,
    ip: str = "",
) -> dict:
    if not github_user:
        raise HTTPException(401, "请先登录 GitHub")

    target_type, target_id = resolve_target(data)
    content = (data.content or "").strip()
    if not content:
        raise HTTPException(400, "评论内容不能为空")
    if len(content) > 2000:
        raise HTTPException(400, "评论内容过长（上限 2000 字）")

    if data.parent_id:
        parent = session.get(Comment, data.parent_id)
        if not parent:
            raise HTTPException(404, "被回复的评论不存在")
        # 防止跨目标回复
        if parent.target_type != target_type or parent.target_id != target_id:
            raise HTTPException(400, "被回复的评论不属于当前内容")

    comment = Comment(
        post_id=target_id if target_type == "post" else None,
        target_type=target_type,
        target_id=target_id,
        parent_id=data.parent_id,
        github_user_id=github_user.id,
        content=content,
        ip=ip,
    )
    session.add(comment)
    session.commit()
    session.refresh(comment)
    return _comment_to_dict(session, comment)


def update_comment_status(session: Session, comment_id: int, status: str) -> dict:
    comment = session.get(Comment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="评论不存在")
    comment.status = status
    session.add(comment)
    session.commit()
    session.refresh(comment)
    return _comment_to_dict(session, comment)


def delete_comment(session: Session, comment_id: int, github_user: GitHubUser | None = None) -> None:
    """删除评论：作者本人可删自己的；github_user 传 None 表示管理员后台操作。"""
    comment = session.get(Comment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="评论不存在")
    if github_user is not None and comment.github_user_id != github_user.id:
        raise HTTPException(403, "只能删除自己的评论")
    # 连带删除其下子回复，避免出现孤儿
    for reply in session.exec(select(Comment).where(Comment.parent_id == comment_id)).all():
        session.delete(reply)
    session.delete(comment)
    session.commit()
