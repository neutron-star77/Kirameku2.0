# -*- coding: utf-8 -*-
"""修复因 curl/GBK 编码错乱的中文文件/目录名"""
import os

base = r"F:\AI\projects\Kirameku"

def gbk_to_utf8(s: str) -> str:
    try:
        fixed = s.encode("gbk", errors="strict").decode("utf-8", errors="strict")
        return fixed
    except Exception as e:
        return None

print("===== 顶层目录映射 =====")
for name in os.listdir(base):
    fixed = gbk_to_utf8(name)
    if fixed and fixed != name:
        src = os.path.join(base, name)
        dst = os.path.join(base, fixed)
        print(f"  {name!r}  ->  {fixed!r}")
        try:
            os.rename(src, dst)
            print("    [RENAMED OK]")
        except Exception as e:
            print(f"    [FAILED] {e}")

print("===== docs/images 文件映射 =====")
docs_img = os.path.join(base, "docs", "images")
if os.path.isdir(docs_img):
    for name in os.listdir(docs_img):
        fixed = gbk_to_utf8(name)
        if fixed and fixed != name:
            src = os.path.join(docs_img, name)
            dst = os.path.join(docs_img, fixed)
            print(f"  {name!r}  ->  {fixed!r}")
            try:
                os.rename(src, dst)
                print("    [RENAMED OK]")
            except Exception as e:
                print(f"    [FAILED] {e}")

print("===== 其他目录里的乱码名 =====")
for dirpath, dirs, files in os.walk(base):
    for d in dirs:
        fixed = gbk_to_utf8(d)
        if fixed and fixed != d:
            print(f"  DIR {d!r} -> {fixed!r}")
    for f in files:
        fixed = gbk_to_utf8(f)
        if fixed and fixed != f:
            print(f"  FILE {os.path.join(dirpath, f)!r} -> {fixed!r}")

print("DONE")