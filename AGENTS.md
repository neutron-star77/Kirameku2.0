# AGENTS.md

Kirameku2.0 —— 个人全栈博客工程。目标形态：**Astro 主站（内容展示）+ Next 应用区（重型交互）+ FastAPI 后端**，前后端分离、发布即实时生效。

```
Kirameku/          前端 A：Next.js 16 + React 19 + Tailwind 4 + Framer Motion（应用区：novel/garden/practice/music）
Kirameku-backend/  后端：FastAPI + SQLModel + PostgreSQL；admin/ = vue-pure-admin 7 管理后台
docs/              部署与方案文档
```

约定：
- 数据一律经 HTTP API 获取，前端不内置写死内容数据。
- 复刻外部主题时只参考公开演示的视觉/交互，代码自研。
- 后端改造集中在 Alembic 迁移、权限加固、缓存失效 webhook。

## Agent skills

### Issue tracker

Issues and PRDs live in this repo's GitHub Issues (`neutron-star77/Kirameku2.0`), driven by the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The default five-role vocabulary, label string equal to role name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one root `CONTEXT.md` plus `docs/adr/`. See `docs/agents/domain.md`.
