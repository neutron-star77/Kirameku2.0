"""一次性脚本：把 fastimage 图床的 234 张鬼刀图导入相册表。

数据源：F:/projects/fastimage/鬼刀图床链接.md（jsDelivr CDN 清单）
分组：6 个相册，每个 39 张（HANDOFF 定的划分）
幂等：album 按 title 查重；photo 按 (album_id, url) 查重，重复跑不重复插入。
连接：本机直连 NAS PostgreSQL（15432 对外映射），URL 从抢救的 backend.env 读，
      host:port 替换为 NAS 局域网地址。

用法：
  cd Kirameku-backend
  .venv/Scripts/python.exe scripts/oneoff/import_fastimage.py [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import psycopg2

BACKEND_ROOT = Path(__file__).resolve().parents[2]  # .../Kirameku2.0/Kirameku-backend
REPO_ROOT = BACKEND_ROOT.parent  # .../Kirameku2.0
LINKS_MD = REPO_ROOT.parent / "fastimage" / "鬼刀图床链接.md"  # 兄弟仓库 fastimage
ENV_TXT = REPO_ROOT / "backups" / "rescue-from-duplicates" / "backend.env.txt"

NAS_DB_HOST = "192.168.5.4"
NAS_DB_PORT = "15432"

ALBUM_PREFIX = "鬼刀画集"
CHUNK = 39


def read_database_url() -> str:
    # 优先用从 NAS 运行容器里导出的真实连接串（docker inspect，
    # 已存 backups/rescue-from-duplicates/nas-db.env.txt，gitignored）
    live = ENV_TXT.parent / "nas-db.env.txt"
    source = live if live.exists() else ENV_TXT
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL="):
            url = line.split("=", 1)[1].strip()
            # 容器内地址 → NAS 局域网地址
            url = re.sub(r"@[^\:@/]+:\d+/", f"@{NAS_DB_HOST}:{NAS_DB_PORT}/", url)
            return url
    raise SystemExit(f"DATABASE_URL not found in {source}")


def parse_links() -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    for line in LINKS_MD.read_text(encoding="utf-8").splitlines():
        m = re.match(
            r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|[^|]+\|\s*(https://\S+)\s*\|\s*$",
            line,
        )
        if m:
            rows.append((int(m.group(1)), m.group(3)))
    rows.sort(key=lambda r: r[0])
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    links = parse_links()
    if len(links) != 234:
        print(f"[warn] expected 234 links, got {len(links)}")
    print(f"parsed {len(links)} links from {LINKS_MD.name}")

    groups = [links[i : i + CHUNK] for i in range(0, len(links), CHUNK)]
    album_names = [
        f"{ALBUM_PREFIX} {roman}" for roman in ["I", "II", "III", "IV", "V", "VI"]
    ][: len(groups)]

    conn = psycopg2.connect(read_database_url())
    cur = conn.cursor()

    inserted_albums = 0
    inserted_photos = 0
    skipped_photos = 0

    try:
        for idx, (name, group) in enumerate(zip(album_names, groups)):
            cur.execute("SELECT id FROM album WHERE title = %s", (name,))
            row = cur.fetchone()
            if row:
                album_id = row[0]
                print(f"[album] exists: {name} (id={album_id})")
            else:
                if args.dry_run:
                    print(f"[album] would create: {name} ({len(group)} photos)")
                    continue
                cur.execute(
                    "INSERT INTO album (title, description, cover, photo_count, sort) "
                    "VALUES (%s, %s, %s, 0, %s) RETURNING id",
                    (
                        name,
                        f"鬼刀（WLOP）画集，jsDelivr 图床，第 {idx + 1} 册（{len(group)} 张）",
                        group[0][1],
                        idx + 1,
                    ),
                )
                album_id = cur.fetchone()[0]
                inserted_albums += 1
                print(f"[album] created: {name} (id={album_id})")

            count = 0
            for order, (_seq, url) in enumerate(group):
                cur.execute(
                    "SELECT 1 FROM photo WHERE album_id = %s AND url = %s",
                    (album_id, url),
                )
                if cur.fetchone():
                    skipped_photos += 1
                    continue
                if not args.dry_run:
                    cur.execute(
                        "INSERT INTO photo (album_id, url, caption, orientation, sort) "
                        "VALUES (%s, %s, '', 'landscape', %s)",
                        (album_id, url, order),
                    )
                count += 1
            inserted_photos += count
            if not args.dry_run:
                cur.execute(
                    "UPDATE album SET photo_count = ("
                    "SELECT COUNT(*) FROM photo WHERE album_id = %s), "
                    "updated_at = NOW() WHERE id = %s",
                    (album_id, album_id),
                )
            print(f"  photos: +{count} new, {skipped_photos} skipped so far")

        if not args.dry_run:
            conn.commit()
            print(
                f"DONE: {inserted_albums} albums created, "
                f"{inserted_photos} photos inserted, {skipped_photos} skipped"
            )
        else:
            print("DRY-RUN: no changes written")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
