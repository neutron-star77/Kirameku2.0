# -*- coding: utf-8 -*-
"""修复剩余字节错位的中文名 + 全盘扫描非 ASCII 名"""
import os

base = r"F:\AI\projects\Kirameku"

# 1) docs/images 两个错位文件名
docs_img = os.path.join(base, "docs", "images")
manual = {
    "璇磋.png": "说说.png",
    "鐓х墖澧_png": "照片墙.png",
    "鐓х墖澧.png": "照片墙.png",
}
if os.path.isdir(docs_img):
    for name in os.listdir(docs_img):
        if name in manual:
            src = os.path.join(docs_img, name)
            dst = os.path.join(docs_img, manual[name])
            try:
                os.rename(src, dst)
                print(f"[OK] docs {name!r} -> {manual[name]!r}")
            except Exception as e:
                print(f"[FAIL] docs {name!r}: {e}")

# 2) live2d 内部中文目录
live2d_dir = os.path.join(base, r"Kirameku\public\live2d\model\kp31\kp31_\destroy\鏇挎崲閰嶇疆")
target_dir = os.path.join(base, r"Kirameku\public\live2d\model\kp31\kp31_\destroy\替换配置")
if os.path.isdir(live2d_dir):
    try:
        os.rename(live2d_dir, target_dir)
        print(f"[OK] live2d dir -> 替换配置")
    except Exception as e:
        print(f"[FAIL] live2d dir: {e}")

# 3) 全盘扫描：列出所有非 ASCII 名称（含文件名和目录名）
print("\n===== 全盘非 ASCII 名清单 =====")
count = 0
for dirpath, dirs, files in os.walk(base):
    # 跳过 node_modules / .next / venv 等
    if any(skip in dirpath for skip in ("node_modules", ".next", "venv", "__pycache__", ".git")):
        continue
    for d in dirs:
        if any(ord(ch) > 127 for ch in d):
            full = os.path.join(dirpath, d)
            print(f"DIR  {full}")
            count += 1
    for f in files:
        if any(ord(ch) > 127 for ch in f):
            full = os.path.join(dirpath, f)
            print(f"FILE {full}")
            count += 1
print(f"\n非 ASCII 名总数: {count}")
print("DONE")