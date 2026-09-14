"""seed_fonts — 把开源 OFL 古典字体下载、转 woff2、写入 font_asset 表

用法（在 Kirameku-backend 目录、venv 内）：
    pip install fonttools brotli
    DATABASE_URL=postgresql://... python scripts/seed_fonts.py --download-dir .fontdl

行为：
- 从 CDN 下载 3 款 OFL 字体（霞鹜文楷 / 思源宋体 / 思源黑体）
- fontTools 转成 woff2（体积约为原始 TTF/OTF 的 1/3），二进制写进 font_asset.file_data
- 按 family 去重：已存在则跳过（或 --force 覆盖文件与元信息）
- 不设 is_default：前台"未选字体"继续走现有默认豆腐块，行为零变化

瘦金体：目前没有可靠的 OFL 开源版本（方正瘦金书/三极瘦金简体均需商业授权），
故不内置。数据库结构天然支持后续追加——拿到合法授权文件后用
`POST /api/fonts`（multipart）或本脚本同结构扩展即可。
"""
import argparse
import io
import os
import sys
import tempfile
import shutil
import urllib.request
from pathlib import Path

FONTS = [
    {
        "name": "霞鹜文楷",
        "family": "LXGW WenKai",
        "role": "cjk",
        "weight": 400,
        "license_name": "OFL-1.1",
        "license_url": "https://github.com/lxgw/LxgwWenKai/blob/main/OFL.txt",
        "mime_type": "font/woff2",
        "url": "https://raw.githubusercontent.com/lxgw/LxgwWenKai/main/fonts/TTF/LXGWWenKai-Regular.ttf",
    },
    {
        "name": "思源宋体",
        "family": "Noto Serif CJK SC",
        "role": "serif",
        "weight": 400,
        "license_name": "OFL-1.1",
        "license_url": "https://github.com/notofonts/noto-cjk/blob/main/SERIF/LICENSE",
        "mime_type": "font/woff2",
        "url": "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Serif/OTF/SimplifiedChinese/NotoSerifCJKsc-Regular.otf",
    },
    {
        "name": "思源黑体",
        "family": "Noto Sans CJK SC",
        "role": "sans",
        "weight": 400,
        "license_name": "OFL-1.1",
        "license_url": "https://github.com/notofonts/noto-cjk/blob/main/LICENSE",
        "mime_type": "font/woff2",
        "url": "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf",
    },
]


def download(url: str, target: Path):
    print(f"[download] {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Kirameku-font-seed/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(target, "wb") as f:
        shutil.copyfileobj(r, f)
    print(f"           -> {target.name} ({target.stat().st_size / 1024 / 1024:.1f} MB)")


def to_woff2(src: Path, dst: Path):
    import fontTools.ttLib  # noqa: F401  # ensure import path
    from fontTools.ttLib import TTFont

    font = TTFont(str(src))
    font.flavor = "woff2"
    buf = io.BytesIO()
    font.save(buf)
    dst.write_bytes(buf.getvalue())
    print(f"[woff2]    {dst.name} ({dst.stat().st_size / 1024 / 1024:.1f} MB)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--download-dir", default=".fontdl", help="原始字体下载目录（默认 .fontdl）")
    parser.add_argument("--force", action="store_true", help="已存在的字体族也覆盖重写")
    args = parser.parse_args()

    base = Path(".").resolve()
    dl = Path(args.download_dir).resolve()
    dl.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("DATABASE_URL", os.environ.get("DATABASE_URL", ""))
    sys.path.insert(0, str(base))

    try:
        from sqlmodel import Session, select
        from app.database import engine
        from app.models import FontAsset
    except Exception as e:  # noqa: BLE001
        print(f"[fatal] 导入后端模块失败，请在 Kirameku-backend 目录、venv 内运行: {e}")
        sys.exit(1)

    created = skipped = 0
    with Session(engine) as session:
        for spec in FONTS:
            exist = session.exec(select(FontAsset).where(FontAsset.family == spec["family"])).first()
            if exist and not args.force:
                print(f"[skip]    {spec['family']} 已存在（--force 可覆盖）")
                skipped += 1
                continue

            tmp_in = dl / f"{spec['family'].replace(' ', '')}.{spec['url'].split('.')[-1]}"
            tmp_w2 = dl / f"{spec['family'].replace(' ', '')}.woff2"
            try:
                download(spec["url"], tmp_in)
                to_woff2(tmp_in, tmp_w2)
            except Exception as e:  # noqa: BLE001
                print(f"[skip]    {spec['family']} 下载/转换失败: {e}")
                continue

            data = tmp_w2.read_bytes()
            if exist:
                for k, v in spec.items():
                    if k != "url":
                        setattr(exist, k, v)
                exist.file_name = tmp_w2.name
                exist.file_size = len(data)
                exist.file_data = data
                session.add(exist)
            else:
                session.add(
                    FontAsset(
                        name=spec["name"],
                        family=spec["family"],
                        role=spec["role"],
                        weight=spec["weight"],
                        license_name=spec["license_name"],
                        license_url=spec["license_url"],
                        mime_type=spec["mime_type"],
                        file_name=tmp_w2.name,
                        file_size=len(data),
                        file_data=data,
                        enabled=True,
                        is_default=False,
                        sort=0,
                    )
                )
            created += 1
            print(f"[ok]      {spec['family']} -> font_asset (woff2 {len(data) / 1024 / 1024:.1f} MB)")

        session.commit()

    print(f"\n完成：新增/更新 {created} 款，跳过 {skipped} 款。")
    print("提示：瘦金体无 OFL 开源版未内置；获得合法授权后可用 POST /api/fonts 追加。")


if __name__ == "__main__":
    main()