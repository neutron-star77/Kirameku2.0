# -*- coding: utf-8 -*-
"""合并 backend/frontend/admin 三份图谱，补跨端 HTTP 边，写统一 knowledge-graph.json"""
import json, os

base = r"F:\AI\projects\Kirameku\docs\understand-anything"
raw = os.path.join(base, "raw")

def load(name):
    p = os.path.join(raw, name)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

backend = load("backend.json")
frontend = load("frontend.json")
admin = load("admin.json")

nodes = backend["nodes"] + frontend["nodes"] + admin["nodes"]
edges = backend["edges"] + frontend["edges"] + admin["edges"]

ids = {n["id"] for n in nodes}
print(f"节点: backend={len(backend['nodes'])} frontend={len(frontend['nodes'])} admin={len(admin['nodes'])} 合计={len(nodes)}")
print(f"边: backend={len(backend['edges'])} frontend={len(frontend['edges'])} admin={len(admin['edges'])} 合计={len(edges)}")

# 跨端 HTTP 调用映射：前端/后台 api 文件 -> 后端 api 文件
mapping = [
    # 前端
    ("frontend/app/api/posts.ts", "backend/app/api/posts.py"),
    ("frontend/app/api/categories.ts", "backend/app/api/categories.py"),
    ("frontend/app/api/chatters.ts", "backend/app/api/chatters.py"),
    ("frontend/app/api/comments.ts", "backend/app/api/comments.py"),
    ("frontend/app/api/messages.ts", "backend/app/api/messages.py"),
    ("frontend/app/api/albums.ts", "backend/app/api/albums.py"),
    ("frontend/app/api/bookmarks.ts", "backend/app/api/bookmarks.py"),
    ("frontend/app/api/friends.ts", "backend/app/api/friend_links.py"),
    ("frontend/app/api/projects.ts", "backend/app/api/projects.py"),
    ("frontend/app/api/site-config.ts", "backend/app/api/site_config.py"),
    ("frontend/app/api/client.ts", "backend/app/main.py"),
    # 后台
    ("admin/src/api/post.ts", "backend/app/api/posts.py"),
    ("admin/src/api/album.ts", "backend/app/api/albums.py"),
    ("admin/src/api/category.ts", "backend/app/api/categories.py"),
    ("admin/src/api/tag.ts", "backend/app/api/tags.py"),
    ("admin/src/api/comment.ts", "backend/app/api/comments.py"),
    ("admin/src/api/chatter.ts", "backend/app/api/chatters.py"),
    ("admin/src/api/message.ts", "backend/app/api/messages.py"),
    ("admin/src/api/friend-link.ts", "backend/app/api/friend_links.py"),
    ("admin/src/api/friendLink.ts", "backend/app/api/friend_links.py"),
    ("admin/src/api/project.ts", "backend/app/api/projects.py"),
    ("admin/src/api/siteConfig.ts", "backend/app/api/site_config.py"),
    ("admin/src/api/visitor.ts", "backend/app/api/visitors.py"),
    ("admin/src/api/bookmark.ts", "backend/app/api/bookmarks.py"),
    ("admin/src/api/dashboard.ts", "backend/app/api/dashboard.py"),
    ("admin/src/api/user.ts", "backend/app/api/auth.py"),
]

added = 0
skipped = []
for src, dst in mapping:
    if src in ids and dst in ids:
        edges.append({"source": src, "target": dst, "type": "api_call", "label": "HTTP 调用"})
        added += 1
    else:
        skipped.append((src, dst))

print(f"跨端边: 成功 {added} 条, 跳过(节点缺失) {len(skipped)} 条")
for s in skipped:
    print(f"  [跳过] {s}")

# 校验无悬空引用 & 无重复 id
assert len(ids) == len(nodes), "存在重复 node id"
dangling = [e for e in edges if e["source"] not in ids or e["target"] not in ids]
print(f"悬空边: {len(dangling)} 条")
for d in dangling:
    print(f"  [悬空] {d}")

result = {
    "meta": {
        "project": "Kirameku",
        "tool": "Understand Anything (内建多 Agent 分析)",
        "nodeCount": len(nodes),
        "edgeCount": len(edges),
        "layers": ["entry", "config", "router", "api", "service", "model", "schema", "utils", "deps",
                    "page", "layout", "component", "provider", "data", "widget", "view", "store"],
    },
    "nodes": nodes,
    "edges": edges,
}

out = os.path.join(base, "knowledge-graph.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=1)
print(f"\n已写入: {out}")
print(f"最终节点 {len(nodes)} / 边 {len(edges)}")