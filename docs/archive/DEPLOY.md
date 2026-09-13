# Kirameku2.0 部署说明

> 目标架构：Astro 前端部署到 Cloudflare Pages，Worker BFF 做边缘代理与缓存，FastAPI + PostgreSQL 保留在 NAS。
> 正式域名：`https://neutronstar.fun`；`https://www.neutronstar.fun` 301 重定向到根域。
> 更新日期：2026-09-09（Astro Pages、Worker BFF、根域切换已完成）

## 一、端口清单（全部）

| 端口 | 服务 | 位置 | 对外暴露 |
|---|---|---|---|
| 23023 | SSH 登录 | NAS | 内网 |
| 55284 | QTS 管理面板 | NAS | 内网 |
| 9999 | 统一任务管理面板 | NAS | 内网 |
| ~~520~~ | 旧 Typecho 站点（已下线 2026-09-08，文件保留 /share/Web/typecho） | NAS | 已停 |
| **15432** | **PostgreSQL 容器**（kirameku-pg 容器内 5432） | NAS Docker | 仅本机 |
| **8100** | **FastAPI 后端**（kirameku/backend） | NAS uvicorn | 仅 Tunnel |
| **3000** | 旧 Next.js 前端（保留源码，不再作为正式主站） | NAS Docker | 不再对外 |
| 18080 | Novel 阅读服务（可选） | NAS | 仅内网 |
| 443/80 | cloudflared Tunnel 出站 | NAS → CF | 出站连接 |

> NAS 只向内监听，公网访问一律经 Cloudflare Tunnel，无新公网入站端口。

## 二、架构

```
浏览器 → https://neutronstar.fun (Cloudflare Tunnel)
              │
              ├── neutronstar.fun / www → Cloudflare Pages（Astro）
              │        └── 前端请求 → bff.neutronstar.fun
              ├── bff.neutronstar.fun → Cloudflare Worker BFF
              │        └── kirameku-api.neutronstar.fun → NAS FastAPI
              └── PostgreSQL (Docker, 宿主机 15432)
```

## 三、域名与 CF

| 域名 | 用途 | 指向 |
|---|---|---|
| neutronstar.fun | 主站（Astro） | Cloudflare Pages 项目 `neutronstar-web` |
| www.neutronstar.fun | 主站别名 | Cloudflare Redirect Rule → 根域 |
| bff.neutronstar.fun | 边缘 API | Cloudflare Worker `kirameku-bff` |
| kirameku-api.neutronstar.fun | 后端 API | Cloudflare Tunnel → NAS 8100 |

- Tunnel：`kirameku-api`（id `710bfae8-...`，token 托管模式），仅负责 FastAPI 源站
- Worker：`kirameku-bff`，自定义域名 `bff.neutronstar.fun`
- 旧 Pages 项目 `neutronstar` 已删除；旧 Next/Vite 页面不再作为正式入口

## 四、NAS 环境（已确认）

- Docker 27.1.2-qnap8（container-station）
- Python3.12 + pip3（/share/CACHEDEV1_DATA/.qpkg/Python3/opt/python3/bin/）
- Node 22（便携版解压于 /share/CACHEDEV1_DATA/kirameku/node，构建在 Docker 内完成）
- cloudflared 2026.8.3（/share/CACHEDEV1_DATA/kirameku/bin/）
- 无 PostgreSQL qpkg（用 Docker 容器）

## 五、数据库

- 容器：`postgres:16`，容器内 5432，宿主机映射 **15432**
- 库名：kirameku；用户：postgres；密码：部署时生成（存 .env，不入 git）
- 连接串：`postgresql://postgres:<密码>@127.0.0.1:15432/kirameku`
- 初始化：`init_db.sql`

## 六、后端（NAS 8100）

- 依赖：`backend/venv/bin/pip install --only-binary :all: -r requirements.txt`（fastapi/uvicorn/sqlmodel/psycopg2-binary；oss2 需单独源码装）
- 运行：`backend/start_backend.sh`（setsid uvicorn app.main:app --host 127.0.0.1 --port 8100），crontab @reboot
- OSS 已改双模式：无 Key 时图片存 NAS `uploads/`，经 `/uploads/` 服务
- 前端 rewrites：`/api/*`、`/uploads/*` → 公网隧道 `kirameku-api.neutronstar.fun`
- 坑：passlib 1.7.4 需 bcrypt==4.0.1（否则登录 500）；init_db.sql 初始 admin 哈希无效，已用应用 hash_password 重设 admin123

## 七、前端（NAS 容器 3000）

- 源码 `Kirameku/`，Next.js 16，apiBaseUrl 留空走同源 /api；next.config 的 /api、/uploads rewrites 指向公网隧道
- 部署：`Kirameku/Dockerfile` → 镜像 `kirameku-fe:latest`（容器 --restart always，`127.0.0.1:3000:3000`）
- 首页服务端 fetch 兜底 `NEXT_PUBLIC_API_URL` 已设为隧道域名
- 更新方法：改源码 → 本地 `pnpm install`/改 `Dockerfile` → 推送 Kirameku/ 到 NAS → docker build → docker rm/run 重建

## 八、本地（台式机）

- 项目根：`F:\AI\projects\Kirameku2.0`（git 仓库 + 备份）
- 代码与 NAS 同步；.env/密码/token 只在部署机理解（NAS /share/CACHEDEV1_DATA/kirameku/），不入 git
- 数据库备份：`pg_dump` → 台式机存档
- NAS 统一入口：`ssh admin@hewll`(uid=0)；docker 在 `/share/CACHEDEV1_DATA/.qpkg/container-station/bin/docker`（不在 PATH）

## 九、待办

- [x] NAS Docker 起 PostgreSQL
- [x] NAS pip3 装依赖 + 起后端 8100 + crontab 自启
- [x] NAS cloudflared + Tunnel + DNS + ingress
- [x] 前端 Docker 容器 3000 + 主站公网上线
- [x] git 本地提交（含 .gitignore 排除密钥/构建产物）
- [x] 推送 GitHub（源码约 11MB；live2d 213MB 不入库，源在 `F:\AI\projects\Kirameku`，仓库 neutron-star77/Kirameku2.0）
- [x] 下线 NAS 旧 Typecho（520，文件保留，vhost 已注释 + 备份）
- [x] 下线旧 CF Pages 项目 `neutronstar` 并迁移根域
- [x] `www.neutronstar.fun` 统一 301 到 `neutronstar.fun`
- [x] 台式机 pg_dump 时序备份（NAS cron 每日 03:30 保留 30 份；首份已于 2026-09-08 拉回 `backups/db/`）
