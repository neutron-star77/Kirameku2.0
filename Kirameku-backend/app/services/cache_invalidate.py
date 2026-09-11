"""边缘缓存失效：发布/修改内容后通知 BFF 清缓存。

fire-and-forget：BFF 不可达或未配置密钥时静默跳过，绝不阻塞主流程。
NAS 容器需要在环境变量里配置 REVALIDATE_SECRET 与 BFF_ORIGIN 后才会真正生效；
未配置时本模块是 no-op，页面靠 BFF 的 s-maxage TTL 兜底更新。
"""

import hashlib
import hmac
import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)

BFF_ORIGIN = os.getenv("BFF_ORIGIN", "https://bff.neutronstar.fun")
SECRET = os.getenv("REVALIDATE_SECRET", "")


def invalidate_cache(tags: list[str], urls: list[str] | None = None) -> None:
    """按 tag/URL 清 BFF 边缘缓存。tags 例：posts / moments / albums / site。"""
    if not SECRET:
        return
    payload = {"tags": tags, "urls": urls or []}
    body = json.dumps(payload, separators=(",", ":"))
    signature = hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    try:
        httpx.post(
            f"{BFF_ORIGIN}/internal/revalidate",
            content=body,
            headers={
                "x-signature": signature,
                "content-type": "application/json",
            },
            timeout=3,
        )
    except Exception:  # noqa: BLE001 - 缓存失效失败不影响写操作
        logger.warning("cache invalidate failed (BFF unreachable?)", exc_info=True)
