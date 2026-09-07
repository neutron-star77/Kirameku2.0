import uuid
from io import BytesIO
from pathlib import Path

import oss2
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from PIL import Image

from app.deps import get_current_user
from app.config import (
    OSS_ACCESS_KEY_ID,
    OSS_ACCESS_KEY_SECRET,
    OSS_BUCKET_NAME,
    OSS_ENDPOINT,
    OSS_CUSTOM_DOMAIN,
    OSS_PREFIX,
    OSS_ENABLED,
)

router = APIRouter(prefix="/api/upload", tags=["上传"])

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/svg+xml"}
MAX_SIZE = 10 * 1024 * 1024  # 10MB

LOCAL_UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"


def _get_bucket():
    auth = oss2.Auth(OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET)
    return oss2.Bucket(auth, OSS_ENDPOINT, OSS_BUCKET_NAME)


@router.post("/image")
async def upload_image(
    file: UploadFile = File(...),
    _: dict = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"不支持的文件类型: {file.content_type}")

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(400, "文件大小不能超过 10MB")

    # 检测方向
    orientation = "landscape"
    try:
        img = Image.open(BytesIO(content))
        w, h = img.size
        orientation = "landscape" if w >= h else "portrait"
    except Exception:
        pass

    # 生成文件名
    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "webp"
    filename = f"{uuid.uuid4().hex}.{ext}"

    if OSS_ENABLED:
        oss_key = f"{OSS_PREFIX}{filename}"
        bucket = _get_bucket()
        bucket.put_object(oss_key, content)
        url = f"{OSS_CUSTOM_DOMAIN}/{oss_key}"
    else:
        LOCAL_UPLOAD_DIR.mkdir(exist_ok=True)
        target = LOCAL_UPLOAD_DIR / filename
        target.write_bytes(content)
        url = f"/uploads/{filename}"

    return {"url": url, "orientation": orientation}
