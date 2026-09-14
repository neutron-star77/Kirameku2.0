"""字体资源 API：公开读取（列表 + 二进制下发），后台管理（上传/更新/删除）

- GET  /api/fonts            公开：字体元数据列表（不含二进制）
- GET  /api/fonts/{id}/file  公开：woff2 二进制，带长缓存头（字体几乎不变）
- POST /api/fonts            登录：上传新字体（multipart: JSON 字段 + 文件）
- PUT  /api/fonts/{id}       登录：更新元数据（启用/默认/排序/授权等）
- POST /api/fonts/{id}/file  登录：替换字体文件
- POST /api/fonts/{id}/default 登录：设为默认字体
- DELETE /api/fonts/{id}     登录：删除（有文章引用时置空其 font_id）
"""
from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException
from fastapi.responses import Response
from sqlmodel import Session, select

from app.deps import get_session, get_current_user
from app.schemas.font import FontOut, FontCreate, FontUpdate
from app.services import font_service

router = APIRouter(prefix="/api/fonts", tags=["字体"])

ALLOWED_MIME = {"font/woff2", "font/ttf", "font/otf", "application/octet-stream"}
MAX_FILE_SIZE = 30 * 1024 * 1024  # 30MB（woff2 字体通常 1-5MB）


@router.get("", response_model=list[FontOut])
def list_fonts(session: Session = Depends(get_session)):
    """公开：返回启用的字体元数据列表（不包含二进制数据）"""
    return font_service.list_fonts(session, enabled_only=True)


@router.get("/all", response_model=list[FontOut])
def list_all_fonts(
    session: Session = Depends(get_session),
    _: dict = Depends(get_current_user),
):
    """后台：返回全部字体（含禁用项）"""
    return font_service.list_fonts(session, enabled_only=False)


@router.get("/{font_id}/file")
def get_font_file(font_id: int, session: Session = Depends(get_session)):
    """公开：下发字体二进制（字体文件几乎不变，浏览器/BFF 可长缓存）"""
    font, data = font_service.get_font_file(session, font_id)
    return Response(
        content=data,
        media_type=font.mime_type or "font/woff2",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Disposition": f'inline; filename="{font.file_name or font.family}"',
        },
    )


@router.post("", response_model=FontOut)
async def create_font(
    name: str = Form(...),
    family: str = Form(...),
    role: str = Form("cjk"),
    weight: int = Form(400),
    license_name: str = Form(""),
    license_url: str = Form(""),
    is_default: bool = Form(False),
    sort: int = Form(0),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    _: dict = Depends(get_current_user),
):
    mime = file.content_type or "application/octet-stream"
    if mime not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {mime}（仅 woff2/ttf/otf）")
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="字体文件不能超过 30MB")
    data = FontCreate(
        name=name,
        family=family,
        role=role,
        weight=weight,
        license_name=license_name,
        license_url=license_url,
        is_default=is_default,
        sort=sort,
    )
    return font_service.create_font(
        session, data, file.filename or "font.woff2", mime, content
    )


@router.put("/{font_id}", response_model=FontOut)
def update_font(
    font_id: int,
    data: FontUpdate,
    session: Session = Depends(get_session),
    _: dict = Depends(get_current_user),
):
    return font_service.update_font(session, font_id, data)


@router.post("/{font_id}/file", response_model=FontOut)
async def replace_font_file(
    font_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    _: dict = Depends(get_current_user),
):
    mime = file.content_type or "application/octet-stream"
    if mime not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {mime}（仅 woff2/ttf/otf）")
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="字体文件不能超过 30MB")
    return font_service.replace_font_file(
        session, font_id, file.filename or "font.woff2", mime, content
    )


@router.post("/{font_id}/default", response_model=FontOut)
def set_default_font(
    font_id: int,
    session: Session = Depends(get_session),
    _: dict = Depends(get_current_user),
):
    return font_service.set_default_font(session, font_id)


@router.delete("/{font_id}")
def delete_font(
    font_id: int,
    session: Session = Depends(get_session),
    _: dict = Depends(get_current_user),
):
    # 先置空引用该字体的文章，避免外键约束卡删除
    from app.models import Post

    posts = session.exec(select(Post).where(Post.font_id == font_id)).all()
    for p in posts:
        p.font_id = None
        session.add(p)
    session.commit()

    font_service.delete_font(session, font_id)
    return {"ok": True}