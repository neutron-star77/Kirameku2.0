"""B 站收藏夹代理（悬浮音乐播放器取数用）。

浏览器直连 api.bilibili.com 会因 Origin 头触发风控 403（CORS 不可用、
JSONP 已下线），Cloudflare Worker 出口 IP 也会被 412 风控，所以由
NAS（国内家宽 IP）代拉。注意该接口 ps 上限是 20，传更大的值会返回
code -400——所以这里固定 ps=20 并在服务端自动翻页聚合。响应标注
s-maxage=600 让 BFF 边缘缓存 10 分钟，对 B 站的真实请求频率被压到
每 colo 每 10 分钟至多一批。
"""

from fastapi import APIRouter, HTTPException, Query, Response
import httpx
import math
import re

router = APIRouter(prefix="/api/bili-fav", tags=["B站收藏夹"])

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
_PAGE_SIZE = 20  # 该接口的硬上限，超过返回 code -400
_MAX_PAGES = 5  # 最多聚合 5 页 = 100 首，够用且可控


@router.get("")
async def get_fav_list(
    response: Response,
    media_id: str = Query(..., description="收藏夹 media_id（favlist 的 fid 参数）"),
    pn: int = Query(1, ge=1, le=_MAX_PAGES, description="起始页（默认第 1 页）"),
):
    digits = "".join(ch for ch in media_id if ch.isdigit())
    if not digits:
        raise HTTPException(400, "media_id 必须是数字")

    headers = {"user-agent": _UA, "referer": "https://space.bilibili.com/"}
    tracks: list[dict] = []
    title: str | None = None
    media_count = 0

    async with httpx.AsyncClient(timeout=10) as client:
        page = pn
        for _ in range(_MAX_PAGES):
            url = (
                "https://api.bilibili.com/x/v3/fav/resource/list"
                f"?media_id={digits}&pn={page}&ps={_PAGE_SIZE}&order=mtime&type=0"
            )
            try:
                r = await client.get(url, headers=headers)
            except httpx.HTTPError as e:
                raise HTTPException(502, f"bilibili 请求失败: {e}") from e
            if r.status_code != 200:
                raise HTTPException(502, f"bilibili http {r.status_code}")
            raw = r.json()
            if raw.get("code") != 0:
                raise HTTPException(502, f"bilibili code {raw.get('code')}: {raw.get('message')}")

            data = raw.get("data") or {}
            info = data.get("info") or {}
            title = info.get("title") or title
            media_count = int(info.get("media_count") or 0)
            medias = data.get("medias") or []
            tracks.extend(
                {
                    "bvid": str(m["bvid"]),
                    "title": re.sub(r"<[^>]*>", "", str(m.get("title") or "")),
                    "cover": str(m.get("cover") or "").replace("http://", "https://"),
                    "duration": int(m.get("duration") or 0),
                    "author": (m.get("upper") or {}).get("name"),
                }
                for m in medias
                if m.get("bvid")
            )
            # media_count 以首页为准；拉满或不足一页即停
            if page == pn:
                last_page = min(math.ceil(media_count / _PAGE_SIZE) if media_count else 1, _MAX_PAGES)
            if page >= last_page or len(medias) < _PAGE_SIZE:
                break
            page += 1

    # 让 BFF 边缘缓存 10 分钟（proxyWithCache 尊重上游 Cache-Control）
    response.headers["Cache-Control"] = "public, s-maxage=600, stale-while-revalidate=1800"
    return {
        "title": title,
        "mediaCount": media_count,
        "page": pn,
        "pageSize": _PAGE_SIZE,
        "tracks": tracks,
    }
