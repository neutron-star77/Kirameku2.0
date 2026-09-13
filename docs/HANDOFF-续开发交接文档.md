# Kirameku2.0 交接文档（给下一个 AI / 开发者）

> 更新时间：**2026-09-13（第三轮续作后）**　主工程：`F:\AI\projects\Kirameku2.0`
> 一句话现状：**正式站 <https://neutronstar.fun> 已经是新站** —— Shirone 外壳（Astro 7 + Svelte 5 + React 19 islands）+ 真实后端数据（NAS FastAPI/PG）+ SSE 实时 + GitHub 登录/评论/点赞，跑在 **Cloudflare Workers（SSR）** 上。
> 进度：**P0–P7 全部完成并线上验收，P7 域名切换完成；可选加固全部完成**。第二轮 8 项需求 6 项已上线（见 4.9+4.10）；**第三轮续作（2026-09-13，见 4.11）：音乐功能最终形态 = B 站收藏夹悬浮播放器（方案 B：站内直接播放、可拖动、自动连播，后端新增 /api/bili-fav 代理）；修复了 SSR 响应流截断重大 bug（LiveRefreshBanner SSR 返回 null）；旧博客文章迁移补齐（8→11 篇）。** 真正待办只剩 1 项需用户输入：Umami 真实统计凭据（后台直接填）。见 7.5。
>
> ⚠️ **本文是深层档案，不再是阅读入口**。入口 = [`docs/README.md`](README.md)（索引+任务路由）；全面总结 = [`docs/项目全景与开发史.md`](项目全景与开发史.md)。
> 原第 6 节坑大全 → [`docs/坑大全.md`](坑大全.md)；原第 8/9/10 节 → [`docs/命令与运维速查.md`](命令与运维速查.md)（编号不变，「坑 6.x」引用仍有效）。
>
> 本文按需查阅的小节：§0 铁律｜§1 架构｜§2 仓库｜§3 进度总览｜§4 各阶段实现细节（4.1–4.11）｜§5 关键实现细节｜§7 待办详情
> 其余文档：`站点功能与使用说明.md`（用户视角）、`方案-v2.0-*.md`（设计锁定）、`CONTEXT.md` + `docs/adr/`（领域）、`web/docs/部署与二次开发指南.md`、`.codebuddy/memory/*.md`（每日原始记录）

---

## 0. 30 秒上手

### 0.1 三条铁律（违反会出事）

1. **绝不碰 NAS 的 `kirameku-pg` 容器与 `kirameku_pgdata` / `kirameku_uploads` 两个数据卷**（重建服务时只删 `kirameku-backend` 应用容器）。
2. **不要 `git add -A`**（历史上把后端/worker/docs 的 WIP 一起打包过，回退只能外科手术）；一切按显式路径 `git add <file>`。
3. **`.env` / `.dev.vars` / `.cf.local.env` / token / 密钥绝不入库**（`.gitignore` 已覆盖，仍要自觉）。

### 0.2 想改哪里 → 去哪个仓

| 想改的东西 | 仓库 / 目录 | 部署方式 |
|:--|:--|:--|
| 博客前端（页面/组件/样式/动画） | `web/`（**独立 git 仓**，外仓忽略它） | push 到 main → GitHub Actions 自动 `pnpm dlx wrangler@4 deploy -c wrangler.deploy.json`（CI 已配，见 4.8） |
| BFF（边缘缓存/聚合/SSE） | `worker-bff/`（外仓内） | `cd worker-bff && ./scripts/Deploy.ps1`（自动加载 `.cf.local.env`） |
| 后端 API / 模型 / 迁移 | `Kirameku-backend/`（外仓内） | SMB 同步 → NAS `docker build` → 重建容器（第 8.3 节） |
| 后台界面（Vue admin） | `Kirameku-backend/admin/src` | `vite build` → 同步 `admin/dist` 到 NAS（**bind mount，立即生效，不用重启容器**） |

### 0.3 跑起来（本地）

```powershell
# 前端：注意 dev 服务器当前不可用（见 6.1），用 build + preview（workerd 本地跑产物）
cd F:\AI\projects\Kirameku2.0\web
pnpm install
$env:NO_PROXY="127.0.0.1,localhost"
pnpm build
pnpm preview            # http://localhost:4321

# BFF（另一个终端）
cd ..\worker-bff
pnpm install
pnpm exec wrangler dev  # http://localhost:8787，读 .dev.vars

# 后端（可选；平时直接用线上 https://kirameku-api.neutronstar.fun）
cd ..\Kirameku-backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
.\.venv\Scripts\python.exe -m pytest -q      # 19 个测试应全绿
```

### 0.4 改完必做：跑验证清单（第 8.5 节）

---

## 1. 现网架构（务必先搞清楚谁在服务谁）

```
浏览器
  │
  ├─ https://neutronstar.fun        → ★ Cloudflare Worker「neutronstar-web」（SSR + 静态资源 ASSETS）
  │                                    源码 = web/ 子仓；配置 = web/wrangler.deploy.json
  │                                    （custom domain: neutronstar.fun + www.neutronstar.fun）
  ├─ https://www.neutronstar.fun    → 301 到根域（zone 的 Dynamic Redirect Rule，不在 Pages/Worker 配置里）
  ├─ https://bff.neutronstar.fun    → Cloudflare Worker「kirameku-bff」（Hono：缓存/聚合/SSE/图片）
  │                                    源码 = worker-bff/；含 Durable Object「RealtimeRoom」
  └─ https://kirameku-api.neutronstar.fun → Cloudflare Tunnel → NAS(192.168.5.4) Docker
                                                   ├─ kirameku-backend :8100→8000（FastAPI + /admin 静态后台 + /uploads）
                                                   └─ kirameku-pg       :15432→5432（PostgreSQL 16，库名 kirameku）
```

**当前线上事实（2026-09-13 实测）**

| 项 | 值 |
|:--|:--|
| 前端 Worker `neutronstar-web` | version `f1ab416d-f0c5-434d-919c-2182a1cd8e8e` |
| BFF `kirameku-bff` | version `042fd49f-6028-4233-b06e-8c0b3de6a05c` |
| 后端镜像 / 容器 | image sha `3d1ecd44b736`（tag `latest` + `bak-20260913`），容器 `9acbfebe…` healthy |
| Pages 项目 `neutronstar-web` | **已解绑自定义域**；只剩 `*.pages.dev` 预览（⚠️ 其上的 SSR 路由必然 404） |
| DNS（zone `neutronstar.fun`） | `neutronstar.fun` / `www` → `AAAA 100::`（Worker 自定义域标记）；`bff` → `100::`；`kirameku-api`、`dashboard`、`hermes`、`news` → CF Tunnel |
| zone Worker routes | **空**（没有路由抢占；Worker 靠 custom domain 接管） |

**发布链路现状（2026-09-13 更新）**

- 前端 `web/` push 到 GitHub main → GitHub Actions 自动构建并 `pnpm dlx wrangler@4 deploy -c wrangler.deploy.json` 部署到 Worker `neutronstar-web`（CI 已配，secrets `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` 已就绪）。
- 踩坑：`npx wrangler@4` 在 ubuntu runner 上报 `sh: wrangler: not found`（exit 127），必须用 `pnpm dlx wrangler@4`。

---

## 2. 仓库与目录

| 仓库 | 路径 | remote | 说明 |
|:--|:--|:--|:--|
| 外仓（主） | `F:\AI\projects\Kirameku2.0` | `neutron-star77/Kirameku2.0.git`（分支 **master**） | 后端、BFF、文档、脚本 |
| 前端子仓 | `…\Kirameku2.0\web` | `neutron-star77/neutronstar-web.git`（分支 **main**） | **独立 git**，被外仓 `.gitignore` 忽略；HEAD `2f77b19` |
| 图床仓 | `F:\AI\projects\fastimage` | `neutron-star77/fastimage.git` | 234 张鬼刀图 + 两级派生图（thumbs/full），jsDelivr/gcore |
| 上游基线 | `…\Kirameku2.0\_upstream_shirone` | `LyraVoid/Shirone.git`（浅克隆） | **不入库**，pinned `b79d301e…`，由 `scripts/sync-upstream.mjs` 管理 |

**易踩**：改 `web/` 的代码，在外仓 `git status` 里**看不到任何变化** —— 必须 `cd web` 单独 commit/push。

---

## 3. 进度总览

| 阶段 | 状态 | 关键证据 | 剩余 |
|:--|:--|:--|:--|
| **P0 基线** | ✅ | 完整上游 clone、清理重复副本、ADR/领域文档、方案 v2.0 | — |
| **P1 外壳移植** | ✅ | `web@e2fa995`、四组截图对照通过、`07ecf0a` 中文化上线 | 上游 demo 内容已换血 |
| **P2 数据换血** | ✅ | `web@65c07a1`+`424e72d`；BFF `/bff/archive|sidebar|home`；相册 234 张入库；site_config 覆盖层 | 导航已接后台 API（见 4.8） |
| **P3 三页动画** | 🟡 已接入未做像素验收 | `MomentsList`（堆叠+倾斜+弹簧展开）、`AlbumGrid`（扇形+拍立得+内联展开）、`FriendsGrid`、`Lightbox` | 与 boke.hiromu.top 的逐项手感对照（需要人眼） |
| **P4 SSE 实时** | ✅ | DO `RealtimeRoom` + `/sse/:channel`；实测「写操作 → 缓存 MISS + SSE 收到 change 事件」 | 首页/归档/详情已加 LiveRefreshBanner（见 4.8） |
| **P5 登录/评论/点赞** | ✅ | GitHub OAuth 全链路；`likes` 唯一约束防重；评论多态（post/chatter/album）+ 后台双 Tab | 评论已加目标存在性校验 + 分页 + 默认 pending 审核（见 4.8） |
| **P6 Shirone 全特性** | ✅ | RSS/Atom/llms、Lighthouse、字体子集化（14.5MB→770KB）、SSR 自动刷新横幅、导航接后台 API、Pagefind 搜索+mermaid/katex、追番页+分享海报 | 文章加密组件就绪但无加密文章（API 无 encrypted 字段） |
| **P7 上线** | ✅ | Worker 接管根域 + www 301 + 旧链 `/blog/*→/posts/*`；CI 自动部署；Lighthouse Performance 84 | TTFB ~1640ms（SSR 回源 BFF 固有延迟，非 bug） |

### 3.1 第二轮需求（2026-09-13，用户下达 8 项）

| # | 需求 | 状态 | 关键证据 / 剩余 |
|:--|:--|:--|:--|
| ① | JWT→httpOnly cookie 好处解释 | ✅ 已口头解释 | 纯文字，无代码改动 |
| ② | TTFB 缓存好处解释 | ✅ 已口头解释 | 纯文字，无代码改动 |
| ③ | 音乐挂件改 B 站收藏夹顺序播放（最小代价） | ✅ **代码已上线（默认关闭）** | 方案 A 落地：MusicLinkCard.astro 外链卡片 + music_widget 后台可配；线上验收「启用出卡片/禁用零残留」通过；**只差用户在后台填一条收藏夹链接**，见 4.11.1 |
| ④ | 3 项小修：删 5 死 island + 后台两占位接口 + cloudflared 自启 | ✅ 全部完成 | 见 4.9①②③ |
| ⑤ | 排查"说说和友链导航栏看不到" | ✅ 已修复并**线上验收** | 根因：中等宽度(1024–1279px)居中导航被挤压竖排；修复：断点 lg→xl + nowrap；commit ebff376 已上线，三宽度截图通过 |
| ⑥ | CI 构建时自动重新子集化字体 | ✅ 已上线验证 | CI 实测拉 8 篇文章→3264 字符→771KB(-94.8%)；commit ebff376 |
| ⑦ | 文章加密接入 | ⏸️ 用户明确暂不做 | 组件已就绪，API 无 encrypted 字段 |
| ⑧ | Umami 统计 ID 放后台配置+查看 | ✅ 全部完成 | 后端默认值 + admin 面板 + 前端覆盖层；见 4.9④ |

---

## 4. 已完成工作详细记录

### 4.1 P0 基线（2026-09-12）

- 完整上游基线 `_upstream_shirone/`（浅克隆，15 个 src 模块齐全）；删掉工作空间重复副本 `projects/Kirameku`（2.4GB）、`Kirameku-ref`（0.5GB），删前 hash 级 diff，独有 `.env` 抢救到 `backups/rescue-from-duplicates/`（gitignored）。
- 一次性脚本归入 `Kirameku-backend/scripts/{oneoff,ops}/`；退役旧 `worker/`。
- NAS 核查：只有 `kirameku-backend`、`kirameku-pg` 两容器（旧 `kirameku-fe` 不存在）。

### 4.2 P1 外壳移植（2026-09-12）

- 装齐上游依赖（svelte 5 / `@astrojs/svelte` 9 / `@swup/astro` / expressive-code / astro-icon / remark-rehype 管线 / katex / mermaid / `@fancyapps/ui` / subset-font …）。
- `astro.config.mjs` 对齐上游（swup/icon/expressiveCode/svelte/mdx/sitemap + markdown processor + 音乐虚拟模块插件），保留 cloudflare adapter 与 react()。
- 整体移植 `src/`：layouts、15 个样式、35 个配置、constants、i18n、~90 个 utils、plugins、integration、types、data、user、assets（15MB Yozai 字体）、public 资产。
- 首页照搬上游 `pages/[...page].astro`；其余页面改 `MainGridLayout` 薄壳。拆除自创件（HomeHero / AlbumCarousel / 手搓 Base/Page/SiteHeader/Sidebar/AuthorCard/Calendar/SurfaceCard/PageHeader / global.css+animations.css）。
- **相对上游的刻意偏离（都有注释）**：`siteConfig.site` → neutronstar.fun；`fontConfig.subsetting.enable=false`；`musicConfig.enable=false`（运行时 stylus 编译与 workerd 冲突）；字体加载离线化（`fontsourceCssToLocalVariants()`，全角色 `optimizedFallbacks:false`）；`imageService: {build:"compile", runtime:"passthrough"}`；`integration/ssr-node-shims.ts` 加固；`plugins/rehype-markdown-images.mjs` sharp 改惰性 import。

### 4.3 P2 数据换血（2026-09-12）

1. **BFF 聚合口**：`/bff/archive`（分页+总数）、`/bff/sidebar`（分类/标签/统计/日历）、`/bff/home`。
2. **BFF 缓存正确性**：Cache API 不按 Origin 分键 → 缓存条目**剥离 CORS 头**，由 cors 中间件按请求重新注入；白名单含 `neutronstar.fun`/`www`/`pages.dev`/`bff`/`localhost:4321`/`127.0.0.1:4321`。
3. **前端数据层换血**：`web/src/lib/server/api.ts`（SSR 回源 + 15s isolate 内存缓存）；`utils/content-utils.ts` 把 API 文章**适配成原版 CollectionEntry 鸭子形状**（`PostEntry`，另带 `postId`）；`content.config.ts` 与上游 demo content 删除。
4. **页面渲染策略**（Astro 7：`output:"static"` + 适配器 = 默认预渲染，实时页写 `export const prerender = false`）：
   - `prerender=false`（SSR）：首页 `pages/[...page].astro`、`archive.astro`、`posts/[slug].astro`、`auth/callback.astro`
   - 静态壳 + islands：`moments` / `albums` / `friends` / `messages` / `about` / `novel`
5. **站点覆盖层** `web/src/utils/site-overrides.ts`：`site_title` / `site_description` / `site_images` / `sidebar_widgets` 后台可配（站名已改 **Neutronstar**）。
6. **相册 234 张导入后端**：`Kirameku-backend/scripts/oneoff/import_fastimage.py`（幂等，直连 NAS PG 15432；真实 `DATABASE_URL` 存 `backups/rescue-from-duplicates/nas-db.env.txt`，gitignored）→ 6 册 × 39 张。
7. **fastimage 两级派生图**：`fastimage/scripts/derive_images.py` 生成 `thumbs`（800/q72，中位 25KB）+ `full`（1600/q74，中位 71KB），母版 1920/q82（中位 156KB）；**URL 统一走 `gcore.jsdelivr.net`**（cdn/fastly 对 gh 资源会 301 到 raw）。
8. **admin 面板**：站点配置页新增 `site_images` 编辑面板 + 侧栏开关对齐新主题 widget。
9. **后端发布失效联动**：`app/services/cache_invalidate.py`（HMAC → BFF `/internal/revalidate`）挂到 posts/chatters/albums/friend_links/messages/site_config 全部写接口；缺 `REVALIDATE_SECRET` 时 no-op。

### 4.4 P3 三页动画（接入完成，待像素验收）

- 说说 `/moments`：`MomentsList.tsx` —— 按日分组、同日绝对定位堆叠（`top: i*18`、zIndex 倒序）、确定性倾斜序列、点击 `spring(300,25)` 展开、展开后平滑滚动、「只看这条」隔离模式、灯箱。
- 相册 `/albums`：`AlbumGrid.tsx` —— 封面 3 张堆叠 → 悬停扇形展开（`STACK_ANGLES/FAN_ANGLES/FAN_Y`）→ 点击内联高度展开照片墙（拍立得白边+胶带+`tiltFromId` 确定性倾斜）→ `Lightbox`（弹簧缩放 + 键盘 ←/→ + 触摸滑动）。
- 友链 `/friends`：`FriendsGrid.tsx` 错位卡片。
- 留言 `/messages`：`MessagesList.tsx`。
- ⚠️ **已无人引用的历史 island（死代码）**：`PostList.tsx`、`HomeFeed.tsx`、`SidebarVisibility.tsx`、`MusicFloatingCard.tsx`、`PostView.tsx`（P1 拆壳后遗留；`/`、`/archive` 已改 SSR 直出）。`NavigationIsland.tsx`、`MobileNavigation.tsx` 已于 2026-09-13 删除。剩余可清理或按需复活。

### 4.5 P4 SSE 实时（2026-09-12 完成并验收）

**数据流**：后台写库 → `invalidate_cache(tags)` → BFF `/internal/revalidate`（HMAC 校验）→ ①按 tag 清 Cache API ②`waitUntil` 异步向各频道 DO 投递事件 → DO 扇出给在线 SSE 连接 → 浏览器 `window.__kiramekuRealtimeHub` 收到 change → 各 island 用**自己的** SWR 实例重校验。

- BFF `src/realtime-room.ts`：`RealtimeRoom` DO（一个频道一个实例，`idFromName("v2:<channel>")`），路由 `/subscribe`（SSE）、`/broadcast`、`/status`；25s 心跳；**每次写入 2s 超时 + 摘除死连接**。
- `worker-bff/wrangler.toml`：`[[durable_objects.bindings]] REALTIME_ROOM` + `[[migrations]] new_sqlite_classes=["RealtimeRoom"]`（⚠️ 免费计划必须 SQLite 后端类）；wrangler 升到 4。
- `worker-bff/src/index.ts`：`GET /sse/:channel`（频道名净化）+ `/internal/revalidate`（清缓存后 `waitUntil` 广播，响应回到亚秒级）。
- 频道映射 `TAG_CHANNELS`：posts→posts、moments→moments、albums→albums、friends→friends、messages→messages、comments→comments、site→nav，**恒定含 home + all**。
- 前端 `web/src/lib/realtime.ts`：`window` 全局 hub（全站唯一 EventSource + 指数退避重连 + 引用计数 + 5s 宽限关闭）+ `useRealtimeRefresh(prefixes[, onChange])`；已接入 MomentsList / AlbumGrid / MessagesList / FriendsGrid / NavigationIsland（后两者走 onChange）。
- **实测**：`POST /api/chatters/1/like` → 同 URL `X-Cache: MISS`（后端→BFF 失效通）+ 同时挂着的 `/sse/all` 收到 `event: change {"channel":"all","action":"published"}`（扇出通）；`/internal/revalidate` 耗时 0.72s。

### 4.6 P5 登录 / 评论 / 点赞（2026-09-12 ~ 09-13）

**登录（GitHub OAuth）**

- 前端 `pages/auth/callback.astro`（`prerender=false`）：接后端 302 带来的 `?token=`，写 `localStorage["kirameku_github_token"]` 后回首页；无 token 显示「没有拿到授权信息」。
- `web/src/lib/auth.ts`：`getToken/setToken/clearToken/loginUrl/useGithubUser`；`lib/api/client.ts` 的 `apiGet/apiPost` **自动带 `Authorization: Bearer`**。
- `AuthButton.tsx` island：未登录显示「用 GitHub 登录」（跳 `${API_BASE_URL}/api/auth/github/login`），已登录显示头像+`@login`+退出；挂在 `/moments`、`/albums` 顶部右侧。
- 后端 `app/api/github_auth.py`：`/login`（302 到 GitHub，`scope=read:user`）、`/callback`（code→token→GitHub user→upsert `github_user`→JWT→302 到 `{FRONTEND_ORIGIN}/auth/callback?token=`）、`/me`；`FRONTEND_ORIGIN` 默认值已修正为 `https://neutronstar.fun`。
- 配置：OAuth App 回调必须是 `https://bff.neutronstar.fun/api/auth/github/callback`；容器 env 带 `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET`/`FRONTEND_ORIGIN`。

**点赞（防重）**

- 表 `likes`（`app/models/like.py`）：`user_id + target_type + target_id` 唯一（`uq_likes_user_target`）；**表名用复数**（`like` 是 SQL 关键字）。目标表的 `likes` 字段是**冗余计数**，真值在本表。
- 支持 `target_type`：`chatter` / `chatter_comment` / `comment` / `post`（`app/services/like_service.py`，toggle 幂等 + `IntegrityError` 兜底）。
- 接口：`POST /api/likes/toggle`（**需登录**，幂等切换，返回 `{liked, likes}`）、`GET /api/likes/mine?target_type=`（未登录返空数组不报错）。
- 前端：说说卡片点赞走 toggle（乐观更新 + 失败回滚 + 成功后 SWR mutate），登录后回填「我点过赞的说说」。

**评论（多态 + 楼中楼）**

- `comment` 表：新增 `target_type`（post/chatter/album）+ `target_id`，`post_id` 改可空（历史数据已按 post 回填）。
- 说说评论历史上有**独立表** `chatter_comment` + 独立接口（`/api/chatters/{id}/comments`、`POST /api/chatters/comments`），本次保留并复用。
- 接口：`GET /api/comments?target_type=&target_id=`、`POST /api/comments`（target_type+target_id，兼容只传 post_id）、`DELETE /api/comments/{id}`（**作者本人或后台管理员**，连带删子回复）、评论点赞兼容接口（改需登录 + 幂等）。
- 前端 `CommentsThread.tsx`：**一个组件适配两套表**（`kind="chatter"` 走说说专用表；`kind="post"` / `kind="album"` 走多态表），含楼中楼两层、回复、点赞、删除自己的、未登录给登录入口；已挂到**说说展开卡片**、**文章详情页**、**相册展开卡片**。

**后台评论管理（Vue admin）**

- 后端：`GET /api/comments/admin` 支持 `target_type` 过滤并给每条返回 `target{type,id,title,url}`（`comment_service.target_info()`：文章→标题+`/posts/{slug}`、相册→标题+`/albums`、说说→摘要+`/moments`）；`GET /api/chatters/comments/admin` 同样带 `target`。
- 顺手修 bug：`chatter_service.delete_chatter_comment` 原来**不删子回复、不回退 `comments_count`** → 已修。
- 界面 `admin/src/views/comment/index.vue` 重写：**内容评论（文章/相册）/ 说说评论双 Tab**、类型过滤下拉、「文章ID」列 → **「所属内容」**（类型标签 + 标题，点击新窗口打开前台）、操作按当前 Tab 路由到对应接口。

### 4.7 P7 域名切换（2026-09-12 完成，步骤可复用）

> 背景：@astrojs/cloudflare v14 输出 **Workers 格式**（`dist/server/wrangler.json` + `dist/client` assets），**Pages CI 只部署静态部分** → 所有 `prerender=false` 路由在 Pages 上必然 404。所以正式站改为 **Workers 部署**。

实际执行顺序（每步都验证过）：

1. 解除 Pages 项目自定义域：`DELETE /accounts/{acc}/pages/projects/neutronstar-web/domains/{neutronstar.fun|www.neutronstar.fun}`
2. 删除 DNS 里两条 `CNAME → neutronstar-web.pages.dev`
3. **`PUT /accounts/{acc}/workers/domains`**（⚠️ 是 **PUT**，POST 返回 405）：body `{zone_id, hostname, service:"neutronstar-web", environment:"production"}` → CF 自动建 `AAAA 100::`
4. `cd web && npx wrangler@4 deploy -c wrangler.deploy.json`（配置里 `routes` 含根域 + www 两个 custom domain）
5. `POST /zones/{zone}/purge_cache {"purge_everything":true}`
6. 验证：`/`、`/2/`、`/archive/`、`/moments/`、`/albums/`、`/friends/`、`/messages/`、`/about/`、`/novel/`、`/posts/<真实 slug>` 全 200；`www` 301；未知路径 404

**顺带修的**：SSR 化后根级 catch-all `[...page].astro` 会把任意未知路径渲染成首页（软 404）→ 已加守卫「只放行 `/` 与纯数字分页，其余直接 `Response(404)`」；删除临时诊断路由 `api-debug.astro`。

### 4.8 P6 全特性 + 可选加固（2026-09-13 完成并线上验收）

**① 前端 CI 自动部署**
- `web/.github/workflows/deploy.yml` 从 Pages 上传改为 `pnpm dlx wrangler@4 deploy -c wrangler.deploy.json`。
- 踩坑：`npx wrangler@4` 在 ubuntu runner 报 `sh: wrangler: not found`（exit 127），必须 `pnpm dlx`。
- 验收：push 后 CI success，Worker 版本更新，站点 200。

**② RSS / Atom / llms.txt / llms-full.txt**
- 移植上游 `_upstream_shirone/` 的四个端点，适配 API 数据源（上游读 content collection，我们读后端 API）。
- 关键：列表接口不返回正文，feed 的 contentHtml 回退 description；llms-full.txt 用新增 `getSortedPostsWithContent()` 并行拉单篇详情。
- 站名走 `getSiteIdentity()`（后台覆盖为 Neutronstar，而非 Shirone）。

**③ Lighthouse 性能预算**
- 基线（热缓存）：Performance 84 / LCP 2.6s / TTFB 1640ms / CLS 0.005 / TBT 270ms / SI 6.7s。
- TTFB 高是 SSR 每次回源 BFF 的固有延迟（冷 isolate 更明显），非代码 bug。

**④ 字体子集化**
- `scripts/subset-font.mjs`：从 BFF 拉 8 篇文章正文 + i18n + config 收集 3264 个唯一字符，用 `subset-font@2.5.0` 生成 WOFF2。
- 产物 `Yozai-Medium.subset.woff2` 770KB（原 TTF 14.5MB，-94.8%）；`fontConfig.ts` yozai-cjk 指向子集。
- 重新生成：`pnpm fonts:subset`。注意：静态子集，新增生僻字文章可能缺字。

**⑤ SSR 页停留自动刷新**
- `LiveRefreshBanner.tsx` React island：`useRealtimeRefresh(["posts","home"])` 监听 SSE，收到后顶部弹「有新内容，点击刷新」横幅。
- 挂到首页、archive、posts/[slug] 三个 SSR 页面。

**⑥ 导航/侧栏接后台 site_config**
- `utils/navigation-api.ts`：`fetchNavigation()` + `getNavigation()`（30s 缓存）+ `apiNavToLinks()`（按 href 匹配 LinkPresets 补 icon/pageKey）。
- `TopAppBar.astro` 改 SSR `await getNavigation()`；`SiteNavigationDrawer.svelte` 改 `$state/$derived` + onMount fetchNavigation()。
- 验收：线上首页导航显示 API 默认导航（首页/文章/归档/说说/相册/友链/杂谈/小说/关于），而非静态配置。

**⑦ 搜索（Pagefind）+ mermaid/katex/expressive-code**
- mermaid/katex/expressive-code 此前已接入构建链。缺口是 Pagefind 索引从未生成。
- `scripts/build-search-index.mjs`：从 BFF API 拉全部已发布文章 → 拉单篇详情正文 → 生成最小 HTML 到临时目录 → 调 pagefind CLI 建索引 → 输出 `dist/client/pagefind`。
- `package.json` 加 `"postbuild": "node scripts/build-search-index.mjs"`。
- 踩坑：Windows 上调 pagefind 需 `shell:true` + 完整 `node_modules/.bin/pagefind.cmd` 路径。

**⑧ P6 长尾（追番页 / 分享海报 / 纹理 / FAB）**
- 纹理（textures.css）和 FAB（FloatingControls.astro + fab-controller）已存在，无需改动。
- 追番页：新建 `pages/anime.astro`（`AnimeSection client:load animes={animeData}`），数据来自 `src/data/anime.ts`（5 条静态数据）。
- 分享海报：`posts/[slug].astro` 加 `ArticleShare`（受 `articleConfig.share.enable` 控制），传 title/description/author/published/siteTitle/postPath。
- 文章加密：`ProtectedPost/PasswordGate/post-decryption` 组件已存在但未接入，因 API PostEntry 无 encrypted 字段，当前无加密文章。

**可选加固（已完成）**
- 评论创建校验目标存在性：`comment_service._verify_target_exists()`，对不存在的 post/chatter/album 返回 404。
- `/api/comments` 读接口分页：加 `page/size` 参数（默认 page=1, size=100），分页只作用于根评论，replies 一并返回；同时优化为批量拉回复避免 N+1。
- 评论审核流程：`Comment.status` 默认从 `approved` 改为 `pending`，新评论需后台审核后才公开；公开接口已过滤 `status=="approved"`。
- 清理死 island：删除 `NavigationIsland.tsx`、`MobileNavigation.tsx`（确认无引用）。
- Shirone 残留字样：`share-poster.ts` 回退站名、`siteConfig.ts` 默认 title 改为 Neutronstar（其余 307 处为内部标识符/CSS 类名/事件名，不可改）。

**基础设施修复（cloudflared 隧道）**
- 两次隧道掉线（530/502），最终定位为 NAS 网络限制 UDP/QUIC，cloudflared 注册连接后立即 "timeout: no recent network activity"。
- 解法：重启脚本加 `--protocol http2`，稳定运行。
- 脚本：`scripts/restart-tunnel.sh`（LF 行尾，已复制到 `U:\kirameku\`）。
- cloudflared 以 nohup 后台进程运行（非 systemd 非 Docker），NAS 重启后需手动拉起。

**后端部署注意**
- 后端容器无 `.env` 文件，env 通过 `docker run -e` 传入。重建容器时必须带完整 env（DATABASE_URL / SECRET_KEY / CORS_ORIGINS / FRONTEND_ORIGIN / BFF_ORIGIN）。
- PG 在 bridge 网络 IP `10.0.3.2:5432`（容器名解析在默认 bridge 不工作）。
- 部署脚本：`scripts/rebuild-backend.sh`（复制到 U:\kirameku\ 后 `sh` 执行）。

### 4.9 第二轮需求（2026-09-13，6 项完成 + 2 项待办）

#### 4.9.1 导航栏"说说/友链看不到"根因与修复（⑤）

**现象**：用户反馈导航栏看不到说说和友链。排查链路：
1. 直连后端 `https://kirameku-api.neutronstar.fun/api/site-config/navigation` → 返回完整 9 项（首页/文章/归档/说说/相册/友链/杂谈/小说/关于，全 visible:true）。
2. BFF `https://bff.neutronstar.fun/api/site-config/navigation`（X-Cache:MISS，`s-maxage=60 SWR 300`）→ 同样完整 9 项，排除数据源/缓存问题。
3. 抓线上首页 SSR HTML 解析，桌面 nav 9 项全部渲染。
4. **Edge headless 截图定位真因**：1440px 下 9 项横排完全正常；但 **1024px/1180px 宽度下，因 TopAppBar 用 `contentAlign:center` → nav 绝对定位居中（`lg:absolute lg:left-1/2`），9 项被左侧站名+右侧搜索/设置图标挤压，每个两字词被压成竖排、挤成一团**，说说/友链就在其中变得难以辨认。移动端(390)只有汉堡菜单（正常）。

**修复（`web/src/components/organisms/TopAppBar.astro` 三处）**：
- 横排断点从 `lg`(1024) 提高到 `xl`(1280)：汉堡按钮 `lg:!hidden`→`xl:!hidden`、nav `lg:flex`→`xl:flex`、居中 class 同步 `lg→xl`。
- 两处 nav-link 加 `shrink-0 whitespace-nowrap` 双保险，防文字竖排。
- <1280 走汉堡抽屉（抽屉内 9 项完整，SiteNavigationDrawer.svelte onMount fetchNavigation 覆盖静态值）。

**验收**：本地 `pnpm build && pnpm preview` 后 Edge headless 截图——1440px 横排 9 项清晰、1024px 出汉堡菜单无竖排。**待 push main 走 CI 后线上复截验收。**

#### 4.9.2 删 5 个死 island（④-a）

grep 确认 `PostList/HomeFeed/SidebarVisibility/MusicFloatingCard/PostView` 五个 `.tsx` 无任何 import（`DisplaySettings.svelte`、`layout-mode.ts` 引用的是 `PostListMode` 类型，来自 `types/postListConfig`，与组件无关，类型文件保留）。已 `Remove-Item` 删除。islands 目录现存 8 个：AlbumGrid/AuthButton/CommentsThread/FriendsGrid/Lightbox/LiveRefreshBanner/MessagesList/MomentsList。

#### 4.9.3 后台两个占位接口实现 + 登录日志表（④-b）

**背景**：`admin/src/api/user.ts` 第 55-67 行有 `refreshTokenApi`（POST `/api/auth/refresh-token`）和 `getMineLogs`（GET `/api/auth/me-logs`）两个占位，后端均无路由。后台"账号设置-安全日志"页（`SecurityLog.vue`）调用 me-logs，期望 `{code,data:{list:[{summary,ip,address,system,browser,operatingTime}],total,pageSize,currentPage}}`。

**实现**：
1. **新模型** `app/models/login_log.py`：`LoginLog` 表（id/username/summary/ip/address/system/browser/success/created_at），username+success+created_at 建索引。
2. **迁移** `migrations/versions/0003_login_log.py`（down_revision=0002_likes_comments）。
3. **`app/api/auth.py` 重写**：
   - `login`：成功/失败都写登录日志（`_write_login_log`），IP 优先取 `CF-Connecting-IP`（隧道穿透真实客户端 IP），UA 粗解析 system/browser（不引第三方依赖）；返回的 `refreshToken` 从空字符串改为等于 accessToken。
   - `POST /api/auth/refresh-token`：`Depends(get_current_user)` 鉴权后重新签发 JWT（无状态，旧 token 自然到期）。
   - `GET /api/auth/me-logs`：`page/pageSize` Query（默认 1/10），按当前用户 username 查 login_log，created_at 倒序分页。
4. **`admin/src/api/user.ts`**：更新注释（去掉"后端暂未实现"），getMineLogs 改 `params` 传参，返回类型补全 currentPage/pageSize。

**踩坑（重要）**：应用 lifespan 启动时 `init_db()` → `SQLModel.metadata.create_all(engine)` 会**自动为所有已 import 的模型建表**。新容器启动时 LoginLog 表已被 create_all 建好，但 alembic version 还停在 0002，此时跑 `alembic upgrade head` 报 `DuplicateTable: relation "login_log" already exists`。**解法**：核对 create_all 建出的表结构与模型一致（9 列+3 索引+主键齐全）后，执行 `alembic stamp 0003_login_log` 把版本标记为已应用。**后续新增模型务必先跑迁移再启动新容器，或接受 create_all 建表后 stamp。**

**验收（公网实测）**：
- `POST /api/auth/login`（admin/admin123）→ code=0，refreshToken 非空，同时写一条成功日志。
- 故意用错密码登录 → 写一条失败日志（防爆破排查用）。
- `GET /api/auth/me-logs`（带 token）→ code=0，total=2，list 含成功/失败两条，IP=219.136.153.17（CF 真实 IP 穿透生效），system=Windows，分页字段齐全。
- `POST /api/auth/refresh-token`（带 token）→ code=0，返回新 token+expires。
- 无 token 调两接口 → 403（路由已注册，不再 404）。

#### 4.9.4 Umami 后台可配可查看（⑧）

**背景**：前端 `umamiConfig.ts` 是静态配置（enable:false/shareUrl/websiteId/scriptUrl），`Layout.astro` 用 `resolveUmamiOptions()` 解析，有 websiteId+scriptUrl 时注入采集脚本，`UmamiStats.astro` 用 shareUrl 展示访问数。用户要求"Umami 统计 ID 放在后台进行统计和查看"。

**实现（三层）**：
1. **后端**：`app/services/site_config_service.py` 的 `DEFAULT_PUBLIC_CONFIG` 加 `umami` 默认值 `{enable:false, websiteId:"", scriptUrl:"", shareUrl:""}`。通用 KV 表无需改结构。`GET /api/site-config/umami` 公开返回默认值（实测 200）。
2. **后台 admin**（`admin/src/views/site-config/index.vue`）：
   - 头部加"初始化统计配置"按钮。
   - 表格 value 列对 `key==='umami'` 显示专用行（开启状态+ID 前缀+"编辑统计配置"按钮）。
   - Umami 编辑对话框：enable 开关 + websiteId + scriptUrl + shareUrl 四个字段；有 shareUrl 时显示"打开 Umami 统计面板（只读）"外链（新窗口打开 Umami 分享仪表盘，即"后台查看"入口）；保存时校验"开启至少需 websiteId 或 shareUrl"。
3. **前端**：
   - `web/src/utils/site-overrides.ts`：`SiteOverrides` 加 `umami` 字段，`getSiteOverrides()` 解析 `cfg.umami`（兼容字符串 JSON），新增 `getUmamiOverride()`（enable 且有 websiteId/shareUrl 时返回对齐 `ResolvedUmamiOptions` 的对象，否则 null）。
   - `web/src/layouts/Layout.astro`：`umamiOptions = (await getUmamiOverride()) ?? resolveUmamiOptions(umamiConfig)`——后台配置优先，未配置回退静态默认（关闭）。

**注意**：前端 `GET /api/site-config` 全量接口只返回数据库中实际存在的行（不合并 DEFAULT_PUBLIC_CONFIG），所以后台未初始化 umami 行时前端拿不到默认值——但此时 `getUmamiOverride()` 返回 null，回退静态 umamiConfig（关闭），行为正确。用户在后台点"初始化统计配置"或保存后，数据库有这行，全量接口即返回。BFF 对 site-config 有 `s-maxage=60` 缓存，保存后最多 60 秒前台生效。

**验收**：后端 `/api/site-config/umami` 返回默认关闭配置；admin 构建产物含 `site-config-*.js` chunk；前端构建通过（Layout.astro 改动无类型错误）。**待用户填入真实 Umami 凭据后端到端验证采集。**

#### 4.9.5 CI 构建时自动重新子集化字体（⑥）

`web/.github/workflows/deploy.yml` 在 Install 后、Build 前加一步：
```yaml
- name: Subset CJK font from latest posts
  run: node scripts/subset-font.mjs
  continue-on-error: true
```
- `subset-font.mjs` 默认 `API_BASE=https://bff.neutronstar.fun`，CI runner 能访问公网，从线上最新文章收集字符。
- `continue-on-error: true`：网络抖动时不阻断部署，回退仓库内已提交的 `Yozai-Medium.subset.woff2`。
- 子集产物在 CI 工作区被覆盖后直接用于后续 `pnpm build`，无需回写 git（每次构建都是最新的）。
- 源 TTF（14.5MB）在仓库里，checkout 即可用；`subset-font` 包在 devDependencies，CI `pnpm install` 已装。

**待 push main 触发 CI 验证该步骤实际执行。**

#### 4.9.6 cloudflared 开机自启持久化（④-c）

**背景**：cloudflared 以 nohup 后台进程运行（非容器非 systemd），NAS 重启会掉。QNAP `/etc/config/autorun.sh` 已存在但引用的 `/share/CACHEDEV1_DATA/cloudflared/` 目录**已不存在**（历史残留），所以开机自启实际失效。

**实现**：
1. 写幂等启动脚本 `scripts/start-tunnel.sh`，同步到 NAS `/share/CACHEDEV1_DATA/Container/kirameku/start-tunnel.sh`：
   - 用 `ps w | grep '[c]loudflared'` 检测已有进程（**这台 QNAP 没有 pgrep**，见 6.3.14），有则 skip。
   - 等网络就绪（ping 1.1.1.1，最多 60 秒）。
   - 用 **`setsid`** 拉起（**这台 QNAP 没有 nohup**，见 6.3.15），`--protocol http2`（QUIC/UDP 超时，见 6.3.10），日志 `/tmp/cloudflared.log`。
2. 修改 `/etc/config/autorun.sh`（位于持久 RAID md9，直接改即持久，已备份为 `autorun.sh.bak.20260913025258`）：删除两行失效的旧 cloudflared 引用，替换为调用 `start-tunnel.sh`；保留 hermes agent 自启行。
3. **完整演练验证**：kill 当前 cloudflared → 跑 start-tunnel.sh → 确认 setsid 拉起新进程（脱离 SSH 会话存活）→ 4 条边缘连接全部 Registered（protocol=http2）→ 公网 `https://kirameku-api.neutronstar.fun/api/health` 返回 ok。

**关键文件**：`scripts/start-tunnel.sh`（生产用，已同步 NAS）、`scripts/restart-tunnel.sh`（手动重启用，kill 后再拉起，已同步 NAS）。

### 4.10 续作阶段：双仓推送上线 + admin 404 修复 + 全站回归（2026-09-13）

4.9 的代码此前只落盘未上线，本阶段完成提交、部署、线上验收，并在健康检查中额外发现并修复一个 admin 挂载坑。

#### 4.10.1 双仓提交与推送（已完成）

- **web 子仓**（分支 main）：commit `ebff376`「fix(nav) + Umami 后台覆盖 + CI 字体子集 + 删 5 死 island」，10 files changed (+60/-301)，已 push。提交前把字体子集产物目录 `src/assets/fonts/.subset/` 加进 `.gitignore`（charset.txt 是 CI 每次重建的产物，不入库）。**严格按显式路径 `git add`，未用 `git add -A`（铁律）**；删除的 5 个 island 用 `git add -u src/components/islands/` 记录。
- **外仓**（分支 master）：commit `03186c3`（后端 login_log/auth/site_config + admin Umami 面板 + 6 个 NAS 运维脚本 + 本文档，14 files +673/-18）→ `aa3ac0d`（文档状态回写）→ `9d22e78`（补坑 6.3.18），均已 push。
- **PowerShell 假报错**：`git push` 的进度信息走 stderr，PowerShell 会包成 `NativeCommandError` 红字，只要看到 `<old>..<new> branch -> branch` 就是推送成功，别误判（已记入 6.5）。

#### 4.10.2 CI 自动部署 + 字体子集实测生效（已完成）

- web push 触发 GitHub Actions run **34713250765**，**success，1m37s**（`cd web; gh run list --limit 1` 查状态）。
- "Subset CJK font from latest posts" 步骤日志确认：`Got 8 posts → Collected 3264 unique characters → Source 14869 KB → Output 771 KB (-94.8%)`，证明 4.9.5 的 CI 字体子集化不是空跑，确实每次构建按最新文章重新裁剪字体。

#### 4.10.3 线上导航三宽度验收（已完成）

CI 部署后用 Edge headless（独立 `--user-data-dir`，见 6.4.8）对正式站截 1024 / 1180 / 1440 三宽度并逐张 Read 核对：
- 1024px、1180px：只显示汉堡按钮 ☰ + 站名 + 右侧图标，**无竖排文字、无拥挤** ✓
- 1440px：横排完整 9 项（首页/文章/归档/说说/相册/友链/杂谈/小说/关于），"说说""友链"清晰可见 ✓
- 导航问题（用户反馈"说说和友链看不到"）线上闭环。

#### 4.10.4 【新发现并修复】admin 后台 /admin 全 404（bind mount inode 失效）

**现象**：全站健康检查时 `https://kirameku-api.neutronstar.fun/admin/` 返回 404，但后端 API、health 全正常。
**排查**：进容器 `ls /app/admin/dist` 是**空的**（total 0），而宿主机挂载源 `/share/.../kirameku/backend/admin/dist` 文件齐全（index.html/static/version.json 都在），`docker inspect` 挂载关系也正确。
**根因**：后端容器启动时宿主机 dist 还是空的，Docker bind 了当时的目录 inode；之后用 `robocopy /MIR` 同步 dist（/MIR 先清空再重建，**目录 inode 改变**），容器仍绑定旧 inode 所以看不到新文件；叠加 `main.py` 只在**启动时**判断一次 `admin_dist.exists()` 才 `app.mount("/admin", StaticFiles(..., html=True))`。
**修复**：`docker restart kirameku-backend`（重新 bind + 重走启动挂载判断，几秒中断，不碰 PG）。重启后容器内 dist 文件齐全、healthy，`/admin/` 200（text/html），入口 JS `index-*.js`（2.67MB）、CSS、icon、version.json 全部 200，Edge 截图确认 pure-admin 登录页插画正常渲染。
**沉淀**：踩坑 6.3.18、修正 5.6 后台生效机制、8.3 第 5 步补"同步 dist 后必须 restart 收尾"。**以后 admin 重新 build+robocopy 同步后，固定要 restart 后端容器。**

#### 4.10.5 全站回归（结论：零回归）

- **前端 10 个路由全部 200**：/ /posts /archive /moments /albums /friends /messages /novel /about /anime。
- **BFF/后端数据 API**：posts=8 篇、chatters=1、albums=6，BFF 与后端条数一致；navigation 9 项、site-config 含 music_widget/umami 等键正常。
- **两个"看似 404"实为测试误判，不是 bug**：`/api/anime`、`/api/novels` 在 BFF 404，是因为追番页 `anime.astro` 用**静态数据源** `src/data/anime.ts`（构建时打包，本就无后端 API），`novel.astro` 目前是"P2 迁移占位"静态页，都不取数。
- **友链为空不是 bug**：`/api/friend-links` 返回 `[]`，进库 `select count(*) from friend_link` = **0 行**，是用户尚未在后台添加友链数据（页面、接口、链路都正常，添加数据即显示）。
- 本轮所有改动（导航/Umami/删 island/CI/后端 auth/login_log/cloudflared）对既有 P0–P6 功能**无回归**。

### 4.11 第三轮续作（2026-09-13）：音乐挂件上线 + 修复 SSR 截断重大 bug

#### 4.11.1 音乐挂件方案 A 落地（web commit `cdb840b`，CI run 34715783783 success）

严格按 7.5② 的细化方案实现，改动 3 文件（+108/-3）：

1. **新建 `web/src/components/molecules/MusicLinkCard.astro`**：纯静态 SSR 外链卡片（WidgetLayout 外壳 + 音符图标 + 标题/副标题 + 外链箭头），零 island/零运行时 JS；内部再校验一次 `getMusicWidgetOverride()`，url 为空不渲染（双保险零残留）。
2. **`web/src/utils/site-overrides.ts`**：新增 `MusicWidgetOverride` 接口 + `musicWidget` 解析（兼容 JSON 字符串/对象；`enabled||enable` 双键兼容；**url 仅接受 `https?://` 外链防 `javascript:` 注入**）+ `getMusicWidgetOverride()`（enabled 且 url 非空才返回）。
3. **`web/src/components/organisms/SideBar.astro`**：`MusicFallback = !MusicSidebar && musicWidget?.enabled && musicWidget.url ? MusicLinkCard : null`；`componentMap.music = MusicSidebar ?? MusicFallback`；过滤条件改 `widget.type!=="music" || componentMap.music != null`。原 Shirone 播放器逻辑原样保留（musicConfig.enable 仍为 false，未来若解决 stylus/workerd 冲突可无缝切回）。

**验证方法（沉淀）**：本地 preview 的 SSR 渲染不可靠（见 4.11.2，当时误判为"本地怪象"），改用**构建期预渲染 + mock 配置服务器**做确定性验证——`PUBLIC_API_BASE=http://127.0.0.1:9999 pnpm build` 指向只服务 `/api/site-config` 的 node mock（enabled:true + 占位 B 站链接），从 `dist/client/albums/index.html` 直接断言卡片 HTML（href/target=_blank/rel/文案全对）；真实 BFF 构建断言 `music-link` 出现 0 次（禁用零残留）。

**线上验收**：部署后通过 `PUT /api/site-config/music_widget`（admin JWT，body 是 `{"value":"<JSON字符串>"}`，注意 Git Bash 直接 -d 内嵌转义会报 parsing body 错误，**要写 JSON 文件 `-d @file`**）临时启用占位 `https://www.bilibili.com` → 线上卡片渲染 ✓（Edge headless 截图确认视觉：Profile 卡下方，WidgetLayout 样式与其它 widget 一致）→ 回滚 enabled:false → 卡片零残留 ✓。注意 BFF site-config 缓存是 **per-colo Cache API**，写接口的失效只清当前 colo，其它 colo 最长 60s 才生效。

**当前状态**：代码上线，`music_widget` 已回滚为 `{"enabled":false,"title":"音乐","subtitle":"悬浮播放器","url":""}`。**用户在后台「站点配置」把 music_widget 填成 `{"enabled":true,"title":"音乐","subtitle":"B站收藏夹 · 点击顺序播放","url":"<收藏夹链接>"}` 即上线**（等 ≤60s 缓存）。

#### 4.11.2 【重大】发现并修复 SSR 页面响应流截断（web commit `2f77b19`，CI run 34716510215 success）

**现象**：验收音乐挂件时发现线上首页 HTML 只有 74–95KB（正常 159KB）、无 `</html>` 结尾，截断点随机（banner 后/侧栏中段/calendar 里都有）；首页主内容区（文章列表）经常整个缺失。**这是 P6 上线 LiveRefreshBanner 以来就存在的 bug**——`GET 200` 状态码掩盖了截断，此前 4.10.5 的"全站回归"只查了状态码所以没发现。本地 `astro preview`（wrangler dev）复现同样截断，且 **git stash 回滚到 ebff376 基线同样复现**，排除本轮改动嫌疑。

**根因**（`wrangler dev` 本地跑构建产物抓到完整堆栈）：`LiveRefreshBanner.tsx` 第 31 行 `if (!visible) return null;`——SSR 期 `visible` 恒为 false，React island 服务端渲染返回 null，Astro `renderFrameworkComponent` 抛 `Uncaught Error: Unable to render LiveRefreshBanner!`，**中断整个响应流**。首页/归档/文章详情三个 SSR 页面全中招；静态页（albums 等）不带这个 island 所以完好。这正是坑 6.1.7 描述的模式（`client:load` island 会在 SSR 期执行）。

**修复**：`if (!visible) return <div role="alert" hidden />;`（返回隐藏占位而不是 null），一处 4 行。实测：wrangler dev 控制台 0 错误，首页连续 3 次完整渲染 159KB（footer/calendar/文章列表 16 条链接全在）；push 后线上 3/3 完整渲染；文章详情页 141KB 完整（含评论/分享）。

**判定页面是否完整的正确方法（教训）**：不能用 `</html>` 判断——**Astro 产物（含预渲染静态页）本来就不输出 `</html>` 闭合标签**；应检查 `footer` 出现次数 ≥1、文章链接数、结尾是否是完整元素而非中途截断。

**诊断手段（沉淀）**：`astro preview` 吞掉 SSR 错误只显示 `GET / 200 OK`；用 **`pnpm dlx wrangler@4 dev -c wrangler.deploy.json --port 4331` 直接跑构建产物**，SSR 异常会完整打印堆栈。（`wrangler tail` 因本机网络连不上 CF tail 端点不可用。）

#### 4.11.3 旧博客文章迁移补齐（已完成，2026-09-13）

用户确认"旧文章要迁移"后执行。三代博客源盘点：**Typecho（NAS MariaDB `typecho1.3` 库，5 篇）→ HewllBlog/Next.js（GitHub 私有仓 `neutron-star77/HewllBlog`，`posts/*.md` 5 篇）→ Astro（`F:\AI\projects\blog\neutronstar-front`，8 篇正式 + 主题 demo）**。

- **迁移结果：新站从 8 篇补齐到 11 篇**，新增《洛神赋》(luoshenfu)、《千字文》(qianziwen)、《难经》(nanjing)，id=10/11/12，slug 沿用旧站英文文件名，标签/描述/封面（pic2.ziyuan.wang 外链，实测 200）原样保留，`published_at` 事后用一次性容器脚本改回原文日期 2026-07-29。
- **做法**：admin API `POST /api/posts`（注意：**urllib 默认 UA 会被 Cloudflare 1010 拦，要带浏览器 UA**；`POST /api/posts` 无 published_at 字段，schema 不收）→ 写 `fix_dates.py` 用 `app.database.engine` 直接 UPDATE（容器 `docker run --rm` 一次性脚本模式，**`app.config` 强制要求 SECRET_KEY env，哑值即可**；MariaDB 库名 `typecho1.3` 含点，SQL 要用反引号）。
- **核对结论**：Typecho 5 篇与新站完全重合（《0-JpgLossless》→《图片压缩》、《13》→《革命》、《17》→《大远征》，标题在后代博客改过）；HewllBlog 的 yang-gensi→《革命》、bt-7274→《BT-7274》也已在新站。**除主题 demo（hello-astro/launch-day/guide 等）外无遗漏，迁移闭环。**
- **渲染验证**：洛神赋/难经详情页完整（143KB/185KB，footer 在，`<style>` 自定义样式块透传正常——新站 markdown 管线允许原生 HTML，与《44》的 `<details>` 一致）。
- **搜素/字体注意**：pagefind 索引与字体子集只在 CI 构建时重建，当前 3 篇新文章要等下次 web push 部署才会进搜索索引与字体子集。

#### 4.11.4 音乐悬浮播放器（方案 B 落地，2026-09-13）

用户升级需求："音乐卡片要做成直接点击就可以播放……最好做成可以在页面随时移动的悬浮卡片"。已实现并上线（web `cd1a93a`+`2396e47`，CI 34754977579/34755779988 success；后端新增 `/api/bili-fav` 代理）。

**架构**：
- **BFF 尝试被否**：先在 BFF 加了代理，实测 B 站对 Cloudflare Worker 出口 IP 返回 **412 风控**——B 站代理只能放 NAS 后端（国内家宽 IP）。BFF 版代码已撤。
- **后端代理** `Kirameku-backend/app/api/bili_fav.py`：`GET /api/bili-fav?media_id=<fid>`，httpx 带 UA+referer 代拉收藏夹列表，**服务端按 ps=20 自动翻页聚合（最多 5 页=100 首）**，响应带 `Cache-Control: s-maxage=600`（BFF 边缘缓存 10 分钟，对 B 站真实请求每 colo 每批 ≤1 次）。失效视频（无 bvid）自动过滤。
- **前端 island** `web/src/components/islands/BiliFloatPlayer.tsx`（React，**client:only**）：挂在 Layout body（Swup 容器外）→ 全站唯一实例、切页不断播。浏览器现场拉 `/api/site-config/music_widget`（enabled+url 解析 fid）和 `/api/bili-fav`，后台改配置 ≤60s 全站生效，且规避 island SSR null 坑。交互：点封面/播放键直接播（B 站 iframe，自带播放/暂停/进度/音量）、上一首/下一首、播放列表抽屉（封面+时长）、连播=postMessage "ended" + 时长+3s 兜底双机制（去抖 2.5s）、**头部可拖动**（pointer capture，位置存 localStorage）、最小化成小球（iframe 不卸载不断播）、关闭存 sessionStorage。`music_widget.url` 含 fid 时播放器接管，侧栏外链卡片退为无 fid 时的兜底（site-overrides 的 MusicWidgetOverride 新增 fid 解析）。
- **验收**：本地 wrangler dev + dump-dom 证实完整渲染（「♪ 收藏音乐 / 曲目 / 1 / 26 / ☰ 列表」）；线上首页 island 占位+chunk 200、CORS 契约（Origin→ACAO）实测通过、页面完整无回归。

**首版四项修复（`8aad179`+`2bca990`，2026-09-13）**：①最小化/关闭点击无反应——头部 onPointerDown 的 setPointerCapture 把 click 重定向到捕获元素，按下时放过 button/a（根因）；②播放列表封面全 403——B 站图片 CDN 防盗链（带本站 Referer 403/无 Referer 200），所有 img 加 referrerPolicy="no-referrer"；③窗口大小自定义——右下角缩放手柄 240–520px + localStorage 记忆；④取数加 8s/12s 超时兜底 + 错误态提供外链兜底（防任何网络怪异导致永远卡加载态）。进度条拖动提示：跨域 iframe 手势拖出边界即断，默认宽度 288→320 并可调大。

**已知限制**：跨域 iframe 拿不到真实暂停/进度——用户在 iframe 里手动暂停后，时长兜底定时器到点仍会切下一首；B 站接口风控若将来连 NAS IP 也拦，需要加 cookie 或换用 wbi 签名（现在没这问题）。

#### 4.11.5 遗留观察：后端 2 个测试在干净库上失败（既有问题）

`pytest` 报 2 failed（test_likes_and_comments 的 github_user UNIQUE 约束冲突），**git stash 基线同样失败**，与第三轮改动无关。疑与 4.9.3 登录日志改动后测试种子的 github_user 复用有关。待办（P2）：修测试种子，恢复"19 passed"基线。

#### 4.11.6 全站回归（第三轮，结论：零回归）

- 13 个路由全 200（/ /2/ /archive/ /moments/ /albums/ /friends/ /messages/ /about/ /novel/ /anime/ /sitemap-index.xml /robots.txt /auth/callback/）。
- BFF/后端 health ok；admin 200；www 301；BFF 缓存 `X-Cache: MISS`（失效联动正常）。
- 首页/归档/文章详情三个 SSR 页面修复后完整渲染；静态页不受影响。
- 音乐挂件禁用态零残留；启用态卡片渲染正确。
- **旧文章迁移补齐后复验**：文章 8→11 篇（洛神赋/千字文/难经），详情页完整渲染，`/api/posts` 11 条、BFF 与后端一致，归档/首页分页正常。

---

## 5. 关键实现细节（改代码前必看）

### 5.1 取数两条路（别混）

| 场景 | 文件 | 说明 |
|:--|:--|:--|
| SSR/构建期取数 | `web/src/lib/server/api.ts` | `apiGet()`，base=`import.meta.env.PUBLIC_API_BASE ?? https://bff.neutronstar.fun`，自带 15s 进程内缓存；页面在 Worker 里**直接回源 BFF** |
| 浏览器取数 | `web/src/lib/api/client.ts` + `hooks.ts` | `apiGet/apiPost`（自动带 Bearer）、SWR hooks（`usePosts/usePost/useChatters/useAlbums/useMessages`，key 形如 `["posts",page,size]`） |
| 文章适配 | `web/src/utils/content-utils.ts` | `apiPostToEntry()` 把后端字段映射成原版 CollectionEntry 形状（组件零改动）；`entry.postId` 是数字主键（评论要用） |

### 5.2 缓存与失效（BFF）

- `tagsForPath()`：`/api/chatters→moments`、`/api/albums→albums`、`/api/comments→comments`、`/api/posts|categories|tags→posts`、`/api/friend-links→friends`、`/api/site-config→site`、`/bff/*` 各自映射，**恒含 `all`**。
- 读接口默认 `s-maxage=60, stale-while-revalidate=300`；聚合口 120s；命中返回 `X-Cache: HIT`（调试用）。
- 失效：`POST /internal/revalidate`（HMAC-SHA256，`x-signature`，body `{tags:[], urls:[]}`）→ 按 KV `CACHE_TAGS` 自建 tag→URL 索引清缓存 + 广播 SSE。**响应快（~0.7s），广播异步。**
- ⚠️ 后端调 BFF 是 fire-and-forget（httpx timeout=3s），失败只记 warning，不阻塞写操作。

### 5.3 两套鉴权（别搞混）

| 身份 | 签发 | 校验 | 用途 |
|:--|:--|:--|:--|
| 管理员 | `POST /api/auth/login`（用户名密码） | `get_current_user`（JWT `sub`=**用户名**，落库校验 `is_admin`） | 后台 admin 写接口 |
| 访客 | GitHub OAuth 回调签发 | `get_github_user_optional` / `require_github_user`（JWT `sub`=**github_user.id**，payload `type:"github"`） | 评论/点赞 |

- 后台管理员默认 `admin`（密码见第 9 节）；`DELETE /api/comments/{id}` 支持两种身份（作者本人 or 管理员）。

### 5.4 数据模型要点

- `comment`：多态（`target_type`+`target_id`），`post_id` 仅 post 维度同步；`status` 默认 `approved`（暂无审核流程，后台可改）。
- `chatter_comment`：说说评论独立表，`chatter.comments_count` 冗余计数（**增删都要维护**）。
- `likes`：唯一约束防重；计数在目标表（`chatter.likes` / `comment.likes` / `post.likes`）。
- 迁移：`migrations/versions/0001_baseline.py`、`0002_likes_and_polymorphic_comments.py`（生产已 head）。**Stale 提醒**：新模型变更一律走 Alembic，别用 `create_all` 期待它改表。

### 5.5 图片

- 母版：`https://gcore.jsdelivr.net/gh/neutron-star77/fastimage@main/2026/08/{433..666}.webp`（1920/q82）
- 派生：`…/thumbs/{name}`（800/q72，列表）、`…/full/{name}`（1600/q74，灯箱）；`AlbumGrid.deriveVariants()` 按目录约定派生，**不要逐条硬编码**。
- 全量链接清单：`F:\AI\projects\fastimage\鬼刀派生图链接.md`。
- BFF `/img/*` 是 CF Image Resizing（付费权益未验证），当前只用于**后端本地上传**的图（`/uploads/...`），**不要**用它代理 jsDelivr 远程图。

### 5.6 后台界面生效机制

`admin/dist` 以 **bind mount** 方式挂进容器（`-v /share/.../backend/admin/dist:/app/admin/dist:ro`）。源码改动需 `vite build` 后用 robocopy 同步 dist 到 NAS。**注意**：由于 `main.py` 在启动时才判断 `admin/dist.exists()` 并挂载，且 `robocopy /MIR` 会重建目录改变 inode，**同步后必须 `docker restart kirameku-backend`** 才能让容器看到新文件（详见坑 6.3.18）。若容器启动时 dist 已存在且只是覆盖个别文件（非 /MIR 重建），则可免重启。

---

## 6. 踩坑大全

> **已抽离为独立文件 [`docs/坑大全.md`](坑大全.md)**（编号 6.1–6.5 不变，历史「坑 6.x」引用仍有效）。改代码前先按场景读对应分区。

---

## 7. 下一步待办（含做法与验收）

> **2026-09-13 更新**：7.1 ①–④、7.2 ⑤–⑧ 全部完成并线上验收（见 4.8）。7.3 可选加固大部分完成。剩余项见下方标注。

### 7.1 高优先（运维风险 / 明显缺口）—— ✅ 全部完成

**① 前端自动部署（正式站）** — ✅ 已完成（CI 自动 `pnpm dlx wrangler@4 deploy`，见 4.8①）

**② RSS / Atom / llms.txt / robots.txt 端点** — ✅ 已完成（四个端点 200，见 4.8②）

**③ Lighthouse 性能预算** — ✅ 已完成（Performance 84，见 4.8③）；TTFB ~1640ms 是 SSR 回源 BFF 固有延迟

**④ 字体子集化** — ✅ 已完成（14.5MB→770KB，见 4.8④）

### 7.2 中优先（功能完整性）—— ✅ 全部完成

**⑤ 首页/归档/文章详情「停留时自动刷」** — ✅ 已完成（LiveRefreshBanner，见 4.8⑤）

**⑥ 导航/侧栏接后台 `site_config`** — ✅ 已完成（navigation-api.ts + TopAppBar/Drawer 改造，见 4.8⑥）

**⑦ 搜索（Pagefind）+ Markdown 增强** — ✅ 已完成（postbuild 生成索引 + mermaid/katex/expressive-code，见 4.8⑦）

**⑧ 文章加密 / 追番 / 纹理 / FAB / 分享海报** — ✅ 基本完成（追番页+分享海报+纹理+FAB 已上线；文章加密组件就绪但无加密文章，见 4.8⑧）

### 7.3 可选加固

| 项 | 状态 | 说明 |
|:--|:--|:--|
| JWT 从 localStorage 升级为 httpOnly cookie | ⏳ 未做（用户已了解好处，暂不实施） | 需改后端回调形态（不再 302 带 token，改 Set-Cookie）+ 前端 fetch 带 credentials；架构级改动。好处见 7.5① |
| 评论创建时校验目标存在性 | ✅ 已完成 | `_verify_target_exists()`，见 4.8 |
| 后台评论分页 | ✅ 已存在 | `GET /api/comments/admin` 已有 page/size（默认 20） |
| 清理 7 个死 island | ✅ 全部完成 | 已删 NavigationIsland/MobileNavigation（上轮）+ PostList/HomeFeed/SidebarVisibility/MusicFloatingCard/PostView（本轮，见 4.9.2）；islands 目录现存 8 个均在用 |
| `/posts/` 改 301 评估 | ✅ 不需要改 | `/posts/` 当前返回 200 是有效文章列表页，非 meta-redirect |
| 首页残留 `Shirone` 字样 | ✅ 已清理 | share-poster/siteConfig 默认值改 Neutronstar；其余为内部标识符不可改 |
| `/api/comments` 读接口分页 | ✅ 已完成 | page/size 参数，默认 100，见 4.8 |
| 后台 refresh-token / me-logs 占位接口 | ✅ 已完成 | 本轮实现，含 login_log 表+登录埋点，见 4.9.3 |
| cloudflared 开机自启 | ✅ 已完成 | autorun.sh + start-tunnel.sh（幂等+setsid+http2），见 4.9.6 |
| CI 自动字体子集化 | ✅ 已改 deploy.yml | install 后 build 前跑 subset-font，continue-on-error 回退，见 4.9.5；待 push 触发 CI 验证 |
| Umami 后台可配可查看 | ✅ 已完成 | 后端默认+admin面板+前端覆盖层，见 4.9.4；待用户填真实凭据端到端验证 |

### 7.4 已知缺陷清单

| 缺陷 | 影响 | 状态 / 备注 |
|:--|:--|:--|
| `astro dev` 不可用 | 开发体验（只能 build+preview） | 已知限制，见 6.1.1 |
| 前端改动不会自动上线 | 可能忘记部署 | ✅ 已解决（CI 自动部署） |
| 导航/侧栏未接后台 | 后台改了不生效 | ✅ 已解决（见 4.8⑥） |
| RSS/atom/llms 404 | 订阅/SEO | ✅ 已解决（见 4.8②） |
| Yozai 字体 15MB 入库 | 仓库体积 + 首屏 | ✅ 已解决（子集化 770KB，原 TTF 保留作源；CI 自动重新子集化见 4.9.5） |
| 音乐挂件未启用 | Shirone 特性缺失 | ✅ 已解决（方案 A 外链卡片上线，后台 music_widget 可配，默认关闭；只差用户填收藏夹链接，见 4.11.1） |
| 构建期个别图片 compile 后变大 | 体积 | 例：extreme-3 1.6MB→3.8MB；Astro sharp 处理问题，影响小 |
| 评论无审核流程 | 内容风险 | ✅ 已解决（默认 pending，后台可审核，见 4.8） |
| cloudflared 隧道持久化 | NAS 重启后需手动拉起 | ✅ 已解决（autorun.sh + start-tunnel.sh，见 4.9.6） |
| 导航栏中等宽度竖排拥挤 | 1024–1279px 用户看不到完整导航 | ✅ 已修复（断点 lg→xl + nowrap，见 4.9.1）；待 push 上线 |
| 后台安全日志页空白 | me-logs 接口 404 | ✅ 已解决（login_log 表 + 接口实现，见 4.9.3） |
| Umami 统计无法后台配置 | 需改代码才能换统计 ID | ✅ 已解决（后台站点配置页 Umami 面板，见 4.9.4） |
| **SSR 页面响应流被随机截断** | 首页/归档/文章详情经常缺文章列表、footer、侧栏后半段 | ✅ 已修复（LiveRefreshBanner SSR 返回 null 所致，`2f77b19` 已上线并三连验证，见 4.11.2） |

### 7.5 第二轮需求剩余项与下一步行动（2026-09-13 交接点）

> **当前状态（2026-09-13 第三轮续作后）**：本轮 8 项需求中 6 项已完成并**全部上线、线上验收、全站零回归**（详见 4.9 + 4.10）。第三轮续作（4.11）：**②音乐功能最终形态 = B 站收藏夹悬浮播放器**（方案 B：站内直接播放/可拖动/自动连播/播放列表，BiliFloatPlayer island + 后端 /api/bili-fav 代理，web cd1a93a+2396e47 CI success；侧栏外链卡片退为无 fid 兜底，见 4.11.4）；**发现并修复了 SSR 页面响应流随机截断的重大 bug**（LiveRefreshBanner SSR 返回 null，首页/归档/文章页缺文章列表的元凶，`2f77b19` 已上线三连验证，见 4.11.2）；**旧文章迁移补齐 8→11 篇**（见 4.11.3）。web 子仓 main = `2396e47`（4 次 CI success）。**真正待办只剩需要用户输入的 1 项**：⑧Umami 的 websiteId/scriptUrl/shareUrl（后台直接填，无需改代码）。③JWT cookie、④TTFB 用户暂缓；⑦文章加密用户明确不做。

#### ① 前端 web 仓：commit → push → CI 部署 → 线上验收 —— ✅ 已完成（2026-09-13）

**已提交并上线**（web 仓 commit `ebff376`，10 files changed, +60/-301）：
- `src/components/organisms/TopAppBar.astro`（导航断点 lg→xl + nowrap，见 4.9.1）
- 删除 `src/components/islands/{PostList,HomeFeed,SidebarVisibility,MusicFloatingCard,PostView}.tsx`
- `src/utils/site-overrides.ts` + `src/layouts/Layout.astro`（Umami 覆盖层，见 4.9.4）
- `.github/workflows/deploy.yml`（CI 字体子集步骤，见 4.9.5）
- `.gitignore`（忽略 `src/assets/fonts/.subset/` 字符集产物）

**CI 验收**：run 34713250765 success；"Subset CJK font" 步骤实际执行——从 BFF 拉 8 篇文章、收集 3264 字符、14869KB→771KB（-94.8%），证明 CI 自动字体子集化生效。

**线上导航验收（Edge headless 三宽度截图）**：
- 1024px / 1180px：出汉堡菜单按钮（☰），无竖排拥挤 ✓
- 1440px：横排 9 项（首页/文章/归档/说说/相册/友链/杂谈/小说/关于）清晰横排 ✓
- 说说、友链在宽屏正常显示，问题解决。

#### ② 音乐挂件改"点击进 B 站网页版收藏夹顺序播放" —— ✅ 已全部完成并启用（2026-09-13）

> **闭环记录**：方案 A 代码上线（`cdb840b`，见 4.11.1）→ 用户提供收藏夹链接 `https://space.bilibili.com/90898408/favlist?fid=3631802308&ftype=create` → 后台 `music_widget` 已填入并启用（enabled:true），线上验证卡片 href/文案/rel 正确、页面完整。想换文案或链接：后台站点配置编辑 `music_widget` 行即可，≤60s 生效。以下为原始方案记录（背景与原理仍有参考价值）。

**用户需求原话**：音乐挂件点击后链接到"网页版 B 站收藏夹"进行**顺序播放**，要求**最小代码代价**。

**为什么现在侧栏没有音乐挂件（已摸清完整链路，下一个 AI 不用重新调研）**：
1. `src/config/sidebarConfig.ts:31` 里 music widget 是 `{ type:"music", enable:true, slot:"top" }`（编排层是开的）。
2. 但 `src/components/organisms/SideBar.astro:58-67`：`const musicOptions = resolveMusicOptions(musicConfig)`，只有 `musicOptions && hasEnabledMusicWidget` 才去 `await import("virtual:shirone-music-sidebar")` 拿重型播放器组件，否则 `MusicSidebar = null`。
3. `src/config/musicConfig.ts:50` 是 `enable:false`（原 Shirone 播放器的 stylus 在 workerd 运行时编译冲突，故关闭），`resolveMusicOptions` 在 `!config.enable` 时直接返回 null（musicConfig.ts:124）。
4. 于是 SideBar.astro:92 的过滤条件 `widget.type!=="music" || MusicSidebar!==null` 把 music widget 滤掉 → 不渲染。
5. 后台配置位已现成：后端 `app/services/site_config_service.py` 的 `DEFAULT_PUBLIC_CONFIG.music_widget = {enabled:false, title:"音乐", subtitle:"悬浮播放器", url:""}`，会经 `/api/site-config` 下发；但**前端 `src/utils/site-overrides.ts` 目前只解析了 title/description/images/sidebar/umami，还没解析 music_widget**（SiteOverrides 接口里没有这个字段，需新增）。

**关键认知（决定方案选型）**：用户要的是"跳到 B 站网页版收藏夹，由 B 站自己顺序连播"，**不是在自己站内做播放器**。B 站收藏夹页本身就支持"播放全部 → 按列表顺序自动连播下一个"。所以最小方案根本不需要碰原 Shirone 播放器、不需要音频 API、不存在 CORS、不触发 stylus/workerd 冲突——只做一个"外链卡片"。

**✅ 方案 A（强烈推荐，真正最小，约 40 行，零运行时 JS/零 island/零虚拟模块）——外链卡片**：
- **(1) 新建纯 Astro 组件** `src/components/molecules/MusicLinkCard.astro`：一个语义化 `<a href={url} target="_blank" rel="noopener noreferrer" class="card-base ...">`，里面显示一个音符图标 + `title` + `subtitle`（如"点击前往 B 站收藏夹顺序播放 →"）。纯静态、SSR 直出，不 import 任何 svelte/react/虚拟模块，从根上绕开 workerd 冲突。
- **(2) `src/utils/site-overrides.ts` 增加 musicWidget 解析**：`SiteOverrides` 接口加 `musicWidget: { enabled:boolean; title:string; subtitle:string; url:string } | null`；`EMPTY` 加 `musicWidget:null`；在 getSiteOverrides 里照 umami 的写法解析 `cfg.music_widget`（后端下发的是 JSON 字符串，`typeof raw==="string"?JSON.parse(raw):raw`，校验 enabled===true 且 url 非 http 链接才保留，防 `javascript:` 注入）；导出一个 `getMusicWidgetOverride()` 便捷函数。
- **(3) `src/components/organisms/SideBar.astro` 接 fallback**：顶部 `const musicWidget = (await getSiteOverrides()).musicWidget;`；把第 64-67 行改成"重型播放器优先，拿不到再退到外链卡片"——
  - `MusicSidebar` 仍按原逻辑取虚拟模块（保持 null）；
  - 新增 `const MusicFallback = (!MusicSidebar && musicWidget?.enabled && musicWidget.url) ? MusicLinkCard : null;`（import MusicLinkCard）；
  - `componentMap.music` 改成 `MusicSidebar ?? MusicFallback`；
  - 第 92 行过滤条件同步改成 `widget.type!=="music" || componentMap.music != null`。
  - 给 MusicLinkCard 透传 `widget` 的同时把 musicWidget 的 title/subtitle/url 通过 props 或在 SideBar 里直接包一层传下去（最简单：MusicLinkCard 直接 `Astro.props` 收 title/subtitle/url，SideBar 渲染 music 类型时传这三个值）。
- **(4) 后台填写**：admin「站点配置」页给 `music_widget` 这一行填 JSON：`{"enabled":true,"title":"我的歌单","subtitle":"B站收藏夹 · 点击顺序播放","url":"<收藏夹链接>"}`。若后台没有 music_widget 专用编辑 UI，就先用现有通用 KV 编辑行（和其他 site_config 一样）；想更好用可仿 4.9.4 的 Umami 专用面板做一个（非必须）。
- **B 站收藏夹链接怎么拿（告诉用户）**：打开自己的 B 站收藏夹，浏览器地址栏形如 `https://space.bilibili.com/<你的mid>/favlist?fid=<收藏夹media_id>&ftype=create`，**整条复制填进后台 url 即可**；这个页面点"播放全部"就会顺序连播。想要落地即自动播放列表，可用 `https://www.bilibili.com/list/ml<media_id>`（收藏夹播放列表视图，自带顺序/随机切换，默认顺序）。
- **验收**：本地 `pnpm build && pnpm preview`（dev 不可用，见 6.1）→ 侧栏出现音乐卡片 → 点击新标签打开收藏夹；后台 `enabled:false` 或清空 url 时卡片消失（零残留 DOM，符合"禁用零负担"原则）；`pnpm build` 不报 stylus/workerd 错。push 走 CI 后线上复核。

**方案 B（较重，约 200 行 + 1 个后端代理，仅当用户坚持"不离开本站播放"才做）——站内浮层连播**：
- 后端新增代理接口转 B 站收藏夹列表 API `api.bilibili.com/x/v3/fav/resource/list?media_id=<id>&ps=20&pn=N`（**浏览器直连必 CORS**，必须由后端代拉并可加浏览器 UA），返回 [{bvid,title,cover,duration}...]。
- 前端侧栏/浮层用 `<iframe src="https://player.bilibili.com/player.html?bvid=<当前>&autoplay=1&high_quality=1">` 播当前视频，监听 iframe/播放器无法直接拿 ended（跨域），需用 B 站 `&t=` 轮询或 postMessage，到点后把 bvid 指针 +1 换 src 实现顺序连播。
- 代价：要维护播放列表状态、跨域 ended 检测不可靠（B 站 iframe 不抛 ended 事件，只能靠 duration 计时，用户拖动会错位）、后端要承担对 B 站的请求。**除非用户明确要站内沉浸播放，否则不建议。**

**✅ 已完成**：后台 `music_widget` 现值为 `{"enabled":true,"title":"音乐","subtitle":"B站收藏夹 · 点击顺序播放","url":"https://space.bilibili.com/90898408/favlist?fid=3631802308&ftype=create"}`。日后想换链接/文案：后台站点配置编辑该行 JSON，≤60s 生效；若用户改主意要站内不跳转播放，再评估方案 B。

#### ③ JWT→httpOnly cookie（已解释好处，用户暂不实施）

**好处（已向用户解释）**：
- 防 XSS 窃取 token（httpOnly cookie 无法被 document.cookie 读取，localStorage 可被 XSS 读走）。
- 自动随请求携带（fetch 带 `credentials:include`），无需手动塞 Authorization 头。
- 可设 `Secure` + `SameSite=Lax/Strict`，防 CSRF 面更广。
- 过期/登出由服务端 Set-Cookie 清空，比前端清 localStorage 更可靠。

**代价/风险**：后端 GitHub OAuth 回调要从"302 带 ?token="改成"Set-Cookie 后 302"；前端所有 `apiGet/apiPost` 要加 `credentials:"include"`；BFF/后端 CORS 要 `allow_credentials=True` 且不能 `allow_origins=*`；CSRF 防护需额外加 token。架构级改动，用户暂不做。

#### ④ TTFB 缓存（已解释好处，用户暂不实施）

**好处（已向用户解释）**：
- 当前 TTFB ~1640ms 是 SSR 每次回源 BFF 的固有延迟。TTFB 缓存（如 BFF 对 SSR 页面 HTML 做边缘缓存 + stale-while-revalidate）可把重复访问降到 <100ms。
- 减轻 Worker isolate 冷启动和 BFF 回源压力。
- 对 SEO 爬虫友好（Google 用 TTFB 作 Core Web Vitals 指标）。

**代价/风险**：页面含用户态（登录状态/评论）时缓存需按身份分键或用客户端水合；写操作后需主动 purge；实现复杂度中等。用户暂不做。

#### ⑤ 文章加密接入（用户明确暂不做）

`ProtectedPost/PasswordGate/post-decryption` 组件已存在但未接入，因 API PostEntry 无 encrypted 字段。用户明确"暂时不用管"。后续要做需：后端 Post 模型加 encrypted/password_hash 字段+迁移，文章详情接口按密码校验返回正文，前端 PasswordGate 组件接入。

#### ⑥ 外仓 commit（后端+admin+脚本+文档）—— ✅ 已完成并 push（master 到 `9d22e78`）

外仓已分三次提交并全部推送：`03186c3`（后端 login_log/auth/site_config + admin Umami 面板 + 6 个 NAS 运维脚本 + 本文档，14 files +673/-18）→ `aa3ac0d`（文档状态回写）→ `9d22e78`（补坑 6.3.18）。
- `Kirameku-backend/app/models/login_log.py`（新）、`app/models/__init__.py`、`app/api/auth.py`、`app/services/site_config_service.py`、`migrations/versions/0003_login_log.py`（新）
- `Kirameku-backend/admin/src/api/user.ts`、`admin/src/views/site-config/index.vue`
- `scripts/start-tunnel.sh`（新）+ 其余 NAS 运维脚本（rebuild/start/redeploy-backend、restart-tunnel、diag-nas）入库
- `docs/HANDOFF-续开发交接文档.md`

后端源码此前已同步 NAS 并重建容器（线上已生效），外仓 commit 是版本记录。**注意**：`admin/dist` 不入库（gitignored），线上后台用的是已同步到 NAS bind mount 的 dist；且同步 dist 后必须 restart 后端容器（坑 6.3.18）。

#### ⑦ 临时文件清理 —— ✅ 已完成

本地 `scripts/` 与 NAS `U:\kirameku\` 的调试临时文件（`_*.sh`、`_*.png`、`_home_debug.html`、`_parse_nav.mjs`、`verify-stamp-loginlog.sh`、`rebuild-backend-migrate.sh`）已全部删除。本地 scripts 目录现存 7 个文件均为有价值脚本：diag-nas.sh、rebuild-backend.sh、redeploy-backend.sh、restart-tunnel.sh、start-backend.sh、start-tunnel.sh、sync-upstream.mjs。

#### ⑧ 下一个 AI 接手顺序（Checklist，按序执行）

1. **先 grounding**：`cd web; git log --oneline -3`（应见 2f77b19 → cdb840b → ebff376）、外仓 `git log --oneline -3`（本文档提交应在最上），两仓 `git status` 都应干净；读本文 0.1 铁律 + 第 1 节架构 + 4.9/4.10/4.11 + 第 6 节坑（尤其新增的 6.1.14/6.1.15）。
2. **向用户要的东西**：~~B 站收藏夹链接~~（✅ 已提供并启用，见 7.5②）；只剩 **Umami 的 websiteId / scriptUrl / shareUrl**（拿到后后台 Umami 面板直接填，≤60s 生效；若用户没自建 Umami 服务则搁置）。
3. **每步都验收**：前端改动必跑本地 build+preview（dev 不可用）；**SSR 页面改动必须验证响应完整性**（footer 次数/结尾元素完整，见坑 6.1.14——状态码 200 不代表页面完整）；后端改动走 SMB 同步→rebuild-backend.sh→健康检查。
4. **不要主动做**：③JWT cookie、④TTFB（用户暂缓）、⑦文章加密（用户明确不做），除非用户重新提起。
5. **完成后同样回写本文**：更新第 3、4、6、7、10 节对应内容（遵循文末"只减不增、同源唯一"原则）。

---

## 8. 命令速查 / 9. 凭据与环境变量 / 10. 关键 ID 速查

> **已抽离为独立文件 [`docs/命令与运维速查.md`](命令与运维速查.md)**（编号 8.x/9.x/10.x 不变）。部署、排障、查凭据去那里。

---

> 更新本文件的原则：**只减不增、同源唯一、过时即删**。每次完成一个阶段，更新第 3 节（进度总览）、第 4 节（完成记录）、第 6 节（新踩的坑）、第 7 节（待办销项）四处的对应内容，再把原文细节留在 `.codebuddy/memory/YYYY-MM-DD.md`。
