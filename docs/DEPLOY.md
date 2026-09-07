# Kirameku2.0 部署说明

> 目标架构：前端 Cloudflare Pages + 后端 NAS 自托管 + 域名 neutronstar.fun
> 更新日期：2026-09-08

## 一、端口清单（全部）

| 端口 | 服务 | 位置 | 对外暴露 |
|---|---|---|---|
| 23023 | SSH 登录 | NAS | 内网 |
| 55284 | QTS 管理面板 | NAS | 内网 |
| 9999 | 统一任务管理面板 | NAS | 内网 |
| 520 | 旧博客 Web 虚拟机（待下线） | NAS | 内网/IPv6 |
| **15432** | **PostgreSQL 容器**（映射自容器内 5432） | NAS Docker | 仅本机 |
| **8100** | **FastAPI 后端**（Kirameku-backend） | NAS | 仅 Tunnel |
| 18080 | Novel 阅读服务（可选） | NAS | 仅内网 |
| — | Next.js 前端 | **Cloudflare Pages** | 全球 CDN |
| — | API 代理 Worker | **Cloudflare Workers** | 全球 CDN |
| 443/80 | cloudflared Tunnel 出站 | NAS → CF | 出站连接 |

> 设计原则：NAS 只向内监听（8100 绑 127.0.0.1 或内网），公网访问一律经 Cloudflare Tunnel，**不开任何新公网入站端口**。

## 二、架构

```
浏览器 → https://neutronstar.fun (Cloudflare Pages 前端)
              │
              ├── /api/*  → CF Worker 代理
              │              │
              │              └── cloudflared Tunnel → NAS 127.0.0.1:8100 (FastAPI)
              │                                              │
              │                                              └── PostgreSQL (Docker, 宿主机 15432)
              │
              └── /uploads/* → 同上经 Worker/Tunnel 到 NAS uploads 目录
```

## 三、域名与 CF

| 域名 | 用途 | 指向 |
|---|---|---|
| neutronstar.fun | 主站 | Cloudflare Pages（CNAME/托管） |
| kirameku-api.neutronstar.fun | 后端 API（Tunnel 域名） | Cloudflare Tunnel |

- CF Token：账户 d4add8ad...（已验证 active）
- 旧部署下线：阿里云宝塔旧站、旧 CF Pages/Vercel 项目、520 虚拟机 Typecho（已 500）

## 四、NAS 环境（已确认）

- Docker 27.1.2-qnap8（container-station）
- Python3.12 + pip3（/share/CACHEDEV1_DATA/.qpkg/Python3/opt/python3/bin/）
- 无 cloudflared（需安装）
- 无 PostgreSQL qpkg（用 Docker 容器）

## 五、数据库

- 容器：`postgres:16`，容器内 5432，宿主机映射 **15432**
- 库名：kirameku；用户：postgres；密码：部署时生成（存 .env，不入 git）
- 连接串：`postgresql://postgres:<密码>@127.0.0.1:15432/kirameku`
- 初始化：`init_db.sql`

## 六、后端（NAS 8100）

- 依赖：`pip3 install -r requirements.txt`（fastapi/uvicorn/sqlmodel/psycopg2/oss2 等）
- 运行：`uvicorn app.main:app --host 127.0.0.1 --port 8100`
- OSS 已改双模式：无 Key 时图片存 NAS `uploads/`，经 `/uploads/` 服务
- 前端 rewrites：`/api/*` → `127.0.0.1:8100`，`/uploads/*` → 同后端

## 七、前端（CF Pages）

- 源码 `Kirameku/`，Next.js 16，apiBaseUrl 留空走同源 /api
- 部署：CF Pages 连接 GitHub 仓库 Kirameku2.0，构建命令 `pnpm build`
- Worker 路由：`/api/*`、`/uploads/*` → 代理到 Tunnel 域名

## 八、本地（台式机）

- 项目根：`F:\AI\projects\Kirameku2.0`（git 仓库 + 备份）
- 代码与 NAS 同步；.env 只存在于部署环境，不入 git
- 数据库备份：`pg_dump` → 台式机存档

## 九、待办

- [ ] git 提交并推 GitHub
- [ ] CF Pages 绑定仓库
- [ ] NAS Docker 起 PostgreSQL
- [ ] NAS pip3 装依赖 + 起后端
- [ ] NAS 装 cloudflared + Tunnel
- [ ] CF Worker 部署
- [ ] 域名绑定 neutronstar.fun
- [ ] 下线旧部署
