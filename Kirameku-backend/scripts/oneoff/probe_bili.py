"""临时诊断：容器内直连 B 站，测试不同头组合下的返回。"""
import asyncio
import httpx

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
URL = "https://api.bilibili.com/x/v3/fav/resource/list?media_id=3631802308&pn=1&ps=3&order=mtime&type=0"


async def probe(name: str, headers: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(URL, headers=headers)
            body = r.json()
            print(f"{name}: http={r.status_code} code={body.get('code')} msg={body.get('message')}")
    except Exception as e:  # noqa: BLE001
        print(f"{name}: EXC {type(e).__name__} {e}")


async def main() -> None:
    await probe("A-仅UA", {"user-agent": UA})
    await probe("B-UA+referer", {"user-agent": UA, "referer": "https://space.bilibili.com/"})
    await probe(
        "C-全套浏览器头",
        {
            "user-agent": UA,
            "referer": "https://space.bilibili.com/90898408/favlist?fid=3631802308&ftype=create",
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9",
            "origin": "https://space.bilibili.com",
        },
    )
    await probe("D-空 headers", {})


asyncio.run(main())
