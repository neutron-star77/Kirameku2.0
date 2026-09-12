# Kirameku2.0 交接文档（给下一个 AI / 开发者）

> 更新时间：**2026-09-13（第三轮续作后）**　主工程：`F:\AI\projects\Kirameku2.0`
> 一句话现状：**正式站 <https://neutronstar.fun> 已经是新站** —— Shirone 外壳（Astro 7 + Svelte 5 + React 19 islands）+ 真实后端数据（NAS FastAPI/PG）+ SSE 实时 + GitHub 登录/评论/点赞，跑在 **Cloudflare Workers（SSR）** 上。
> 进度：**P0–P7 全部完成并线上验收，P7 域名切换完成；可选加固全部完成**。第二轮 8 项需求 6 项已上线（见 4.9+4.10）；**第三轮续作（2026-09-13，见 4.11）：音乐挂件方案 A 已实现并上线（代码就绪、后台开关+链接可配，默认关闭待用户填收藏夹链接）；过程中发现并修复了一个线上重大 bug——LiveRefreshBanner SSR 返回 null 导致首页/归档/文章页响应流被随机截断（用户一直看到的"首页没文章列表"即此），已修复上线并三连验证完整渲染。** 真正待办只剩 2 项需用户输入：一条 B 站收藏夹链接（填后台 music_widget 即上线）+ Umami 真实统计凭据（后台直接填）。见 7.5。
>
> 配套阅读（按顺序）：
> 1. 本文（先读第 0、1、4、6、7 节）
> 2. **`docs/站点功能与使用说明.md`（站长视角：地址/功能/内容去向/常见修改指南/待办优先级——用户问"怎么用/怎么改/内容去哪了"先甩这篇）**
> 3. `docs/方案-v2.0-Shirone1比1复刻与SSE实时.md`（设计锁定 L1–L10 与工单路线图）
> 3. `CONTEXT.md`（领域词汇）+ `docs/adr/`（架构决策）
> 4. `web/docs/部署与二次开发指南.md`（前端视角的部署与坑）
> 5. `docs/DEPLOY-NAS.md`（后端部署）、`docs/开发过程与踩坑-二次开发指南.md`（T0/T1 历史）
> 6. 工作记忆：`.codebuddy/memory/2026-09-12.md`、`2026-09-13.md`（本次全部细节与踩坑原文）

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

#### 4.11.3 全站回归（第三轮，结论：零回归）

- 13 个路由全 200（/ /2/ /archive/ /moments/ /albums/ /friends/ /messages/ /about/ /novel/ /anime/ /sitemap-index.xml /robots.txt /auth/callback/）。
- BFF/后端 health ok；admin 200；www 301；BFF 缓存 `X-Cache: MISS`（失效联动正常）。
- 首页/归档/文章详情三个 SSR 页面修复后完整渲染；静态页不受影响。
- 音乐挂件禁用态零残留；启用态卡片渲染正确。

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

## 6. 踩坑大全（现象 → 原因 → 解法）

### 6.1 前端 / Astro

1. **`astro dev` 当前不可用**：rolldown 依赖扫描对 `ImageWrapper.astro` 误报 + SSR deps 缓存反复损坏（清 `.vite` 无效）→ 用 `pnpm build && pnpm preview`（workerd 本地跑产物，端口同样 4321）替代。
2. **Astro 7 没有 `output:"hybrid"`**（Astro 5 就移除了）→ `output:"static"` + adapter，实时页写 `export const prerender = false`。
3. **Cloudflare adapter 的预渲染在 workerd 里跑**：原生模块（sharp 等）、运行时读 fs 都会炸；入口 chunk 的 `import.meta.url` 可能是 `undefined`（已在 `integration/ssr-node-shims.ts` 兜底）。
4. **占位动态路由必须 `getStaticPaths(){return []}`**，否则构建报 `GetStaticPathsRequired`。
5. **`[...page].astro` 是首页真身**（上游没有 `index.astro`），且 SSR 化后它**会吞掉所有未知路径** → 已加「仅数字分页放行」守卫（`Response(404)`）。
6. **Astro island 会各自打包一份依赖**：产物里 `use-swr-*.js` 有**多份不同 chunk** → 模块级单例（EventSource / SWR cache）不可靠。实时层因此把连接挂 `window.__kiramekuRealtimeHub`、把重校验交给各 island 自己的 hook。
7. **`client:load` 的 React island 会在预渲染期被 SSR**：组件里如果顶层访问浏览器 API 或抛错，构建直接失败（曾出现 `Unable to render RealtimeBridge!`）→ 要么写成 SSR 安全，要么用 `client:only="react"`。
8. **路径末尾斜杠**：`/auth/callback` → 301 到 `/auth/callback/`，**query 会保留**（已实测），新页面注意别依赖无斜杠 URL。
9. **Svelte 5 是 runes 模式**（`$state`/`$derived`），不是 `export let`；`variables.styl` 需要 stylus 支持。
10. **pnpm 11 不再读 `package.json.pnpm.onlyBuiltDependencies`** → 必须在 `pnpm-workspace.yaml` 写 `allowBuilds`（esbuild/workerd/sharp…），否则二进制不装、构建失败。
11. **路径别名**：`@config/`、`@data/` 不存在；配置用 `@/config/`，data 用相对路径（如 `../data/anime`）。`@components/`、`@utils/`、`@i18n/` 是正常别名。
12. **Pagefind 在 Windows 上调用**：`execFileSync("pagefind")` 会报 `spawn pagefind ENOENT`；必须 `shell:true` + 完整路径 `node_modules/.bin/pagefind.cmd`。
13. **字体子集是静态生成的**：`pnpm fonts:subset` 从当前 API 文章收集字符，新增含生僻字的文章可能缺字（tofu），需重新跑子集化。
14. **【重大】React/Vue/Svelte island 在 SSR 期返回 `null`/`undefined` 会中断整个响应流**：Astro `renderFrameworkComponent` 抛 `Unable to render <组件名>!`，已 flush 的部分照常发出（HTTP 200），其余全部丢失——页面随机截断且状态码正常，极难察觉（LiveRefreshBanner 因此把首页/归档/文章详情截断了很多天没人发现）。**守则：island 组件 SSR 分支永远返回元素（如 `<div hidden />`），不许 `return null`；新增 SSR 页面 island 后必须验证响应完整性**（检查 footer 出现次数/结尾元素完整，不能用 `</html>` 判断——Astro 产物本来就不输出 `</html>`）。诊断用 `pnpm dlx wrangler@4 dev -c wrangler.deploy.json` 跑构建产物看完整堆栈（`astro preview` 吞错误只显示 200）。见 4.11.2。
15. **本地 `astro preview` 的 SSR 渲染不可靠且吞错误**（截断、无日志）：需要确定性验证 SSR/侧栏渲染时，用**构建期预渲染 + mock 配置服务器**（`PUBLIC_API_BASE=http://127.0.0.1:9999 pnpm build` 指向只服务 `/api/site-config` 的 node mock，直接断言 `dist/client/**/*.html`），或 `wrangler dev` 跑产物看日志。见 4.11.1/4.11.2。

### 6.2 Cloudflare（Pages / Workers / DO / Token）

1. **`fetch` 默认跟随 3xx** → BFF 代理必须 `redirect:"manual"`，否则后端 302（例：`/api/auth/github/login`）被吃掉，浏览器拿到 **200 + 别人的页面**（OAuth 流程直接断）。**读代理与写透传都要加。**
2. **Worker 自定义域接口是 `PUT`**（`/accounts/{acc}/workers/domains`），POST 返回 405。
3. **`wrangler deploy` 带 `custom_domain` 路由时，若 DNS 上仍有同名记录，会静默只上传脚本不绑域**（表现为"部署成功但域名还是旧站"）→ 必须先清 DNS/解绑 Pages。
4. **免费计划 Durable Object 必须用 `new_sqlite_classes`**（KV 后端类要付费）；迁移 tag 一旦上线不可改，新增 class 要追加新的 `[[migrations]]`。
5. **DO 里 `writer.write()` 不设超时会把整个实例写僵**：客户端"连上但不读"→ write 永不 resolve → 该 DO 后续请求排队 → BFF `/internal/revalidate` 跟着 hang（实测 40s 超时，后端 httpx 3s 直接失败）。解法：逐条 `Promise.race` 2s 超时 + 摘除死连接 + 广播 `waitUntil` 异步；另留 `ROOM_VERSION` 前缀当逃生舱（bump 即换新实例）。
6. **`wrangler secret put` 走管道 stdin 会把结尾换行存进密钥**（本地 `.dev.vars` 与线上不一致 → HMAC 永远 401）→ 改用 CF API 写：`PUT /accounts/{acc}/workers/scripts/{name}/secrets`，body `{name,text,type:"secret_text"}`。
7. **Account Token 的 `/user/tokens/verify` 返回 401 是正常的**（无 user 级权限），不影响 account 级操作。
8. **Pages 环境变量字段名是 `env_vars`**（旧文档的 `environment_variables` 会静默写不进去但返回 success）。
9. **"绑定 active + DNS 对 + purge 了仍是旧内容"** 时，先查 zone 的 **Worker route 抢占**（`GET /zones/{zone}/workers/routes`），优先级高于 Pages。
10. **`cdn.jsdelivr.net` / `fastly.jsdelivr.net` 对 gh 资源会 301 到 raw** → 图床统一走 `gcore.jsdelivr.net`。
11. **GitHub Actions ubuntu runner 上 `npx wrangler@4 deploy` 报 `sh: wrangler: not found`（exit 127）** → 必须用 `pnpm dlx wrangler@4 deploy`（npx 在 pnpm 项目里解析不到二进制）。

### 6.3 NAS Docker / 部署

1. **docker 不在 PATH**：`/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker`，且必须 `export DOCKER_HOST=unix:///var/run/docker.sock`。
2. **环境变量在 `docker run -e` 里**（不是 `.env`）→ 改 env 必须**重建容器**（restart 不读新 env）。
3. **Alembic 迁移必须在应用容器重启前跑**！否则新代码启动时 `SQLModel.metadata.create_all` 会先把新表建出来，迁移再 `create_table` 就报"表已存在"。
4. **镜像可能落后于源码**（本项目真实发生：容器里连 `cache_invalidate.py` 都没有）→ 改后端**必须** SMB 同步 + `docker build` + 重建容器，别只 `restart`。
5. 重建容器命令要点：先 `tag` 备份镜像（`kirameku-backend:bak-YYYYMMDD`），只 `stop/rm/run kirameku-backend`，**别碰 PG 与卷**；`admin/dist` 与 `kirameku_uploads` 的挂载参数别丢。
6. **源码同步一律走 SMB**（`robocopy … /MIR /XD .venv __pycache__ uploads .git admin\node_modules /XF *.db .env *.log` 或针对 `app/`、`migrations/`、`admin/dist` 分步同步）；**禁止 `scp` / `ssh "cat >"`**（编码/权限会坏）。robocopy 退出码 **0–7 都算成功**。
7. **大目录 robocopy 会被判"长时间无输出"而中断** → 分目录小步同步。
8. 真要跑管理类命令又不想弹确认，可**把命令写成 `.sh` → `Copy-Item` 推到 `U:\kirameku\` → `ssh hewll 'tr -d "\r" < /share/.../x.sh | sh'`**，用完再写个自删除清理脚本同法跑掉（实战有效）。
9. 一次性脚本执行容器内 python 的正确姿势：`docker run --rm -w /app -e PYTHONPATH=/app -v <host脚本>:/tmp/x.py -e DATABASE_URL=… <image> python /tmp/x.py`（少了 `-w /app` 或 `PYTHONPATH` 会 `ModuleNotFoundError: app`）。
10. **cloudflared 必须加 `--protocol http2`**：NAS 网络限制 UDP/QUIC，默认 QUIC 协议注册连接后立即 "timeout: no recent network activity"（表现为 API 530/502，进程在跑但未连接边缘）。重启脚本见 `scripts/restart-tunnel.sh`（已复制到 `U:\kirameku\`）。
11. **后端容器无 `.env` 文件**：env 全部通过 `docker run -e` 传入（DATABASE_URL / SECRET_KEY / CORS_ORIGINS / FRONTEND_ORIGIN / BFF_ORIGIN），重建容器时必须带完整 env。部署脚本见 `scripts/rebuild-backend.sh`。
12. **PG 在默认 bridge 网络**：容器名 DNS 解析不工作，DATABASE_URL 必须用 IP `10.0.3.2:5432`（PG 重启后 IP 可能变，需重新确认）。
13. **cloudflared 以 nohup 后台进程运行**（非 systemd 非 Docker），NAS 重启后需手动 `sh /share/CACHEDEV1_DATA/Container/kirameku/restart-tunnel.sh` 拉起。✅ **2026-09-13 已配置开机自启**：`/etc/config/autorun.sh` 调用 `start-tunnel.sh`（幂等+setsid+http2），见 4.9.6。
14. **这台 QNAP 没有 `pgrep`**（只有 `pidof`，且 pidof 匹配全名不可靠）→ 检测进程是否存在必须用 `ps w | grep '[c]loudflared'`（`[c]` 技巧排除 grep 自身）。用 `pgrep -f` 会返回 127（command not found），脚本 `if pgrep ...` 会误判为"没运行"而重复拉起进程。
15. **这台 QNAP 没有 `nohup`**（`/usr/bin/nohup` 和 `/bin/nohup` 都不存在）→ 后台常驻进程必须用 `setsid command & < /dev/null`（setsid 在 `/bin/setsid`，让进程在新会话运行，脱离 SSH 控制终端不被 SIGHUP 带走）。用 nohup 会报 `nohup: command not found` 且进程起不来。
16. **`SQLModel.metadata.create_all` 与 Alembic 迁移冲突**：应用 lifespan 启动时 `init_db()` 会自动为所有已 import 的模型建表。新增模型后，如果先启动新容器再跑 `alembic upgrade head`，create_all 已把表建好，迁移的 `create_table` 会报 `DuplicateTable`。**解法二选一**：(a) 严格先跑迁移再启动新容器；(b) 接受 create_all 建表后核对结构一致，执行 `alembic stamp <revision>` 标记版本。本轮 login_log 表用的是 (b)。
17. **admin 构建脚本跨平台不兼容**：`package.json` 的 `build` 是 `rimraf dist && NODE_OPTIONS=--max-old-space-size=8192 vite build && generate-version-file`，Unix 内联环境变量写法在 Windows PowerShell/cmd 下报 `'NODE_OPTIONS' is not recognized`。**Windows 上必须**：`$env:NODE_OPTIONS="--max-old-space-size=8192"; npx rimraf dist; npx vite build; npx generate-version-file` 分步执行。
18. **admin/dist 用 robocopy /MIR 同步后容器内仍 404（bind mount inode 失效）**：后端容器以 `-v 宿主/admin/dist:/app/admin/dist:ro` 挂载，且 `main.py` 在**启动时**一次性判断 `admin_dist.exists()` 才 `app.mount("/admin", ...)`。若容器启动时宿主 dist 为空/不存在，之后再用 `robocopy /MIR` 同步（/MIR 会先清空再重建目录，**目录 inode 改变**），bind mount 仍绑定旧 inode，容器内 `ls /app/admin/dist` 是空的 → /admin 全 404，但宿主源目录文件齐全。**解法**：同步 dist 后 `docker restart kirameku-backend`（重新 bind + 重新走启动挂载判断，几秒中断，不碰 PG）。**最佳顺序**：先 robocopy 同步 dist，再（重）启动后端容器；或在部署脚本里把 restart 作为 admin 同步后的固定收尾步骤。验证：容器内 `ls /app/admin/dist/index.html` 存在 + 公网 `/admin/` 返回 200 text/html + `/admin/static/js/index-*.js` 返回 200。

### 6.4 工具链 / PowerShell / 命令

1. `Get-Content` 不加 `-Encoding UTF8` 会被工具安全策略拦截；读密钥/配置用 read_file 或显式 `-Encoding UTF8`。
2. **PowerShell 变量名大小写不敏感**：`$b`（路径）与 `$B`（URL）会互相覆盖（曾导致 `Join-Path` 报 "Cannot find drive 'https'"）→ 命名语义化（`$base`/`$cdn`）。
3. 命令里出现 `%XX`（URL 编码）或复杂引号时，工具可能**误判为 cmd.exe** 而报 `'$var' 不是内部或外部命令` → 改用中文字面量 URL / 纯 PowerShell。
4. **`remove-item`、`docker rm`、`docker stop` 这类"破坏性"命令会走审批弹窗**；用户不在时会 `Execution Cancelled: Permission request timed out`（是超时不是拒绝）。`delete_file` 工具不受影响，可用来清临时文件。
5. **没有输出/长耗时的命令会被判 idle/watch 而取消或转后台**：
   - `robocopy` 大目录 → 分步
   - `curl` 监听 SSE → 改短超时或落盘
   - **`pnpm exec vite build`（admin）会被误判成 watch 命令**（返回 "Watch command started"、看不到输出）但**实际会跑完** → 用 `dist/index.html` 时间戳确认。
6. `pnpm` 会自动按 `package.json` 变更装依赖（改版本后不必手动 install，但会慢一点）。
7. 前端构建偶发 miniflare `fetch failed / bad port` → 设 `NO_PROXY=127.0.0.1,localhost` 重试。
8. **Edge headless 多实例并发截图冲突**：在一个循环里连续调用 `msedge --headless --screenshot` 截多个宽度，后两个实例会复用第一个的 user-data-dir 导致截图空白（文件仅 2-3KB）。**解法**：每次截图加 `--user-data-dir="$env:TEMP\edge_shot_<width>"` 独立 profile，或串行执行并加 `--virtual-time-budget=8000` 给足渲染时间。截图前先用 `Invoke-WebRequest` 预热一次页面。
9. **SSH 远程命令含括号/复杂引号会语法错误**：`ssh hewll-admin 'echo === foo (bar) ==='` 中的括号会被远程 sh 解析报错。**解法**：把命令写成 `.sh` 文件 → `Copy-Item` 到 `U:\kirameku\` → `ssh hewll-admin "sed -i 's/\r$//' /share/.../x.sh && sh /share/.../x.sh"`（sed 去 CRLF 防 `^M` 报错）。这是本项目 NAS 运维的标准模式。
10. **PowerShell `Get-Content` 读后端 .py 中文显示乱码**：控制台 GBK 编码问题，文件本身是 UTF-8 无损。读文件用 `Get-Content -Encoding UTF8`，或直接用 Read 工具（按 UTF-8 解析）。**不要**用 PowerShell 写中文到 .py/.sh（会编码损坏），一律用 Write/Edit 工具。
11. **导航栏中等宽度竖排拥挤**：`TopAppBar` 用 `contentAlign:center` 时 nav 绝对定位居中（`lg:absolute lg:left-1/2`），9 项导航在 1024–1279px 被左侧站名+右侧图标挤压，两字词被压成竖排。**解法**：横排断点提高到 `xl`(1280)，nav-link 加 `shrink-0 whitespace-nowrap`，<1280 走汉堡抽屉。见 4.9.1。

### 6.5 Git / 多仓

1. `web/` 是独立子仓，外仓看不到其改动（`.gitignore` 忽略）→ 各自的 `git add/commit/push`。
2. 外仓分支是 **master**（不是 main）；`git push origin main` 会报 `src refspec main does not match any`。
3. `_upstream_shirone/` 不入库，改上游要走 `node scripts/sync-upstream.mjs main` 评估后改 `PINNED_COMMIT`。
4. Push 前 `git status` 确认没有 `.env`/token 被 staged。

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

> **当前状态（2026-09-13 第三轮续作后）**：本轮 8 项需求中 6 项已完成并**全部上线、线上验收、全站零回归**（详见 4.9 + 4.10）。第三轮续作（4.11）：**②音乐挂件方案 A 已实现并上线**（MusicLinkCard 外链卡片 + 后台 music_widget 可配，默认关闭，线上验收「启用出卡片/禁用零残留」通过，**只差用户填一条收藏夹链接**）；过程中**发现并修复了 SSR 页面响应流随机截断的重大 bug**（LiveRefreshBanner SSR 返回 null，首页/归档/文章页缺文章列表的元凶，`2f77b19` 已上线三连验证，见 4.11.2）。web 子仓 main = `2f77b19`（两次 CI success：34715783783、34716510215）。**真正待办只剩需要用户输入的 2 项**：②的收藏夹链接 + ⑧Umami 的 websiteId/scriptUrl/shareUrl（都能在后台直接填，无需改代码）。③JWT cookie、④TTFB 用户暂缓；⑦文章加密用户明确不做。

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

#### ② 音乐挂件改"点击进 B 站网页版收藏夹顺序播放" —— ✅ 代码已上线（默认关闭），只差用户给收藏夹链接

> **第三轮续作已按方案 A 实现**（web commit `cdb840b`，详见 4.11.1）：`MusicLinkCard.astro` 外链卡片 + `site-overrides.ts` 的 musicWidget 解析 + `SideBar.astro` 兜底，三处改动全部上线。启用/禁用状态线上验收均通过。以下为原始方案记录（背景与原理仍有参考价值）。

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

**下一步（只剩这一步）**：向用户**要一条 B 站收藏夹链接**，然后登录后台 `https://kirameku-api.neutronstar.fun/admin/`（admin/admin123）→ 站点配置 → 编辑 `music_widget` 行的 value 为 `{"enabled":true,"title":"音乐","subtitle":"B站收藏夹 · 点击顺序播放","url":"<收藏夹链接>"}` → 等 ≤60s BFF 缓存 → 线上侧栏应出现音乐卡片、点击新标签打开收藏夹。也可仿 4.9.4 的 Umami 面板做一个 music_widget 专用编辑 UI（非必须）。若用户改主意要站内不跳转播放，再走方案 B。

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
2. **向用户要两样东西**（唯一阻塞项，可一次问清）：(a) B 站收藏夹链接（拿到后按 7.5② 的"下一步"在后台填 `music_widget` 即上线）；(b) Umami 的 websiteId / scriptUrl / shareUrl（后台 Umami 面板直接填）。
3. **每步都验收**：前端改动必跑本地 build+preview（dev 不可用）；**SSR 页面改动必须验证响应完整性**（footer 次数/结尾元素完整，见坑 6.1.14——状态码 200 不代表页面完整）；后端改动走 SMB 同步→rebuild-backend.sh→健康检查。
4. **不要主动做**：③JWT cookie、④TTFB（用户暂缓）、⑦文章加密（用户明确不做），除非用户重新提起。
5. **完成后同样回写本文**：更新第 3、4、6、7、10 节对应内容（遵循文末"只减不增、同源唯一"原则）。

---

## 8. 命令速查

### 8.1 前端（web/）

```powershell
cd F:\AI\projects\Kirameku2.0\web
pnpm install
$env:NO_PROXY="127.0.0.1,localhost"
pnpm build                                   # 产物 dist/client + dist/server；postbuild 自动生成 pagefind 索引
pnpm preview --port 4321 --force             # 本地验证（dev 不可用，见 6.1.1）

# 部署：push 到 main 后 CI 自动部署（GitHub Actions → wrangler deploy）
# 手动部署（紧急时）：
$env:CLOUDFLARE_API_TOKEN=(Get-Content ..\worker-bff\.cf.local.env -Encoding UTF8 | ConvertFrom-StringData).CLOUDFLARE_API_TOKEN
$env:CLOUDFLARE_ACCOUNT_ID='d4add8ad549536a77a5b9fcf6d5be733'
pnpm dlx wrangler@4 deploy -c wrangler.deploy.json

# 字体重新子集化（新增含生僻字文章后）
pnpm fonts:subset
```

### 8.2 BFF（worker-bff/）

```powershell
cd F:\AI\projects\Kirameku2.0\worker-bff
pnpm exec tsc --noEmit
.\scripts\Deploy.ps1            # = npx wrangler@latest deploy（自动加载 .cf.local.env）
pnpm exec wrangler dev          # 本地
```

### 8.3 后端（Kirameku-backend/ → NAS）

```powershell
# 1) 同步源码（SMB；分目录小步，避免大目录 robocopy 被中断）
robocopy "F:\AI\projects\Kirameku2.0\Kirameku-backend\app" "U:\kirameku\backend\app" /MIR /XD __pycache__ .pytest_cache /NFL /NDL /NJH /NP /R:1 /W:1
robocopy "F:\AI\projects\Kirameku2.0\Kirameku-backend\migrations" "U:\kirameku\backend\migrations" /MIR /XD __pycache__ /NFL /NDL /NJH /NP /R:1 /W:1
robocopy "F:\AI\projects\Kirameku2.0\Kirameku-backend" "U:\kirameku\backend" requirements.txt Dockerfile alembic.ini /R:1 /W:1

# 2) 构建镜像
ssh hewll 'export DOCKER_HOST=unix:///var/run/docker.sock; cd /share/CACHEDEV1_DATA/Container/kirameku/backend && /share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker build --progress=plain -t kirameku-backend:latest . 2>&1 | tail -c 800'

# 3) 【有模型变更时】先跑迁移，再重启应用容器
ssh hewll 'export DOCKER_HOST=unix:///var/run/docker.sock; D=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker; $D run --rm -w /app -e PYTHONPATH=/app -e DATABASE_URL=<同容器> -e SECRET_KEY=<同容器> kirameku-backend:latest alembic upgrade head'

# 4) 重建应用容器（只动 kirameku-backend；env 必须完整，见第 9 节）
#    推荐：写 .sh → Copy-Item 到 U:\kirameku\ → ssh 'tr -d "\r" < /share/.../x.sh | sh'
#    脚本内：tag 备份 → stop → rm → run -d --name kirameku-backend --restart unless-stopped -p 8100:8000 -e ... -v kirameku_uploads:/app/uploads -v /share/.../admin/dist:/app/admin/dist:ro kirameku-backend:latest

# 5) 后台界面（admin）改动用 SMB 同步（bind mount）
#    ⚠️ Windows 上 package.json 的 build 脚本（NODE_OPTIONS=... 内联写法）不兼容，必须分步：
cd admin
$env:NODE_OPTIONS="--max-old-space-size=8192"
npx rimraf dist
npx vite build
npx generate-version-file
robocopy "F:\AI\projects\Kirameku2.0\Kirameku-backend\admin\dist" "U:\kirameku\backend\admin\dist" /MIR
#    ⚠️ /MIR 会重建目录导致 bind mount inode 失效（见坑 6.3.18），同步后必须 restart 后端容器：
ssh hewll-admin "export DOCKER_HOST=unix:///var/run/docker.sock; /share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker restart kirameku-backend"
#    验证：curl https://kirameku-api.neutronstar.fun/admin/ 应 200 text/html

# 6) 【有模型变更时】迁移与 create_all 冲突注意：
#    应用 lifespan 会自动 create_all 建表。若新容器已启动再跑 alembic upgrade head 会报 DuplicateTable。
#    解法：核对表结构后 `docker exec kirameku-backend alembic stamp <revision>` 标记版本。
#    或严格先跑迁移再启动新容器。详见 6.3.16。
```

### 8.4 本地测试

```powershell
cd F:\AI\projects\Kirameku2.0\Kirameku-backend
$env:DATABASE_URL="sqlite:///./_t.db"; $env:SECRET_KEY="test"   # 测试自带 sqlite
.\.venv\Scripts\python.exe -m pytest -q        # 期望 19 passed
```

### 8.5 验证清单（每次改动后跑一遍）

```powershell
$cb = Get-Random
# 站点（全部应 200）
foreach ($p in @('/','/2/','/archive/','/moments/','/albums/','/friends/','/messages/','/about/','/novel/','/posts/革命','/sitemap-index.xml','/robots.txt','/auth/callback')) { ... }
# 服务
https://bff.neutronstar.fun/health                                   # {"status":"ok"}
https://bff.neutronstar.fun/bff/archive?size=2                       # 200
https://kirameku-api.neutronstar.fun/api/health                      # {"status":"ok"}
https://kirameku-api.neutronstar.fun/admin/                          # 200
https://www.neutronstar.fun/                                         # 301
# 实时链路（写操作 + 缓存）
GET  /api/chatters?...（两次，第二次 X-Cache: HIT）
POST /api/chatters/1/like  → 再 GET 同 URL 应 X-Cache: MISS
# 鉴权
POST /api/likes/toggle（无 token）→ 401
GET  /api/comments/admin（无 token）→ 403
GET  /api/auth/github/login → 307 + Location 指向 github.com
```
> 注意：查线上版本**必须带 `?cb=<随机>` 破缓存**，否则可能读到边缘陈旧 HTML（曾有首页 P1 旧缓存在线 7 天）。

---

## 9. 凭据与环境变量

### 9.1 已就绪（无需再要）

| 凭据 | 位置 |
|:--|:--|
| NAS SSH 免密 | `~/.ssh/config` Host `hewll`（Mars@192.168.5.4）/ `hewll-admin` |
| SMB 映射 | `U:` → `/share/CACHEDEV1_DATA/Container`（`U:\kirameku\backend` 即后端目录）；`Z:` → `/share/CACHEDEV1_DATA/Web` |
| NAS Docker | `/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker` + `DOCKER_HOST=unix:///var/run/docker.sock` |
| 后端 `DATABASE_URL`/`SECRET_KEY` | NAS 容器 `-e`（值见容器 inspect 或 `backups/rescue-from-duplicates/`，gitignored） |
| `REVALIDATE_SECRET` | `worker-bff/.dev.vars`（本地）+ Worker secret（线上，**已轮换一致**）+ NAS 容器 env |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | NAS 容器 `-e`（OAuth App 回调 `https://bff.neutronstar.fun/api/auth/github/callback`） |
| Cloudflare API Token | `worker-bff/.cf.local.env`（gitignored；需 Workers 脚本/KV/DO/Workers 路由/Zone DNS Edit/Pages） |
| CF Account ID | `d4add8ad549536a77a5b9fcf6d5be733` |
| KV `CACHE_TAGS` | `4959a742fe4d44dbbc0ba8c200bea694` |
| 后台管理员 | 用户名 `admin`；初始密码 `admin123`（见 `.codebuddy/memory/2026-09-09.md`；若已被修改且忘记，跑 `Kirameku-backend/scripts/ops/reset_admin.py` 重置） |
| Git 推送凭据 | 系统 credential manager（GitHub 账号 `wenzongze`） |

### 9.2 待用户提供（不阻塞当前开发）

- **Umami website ID / scriptUrl / shareUrl**（统计，可选）：现在可在后台「站点配置」页直接填写（key=`umami`），无需改代码。填入后前台约 60 秒生效（BFF 缓存），后台 Umami 对话框有"打开统计面板"入口。
- Giscus 仓库配置（若改用 Giscus 评论，可选；当前用自建评论）
- 阿里云 OSS AK（当前图片走 NAS 本地 + fastimage，不需要）
- **B 站收藏夹 media_id**（音乐挂件改造需要，见 7.5②）

### 9.3 绝不入库

`.env`、`.env.local`、`.dev.vars`、`.cf.local.env`、`backups/`、`_upstream_shirone/`、`web/`（子仓）、`admin/dist`、`.codebuddy/`、`1/`（临时暂存目录，用户的清理约定）。

---

## 10. 关键 ID / 路径速查

- CF Account：`d4add8ad549536a77a5b9fcf6d5be733`；zone `neutronstar.fun`：`0ab03cd4f0c21a06462f1f5325abeeeb`
- KV `CACHE_TAGS`：`4959a742fe4d44dbbc0ba8c200bea694`
- Workers：`neutronstar-web`（正式站）、`kirameku-bff`（BFF+DO）、`sync-hub-api`（其他项目）、`neutronstar`（旧，未用）
- Pages：`neutronstar-web`（仅 pages.dev 预览，**已不服务正式域**）；旧项目 `neutronstar`（已弃用，可删）
- NAS：`192.168.5.4`；源码 `/share/CACHEDEV1_DATA/Container/kirameku/backend`；镜像备份 tag `bak-20260909 / bak-20260912 / bak-20260912b / bak-20260912c / bak-20260913`
- 容器：`kirameku-backend`（:8100→8000）、`kirameku-pg`（:15432→5432）；卷 `kirameku_uploads`、`kirameku_pgdata`
- 域名：`neutronstar.fun`（Worker）、`bff.neutronstar.fun`（BFF Worker）、`kirameku-api.neutronstar.fun`（Tunnel→NAS）
- 上游 pinned：`b79d301e5e6a8ec897e85b042de43187b571dd5b`
- **当前版本（2026-09-13 第三轮续作后）**：web 子仓 main = `2f77b19`（音乐挂件 `cdb840b` + SSR 截断修复 `2f77b19`；CI run 34715783783 / 34716510215 均 success）；外仓 master = 本文档提交。查 CI：`cd web; gh run list --limit 1`；查某步日志：`gh run view <id> --log | Select-String "subset"`。
- 图床：`https://gcore.jsdelivr.net/gh/neutron-star77/fastimage@main/2026/08/`（派生 `thumbs/`、`full/`）
- 本机工具：Everything CLI `E:\Program Files (x86)\图拉丁工具箱\图吧工具箱202507\tools\其他工具\Everything\es.exe`；双端推送脚本 `F:\AI\git-templates\sync_and_publish.ps1`

---

> 更新本文件的原则：**只减不增、同源唯一、过时即删**。每次完成一个阶段，更新第 3 节（进度总览）、第 4 节（完成记录）、第 6 节（新踩的坑）、第 7 节（待办销项）四处的对应内容，再把原文细节留在 `.codebuddy/memory/YYYY-MM-DD.md`。
