# AGENTS.md

Kirameku2.0 —— 个人全栈博客工程 **Neutronstar（neutronstar.fun）**：Shirone 外壳（Astro 7 + Svelte 5 + React 19 islands，Cloudflare Workers SSR）+ BFF 边缘层（缓存/聚合/SSE）+ NAS FastAPI/PostgreSQL 后端，前后端分离、发布即实时生效。

## 📇 文档导航（AI 必读第一步，省 token）

**接到任务先读 [`docs/README.md`](docs/README.md)**（本协议在 CLAUDE.md / GEMINI.md / .cursorrules / .windsurfrules / .github/copilot-instructions.md 有同步副本——修改阅读协议后任改一份并 cp 同步其余）（文档索引 + 30 秒现状 + 任务路由表），然后**只读路由表指定的文档/小节**：

- 改代码前 → 按场景读 [`docs/坑大全.md`](docs/坑大全.md) 对应分区（40+ 踩坑，现象→原因→解法）
- 部署/排障/查凭据 → [`docs/命令与运维速查.md`](docs/命令与运维速查.md)
- 用户问用法/内容去向 → [`docs/站点功能与使用说明.md`](docs/站点功能与使用说明.md)
- 了解项目全貌/历史 → [`docs/项目全景与开发史.md`](docs/项目全景与开发史.md)
- 某阶段的实现细节 → [`docs/HANDOFF-续开发交接文档.md`](docs/HANDOFF-续开发交接文档.md) §4 对应小节（**禁止通读全文**，700 行档案）

```
web/               前端（独立 git 仓，main 分支，push 即 CI 部署上线）
worker-bff/        BFF 边缘层（Cloudflare Worker：缓存/聚合/SSE/Durable Object）
Kirameku-backend/  后端：FastAPI + SQLModel + PostgreSQL；admin/ = vue-pure-admin 7 管理后台
docs/              文档（入口 = docs/README.md）
scripts/           NAS 运维脚本（rebuild-backend / start-tunnel 等）
```

## 约定

- 数据一律经 HTTP API 获取，前端不内置写死内容数据（例外：追番页 `web/src/data/anime.ts` 静态数据）。
- 复刻外部主题时只参考公开演示的视觉/交互，代码自研。
- **新功能组件先查开源轮子**（npm/GitHub 有无成熟实现），给出「自研/借用/借鉴」对比结论并写进对应 issue 后再动手（先例：悬浮播放器对比 vue3-music-player——island 栈为 React 19 + Svelte 5 不引 Vue 组件，功能无缺失，保留自研）。
- 后端改造集中在 Alembic 迁移、权限加固、缓存失效 webhook。
- **三条铁律**：① 不碰 NAS 的 `kirameku-pg` 容器与数据卷；② 不 `git add -A`（显式路径）；③ 密钥/`.env` 绝不入库。
- 改完必须验证：前端 build+preview（dev 不可用）；SSR 页面验证响应完整性（footer 次数，不能用 `</html>` 判断）。

## Agent skills

### Issue tracker

Issues and PRDs live in this repo's GitHub Issues (`neutron-star77/Kirameku2.0`), driven by the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The default five-role vocabulary, label string equal to role name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one root `CONTEXT.md` plus `docs/adr/`. See `docs/agents/domain.md`.
