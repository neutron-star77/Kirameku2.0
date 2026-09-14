# 交接：字体系统 + 回顶按钮部署——未完成事项

> 面向接手 AI 的部署交接文档。生成时间 2026-09-14 17:05（Asia/Shanghai）。
> 任务背景：Neutronstar 博客（Kirameku2.0，neutronstar.fun）主题增强两项——①古文开源字体（霞鹜文楷/思源宋体/思源黑体）内嵌数据库 + 后台文章可选字体（不选则默认）；②右下角回顶按钮改为「绳子吊小动物（原创 SVG 小狐狸）」。

---

## 1. 一句话结论

**后端 / admin / BFF 三端已全部部署上线并验证通过；唯一硬阻塞是 web 前端仓 push 需要 GitHub 认证，CI 上线因此未触发。父仓 git 版本记录也未做。**

---

## 2. 已完成并验证 ✅

### 2.1 后端（NAS hewll，Docker）

- 镜像 `kirameku-backend:latest` 已重建：`requirements.txt` 增加 `fonttools>=4.50.0`、`brotli>=1.1.0`（seed 脚本转 woff2 依赖）；`Dockerfile` 增加 `COPY scripts ./scripts`（**接手时如重建镜像，这两处改动必须保留**）。
- Alembic 迁移应用成功：`0003_login_log -> 0004_font_asset`（font_asset 字体资源表 + post.font_id 文章级选字体）。
- 字体已入库（PostgreSQL `font_asset` 表，二进制 woff2 存 `file_data`）：

| id | name | family | size | license |
|---|---|---|---|---|
| 1 | 霞鹜文楷 | LXGW WenKai | 8,016,456 B | OFL-1.1 |
| 2 | 思源宋体 | Noto Serif CJK SC | 16,708,100 B | OFL-1.1 |
| 3 | 思源黑体 | Noto Sans CJK SC | 11,424,976 B | OFL-1.1 |

`is_default=false`（未选字体的文章零影响）。**瘦金体无可靠 OFL 开源版，未内置**（方正瘦金书/三极瘦金简体需商业授权）；数据库结构支持后台上传补充（woff2/ttf/otf，30MB 上限）。
- 容器状态：`kirameku-backend` Up（healthy），bridge 网络 IP `10.0.3.3`，端口 `8100:8000`，挂载 `kirameku_uploads:/app/uploads` + `/share/CACHEDEV1_DATA/Container/kirameku/backend/admin/dist:/app/admin/dist`，restart=unless-stopped。
- API 验证：
  - `GET /api/fonts` → 200（列表，不含二进制）
  - `GET /api/fonts/{id}/file` → 200，`font/woff2`，响应头 `Cache-Control: public, max-age=31536000, immutable`
  - 其余路由已在 openapi 确认：`/api/fonts/all`（后台全量）、`/api/fonts/{font_id}`、`/api/fonts/{font_id}/default`（设默认互斥）、上传/删除。

### 2.2 后台管理（admin，vue-pure-admin）

- `admin/src/api/font.ts`（新增）+ `admin/src/api/post.ts` + `admin/src/views/post/edit.vue`（文章编辑「正文字体」下拉，未选为空→默认字体）。
- dist 已重建并 SMB 全量同步到 NAS `U:\kirameku\backend\admin\dist`（147 文件），容器已 restart（inode 失效坑）。
- `GET /admin/` → 200。已验证 dist 产物含字体管理代码 chunk（`edit-B6248xpo.js` 等）。

### 2.3 BFF（Cloudflare Worker）

- `npx wrangler@4 deploy` 成功：`kirameku-bff`，Version ID `8ad5da42-68d1-49e1-a7ca-0512a867ef0c`，绑定 `bff.neutronstar.fun`。
- `src/index.ts` 的 `tagsForPath` 已加 `/api/fonts` → tag "fonts"。
- 公网验证：`https://bff.neutronstar.fun/api/fonts` → 200，三款字体正常。
- 已知限制：字体文件走 CF 边缘 60s 缓存（无 s-maxage），上传新字体后列表最多延迟 60s 出现；未做 active invalidate（可接受）。

---

## 3. 未完成项 ❗

### 3.1 【硬阻塞】web 前端仓 push（CI 上线前最后一步）

- web 仓（独立 git 仓，`F:\AI\projects\Kirameku2.0\web`，remote `https://github.com/neutron-star77/neutronstar-web.git`，分支 main，push 即 CI 部署）。
- 已 commit：`ff62e07 feat(theme): 文章级字体渲染(API@font-face动态注入) + 绳子吊小狐狸回顶按钮`（**未推送**）。
- 涉 3 文件（其余无改动）：
  1. `src/components/organisms/FloatingControls.astro` — 回顶按钮：FAB 透明化 + 原创 SVG（挂环→绳子→绳结→小狐狸），常态轻摆、hover 摆动+轻跳、点击「收绳」动画后平滑回顶，`prefers-reduced-motion` 降级，保留 aria-label/focus outline。
  2. `src/pages/posts/[slug].astro` — 动态注入 `@font-face`（未选字体的文章零注入）。
  3. `src/utils/content-utils.ts` — 字体字段透传。
- **阻塞原因**：GitHub 认证不可用，已穷尽通道：
  - HTTPS 凭据管理器无账号（`git credential fill` 卡交互；push 挂起超时——**接手后直接跑 `git push` 会卡死，需先 `export GIT_TERMINAL_PROMPT=0` 验证**）。
  - SSH 22 端口被墙：`Connection refused`。
  - SSH 443（`ssh.github.com:443`）：端口通，但本机 `~/.ssh/id_ed25519` **未注册到 GitHub**（`Permission denied (publickey)`）。
  - `gh` CLI 未登录。
- **解锁路径（三选一，需用户参与）**：
  1. 用户提供 GitHub PAT（repo 权限）→ 用 `GIT_ASKPASS` 临时脚本注入 push，token 不落盘、不入库；
  2. 用户把本机 `C:\Users\ADMIN\.ssh\id_ed25519.pub` 添加到 GitHub → 用 `git push ssh://git@ssh.github.com:443/neutron-star77/neutronstar-web.git main`（临时 URL，不改 config）；
  3. 用户手动 `cd web && git push origin main`。
- push 成功后：等 GitHub Actions 构建部署，验证 https://neutronstar.fun 首页/文章页正常（**SSR 完整性看 footer 出现 2 次**——桌面 `hidden lg:block` + 移动 `block lg:hidden` 双份响应式基线，属正常；不能用 `</html>` 判断）。

### 3.2 父仓 Kirameku2.0 未 commit（非阻塞，版本留档）

- 工作区改动：`Kirameku-backend/`（9 改 + 7 新，含 `app/models/font_asset.py`、`app/api/fonts.py`、`app/schemas/font.py`、`app/services/font_service.py`、`migrations/versions/0004_font_asset.py`、`scripts/seed_fonts.py`、`Dockerfile`、`requirements.txt`、admin 三处）+ `worker-bff/src/index.ts`。
- 提交规范：**铁律不 `git add -A`，显式路径**；密钥/`.env` 绝不入库（`.cf.local.env`、`.dev.vars` 等已在 gitignore）。
- 父仓无 CI 依赖后端部署（后端是 NAS Docker 手动部署，已上线），push 仅为版本记录。

---

## 4. 接手必读的坑位清单

1. **铁律**：①不碰 `kirameku-pg` 容器与数据卷；②不 `git add -A`；③密钥/`.env` 不入库。
2. **SSH**：必须用 Git 自带 `C:\Program Files\Git\usr\bin\ssh.exe`，禁用 System32 OpenSSH（否则隧道 RST）。连接 `ssh hewll`（NAS 192.168.5.4:23023）。
3. **SMB**：`U:\` 映射 NAS `/share/CACHEDEV1_DATA/Container/kirameku`，`U:\kirameku\backend` = NAS 后端目录。同步用 robocopy，**禁用 `/MIR` 裸参数**（MSYS 会误解析为路径），需 `export MSYS_NO_PATHCONV=1` 前缀。
4. **NAS Docker**：命令前缀 `export DOCKER_HOST=unix:///var/run/docker.sock; D=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker`。
5. **顺序铁律**：先 `alembic upgrade head` 再启动含新模型的容器，否则 create_all 与 Alembic 冲突报 DuplicateTable。
6. **容器内跑脚本**（迁移/seed/查询）必须带 env：`DATABASE_URL`、`SECRET_KEY`、`CORS_ORIGINS`、`FRONTEND_ORIGIN`、`BFF_ORIGIN`（从旧容器 `docker inspect` 的 `Config.Env` 复制）；python 脚本路径在非 /app 下需加 `-e PYTHONPATH=/app`。现役值以 NAS 容器 inspect 为准（数据库口令/密钥不在本文件重复，避免泄露）。
7. **seed 字体**：脚本 `scripts/seed_fonts.py`（`--download-dir`/`--force` 参数，按 family 去重）；jsDelivr 对 >20MB 文件返回 403，用 `raw.githubusercontent` 直链；NAS 直连 GitHub 慢但可达（三款总耗时约 10 分钟）。
8. **BFF 部署**：`cd worker-bff && npx wrangler@4 deploy`（先 `export CLOUDFLARE_API_TOKEN=$(grep '^CLOUDFLARE_API_TOKEN=' .cf.local.env | cut -d= -f2- | tr -d '\r\n "')`）。⚠️ `scripts/Deploy.ps1` 含 UTF-8 无 BOM 中文注释，PowerShell 5.1 按 ANSI 误读会报解析错误——**别用它，直接 npx**。也别 `pnpm exec wrangler@4`（pnpm exec 不接受带版本包名）。
9. **admin 改动**：改 admin 源码后须本地 `pnpm exec rimraf dist && pnpm exec vite build`（`pnpm build` 里的 `NODE_OPTIONS=...` 是 Unix 语法，Windows 下直接跑会失败，须先 `export NODE_OPTIONS=--max-old-space-size=8192` 再分步执行），再 robocopy dist 到 NAS，**重启容器**（bind mount inode 失效坑）。
10. **web 验证**：无 playwright 基建（tests/ 不存在是上游模板遗留，勿新增依赖），用 `pnpm build` + preview 手动核对。
11. **已知既有错误（非本改动引入，勿修）**：`worker-bff/src/index.ts` 的 WEB_ORIGIN 类型报错（Env 未声明）；admin 若干 UploadRequestHandler/el-button type 字面量 typecheck 错误；web 未装 `@astrojs/check`。

---

## 5. 快速验证命令（接手后自检）

```bash
# 后端
curl -s http://192.168.5.4:8100/api/fonts
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" http://192.168.5.4:8100/api/fonts/1/file
# admin
curl -s -o /dev/null -w "%{http_code}\n" http://192.168.5.4:8100/admin/
# BFF 公网
curl -s https://bff.neutronstar.fun/api/fonts
# NAS 容器状态（ssh hewll）
export DOCKER_HOST=unix:///var/run/docker.sock; D=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker; "$D" ps
# 查 font_asset 表（docker run --rm 临时容器，env 见坑位 6）
```

---

## 6. 预期时间线（其他 AI 接手后）

1. **web 上线（5 分钟，需用户给凭据或手动 push）**→ CI 部署→验证 neutronstar.fun。
2. 父仓 commit（10 分钟，可选）→ 显式路径 add + push。
3. 收尾复查：后台写一篇文章选霞鹜文楷发布，验证前端实际渲染字体 + 回顶按钮动效。