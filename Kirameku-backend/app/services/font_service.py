"""font_asset 字体资源的读写服务。

文件二进制（file_data）只在 /file 接口流式下发，读写列表接口一律不带
file_data 字段（单条可能 1-5MB，塞进 JSON 列表会爆响应体）。
"""
from datetime import datetime

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import FontAsset
from app.schemas.font import FontCreate, FontUpdate


def _to_dict(font: FontAsset, include_data: bool = False) -> dict:
    d = {
        "id": font.id,
        "name": font.name,
        "family": font.family,
        "role": font.role,
        "weight": font.weight,
        "license_name": font.license_name,
        "license_url": font.license_url,
        "file_name": font.file_name,
        "mime_type": font.mime_type,
        "file_size": font.file_size,
        "enabled": font.enabled,
        "is_default": font.is_default,
        "sort": font.sort,
    }
    if include_data and font.file_data:
        d["file_data"] = font.file_data
    return d


def _ensure_single_default(session: Session, keep_id: int | None = None):
    """is_default 只允许一篇（一行）为真，其余一律复位。"""
    defaults = session.exec(select(FontAsset).where(FontAsset.is_default == True)).all()
    for f in defaults:
        if f.id != keep_id:
            f.is_default = False
            session.add(f)


def list_fonts(session: Session, enabled_only: bool = False) -> list[dict]:
    q = select(FontAsset)
    if enabled_only:
        q = q.where(FontAsset.enabled == True)
    fonts = session.exec(q.order_by(FontAsset.sort, FontAsset.id)).all()
    return [_to_dict(f) for f in fonts]


def get_font(session: Session, font_id: int) -> FontAsset:
    font = session.get(FontAsset, font_id)
    if not font:
        raise HTTPException(status_code=404, detail="字体不存在")
    return font


def get_font_file(session: Session, font_id: int) -> tuple[FontAsset, bytes]:
    font = session.get(FontAsset, font_id)
    if not font:
        raise HTTPException(status_code=404, detail="字体不存在")
    if not font.file_data:
        raise HTTPException(status_code=404, detail="字体文件为空")
    return font, font.file_data


def create_font(session: Session, data: FontCreate, file_name: str, mime_type: str, file_bytes: bytes) -> dict:
    exists = session.exec(select(FontAsset).where(FontAsset.family == data.family)).first()
    if exists:
        raise HTTPException(status_code=400, detail=f"字体家族 {data.family} 已存在")
    is_default = data.is_default
    if is_default:
        _ensure_single_default(session)
    font = FontAsset(
        name=data.name,
        family=data.family,
        role=data.role,
        weight=data.weight,
        license_name=data.license_name,
        license_url=data.license_url,
        file_name=file_name,
        mime_type=mime_type or "font/woff2",
        file_size=len(file_bytes),
        file_data=file_bytes,
        is_default=is_default,
        sort=data.sort,
    )
    session.add(font)
    session.commit()
    session.refresh(font)
    return _to_dict(font)


def update_font(session: Session, font_id: int, data: FontUpdate) -> dict:
    font = session.get(FontAsset, font_id)
    if not font:
        raise HTTPException(status_code=404, detail="字体不存在")

    update_data = data.model_dump(exclude_unset=True)
    if "family" in update_data and update_data["family"] != font.family:
        dup = session.exec(
            select(FontAsset).where(FontAsset.family == update_data["family"], FontAsset.id != font_id)
        ).first()
        if dup:
            raise HTTPException(status_code=400, detail=f"字体家族 {update_data['family']} 已存在")

    if update_data.get("is_default"):
        _ensure_single_default(session, keep_id=font_id)

    for k, v in update_data.items():
        setattr(font, k, v)
    font.updated_at = datetime.now()
    session.add(font)
    session.commit()
    session.refresh(font)
    return _to_dict(font)


def replace_font_file(session: Session, font_id: int, file_name: str, mime_type: str, file_bytes: bytes) -> dict:
    font = session.get(FontAsset, font_id)
    if not font:
        raise HTTPException(status_code=404, detail="字体不存在")
    font.file_name = file_name
    font.mime_type = mime_type or "font/woff2"
    font.file_size = len(file_bytes)
    font.file_data = file_bytes
    font.updated_at = datetime.now()
    session.add(font)
    session.commit()
    session.refresh(font)
    return _to_dict(font)


def delete_font(session: Session, font_id: int):
    font = session.get(FontAsset, font_id)
    if not font:
        raise HTTPException(status_code=404, detail="字体不存在")
    session.delete(font)
    session.commit()


def set_default_font(session: Session, font_id: int):
    font = session.get(FontAsset, font_id)
    if not font:
        raise HTTPException(status_code=404, detail="字体不存在")
    if not font.enabled:
        raise HTTPException(status_code=400, detail="禁用的字体不能设为默认")
    _ensure_single_default(session, keep_id=font_id)
    font.is_default = True
    font.updated_at = datetime.now()
    session.add(font)
    session.commit()
    session.refresh(font)
    return _to_dict(font)