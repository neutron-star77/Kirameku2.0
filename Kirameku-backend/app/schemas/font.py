"""font 字体相关 Schema（不含二进制文件数据，file_data 仅通过 /file 接口流式下发）"""
from pydantic import BaseModel


class FontOut(BaseModel):
    id: int
    name: str
    family: str
    role: str = "cjk"
    weight: int = 400
    license_name: str = ""
    license_url: str = ""
    file_name: str = ""
    mime_type: str = "font/woff2"
    file_size: int = 0
    enabled: bool = True
    is_default: bool = False
    sort: int = 0


class FontCreate(BaseModel):
    name: str
    family: str
    role: str = "cjk"
    weight: int = 400
    license_name: str = ""
    license_url: str = ""
    is_default: bool = False
    sort: int = 0


class FontUpdate(BaseModel):
    name: str | None = None
    family: str | None = None
    role: str | None = None
    weight: int | None = None
    license_name: str | None = None
    license_url: str | None = None
    enabled: bool | None = None
    is_default: bool | None = None
    sort: int | None = None