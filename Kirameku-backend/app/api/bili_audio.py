"""B 站音频流代理：悬浮播放器的**回退音频源**。

主音频源 = GitHub 仓 `neutron-star77/bilimusic`（audio/{bvid}.mp3，jsdelivr
CDN 直拉，零风控零带宽）。本端点仅在 GitHub 上没有对应音频文件的曲目时
由前端回退调用（新收藏的歌曲还没来得及转码上传）。

链路（全部由 NAS 后端代发，B 站对浏览器直连/CF 出口均有风控，坑 6.3.19）：
  1. GET frontend/finger/spi 拿合法 buvid3/buvid4（**必须**：随机 UUID 的
     buvid3 会触发 412 风控页——2026 年起 B 站校验 buvid 有效性，实测）
  2. GET view?bvid=             拿 P1 cid（按 bvid 缓存，cid 不变）
  3. GET playurl?platform=html5 拿 360P mp4 durl 直链（按 bvid 缓存 30 分钟，
     直链自带过期签名）；mp4 容器含 AAC 音轨，前端 <audio> 可直接播放
  4. 本端点把上游流转发给浏览器：透传 Range（seek 必需）、206/Content-Range

升级 dash 高码率纯音频需登录 SESSDATA，留待后续（fnval=16 → dash.audio[]）。
"""

import logging
import threading
import time

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bili-audio", tags=["B 站音频"])

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_REFERER = "https://www.bilibili.com/"
_TIMEOUT = httpx.Timeout(15.0, read=60.0)
_URL_TTL = 30 * 60

_lock = threading.RLock()  # 可重入：_ensure_buvid 持锁内会再调 _get_client（也拿锁），Lock 会死锁
_client: httpx.Client | None = None
_buvid_ready = False
_cid_cache: dict[str, int] = {}
_url_cache: dict[str, tuple[str, float]] = {}


def _get_client() -> httpx.Client:
    global _client
    with _lock:
        if _client is None:
            _client = httpx.Client(
                timeout=_TIMEOUT,
                headers={"User-Agent": _UA, "Referer": _REFERER},
                follow_redirects=True,
            )
        return _client


def _ensure_buvid() -> None:
    """拿合法 buvid3/buvid4 写进会话 Cookie（进程内一次）。"""
    global _buvid_ready
    with _lock:
        if _buvid_ready:
            return
        client = _get_client()
        spi = client.get("https://api.bilibili.com/x/frontend/finger/spi").json()
        b3 = spi["data"]["b_3"]
        b4 = spi["data"]["b_4"]
        client.headers["Cookie"] = f"buvid3={b3}; buvid4={b4}"
        _buvid_ready = True
        logger.info("bili-audio buvid ready: %s...", b3[:12])


def _get_json(url: str, tag: str) -> dict:
    """带重试的 GET JSON（B 站偶发 412/空响应，退避重试基本可解）。"""
    client = _get_client()
    last = ""
    for attempt in range(3):
        r = client.get(url)
        try:
            data = r.json()
        except Exception:
            last = f"{tag}: status={r.status_code} body={r.text[:80]!r}"
        else:
            if data.get("code") == 0:
                return data
            last = f"{tag}: code={data.get('code')} {data.get('message')}"
        time.sleep(2 + 2 * attempt)
    raise RuntimeError(last or f"{tag}: exhausted")


def _resolve_url(bvid: str) -> str:
    cached = _url_cache.get(bvid)
    if cached and cached[1] > time.time():
        return cached[0]
    _ensure_buvid()
    cid = _cid_cache.get(bvid)
    if not cid:
        v = _get_json(
            f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}", "view"
        )
        cid = v["data"]["cid"]
        _cid_cache[bvid] = cid
    p = _get_json(
        f"https://api.bilibili.com/x/player/playurl"
        f"?bvid={bvid}&cid={cid}&platform=html5&high_quality=1",
        "playurl",
    )
    durl = (p.get("data") or {}).get("durl") or []
    if not durl:
        raise RuntimeError("playurl returned no durl")
    url = durl[0]["url"]
    _url_cache[bvid] = (url, time.time() + _URL_TTL)
    return url


@router.get("")
def stream_audio(bvid: str, request: Request):
    if not bvid:
        return JSONResponse({"error": "bvid required"}, status_code=400)

    try:
        url = _resolve_url(bvid)
    except Exception as exc:  # noqa: BLE001 - 上游任何风控/网络问题都降级为错误态
        logger.warning("bili-audio resolve failed: %s", exc)
        return JSONResponse({"error": "resolve failed"}, status_code=502)

    client = _get_client()
    forward_headers: dict = {}
    range_header = request.headers.get("range")
    if range_header:
        forward_headers["Range"] = range_header

    opened = None
    try:
        opened = client.stream("GET", url, headers=forward_headers)
        resp = opened.__enter__()
    except Exception as exc:  # noqa: BLE001
        logger.warning("bili-audio upstream connect failed: %s", exc)
        return JSONResponse({"error": "upstream failed"}, status_code=502)

    status = resp.status_code
    if status not in (200, 206):
        opened.__exit__(None, None, None)
        return JSONResponse({"error": f"upstream status {status}"}, status_code=502)

    passthrough: dict = {"cache-control": "public, max-age=3600"}
    for key in ("content-range", "content-length", "content-type", "accept-ranges"):
        if resp.headers.get(key):
            passthrough[key] = resp.headers[key]
    passthrough.setdefault("accept-ranges", "bytes")
    passthrough.setdefault("content-type", "audio/mp4")

    def chunks():
        try:
            with opened:
                for chunk in resp.iter_bytes(chunk_size=64 * 1024):
                    yield chunk
        except Exception:  # noqa: BLE001 - 客户端断开/上游中断
            logger.debug("bili-audio stream aborted", exc_info=True)

    return StreamingResponse(chunks(), status_code=status, headers=passthrough)
