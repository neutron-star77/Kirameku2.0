"""font_asset 字体资源表：开源古典字体文件二进制入库，供文章正文按字体渲染

字段说明：
- role: 字体风格分组（serif 衬线 / sans 黑体 / cjk 楷体 / script 书法），前端按组展示
- file_data: woff2 二进制（入库前已由 seed 脚本/后台用 fontTools 子集化或转换）
- is_default: 未选字体的文章使用的默认字体标记（仅允许一行）
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, LargeBinary
from sqlmodel import SQLModel, Field


class FontAsset(SQLModel, table=True):
    __tablename__ = "font_asset"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=64)  # 展示名，如"霞鹜文楷"
    family: str = Field(max_length=128, unique=True)  # CSS font-family，如"LXGW WenKai"
    role: str = Field(default="cjk", max_length=20, index=True)  # serif/sans/cjk/script
    weight: int = Field(default=400)
    license_name: str = Field(default="", max_length=128)  # 如 OFL-1.1
    license_url: str = Field(default="", max_length=300)
    file_name: str = Field(default="", max_length=128)  # 原文件显示名
    mime_type: str = Field(default="font/woff2", max_length=64)
    file_size: int = Field(default=0)
    file_data: bytes = Field(default=b"", sa_column=Column(LargeBinary, nullable=True))
    enabled: bool = Field(default=True)
    is_default: bool = Field(default=False)
    sort: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)