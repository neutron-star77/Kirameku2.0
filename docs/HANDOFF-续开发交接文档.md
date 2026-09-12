# Kirameku2.0 续开发交接文档（给下一个 AI / 开发者）

> 生成时间：2026-09-12
> 主工程：`F:\AI\projects\Kirameku2.0`
> 目标：在既有工程上 **1:1 复刻 Astro 博客主题 Shirone**，说说/相册/友链三页采用 Kirameku 堆叠/拍立得动画，前后端分离，后台发布经 SSE 实时弹新。
> 当前阶段：**P0/P1/P2 完成，正式站已由 Workers（SSR）接管且内容是真实数据；P4 实时（SSE + Durable Object）代码与 BFF/前端已上线，剩 NAS 后端容器重建与浏览器最终验收（见 0.7）**。
> 配套阅读：`docs/方案-v2.0-Shirone1比1复刻与SSE实时.md`（设计锁定）、`docs/开发过程与踩坑-二次开发指南.md`（T0/T1 历史）、`docs/DEPLOY-NAS.md`（后端部署）。

---

## 0. 30 秒上手（接手第一步）

```powershell
# 1. 读这三个文件（10 分钟）
#    docs/方案-v2.0-*.md  ← 设计锁定与工单
#    docs/HANDOFF-续开发交接文档.md ← 本文
#    _upstream_shirone/src/layouts/Layout.astro + MainGridLayout.astro ← 移植对照源

# 2. 确认环境
node -v          # >=22.13
pnpm -v          # 11.x
python --version # 3.11+

# 3. 启动 P1（外壳移植），见第 10 节 P1 工单
```

**绝对不要做的事**：不要动正式站 `https://neutronstar.fun`；不要把 `.env` / `.dev.vars` / `.cf.local.env` / token 提交进 git；不要用 `scp`/`ssh "cat >"` 写 NAS 文件（走 SMB）；不要删 PostgreSQL 数据卷和 `kirameku_uploads` 卷。

---

## 0.8 P5 起步记录（2026-09-12，OAuth 凭据仍缺）

**先纠正一个容易误会的点**：`https://bff.neutronstar.fun/api/auth/github/callback` **不是给人直接打开的页面**，它是 GitHub 授权后回跳的接口，必须带 `?code=…`（由 GitHub 带上）。直接在浏览器打开会得到
`422 {"detail":[{"type":"missing","loc":["query","code"],…}]}` —— 这是**正常现象**，说明 BFF → 后端的透传是通的。
真正给用户看的落地页是本工程的 **`https://neutronstar.fun/auth/callback?token=…`**。

**本次已完成（不依赖凭据，已上线）**：

1. 前端 `src/pages/auth/callback.astro`（`prerender=false`）：接收后端 302 带来的 `?token=`，写进 `localStorage`（键 `kirameku_github_token`）后回首页；无 token 时显示"没有拿到授权信息"。实测：无 token → `登录失败` 文案；带 token → 页面含写入脚本。
2. 前端登录态层 `src/lib/auth.ts`：`getToken/setToken/clearToken/loginUrl/useGithubUser`；`api/client.ts` 新增 `apiPost()` 与 `authHeaders()`，**所有请求自动带 `Authorization: Bearer`**。
3. 新 island `AuthButton`：未登录显示「用 GitHub 登录」（跳 `${API_BASE_URL}/api/auth/github/login`），已登录显示头像 + `@login` + 退出。已挂在 `/moments`、`/albums` 顶部右侧（实测线上 HTML 含登录文案与 login 链接）。
4. **说说点赞已落库**：`MomentsList` 的 `toggleLike` 改调 `POST /api/chatters/{id}/like|unlike`（乐观更新 + 失败回滚 + 成功后 SWR `mutate` 重拉真实计数）。
5. 后端 `app/api/github_auth.py` 的 `FRONTEND_ORIGIN` 默认值由 `https://boke.hiromu.top`（模板作者站点）改为 `https://neutronstar.fun`（NAS 容器早已用环境变量覆盖，此改动为裸跑兜底；**要生效需下次重建镜像**）。

**凭据已就位 + 链路已打通（2026-09-12 更新）**：

用户已提供 OAuth App 的 Client ID / Secret（值存 NAS 容器 env，不入库）。本次做的：

1. **凭据自校验**：直接打 GitHub `POST /login/oauth/access_token`（假 code）→ 返回 `bad_verification_code` 而**不是** `incorrect_client_credentials` ⇒ Client ID/Secret 配对有效（这是个不用浏览器就能验凭据对不对的好办法）。
2. NAS 后端：SMB 同步源码 → 重新 `docker build`（sha `3286755d…`）→ 重建容器（id `30387ec1…`，备份 tag `kirameku-backend:bak-20260912b`）并带上 `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET`（`FRONTEND_ORIGIN`/`BFF_ORIGIN`/`REVALIDATE_SECRET` 保持）。
3. **新坑（已修，BFF）**：`fetch` 默认跟随 3xx，导致后端 `/api/auth/github/login` 的 302 被 BFF 吃掉 —— 浏览器拿到的是 **200 + GitHub 授权页 HTML**（47KB，直连 bff 域名渲染，流程会断）。修法：`worker-bff` 的代理（读 + 写透传）一律加 **`redirect: "manual"`**，3xx 原样透传。
4. 实测：`GET /api/auth/github/login` → **307** + `Location: https://github.com/login/oauth/authorize?client_id=Ov23li9QIArP2xzucH82&scope=read:user` ✅；`GET /api/auth/github/callback?code=fake` → **400**（后端已把 code 送去 GitHub 并被拒）✅。

**最后一步（只能人工点一次）**：打开 `https://neutronstar.fun/moments/` → 右上角「用 GitHub 登录」→ 在 GitHub 页面点 Authorize → 应回到 `neutronstar.fun/auth/callback` 再跳首页，右上角变成头像 + `@login`。这一步是 OAuth 的固有环节（需要用户在 GitHub 授权），无法在服务端代跑。

**P5 续做：点赞防刷 + 评论区（2026-09-12 已完成并线上验收）**

后端：

1. **新表 `likes`**（`app/models/like.py`）：`user_id + target_type + target_id` 唯一约束（`uq_likes_user_target`）。表名刻意用复数 —— `like` 是 SQL 关键字。目标表的 `likes` 字段降级为**冗余计数**，真值在本表行数。
2. **评论多态**（`app/models/comment.py`）：新增 `target_type`（post/chatter/album）+ `target_id`，`post_id` 改为可空（历史数据用 post_id 回填）。
3. **Alembic `0002_likes_comments`**：建 likes 表 + 回填 + 放开 `post_id` 非空 + 建 `(target_type, target_id)` 索引。⚠️ **迁移必须在应用容器重启前跑**，否则新代码启动时 `SQLModel.metadata.create_all` 会先把 likes 表建出来、导致迁移报"表已存在"。执行方式：`docker run --rm -w /app -e DATABASE_URL=... kirameku-backend:latest alembic upgrade head`。
4. **新接口**：`POST /api/likes/toggle`（**需登录**，幂等切换，并发重复点赞靠唯一约束兜底，不会 +2）、`GET /api/likes/mine?target_type=`（未登录返回空数组不报错）。
5. **评论接口**：`GET /api/comments?target_type=&target_id=`（多态）、`POST /api/comments`（`target_type/target_id`，仍兼容只传 `post_id`）、`DELETE /api/comments/{id}`（**作者本人或后台管理员**可删，连带删子回复）、评论点赞兼容接口保留但改为需登录 + 幂等。
6. 测试：`tests/test_likes_and_comments.py` 9 个用例（未登录 401、重复点赞不叠加、我的点赞态、多态评论、楼中楼、跨目标拒绝、作者/他人/管理员删除权限）—— 全量 16 个测试通过。

前端：

- 新 island `CommentsThread.tsx`：一个组件适配两套后端表（`kind="chatter"` 走说说专用表、`kind="post"` 走多态表），含楼中楼两层、回复、点赞、删除自己的评论、未登录显示登录入口；已接入**说说展开卡片**与**文章详情页**。
- `MomentsList` 点赞改走 `/api/likes/toggle`（登录 + 去重），登录后回填"我点过赞的说说"，未登录点zan会提示去登录。
- 踩坑：`PostEntry` 里原来只带 slug（字符串），评论需要文章数字 id → 给适配层 `content-utils.ts` 补了 `postId`（`p.id`）透传。

线上验收（用一次性验证账号 + 自签 JWT 实跑，跑完已清理干净）：

| 检查 | 结果 |
|:--|:--|
| 未登录点赞 / 发评论 | 401 ✅ |
| 首次点赞 → 再点 → 第三次 | `{liked:true,likes:1}` → `{liked:false,likes:0}` → `{liked:true,likes:1}`（**不叠加**）✅ |
| `GET /api/likes/mine` | `{ids:[1]}` ✅ |
| 发评论（chatter 维度） | 200，`post_id=null`、`target_type=chatter` ✅ |
| 楼中楼回复 | 1 根 + 1 回复 ✅ |
| 作者删除 | `{ok:true}`，且连带删除子回复 ✅ |
| 文章页 SSR | 已含「评论」标题与「用 GitHub 登录」入口 ✅ |

**补做：相册评论（同日完成）**

`CommentsThread` 增加 `kind="album"` 分支（走多态表 `target_type=album`），挂在相册卡片**内联展开**的照片墙下方；实测 `GET /api/comments?target_type=album&target_id=1` → 200 `[]`。至此**说说 / 文章 / 相册**三类内容都有评论区。

**补做：后台评论管理升级（2026-09-13 完成并线上验收）**

原来后台「评论管理」只列 `comment` 表的文章评论、列头还是个 `文章ID`（多态后该字段多为空），说说评论压根没有入口。本次改成：

后端：

1. `GET /api/comments/admin` 新增 **`target_type` 过滤**（post / album），并给每条根评论返回 **`target`** 对象：`{type, id, title, url}` —— 文章取标题 + `/posts/{slug}`（slug 已 URL 编码），相册取标题 + `/albums`，说说取内容摘要 + `/moments`（实现见 `comment_service.target_info()`）。
2. `GET /api/chatters/comments/admin`（说说评论，独立表）同样带上 `target`，复用 `comment_service.target_info()`。
3. 顺手修了个老 bug：`chatter_service.delete_chatter_comment` 只删了自己、**不删子回复也不回退 `chatter.comments_count`** → 现在连带删除并把计数减回去。
4. 新增 3 个测试（后台鉴权、按类型过滤 + target 信息、说说评论 target + 删除回退计数），`tests/test_likes_and_comments.py` 共 12 例、全量 19 例通过。

后台界面（Vue admin，`admin/src/views/comment/index.vue` 重写）：

- 顶部双 Tab：**内容评论（文章/相册）** / **说说评论**；内容 Tab 下多一个「全部内容类型（文章/相册）」下拉。
- 列头 `文章ID` → **「所属内容」**：类型标签（文章/说说/相册）+ 标题（点击新窗口打开前台对应页面）。
- 通过/拒绝/删除按当前 Tab 自动路由到对应接口（`comments/*` 或 `chatters/comments/*`），回复展开逻辑不变。

线上验收：`GET /api/comments/admin?target_type=album` → `target={"type":"album","title":"鬼刀画集 I","url":"/albums"}`；说说评论列表 → `target={"type":"chatter","title":"今天正式把博客推倒重做。删掉了旧脚手架…","url":"/moments"}`；无 token 访问后台接口 403。后台产物经 bind mount 生效（`/admin/static/js/comment-*.js` 200）。

⚠️ 构建后台注意：`pnpm exec vite build` 在 CodeBuddy 里会被**误判成 watch 命令**（返回 "Watch command started"、看不到输出），但实际会跑完 —— 用 `dist/index.html` 时间戳确认，别以为失败了。

**仍然剩余（可选，不急）**：

- JWT 从 localStorage 升级为 httpOnly cookie（需改后端回调形态）。
- 评论创建时未校验目标（album/post/chatter）是否存在，只校验格式；如需严格可在 `create_comment` 里补一次存在性检查。
- 后台评论分页：当前页面固定取 `size: 100`，没有分页组件（评论量大时再加）。

---

## 0.7 P4 实时（SSE + Durable Object）完成记录（2026-09-12）

**目标**：后台发布 → 在线页面秒弹新，零 rebuild。

**实现（BFF + 前端 + 后端三侧）**：

1. **BFF 新增 `src/realtime-room.ts`（`RealtimeRoom` DO）**：一个频道一个实例（`idFromName("v2:<channel>")`），内存维护该频道的 SSE 写入端集合；路由 `/subscribe`、`/broadcast`、`/status`；25s 心跳；**每次写入带 2s 超时**（见踩坑 1）。
2. **`wrangler.toml`**：加 `[[durable_objects.bindings]] REALTIME_ROOM` + `[[migrations]] tag="v1-add-realtime-room" new_sqlite_classes=["RealtimeRoom"]`。⚠️ 免费计划必须用 `new_sqlite_classes`（KV 后端 DO 要付费）。wrangler 升到 4。
3. **`src/index.ts`**：新增 `GET /sse/:channel`（频道名净化后转发给对应 DO）；`/internal/revalidate` 清缓存后按 `TAG_CHANNELS`（posts/moments/albums/friends/messages/comments/site→nav，恒定含 `home`+`all`）**用 `waitUntil` 异步广播**，webhook 响应回到亚秒级。
4. **前端 `web/src/lib/realtime.ts`**：`window` 上的全局 hub（全站唯一 EventSource + 指数退避重连 + 引用计数与 5s 宽限关闭），对外只暴露 `useRealtimeRefresh(prefixes[, onChange])`；已接入 PostList / MomentsList / AlbumGrid / MessagesList / HomeFeed / FriendsGrid（非 SWR，走 onChange）/ NavigationIsland（同上）。
5. **后端**：`cache_invalidate.py` 早已挂在全部写接口（posts/chatters/albums/friend_links/messages/site_config），本次只补容器环境变量。

**踩坑（都值得记住）**：

1. **DO 里 `writer.write()` 不带超时会把整个实例写僵**：客户端"连上但不读"时 write 永不 resolve → 该 DO 后续请求全部排队 → BFF 的 `/internal/revalidate` 跟着 hang（实测 40s+ 超时，后端 httpx 3s 超时直接失败）。修法：逐条 `Promise.race` 2s 超时并摘除死连接 + 广播改 `waitUntil` 异步。另留 `ROOM_VERSION` 前缀当逃生舱（bump 即让所有客户端连到全新实例，不必等平台回收）。
2. **Astro island 会各自打包一份依赖**：产物里 `use-swr-*.js` 存在两份不同 chunk → "模块级单例 EventSource"会按 island 多开连接，且模块级 `mutate` 动不了别的 island 的 SWR 缓存。修法：连接放 `window.__kiramekuRealtimeHub`，重校验交给各 island 自己的 `useRealtimeRefresh`。曾尝试"布局里挂一个 bridge island"，结果 `client:load` 的 React island 在预渲染期报 `Unable to render RealtimeBridge!`（构建直接失败）→ 该方案已废弃并删除组件。
3. **`wrangler secret put` 走管道 stdin 会把结尾换行一起存进去**：导致本地 `.dev.vars` 与线上不一致、HMAC 永远 401。改用 CF API 确定性写入：`PUT /accounts/{acc}/workers/scripts/{name}/secrets` body `{name,text,type:"secret_text"}`。本次已轮换 REVALIDATE_SECRET（新值在 `worker-bff/.dev.vars`，线上同步）。
4. **后端镜像没有随 P2 代码重建**：容器内连 `app/services/cache_invalidate.py` 都不存在（`grep -c invalidate_cache app/api/chatters.py` = 0），所以"发布→清缓存"一直没生效（表现为发布后缓存仍 HIT）。处理：SMB 同步源码 → NAS 重新 `docker build`（已产出新镜像 `sha256:2a758f07…`）。

**当前状态：✅ P4 全链路已打通并完成端到端验收（2026-09-12）**

- ✅ BFF 已部署（DO 绑定正常，version `4ce33881`）：`/sse/all` 实测首帧 `retry: 3000` + `: connected channel=all`；`/internal/revalidate` 验签通过，返回 `{"purged":1,"channels":["home","all","moments"],"urls":7,"realtime":"queued"}`，**耗时 0.72s**。
- ✅ 前端已部署（version `8845fef7`）：线上页面里 MomentsList / AlbumGrid / FriendsGrid / MessagesList 四个 island 的 component chunk 均确认引用 `realtime.*.js`。
- ✅ **NAS 后端容器已用新镜像重建**（容器 id `8d601727…`，`docker build` 产物 sha `2a758f07…`；只替换应用容器，PG 与数据卷未动；重建脚本用完即删，NAS 上无残留）。容器内已确认 `app/services/cache_invalidate.py` 存在、`chatters.py` 含 11 处 `invalidate_cache`。
- ✅ **端到端实测（一次写操作同时验证两条链路）**：
  1. 预热 `/api/chatters?...` → `X-Cache: HIT`；
  2. `POST /api/chatters/1/like`（真实写库）；
  3. 再取同一 URL → `X-Cache: MISS` ⇒ **NAS 后端 → BFF 的 HMAC 失效 webhook 已通**；
  4. 同时挂着的一条 `/sse/all` 连接收到 `event: change` + `data: {"channel":"all","action":"published",…}` ⇒ **BFF → DO → 在线浏览器 的扇出已通**；
  5. 事后 `unlike` 还原数据。

**实时覆盖范围（重要，别误解）**：真正"在线秒弹新"的是带 island 的页面 —— **说说 /moments、相册 /albums、友链 /friends、留言 /messages**；而 **首页 `/`、归档 `/archive`、文章详情 `/posts/*` 是 SSR（无 island）**，它们不会在停留时自动变，但因为 BFF 缓存已被精确清掉，**刷新/跳转即为最新**（原来要等 s-maxage 60s）。要做到停着不动也弹新，得给这些页面加一个轻量 island。

**顺带发现的现状（不是本次引入）**：

- `PostList.tsx`、`HomeFeed.tsx`、`NavigationIsland.tsx`、`MobileNavigation.tsx`、`SidebarVisibility.tsx`、`MusicFloatingCard.tsx`、`PostView.tsx` 这些 island **在当前 Shirone 外壳里已无人引用**（P1 拆壳后遗留；`/archive`、`/` 都已改为 SSR 直出）。本次给前两者加的实时订阅因此是"备用"性质。
- 顶部导航当前来自**构建期静态配置 `src/config/navBarConfig.ts`**，并未接后台 `site_config.navigation`；所以"改导航即时刷新"这条 P4 预案目前无落点 —— 要接后台导航得先让外壳消费 `/api/site-config/navigation`（属于 P2 数据换血的收尾项，不是 P4 缺陷）。

---

## 0.6 P2 数据换血完成记录（2026-09-12）

**已完成**：
1. **BFF 聚合口**（已部署）：`/bff/archive`（分页+总数）、`/bff/sidebar`（分类/标签/统计/日历聚合），带 Cache API + tag 索引，可被 revalidate 精确清除。
2. **修复 BFF 缓存 CORS 污染**：Cache API 不按 Origin 分键，缓存条目剥离 `access-control-*`/`vary` 头由 cors 中间件按请求重新注入；CORS 白名单补 `http://127.0.0.1:4321`。
3. **前端数据层换血**：`lib/server/api.ts`（SSR 回源+内存缓存）、content-utils/site-stats 重写为 API 取数（适配成原版 CollectionEntry 鸭子形状，组件零改动）、删除上游 demo content 与 content.config.ts。
4. **页面 SSR 化**：首页 `[...page]`/归档/文章详情 `prerender=false`（文章 markdown 经 siteMarkdownProcessor 服务端渲染）；说说/友链/留言/相册 = 静态壳 + islands 客户端 SWR。
5. **站点覆盖层** `utils/site-overrides.ts`：site_title/site_description/site_images/sidebar_widgets 全部后台可配。站名已改 **Neutronstar**（PG site_config + profileConfig）。
6. **相册 234 张导入后端**（6 册×39，幂等脚本 `Kirameku-backend/scripts/oneoff/import_fastimage.py` 直连 NAS PG 15432；真实 DATABASE_URL 已存 `backups/rescue-from-duplicates/nas-db.env.txt`，gitignored）。
7. **两级派生图落地**：`fastimage/scripts/derive_images.py` 从鬼刀原图（8450×4263 等）LANCZOS 一次降采样，thumbs 800/q72（22-90KB）+ full 1600/q74（56-296KB），已 push fastimage（29b8d0a）；AlbumGrid 三档 srcset。**坑：jsDelivr 的 cdn/fastly 子域现对 gh 资源 301 到 raw，gcore.jsdelivr.net 直出——派生 URL 统一走 gcore**。
8. **admin 面板**：站点配置页新增 site_images 图片链接编辑（横幅桌面/移动、头像、Logo）+ sidebar_widgets 开关标签对齐新主题 widget；admin/dist 已构建并 SMB 同步 NAS（挂载卷实时生效，未动容器）。
9. **后端发布失效联动**：cache_invalidate 服务（HMAC→BFF revalidate）挂接 posts/chatters/albums/friend_links/messages/site_config 全部写接口；**SECRET 缺失时 no-op**，NAS 容器补 `REVALIDATE_SECRET`/`BFF_ORIGIN` 环境变量后秒级生效（放 P4 重建容器时做，TTL 60s 兜底）。

**✅ 已解决（2026-09-12）：SSR 正式站真正上线，根域由 Workers 接管**

- **根因（已确认）**：@astrojs/cloudflare v14 输出 Workers 格式（`dist/server/wrangler.json` + `dist/client` assets），**Pages CI 只部署静态部分**——线上 `/`、`/archive/`、`/posts/*` 这类 `prerender=false` 路由全 404；其余静态页其实是 P2 构建（标题已是中文 + Neutronstar），唯独首页 200 是 **P1 旧 HTML 的边缘陈旧缓存**（`s-maxage=604800`，加 `?cb=` 破缓存即 404）。
- **域名接管步骤（本次已执行）**：
  1. `DELETE /accounts/{acc}/pages/projects/neutronstar-web/domains/{neutronstar.fun|www.neutronstar.fun}` 解除 Pages 自定义域；
  2. 删除两条 `CNAME → neutronstar-web.pages.dev`（token 已补 Zone DNS Edit）；
  3. `PUT /accounts/{acc}/workers/domains` 把 `neutronstar.fun` + `www.neutronstar.fun` 绑到 Worker `neutronstar-web`（CF 自动建 `AAAA 100::` 记录，与 bff 同款）；
  4. `cd web && npx wrangler@4 deploy -c wrangler.deploy.json` 下发新版本（`wrangler.deploy.json` 的 routes 已补 www）；
  5. `POST /zones/{zone}/purge_cache {"purge_everything":true}`。
- **坑**：① Workers 自定义域接口是 **PUT**（POST 返回 405）；② `wrangler deploy` 带 `custom_domain` 路由时，若 DNS 上仍有同名 CNAME，会**静默只上传脚本不绑域**（"部署成功但域名还是旧站"的隐蔽根因）——必须先清 DNS；③ 删 Pages 域后到绑 Worker 域之间网站会短暂无 DNS。
- **复验（2026-09-12，全部 `?cb=` 破缓存）**：`/` 200（title `Neutronstar - 煌めく — 一个个人博客`）、`/2/`、`/archive/`、`/moments/`、`/albums/`、`/friends/`、`/messages/`、`/about/`、`/novel/` 全 200；8 篇文章详情 `/posts/{革命,技术大停滞,大远征,图片压缩,深色霓虹与玻璃拟态设计笔记,用-astro-7-重铸星舰博客,bt-7274,44}` 全 200；首页文章列表已换成真实后端文章（旧 demo `/posts/guide/`、`/posts/encrypted-demo/` 已消失）；`www` 仍 301 → 根域。
- **顺带修复**：SSR 化后根级 catch-all `[...page].astro` 会把**任意未知路径**（`/foobar-xyz/`、`/albums/1/`）渲染成首页 200（软 404）→ 已加守卫「只放行 `/` 与纯数字分页，其余直接 404」；删除临时诊断路由 `src/pages/api-debug.astro`（线上已验证 404）。
- **遗留（不影响上线）**：`/rss.xml`、`/atom.xml` 仍 404（上游有 `rss.xml.ts`/`atom.xml.ts`/`llms.txt.ts`，本工程未移植 → P6 补）；`/api/albums` 返回的 slug 为空（`albums/[slug].astro` 是 `getStaticPaths(){return []}` 占位，实际相册走 island 内联展开）；首页残留 11 处 `Shirone` 只是 CSS 注释 + nav/footer 指向上游仓库 `LyraVoid/Shirone` 的链接（如需改成本站可改 `navBarConfig`/`footerConfig`）。

**P2 验收状态**：✅ 本地与线上均已通过（线上见上条复验）。

---

## 0.5 P1 完成记录（2026-09-12）

**web 子仓 commit**：`c9cc7dc`（上会话遗留改动收尾）+ `e2fa995`（P1 外壳移植）+ `4a41b40`（/blog/* 旧链重定向）+ `07ecf0a`（站点中文化），**已 push origin/main，正式站已切换**（见下）。

**正式站切换记录（2026-09-12，用户拍板"旧的不要了"提前触发 P7 切换）**：
- Pages 项目 `neutronstar-web` 的 production_branch 本来就是 main、域名直挂 neutronstar.fun/www，push main 即上线，无需改 Pages 配置。
- 上线前补了 `public/_redirects`（`/blog/* → /posts/:splat 301`；HANDOFF 旧版写"已有该文件"是错误信息，实际不存在）。
- 线上验证全过：根域 200（title=Shirone 新站）、www 301 → 根域、pages.dev 200、/archive//moments/ 200、首页 banner/swup 元素在位、BannerStage 打字动画正常运行。
- 站点中文化（`07ecf0a`）：`siteConfig.lang: "en" → "zh_CN"`，UI 走 i18n 词典（`src/i18n/languages/zh_CN.ts`）全量翻译，`<html lang="zh-CN">`、日期/字数格式同步本地化；正式站已验证中文。剩余英文/日文属内容与元数据：大标题 Shirone + 日文副标题（siteConfig.title/subtitle，P2 接 site_config 后台改）、demo 文章与分类名（P2 换血）。
- ~~**待补**：Pages 环境变量~~ **✅ 已配置（2026-09-12）**：用户重建了新 API Token（Workers 脚本/KV/Pages/Workers 路由+区域读，已覆盖 `.cf.local.env`），`PUBLIC_API_BASE=https://bff.neutronstar.fun` 已写入生产+预览环境。**坑**：新版 Pages 配置模型里环境变量字段叫 `env_vars`（旧文档的 `environment_variables` 会静默写不进去但返回 success）；DO 无独立 token 权限项，归 Workers 脚本管。
- 注意：**正式站文章目前是 Shirone demo 内容（22 篇）**，P2 数据换血完成后才会换成真实文章；旧文章链接除 /blog/* 外不再保证可达（用户已确认弃用旧内容）。

已完成：
1. 装齐上游依赖 52 个包（svelte 5 / @astrojs/svelte 9.0.1 / @swup/astro / astro-expressive-code / astro-icon + @iconify-json 全家桶 / remark-rehype 管线 / katex / mermaid / @fancyapps/ui 等）。
2. `astro.config.mjs` 对齐上游（swup/icon/expressiveCode/svelte/mdx/sitemap + markdown processor + 音乐虚拟模块插件），保留 cloudflare 适配器与 react()。
3. 整体移植 `src/`：layouts、15 个样式、35 个配置、constants、i18n、~90 个 utils、plugins、integration、types、data、user、assets（15MB Yozai 字体）、**上游 demo 内容**（22 篇文章 + 5 条说说 + snippets/spec，P1 直接当 mock 数据用，P2 换血）、public 资产（banner/favicon/logo/anime/audio）。
4. 首页 `pages/[...page].astro` 照搬上游（getSortedPosts 分页 /、/2/、/3/）；其余 10 个页面改 MainGridLayout 薄壳（islands 保留未挂，P2/P3 接）。
5. 拆除手搓件：HomeHero、AlbumCarousel、Base/Page、SiteHeader/SiteFooter/ThemeToggle、Sidebar/AuthorCard/Calendar、SurfaceCard/PageHeader、global.css/animations.css。
6. 构建 11 页全过；`astro preview`（workerd）本地 vs `shirone.mysqil.com` 四组截图（桌面/移动 × 亮/暗）逐项一致（仅 Stats 数字内容性微差）；Swup 容器替换验证通过（无整页刷新）。
7. 图标生成：`node _upstream_shirone/scripts/icons/generate-local-icons.mjs`（在 web 下执行）→ `src/generated/local-icon-collections.ts`（已入库；web 未拷上游 scripts，升级上游后需重跑）。

**P1 偏离上游的部分（都有注释）**：
- `siteConfig.site` → `https://neutronstar.fun`
- `fontConfig.subsetting.enable = false`（P6 启用，启用后构建前必须跑 fonts:subset）
- `musicConfig.enable = false`（P6 启用；音乐挂件要运行时编译 stylus，workerd 无 fs 会炸，启用前必须解决）
- 字体加载离线化：`astro.config.mjs` 里 `fontsourceCssToLocalVariants()` 解析本地 @fontsource 包 CSS → local provider（fontsource 远程 provider 构建期要连 jsdelivr，大陆不稳）；全部字体角色 `optimizedFallbacks: false`
- `imageService: { build: "compile", runtime: "passthrough" }`（纯 passthrough 的 `/_image` 端点在纯预渲染部署下 404）
- `src/integration/ssr-node-shims.ts` 加固（workerd 预渲染 chunk 的 `import.meta.url` 可能 undefined，回退 `file:///` 基准）
- `src/plugins/rehype-markdown-images.mjs` sharp 改惰性 import + 降级（原生模块进 workerd 直接炸）

**新坑（P2 前必读）**：
- **Astro 7 没有 `output: "hybrid"`**（Astro 5 就移除了）：`output: "static"` + adapter 就是「默认预渲染 + 按页 `export const prerender = false`」，效果等价旧 hybrid。
- **Cloudflare adapter 的预渲染在 workerd（miniflare）里跑**：原生模块（sharp 等）和运行时读 fs 的代码都会炸；入口 chunk 的 `import.meta.url` 可能是 undefined。
- **占位动态路由**必须 `export function getStaticPaths() { return []; }`，否则构建报 GetStaticPathsRequired。
- **`astro dev` 当前不可用**：rolldown 依赖扫描对 ImageWrapper.astro 误报 parse error（非致命），但 SSR 依赖优化器（deps_ssr/base-*.js）缓存反复损坏导致 dev 崩溃，清 `.vite` 缓存无效。P1/P2 期间用 `pnpm run build && pnpm run preview`（workerd 本地跑产物，端口同 4321）替代；P2 再修 dev。
- miniflare 偶发 `fetch failed / bad port`（inspector 代理竞态）：设 `NO_PROXY=127.0.0.1,localhost` 重试即可。
- 构建期图片 compile 模式下个别已压缩 webp 反而变大（如 extreme-3 1.6MB→3.8MB），P2 图片策略时复核 q 参数。

---

## 1. 多仓关系（最容易踩的坑）

本项目是**三个独立 git 仓库 + 一个图床仓**的组合，外仓不跟踪前端子仓：

| 仓库 | 路径 | remote | 说明 |
|:--|:--|:--|:--|
| 外仓（主） | `F:\AI\projects\Kirameku2.0` | `https://github.com/neutron-star77/Kirameku2.0.git` | 后端、BFF、Next 参考应用、文档、脚本 |
| 前端子仓 | `F:\AI\projects\Kirameku2.0\web` | `https://github.com/neutron-star77/neutronstar-web.git` | **独立 git，被外仓 `.gitignore` 第 43 行 `web/` 忽略** |
| 图床仓 | `F:\AI\projects\fastimage` | `https://github.com/neutron-star77/fastimage.git` | 234 张鬼刀图，jsDelivr CDN |
| 上游基线 | `F:\AI\projects\Kirameku2.0\_upstream_shirone` | `https://github.com/LyraVoid/Shirone.git`（浅克隆） | **不入库**（.gitignore），pinned commit `b79d301e5e6a8ec897e85b042de43187b571dd5b`，由 `scripts/sync-upstream.mjs` 管理 |

**坑**：
- 改 `web/` 里的代码，`git status` 在外仓看不到任何变化——必须 `cd web` 后单独 `git add/commit/push`。
- ~~外仓 8 个本地 commit 未 push~~ **✅ 已全部推送（2026-09-12 核查：外仓 `b0d34af`、web 子仓 `424e72d` 均已与 origin 同步，工作区干净）**。
- `_upstream_shirone/` 是移植对照源，**不要在里面改代码**；升级上游用 `node scripts/sync-upstream.mjs main` 评估，确认后改 `PINNED_COMMIT`。

---

## 2. 三层架构与现网

```
浏览器
  │
  ├─ https://neutronstar.fun        → Cloudflare Pages（Astro 前端，项目名 neutronstar-web）
  ├─ https://bff.neutronstar.fun    → Cloudflare Worker（Hono BFF，name=kirameku-bff）
  └─ https://kirameku-api.neutronstar.fun → Cloudflare Tunnel → NAS(192.168.5.4) Docker
                                                ├─ kirameku-backend :8100→8000 (FastAPI + /admin 静态后台 + /uploads)
                                                └─ kirameku-pg :15432→5432 (PostgreSQL 16, 库名 kirameku)
```

- 预览域：`https://neutronstar-web.pages.dev`（前端 Pages 自动预览）。
- `www.neutronstar.fun` → 根域是 **Cloudflare Dynamic Redirect Rule**（不是 Pages 配置），别去 Pages 里找。
- NAS SSH：`~/.ssh/config` 里 `Host hewll` → `192.168.5.4 User Mars`，免密已通；`Host hewll-admin` → 同 IP `User admin`。
- NAS 源码路径：`/share/CACHEDEV1_DATA/Container/kirameku/backend`，SMB 挂载为 `U:\kirameku\backend`。
- 数据卷：`kirameku_uploads`（→ `/app/uploads`）、`kirameku_pgdata`（→ `/var/lib/postgresql/data`）。**重建后端只删应用容器，绝不碰这两个卷。**
- 回滚镜像：`kirameku-backend:bak-20260909`（T0 加固前）。

---

## 3. 已完成工作（P0 基线）

外仓 git log（本地未 push）：

```
458d29a docs: 更新凭据状态（CF Token 已就绪、图床选定 fastimage 两级派生）
6fabeb2 chore(worker-bff): 本地部署凭据加载脚本与忽略规则（token 不入库）
7421a81 docs: 方案 v2.0 锁定（1:1 移植/Svelte 共存/SSE-DO），加上游同步脚本
519d0ca chore: 退役旧 worker 代理脚本，后端一次性脚本归入 scripts/，忽略上游基线目录
0579549 docs: 定稿领域上下文、ADR 与二次开发指南，更新方案与部署文档
07476f7 feat: 后台站点配置支持一级/二级导航（visible/sort/target/children）
67ec963 chore: 移除 Next 参考应用中的工具箱/小游戏/Live2D 等废弃模块
```

具体完成项：
1. **完整上游基线**：`_upstream_shirone/` 浅克隆，15 个 src 模块、15 个样式文件、26 个页面、32 个构建脚本齐全（之前残缺只抓了 components）。
2. **清理**：删除工作空间重复副本 `F:\AI\projects\Kirameku`（~2.4GB）和 `Kirameku-ref`（~0.5GB），删前 hash 级 diff，独有 `.env.local`、后端 `.env` 抢救到 `backups/rescue-from-duplicates/`（gitignore）；删除旧 `worker/`（proxy.js + start_tunnel.sh）、`.pgpass.tmp`；后端一次性脚本移入 `Kirameku-backend/scripts/{oneoff,ops}/`。
3. **后台导航功能**：`site_config` 通用 KV + 后台视图，支持一级/二级菜单（visible/sort/target/children）。
4. **NAS 核查**：仅 kirameku-backend、kirameku-pg 两容器在跑，旧 kirameku-fe 已不存在。
5. **Cloudflare 授权**：用户提供 Account API Token，wrangler 4.13 whoami 通过；token 存 `worker-bff/.cf.local.env`（双重 gitignore），部署脚本 `worker-bff/scripts/Deploy.ps1`。
6. **方案 v2.0 锁定**：10 项决策（L1-L10）落盘。

---

## 4. 技术栈（精确版本）

### 前端 `web/`（当前）
- `astro ^7.3.2`、`@astrojs/cloudflare ^14.3.1`、`@astrojs/react ^6.0.5`、`react ^19.2.0`、`motion ^13.2.0`（包名 `motion/react`）、`swr ^2.5.1`、`tailwindcss ^4.3.3`、`typescript ^5.9.3`
- `packageManager: pnpm@11.22.0`，`engines.node >=22.13.0`
- `astro.config.mjs`：`output: "static"`（**P1 要改 hybrid**），`imageService: "passthrough"`，`integrations: [react()]`，**未装 @astrojs/svelte**

### Shirone 上游依赖（P1 要对齐）
- `astro 7.2.6`、`vite ^8.2.1`、`svelte ^5.56.8`、`@astrojs/svelte 9.0.1`、`tailwind 4`
- `@material/material-color-utilities`（M3 动态色）、`stylus`（variables.styl）
- 字体：Outfit / Roboto / JetBrains Mono / lxgw-wenkai-screen（`@fontsource*`）
- `@swup/astro`（页面过渡）、`expressive-code`、`mermaid`、`katex`、`@fancyapps/ui`（灯箱）、`pagefind`（搜索）、`subset-font`（字体子集）
- `pnpm@9.14.4`（上游用 9，我们用 11，注意 `allowBuilds` 配置差异）

### BFF `worker-bff/`
- Hono on Cloudflare Workers，`wrangler.toml`：`name=kirameku-bff`，`account_id=d4add8ad549536a77a5b9fcf6d5be733`，`compatibility_date=2026-09-09`，`nodejs_compat`，KV binding `CACHE_TAGS`（id `4959a742fe4d44dbbc0ba8c200bea694`），route `bff.neutronstar.fun`
- 本地 `wrangler` 3.114.17（`npx`），最新 4.131.1；**P4 前升级到 4**
- `[vars]`：`BACKEND_ORIGIN=https://kirameku-api.neutronstar.fun`、`DEFAULT_SMAXAGE=60`、`DEFAULT_SWR=300`、`PROXY_PREFIXES="/api,/uploads,/reader3"`
- `.dev.vars`：`BACKEND_ORIGIN`、`REVALIDATE_SECRET`（本地开发用，不入库）

### 后端 `Kirameku-backend/`
- FastAPI + SQLModel + Alembic + PostgreSQL 16，Python 3.11+
- 14 个模型：album / bookmark / chatter / comment / friend_link / github_user / message / post / project / site_config / user / visitor / `__init__`
- 18 个 API 路由：auth / github_auth / posts / categories / tags / comments / messages / chatters / albums / projects / friend_links / site_config / upload / bookmarks / visitors / dashboard
- 12 个 service
- 后台：Vue3 + Element Plus（pure-admin 风格），23 个视图目录，构建产物 `admin/dist` 挂载进容器
- 图片存储：默认 NAS 本地 `uploads/`；阿里云 OSS 可选（当前密钥空）

---

## 5. 前端现状（web/）—— 哪些要拆

### 页面（全部是薄壳，0-1KB）
`pages/`：index / about / albums / archive / friends / messages / moments / novel / posts + `albums/[slug].astro` + `posts/[slug].astro`。每个页面只 import `Page.astro` + 一个 island，**没有真实 Shirone 结构**。

### 布局（手搓，P1 要整体替换）
- `layouts/Base.astro`（39 行，只有 html 骨架 + 主题 inline script）
- `layouts/Page.astro`（薄壳，包 SiteHeader + Sidebar + slot + SiteFooter）

### 组件（手搓，P1 要拆）
- `components/home/HomeHero.astro`（**原版不存在**，自创的全屏 Hero + 相册背景 + "SCROLL TO EXPLORE"，必须删）
- `components/islands/AlbumCarousel.tsx`（首页轮播，原版不存在，删）
- `components/layout/SiteHeader.astro` / `SiteFooter.astro` / `ThemeToggle.astro`（替换为原版 TopAppBar 等）
- `components/sidebar/Sidebar.astro` / `AuthorCard.astro` / `Calendar.astro`（替换为原版 SideBar + CategoryBar）
- `components/ui/SurfaceCard.astro` / `PageHeader.astro`（删）

### 保留并继续用的 islands（Kirameku 动画，P3 精修）
- `MomentsList.tsx`（17KB，说说堆叠动画已移植）
- `AlbumGrid.tsx` / `Lightbox.tsx` / `AlbumDetail.tsx`（相册瀑布流+灯箱）
- `FriendsGrid.tsx`（友链）
- `NavigationIsland.tsx`（消费 `/api/site-config/navigation`，含二级下拉，defaultNavigation 9 项）
- `MobileNavigation.tsx`、`SidebarVisibility.tsx`、`MusicFloatingCard.tsx`、`HomeFeed.tsx`、`PostList.tsx`、`PostView.tsx`、`MessagesList.tsx`

### 数据层
- `lib/api/client.ts`：base = `import.meta.env.PUBLIC_API_BASE ?? "https://bff.neutronstar.fun"`；自动解包 `{code,data}` 或裸数组
- `lib/api/types.ts`：Post/PostSummary/Chatter/Message/Album/Photo/Tag/Category 契约；**列表接口返回裸数组无 total，前端用返回长度==size 判断 hasMore**
- `lib/api/hooks.ts`：SWR hooks
- `lib/variants.ts`：framer-motion 动画变体
- `data/albums.ts`：**234 张静态 jsdelivr 图（433.webp-666.webp），临时数据，P2 导入后端后删除**
- `config/site.ts`：站点名等基础配置
- `styles/global.css`（11KB，手写，P1 替换为原版 main.css+variables.styl+font-faces+textures）、`styles/animations.css`

### public/
`avatar.svg`、`favicon.svg`、`shirone-hero.webp`

---

## 6. BFF 现状（worker-bff/src/index.ts，278 行）

已实现的路由：
1. `GET /health` → `{status:"ok"}`
2. `GET /api/*` → 缓存代理（Cache API + KV tag 索引），未命中回源 `BACKEND_ORIGIN`
3. `GET /bff/home` → 聚合口（posts+chatters+albums+config 并发），**仅此一个聚合口**；P2 要补 `/bff/archive`、`/bff/album`、侧栏聚合
4. `GET /img/*` → CF Image Resizing（格式协商 avif/webp + ?w= 宽度 + q82），**目前只代理 `BACKEND_ORIGIN/${path}`，不支持 jsdelivr 远程图**；P2 要扩展白名单或改用预生成派生图
5. `POST/PUT/PATCH/DELETE /api/*` → 写操作透传，不缓存
6. `POST /internal/revalidate` → HMAC-SHA256 签名校验，按 tag/URL 清边缘缓存（后端发布时调用）

缓存机制：
- 免费计划没有原生 cache-tag，用 KV `CACHE_TAGS` 自建 `tag → url[]` 索引，单 tag 上限 500 URL
- `tagsForPath()` 按路径推导 tag（moments/messages/albums/posts/all），后端可用 `x-cache-tags` 头覆盖
- 默认 `s-maxage=60, stale-while-revalidate=300`

**SSE（方案 A，P4）尚未实现**：需要在 `wrangler.toml` 加 `durable_objects` binding，新建 `RealtimeRoom` DO 类，后端发布时除了调 `/internal/revalidate` 还要投递事件给 DO，前端用 `EventSource` 订阅。

---

## 7. 后端现状（Kirameku-backend/）

### 关键文件
- `app/config.py`：从 `.env` 读 `DATABASE_URL` / `SECRET_KEY` / `ALGORITHM=HS256` / `ACCESS_TOKEN_EXPIRE_HOURS=72` / `CORS_ORIGINS` / `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` / OSS_*；`OSS_ENABLED` 由三个关键字段非空决定
- `app/api/router.py`：汇总 18 个子路由，`main.py` 只需 `include_router(api_router)`
- `app/api/github_auth.py`：**半成品**，路由前缀 `/api/auth/github`，`/login`（scope=read:user）、`/callback`（code→token→GitHub user→upsert github_user→JWT→302 到 `{FRONTEND_ORIGIN}/auth/callback?token=`）、`/me`；`get_github_user_optional()` 可选登录辅助
- `app/models/github_user.py`：github_user 表已存在
- `app/services/site_config_service.py`：通用 KV（GET/POST/PUT/DELETE，key=navigation 存导航）

### 已知问题 / 待修
1. **`github_auth.py` 第 16 行 `FRONTEND_ORIGIN` 默认值错误**：写死 `https://boke.hiromu.top`（原 Kirameku 作者的站）。P5 必须改默认值为 `https://neutronstar.fun`，或确保 NAS 容器设了 `FRONTEND_ORIGIN` 环境变量。
2. **GITHUB_CLIENT_ID/SECRET 当前为空**（NAS .env 和本地抢救副本都是空），等用户创建 OAuth App 后填入。
3. 点赞持久化：`chatter.likes` / `comment.likes` 字段已有，但**没有 user 维度的防刷唯一约束**，P5 要加 `like` 关联表或唯一索引。
4. 前端目前没有 `/auth/callback` 页面接收 token，P5 要建。
5. 相册后端 `albums` 接口暂无数据（前端用 `data/albums.ts` 静态数据兜底），P2 要导入 234 张图。

### 后台管理
- 访问 `https://kirameku-api.neutronstar.fun/admin/`（容器挂载 `admin/dist`）
- 23 个视图：dashboard / post / editor / category / tag / chatter / comment / message / album / friend-link / project / bookmark / visitor / site-config / account-settings / system / monitor / permission / login / markdown / welcome / empty / error
- `site-config` 视图可编辑 navigation（一级+二级）、sidebar_widgets、music_widget
- 构建：`cd admin && pnpm install && $env:NODE_OPTIONS="--max-old-space-size=8192" && pnpm exec vite build` → `admin/dist`

---

## 8. Shirone 上游基线（_upstream_shirone/）—— 移植对照源

**pinned commit**：`b79d301e5e6a8ec897e85b042de43187b571dd5b`（2026-09 对齐）

### 关键结构
- `src/layouts/Layout.astro`（16KB，**总装布局，含 M3 动态色、字体、纹理、Swup**）
- `src/layouts/MainGridLayout.astro`（5KB，主网格，page="home" 时走首页链）
- `src/pages/[...page].astro`（**首页真身，不是 index.astro**；raw.githubusercontent.com 拉 index.astro 会 404）
- `src/pages/`：26 个页面（about/albums/anime/archive/categories/compass/devices/friends/moments/projects/skills/tags/timeline/404 + atom/rss/robots/llms + `albums/[id]/index.astro` + `posts/[...slug].astro` + `[...permalink].astro`）
- `src/styles/`：15 个文件（main.css / variables.styl / font-faces.css / textures.css / transition.css / scrollbar.css / toc.css / image-bloom.css / fancybox-custom.css / mermaid.css / markdown*.css / breakpoints.styl / markdown-extend.styl）
- `src/config/`：35 个配置文件（siteConfig / profileConfig / navBarConfig / sidebarConfig / postListConfig / articleConfig / fontConfig / musicConfig / animeConfig / footerConfig / umamiConfig / commentConfig / expressiveCodeConfig / permalinkConfig 等 + `index.ts` 汇总）
- `src/constants/constants.ts`、`src/constants/icon.ts`
- `src/utils/`：~90 个工具（date-utils / url-utils / theme-utils / masonry / motion / fancybox-* / mermaid / katex-scroll / post-encryption / post-decryption / password-protection / protected-session / site-stats / calendar-data / banner-animation / banner-state / menu-bus / snackbar / wavy-progress / share-poster / code-copy / code-collapse / code-tree / spoilers / abbreviations / github-cards / bilibili / acfun / youtube / video-facade / audio-reader / asset-utils / content-utils / content-date / article-discovery / feed / font-options / image-bloom / last-updated-notice / layout-mode / llms-utils / markdown-* / mc-utils / nav-utils / option-groups / permalink-utils / project-images / responsive-utils / script-loader / setting-utils / sidebar-page / copy-page-link / config-overlay / feature-data / fab-* / contextMenuConfig 等）
- `src/i18n/`：i18nKey.ts / translation.ts / 两个 runtime
- `src/components/`：原版组件（TopAppBar / BannerStage / SideBar / CategoryBar / PostPage / Pagination / FloatingControls 等）
- `src/integration/`、`src/plugins/`：Astro 集成与 remark/rehype 插件
- `scripts/`：32 个构建脚本（content/sync、icons/generate、images/generate-moment-thumbnails、fonts/subset、anime/sync、lighthouse、perf、new-post、check-design、check-manifest 等）
- `astro.config.mjs`：`@astrojs/svelte` + `@swup/astro` + expressive-code + mdx + sitemap + rss，`output` 需确认

### 首页真实链（之前走样的根因）
```
[...page].astro → MainGridLayout.astro(page="home") → Layout.astro
  + TopAppBar + BannerStage + SideBar + CategoryBar + PostPage + Pagination + FloatingControls
```
**原版没有 HomeHero、没有 AlbumCarousel、没有 "SCROLL TO EXPLORE"**——这些都是旧工程手搓的，P1 必须拆除。

### 移植原则
- **外壳整体移植，只换数据血**：Layout/MainGridLayout/styles/config/constants/utils/i18n/plugins/integration 原样搬入 `web/`，路径别名对齐（@components、@/config 等）
- 唯一允许偏离：数据层——原版 content collection（本地 md）→ BFF API；`getSortedPosts()` → `/bff/archive`、`/bff/home`；SideBar 分类/标签/统计/日历 → 对应 API；profile/site/banner/导航 → 后端 site_config
- 原版 `.svelte` 组件全部保留直接挂；仅说说 MomentSection、相册 AlbumSection/AlbumGallery、友链 FriendSection 三个区块的**内部呈现**替换为 React islands（Kirameku 动画），外壳仍用原版
- 升级上游：`node scripts/sync-upstream.mjs main` 看差异 → 验证 → 改 `PINNED_COMMIT`

---

## 9. 图片存储（fastimage 图床）

- 仓库：`F:\AI\projects\fastimage`，remote `neutron-star77/fastimage`，public
- 管理页：`https://neutron-star77.github.io/fastimage/`
- CDN：`https://cdn.jsdelivr.net/gh/neutron-star77/fastimage@main/2026/08/`
- 234 张（433.webp–666.webp），长边 1920 / WebP q82，总计 46.1MB
- 链接清单：`F:\AI\projects\fastimage\鬼刀图床链接.md`

### 体积实测（2026-09-12）
- 中位 156KB、平均 202KB、P75 243KB、P90 365KB、P95 489KB、最大 1938KB
- 分布：<100KB 58 张(25%)、100-200 89 张(38%)、200-400 66 张(28%)、400-700 19 张(8%)、>700KB 2 张(1%)
- 超大图：`438.webp` 1.9MB、`458.webp` 1.2MB（都是竖长壁纸 1920×3800+）
- jsDelivr 首次回源实测 0.9~1.5 秒（本地广州），缓存后快

### 压缩实验结论（Pillow，5 张抽样）
- **体积杠杆是分辨率，不是质量参数**：同 1920 只降质量仅省 4~9%
- 长边 800/q72：省 78~90%（438 从 1938KB→192KB）
- 长边 1600/q74：省 45~57%（438 从 1938KB→835KB）

### 推荐方案（两级派生，母版不动）
| 用途 | 规格 | 单图目标 |
|:--|:--|:--|
| 瀑布流列表缩略 | 长边 800、WebP q72 | 40~120KB（竖长图≤190KB） |
| 灯箱查看 | 长边 1600、q74 | 150~400KB |
| 仓库母版 | 1920/q82 原样 | 保留不删 |

- 配合 `loading="lazy"` + srcset，列表只拉缩略图
- AVIF 比 WebP 再省 ~20%，但要多维护一套静态文件，暂不做
- BFF `/img/*` 动态裁剪（CF Image Resizing）是付费功能，**权益未验证**；默认走预生成派生图更稳，P2 可验证权益后作为增强
- **待用户确认**：是否批量生成 `2026/08/thumbs/`（800 版）和 `2026/08/full/`（1600 版）并更新「鬼刀图床链接.md」

---

## 10. 后续开发任务（P1-P7 工单）

### P1：外壳移植原型（✅ 已完成 2026-09-12，见第 0.5 节）
**目标**：首页与 Shirone 演示站 1:1 视觉一致（亮/暗 × 桌面/移动四组对照）。

**步骤**：
1. `cd web && pnpm add @astrojs/svelte svelte @material/material-color-utilities stylus @swup/astro expressive-code @fancyapps/ui mermaid katex pagefind subset-font @fontsource/outfit @fontsource/roboto @fontsource-variable/jetbrains-mono`（对齐上游依赖，版本参考第 4 节）
2. `astro.config.mjs`：`output: "hybrid"`，加 `svelte()` integration，加 `@swup/astro`，配置 expressive-code、markdown remark/rehype 管线
3. 从 `_upstream_shirone/src/` 整体移植：`layouts/Layout.astro` + `MainGridLayout.astro`、`styles/*`（15 个）、`config/*`（35 个，路径别名对齐）、`constants/`、`i18n/`、`integration/`、`plugins/`、`utils/`（~90 个，先全搬，编译不过的再按需裁剪）
4. 首页：`pages/[...page].astro`（或保留 index.astro 但内部走 MainGridLayout page="home"），接 `BannerStage + PostPage`，**先 mock 数据**（写死几篇假文章），不接 API
5. 拆除：`HomeHero.astro`、`AlbumCarousel.tsx`、`Base.astro`/`Page.astro` 手搓壳、`SiteHeader`/`SiteFooter`/`Sidebar`/`AuthorCard`/`Calendar`/`SurfaceCard`/`PageHeader`、`styles/global.css`+`animations.css`
6. 保留：`NavigationIsland`、`MomentsList`、`AlbumGrid`、`Lightbox`、`FriendsGrid` 等 islands（P1 先不挂，P2/P3 再接）
7. `pnpm run build` 通过，`pnpm run dev` 本地预览
8. 截图对照：官方 `https://shirone.mysqil.com/` vs 本地，桌面/移动 × 亮/暗四组，像素级走查

**验收**：首页布局、颜色（M3 动态色 --hue）、字体（四套字体角色）、BannerStage、TopAppBar、SideBar、CategoryBar、PostPage、Pagination、Swup 页面过渡全部与原版一致；无 console error。

**坑**：
- Svelte 5 是 runes 模式，`$state`/`$derived`，不是旧版 `export let`
- `variables.styl` 是 Stylus，需要 `@astrojs/svelte` 或 vite 插件处理；Astro 原生支持 stylus？需确认，可能要装 `stylus` 并配 vite
- 原版路径别名 `@components`、`@/config` 等要在 `tsconfig.json` + `vite.resolve.alias` 对齐
- 字体文件较大，先不做子集（P6），直接用 @fontsource 全量
- `output: "hybrid"` 后，默认预渲染，需要实时的页面写 `export const prerender = false`
- 移植 utils 时可能有 Node 内置模块（fs/path）在浏览器端不可用，需按环境裁剪或标记 `?client`

---

### P2：数据换血 + BFF 补口
**目标**：所有内容来自 API，无写死数据；相册 234 张图导入后端。

**步骤**：
1. BFF 补聚合口：`/bff/archive`（文章列表+分页）、`/bff/album`（相册列表+照片）、`/bff/sidebar`（分类/标签/统计/日历/作者/公告聚合）
2. 前端 `PostPage`、`SideBar`、`CategoryBar`、`archive` 页接真实 API（SWR）
3. 相册数据导入后端：写一次性脚本（放 `Kirameku-backend/scripts/oneoff/import_fastimage.py`），把 234 张 jsdelivr URL 按 6 个相册（每 39 张）写入 `album` + `photo` 表；然后删 `web/src/data/albums.ts`
4. 图片策略落地：确认 fastimage 两级派生（第 9 节），或扩展 BFF `/img/*` 支持 jsdelivr 白名单远程源 + CF Image Resizing（先验证权益）
5. `site_config` 接入：导航（NavigationIsland 已接）、sidebar_widgets（SidebarVisibility 已接）、music_widget、profile、banner 配置
6. 后端补缺失接口：SideBar 需要的分类/标签/统计/日历聚合（如果现有 `/api/categories`、`/api/tags`、`/api/dashboard` 不够，补 service）

**验收**：`grep -rn "写死\|mock\|TODO.*数据" web/src` 无业务数据写死；后台发一篇文章，前端 `/archive` 实时可见（经 BFF 缓存，60s 内或手动 revalidate）。

**坑**：
- 列表接口返回裸数组无 total，分页用 `返回长度 < size` 判断末页
- BFF 缓存旧 404：新增接口后若仍 404，用 `?verify=时间戳` 验证，正式页用无参 URL
- 相册导入脚本要幂等（重复跑不重复插入），用 `url` 唯一约束
- `site_config` 是通用 KV，key 不存在时前端要有兜底默认值（NavigationIsland 已有 defaultNavigation）

---

### P3：三页动画（Kirameku）
**目标**：说说/相册/友链与 `https://boke.hiromu.top` 手感一致。

**步骤**：
1. 说说页 `/moments`：挂 `MomentsList.tsx`，按日分组，同日堆叠 top 递增 18px、zIndex 倒序，确定性倾斜序列 `[-2,1.5,-1,2,-1.5,1,-0.5,1.5]`，点击 spring(300,25) 归正展开，stagger 入场；评论楼中楼拍平 + AnimatePresence 高度折叠
2. 相册页 `/albums`：`AlbumGrid.tsx` CSS columns 真瀑布流，拍立得白边胶带，旋转角由 photo.id 确定性派生 `((seed%7)-3)*0.8°`；`Lightbox.tsx` spring + 键盘/触摸（按需 dynamic import）
3. 友链页 `/friends`：`FriendsGrid.tsx` 相册式错位卡片，分类筛选、悬浮展开、键盘可达
4. 三页外壳用原版 MainGridLayout，内部区块替换为 React islands
5. `prefers-reduced-motion` 降级：关堆叠/弹簧，直接平铺
6. 移动端：关重特效，触摸友好

**验收**：与 boke.hiromu.top 对照，动画参数一致；无渲染期 Math.random（确定性派生）；减少动效模式下无动画。

**坑**：
- `motion` 包名是 `motion/react`（不是 framer-motion），import 路径 `import { motion } from "motion/react"`
- React islands 与 Svelte 组件共存时，注意水合边界，不要在 Svelte 里嵌套 React island 的复杂状态
- 瀑布流 CSS columns 与动画 transform 可能冲突，用 `break-inside: avoid`
- 灯箱 dynamic import 要处理 loading 态和错误态

---

### P4：SSE 实时（方案 A：Durable Objects 扇出）
**目标**：后台发布，在线页面秒弹新，零 rebuild。

**步骤**：
1. `worker-bff/wrangler.toml` 加：
   ```toml
   [[durable_objects.bindings]]
   name = "REALTIME_ROOM"
   class_name = "RealtimeRoom"
   [[migrations]]
   tag = "v1-add-realtime-room"
   new_classes = ["RealtimeRoom"]
   ```
2. 新建 `worker-bff/src/realtime-room.ts`：DO 类，维护 `channel → Set<WebSocket>`（SSE 用 Response stream 也可，但 DO + WebSocket 更稳；SSE 方案用 `ReadableStream` + `controller.enqueue`），方法 `subscribe(channel)`、`broadcast(channel, event)`、`unsubscribe`
3. BFF 加路由 `GET /sse/:channel` → 建立 SSE 连接，订阅 DO；心跳 30s
4. BFF `/internal/revalidate` 扩展：清缓存后，向 DO 投递 `{channel, type, id, action}`（HMAC 校验不变）
5. 后端 service 层：写操作（post/chatter/album/comment/navigation 配置）后调用 BFF `/internal/revalidate`（已有 REVALIDATE_SECRET），带对应 tag
6. 前端：新建 `lib/sse.ts`，`EventSource("/sse/moments")` 等，收到事件后 SWR `mutate()` 对应接口；新内容以 Kirameku 入场动画插入；导航/主题配置事件即时刷菜单
7. 断线自动重连（指数退避），SWR 兜底（DO 挂了退化为下次刷新）
8. 升级 wrangler 到 4（`cd worker-bff && pnpm add -D wrangler@4`），用 `scripts/Deploy.ps1` 部署

**频道设计**：`home`、`posts`、`moments`、`albums`、`comments`、`nav`、`all`

**验收**：开两个浏览器，A 在后台发说说，B 的 `/moments` 页 1 秒内出现新卡片（入场动画）；改导航配置，所有页面即时刷新菜单；断网重连后不丢消息（至少不丢后续）。

**坑**：
- Durable Objects 是有状态的，单个 DO 实例内存有限；频道多了要按 channel 哈希分片到多个 DO（`idFromName(channel)`）
- SSE 在 Workers 里用 `transformStream`，注意 `ctx.waitUntil` 保持连接
- CF 免费计划 DO 有额度（400k GB-s、100k 请求/天？需查最新），个人站足够
- 后端调 BFF 是 NAS→公网→CF，要设超时（5s）和失败不阻塞主流程（try/except）
- `REVALIDATE_SECRET` 线上是 wrangler secret（`wrangler secret put REVALIDATE_SECRET`），本地 `.dev.vars`
- EventSource 不支持自定义 header，鉴权用 query param token（如果需要）；目前频道公开，无需鉴权

---

### P5：GitHub OAuth 评论 + 持久点赞
**目标**：说说/相册/文章支持 GitHub 登录评论、点赞持久化。

**步骤**：
1. 用户创建 GitHub OAuth App（见第 11 节），回调 `https://bff.neutronstar.fun/api/auth/github/callback`
2. 后端：
   - 修 `github_auth.py` 第 16 行 `FRONTEND_ORIGIN` 默认值为 `https://neutronstar.fun`
   - NAS 容器设环境变量 `GITHUB_CLIENT_ID`、`GITHUB_CLIENT_SECRET`、`FRONTEND_ORIGIN=https://neutronstar.fun`，重建容器
   - 评论接口 `comments.py`：多态关联（post_id / chatter_id / album_id），楼中楼（parent_id），登录后可发/删自己的评论
   - 点赞：新建 `like` 表（user_id + target_type + target_id 唯一约束），或在 chatter/comment 加 likes 计数 + like 关联表；接口 `POST /api/chatters/:id/like`、`DELETE ...`
   - CORS 已配
3. 前端：
   - 新建 `pages/auth/callback.astro`：接收 `?token=`，存 localStorage（或 httpOnly cookie——目前后端是 302 带 query，前端存 localStorage 最简单）
   - 登录按钮：跳 `/api/auth/github/login`（经 BFF）
   - 说说/相册/文章页：评论区组件（登录态显示输入框，未登录显示"用 GitHub 登录评论"），点赞按钮（登录后可点，乐观更新 + 持久化）
   - `lib/api/client.ts`：请求带 `Authorization: Bearer <token>`
4. BFF：写操作透传已支持；`/api/auth/github/*` 在 PROXY_PREFIXES 里（`/api` 前缀），自动代理
5. 安全：评论内容 XSS 转义（前端渲染时），点赞防刷（唯一约束 + 频率限制）

**验收**：GitHub 登录→发评论→刷新仍在→点赞→刷新仍在→另一个账号登录不能删别人的评论；未登录不能点赞/评论。

**坑**：
- GitHub OAuth App 只能填一个回调 URL；本地开发要另建一个 dev OAuth App，或用本地隧道
- `scope=read:user` 不包含邮箱，评论不需要邮箱
- JWT 存在 localStorage 有 XSS 风险；更安全是 httpOnly cookie，但后端目前是 302 带 query，要改 cookie 模式需后端配合（P5 可先 localStorage，后续升级）
- 评论多态关联要建索引（target_type + target_id）
- 点赞唯一约束要处理并发（INSERT ON CONFLICT DO NOTHING）

---

### P6：Shirone 全特性
**目标**：对照官方功能清单逐项补齐。

**特性清单**（从上游 config 和 pages 推断）：
1. Markdown 扩展：admonition、math(katex)、mermaid、代码块行号/折叠/复制、目录(TOC)、脚注、自定义容器、spoiler、文章加密（password-protection + post-encryption/decryption + protected-session）
2. 搜索：pagefind（构建时索引，`npx pagefind --site dist`）
3. 字体子集：`subset-font`，构建时按需裁剪（P1 先用全量，P6 做子集）
4. 纹理背景：textures.css + canvas 纹理
5. 追番/动漫：`anime.astro` + `animeConfig.ts` + `scripts/anime/sync.mjs`（可选，用户导航暂定没有"追番"，可保留页面不进导航）
6. RSS / sitemap / atom / llms.txt / robots.txt
7. 评论：Giscus（commentConfig.ts，可选，与 GitHub OAuth 评论二选一或并存）
8. 统计：Umami（umamiConfig.ts，可选）
9. 音乐：musicConfig.ts + MusicFloatingCard（已有 island）
10. FAB / 上下文菜单 / wavy-progress / share-poster / last-updated-notice
11. 设备页 / 项目页 / 技能页 / 时间线 / 指南针（compass）—— 部分可保留不进导航
12. 图片 bloom（image-bloom）、fancybox 灯箱（与我们的 Lightbox island 二选一，P3 已用自写 Lightbox，P6 可评估是否换 fancybox）

**验收**：对照 `https://docs.shirone.mysqil.com/` 功能清单逐项过（注意：docs 子页被 robots.txt 禁止自动抓取，需手动浏览）。

**坑**：
- 文章加密是客户端 AES-GCM，加密在构建期或后台，解密在前端；密钥不进 git
- pagefind 索引在构建时生成，放 `dist/pagefind/`，Pages 部署要包含
- 字体子集要处理中文（lxgw-wenkai-screen），子集规则按实际使用字符
- mermaid/katex 是重客户端库，要 dynamic import（只在用到的页面加载）

---

### P7：预览验收 → 合并上线
**目标**：正式站 neutronstar.fun 切换到新站，旧链兼容。

**步骤**：
1. 前端 `web/` 分支推 GitHub，Pages 自动部署到 `neutronstar-web.pages.dev`
2. 全量走查：所有页面 200、亮/暗、桌面/移动、Lighthouse（性能预算：TTFB≤100ms、LCP≤1.5s、CLS≤0.05、首屏 JS≤120KB gzip）
3. 旧链兼容重定向：`/blog/* → /posts/*`（已有 `public/_redirects`），其他旧路径补全
4. BFF 部署（`scripts/Deploy.ps1`），验证 `/health`、缓存、SSE
5. 后端重建（如有模型变更，Alembic 迁移）
6. Pages 自定义域切换：`neutronstar.fun` 从旧分支切到新分支（或直接 main 就是新站）
7. `www` 跳转规则确认（CF Dynamic Redirect Rule）
8. 监控 24h，回滚预案：Pages 回滚到上一个 deployment，BFF `wrangler rollback`，后端镜像 `kirameku-backend:bak-*`

**验收**：正式站首页与 Shirone 1:1；后台发布 10s 内在线页面弹新；GitHub 登录评论全链路通；Lighthouse 达标；无 404。

**坑**：
- Pages 自定义域切换有 DNS 传播延迟，提前降 TTL
- 旧 Pages 项目如果还绑定着自定义域，要先解绑才能切
- 切换后 BFF 的 `BACKEND_ORIGIN` 不变（仍走隧道），不需要改
- 前端 `PUBLIC_API_BASE` 构建时环境变量：Pages 项目设置里配 `PUBLIC_API_BASE=https://bff.neutronstar.fun`

---

## 11. 凭据与环境变量清单

### 已就绪（不需要用户再提供）
| 凭据 | 位置 | 说明 |
|:--|:--|:--|
| NAS SSH 免密 | `~/.ssh/config` Host hewll | Mars@192.168.5.4 |
| 后端 DATABASE_URL | NAS 容器启动参数 + `backups/rescue-from-duplicates/backend.env.txt`（gitignore） | postgresql://... |
| 后端 SECRET_KEY | 同上 | JWT 签名 |
| 后端 CORS_ORIGINS | 同上 | 含 neutronstar.fun 等 |
| BFF REVALIDATE_SECRET | `worker-bff/.dev.vars`（本地）+ wrangler secret（线上） | HMAC 签名 |
| Cloudflare API Token | `worker-bff/.cf.local.env`（gitignore） | Account 级，wrangler 4 whoami 通过 |
| CF Account ID | `d4add8ad549536a77a5b9fcf6d5be733` | wrangler.toml 已写 |
| KV CACHE_TAGS id | `4959a742fe4d44dbbc0ba8c200bea694` | wrangler.toml 已写 |
| Git 推送凭据 | 系统 credential manager | 两个仓库 remote 已配 |

### 待用户提供
| 凭据 | 用途 | 何时需要 |
|:--|:--|:--|
| GitHub OAuth App Client ID + Secret | 评论/点赞登录（P5） | P5 前 |
| （可选）Umami website ID | 统计（P6） | P6 |
| （可选）Giscus 仓库 | 文章评论（P6，与 OAuth 评论二选一） | P6 |
| （可选）阿里云 OSS AK | 图片存 OSS（当前用 NAS 本地 + fastimage，不需要） | 不必须 |

### GitHub OAuth App 创建步骤（给用户）
1. 打开 https://github.com/settings/developers → OAuth Apps → New OAuth App
2. Application name: `NeutronStar Blog`（随意）
3. Homepage URL: `https://neutronstar.fun`
4. Authorization callback URL: `https://bff.neutronstar.fun/api/auth/github/callback`
5. 注册后页面显示 Client ID；点 Generate a new client secret（只显示一次）
6. 把 ID 和 secret 发给开发者，写入 NAS 后端 `.env`（不入库）

### 绝不入库的文件（.gitignore 已覆盖）
- `.env`、`.env.local`、`.env.*.local`
- `.dev.vars`、`.cf.local.env`
- `backups/`（含抢救的真实 .env）
- `_upstream_shirone/`（上游基线，不入库）
- `web/`（独立子仓，外仓忽略）

---

## 12. 部署与发布流程

### 前端（Cloudflare Pages）
```powershell
cd F:\AI\projects\Kirameku2.0\web
pnpm install
pnpm run build          # 产物 dist/client（不是 dist！）
# 方式一：推 git，Pages 自动部署
git add . && git commit -m "..." && git push
# 方式二：手动部署
$env:CLOUDFLARE_API_TOKEN = (Get-Content ..\worker-bff\.cf.local.env | ConvertFrom-StringData).CLOUDFLARE_API_TOKEN
pnpm exec wrangler pages deploy dist/client --project-name neutronstar-web --branch main
```
**坑**：部署目录是 `dist/client`，不是 `dist` 或 `dist/server`；Pages 项目设置里配 `PUBLIC_API_BASE=https://bff.neutronstar.fun`。

### BFF（Cloudflare Worker）
```powershell
cd F:\AI\projects\Kirameku2.0\worker-bff
pnpm install
pnpm run typecheck      # 或 tsc --noEmit
.\scripts\Deploy.ps1    # 自动加载 .cf.local.env，wrangler deploy
# 本地开发
pnpm exec wrangler dev   # 读 .dev.vars
```
**坑**：wrangler 3→4 升级在 P4；`REVALIDATE_SECRET` 线上用 `wrangler secret put REVALIDATE_SECRET` 设置，本地 `.dev.vars`；DO 迁移要 `[[migrations]]`。

### 后端（NAS Docker）
```powershell
# 1. 构建后台（如有改动）
cd F:\AI\projects\Kirameku2.0\Kirameku-backend\admin
pnpm install
$env:NODE_OPTIONS = "--max-old-space-size=8192"
pnpm exec vite build     # 产物 admin/dist

# 2. 同步源码到 NAS（SMB，禁止 ssh 写文件）
robocopy "F:\AI\projects\Kirameku2.0\Kirameku-backend" "U:\kirameku\backend" /MIR `
  /XD .venv __pycache__ .pytest_cache uploads .git "admin\node_modules" /XF *.db .env *.log

# 3. NAS 上构建镜像 + 重建容器（docker 不在 PATH，用全路径）
ssh hewll 'export DOCKER_HOST=unix:///var/run/docker.sock; cd /share/CACHEDEV1_DATA/Container/kirameku/backend && /share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker build -t kirameku-backend:latest .'
ssh hewll 'export DOCKER_HOST=unix:///var/run/docker.sock; D=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker; $D stop kirameku-backend; $D rm kirameku-backend; $D run -d --name kirameku-backend --restart unless-stopped -p 8100:8000 -e DATABASE_URL=<...> -e SECRET_KEY=<...> -e CORS_ORIGINS=<...> -e FRONTEND_ORIGIN=https://neutronstar.fun -e GITHUB_CLIENT_ID=<...> -e GITHUB_CLIENT_SECRET=<...> -v kirameku_uploads:/app/uploads -v /share/CACHEDEV1_DATA/Container/kirameku/backend/admin/dist:/app/admin/dist:ro kirameku-backend:latest'
```
**坑**：
- NAS docker 必须全路径 `/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker` + `DOCKER_HOST=unix:///var/run/docker.sock`
- 只删应用容器，**绝不碰 kirameku-pg 容器和 kirameku_pgdata / kirameku_uploads 卷**
- 环境变量在 `docker run -e` 里，不是 `.env` 文件（容器内 .env 也可，但目前是启动参数）
- 重建前打备份镜像：`docker tag kirameku-backend:latest kirameku-backend:bak-YYYYMMDD`

### 数据库迁移（Alembic）
```bash
docker exec kirameku-backend alembic current           # 查看版本
docker exec kirameku-backend alembic revision --autogenerate -m "描述"
docker exec kirameku-backend alembic upgrade head
```
**坑**：生产库已 `alembic stamp head` 打过基线；改模型必须走 Alembic，不能直接 `create_all`。

### 验证清单
```powershell
curl.exe -s https://neutronstar.fun/                 # 200
curl.exe -s https://bff.neutronstar.fun/health       # {"status":"ok"}
curl.exe -s https://kirameku-api.neutronstar.fun/api/health  # {"status":"ok"}
curl.exe -s https://kirameku-api.neutronstar.fun/admin/       # 200
curl.exe -s -o NUL -w "%{http_code}" https://www.neutronstar.fun/  # 301
```

---

## 13. 避坑大全

### Windows / PowerShell
- 默认 shell 是 PowerShell，**`||`、`&&` 部分可用但行为与 bash 不同**；`NODE_OPTIONS=... cmd` 是 bash 语法，PowerShell 要先 `$env:NODE_OPTIONS="..."`
- 中文 UTF-8 文件在 PowerShell 控制台显示为 GBK 乱码，但**文件本身正常**，用 Read 工具或 VS Code 看
- `Get-Content` 没有 `-TotalCount`（那是 bash head），用 `-TotalCount` 实际是 `-Head` 的别名？PowerShell 5.1 有 `-TotalCount`，但行为不同；用 `-First N`
- 命令超 15s 自动转后台 Task，用 `TaskOutput(task_id, block=true)` 取结果
- pnpm 11 不再读 `package.json` 的 `pnpm.onlyBuiltDependencies`，改在 `pnpm-workspace.yaml` 写 `allowBuilds: {esbuild: true, ...}`，否则 esbuild 二进制不安装、vite 构建失败
- robocopy 返回码 0-7 都是成功（>=8 才是失败），在脚本里要特殊处理

### Git 多仓
- `web/` 是独立子仓，外仓 `git status` 看不到；改前端必须 `cd web` 单独 commit/push
- 外仓 `.gitignore` 第 43 行 `web/` 忽略整个前端目录
- `_upstream_shirone/` 不入库，是浅克隆对照源
- `backups/` 不入库，含真实密钥
- 推送前 `git status` 确认没有 `.env` / token 被 staged
- 双端推送（GitHub+Gitee）脚本：`F:\AI\git-templates\sync_and_publish.ps1`（用户选择是否推送时用）

### Astro
- `output: "static"` 不能 SSR，实时页要改 `output: "hybrid"` + 页面 frontmatter `export const prerender = false`
- `imageService: "passthrough"` 表示构建期不处理远程图，图片走 BFF `/img/*`
- Astro 布尔属性不能依赖猜测，布局内要同时判断 `home || Astro.url.pathname === "/"`
- Svelte 5 是 runes 模式（`$state`/`$derived`），不是旧版 `export let`
- `@astrojs/svelte` 与 `@astrojs/react` 可共存，注意水合边界
- Pages 部署目录是 `dist/client`，不是 `dist`

### Cloudflare
- Account API Token 的 `/user/tokens/verify` 返回 401 是正常的（没有 user 级权限），不影响 account 级操作（workers/KV/DO）
- wrangler 读 `CLOUDFLARE_API_TOKEN` 环境变量，或 `wrangler login`（OAuth）
- 免费计划没有原生 cache-tag，用 KV 自建索引（本项目已实现）
- CF Image Resizing 是付费功能，权益未验证；默认走预生成派生图更稳
- Durable Objects 需要 `[[migrations]]` 声明新 class，首次部署要 `wrangler deploy` 执行迁移
- Pages 自定义域被旧项目占用时，要先解绑旧项目再切
- `www` 跳转是 CF Dynamic Redirect Rule，不在 Pages 配置里

### NAS Docker
- docker 不在 PATH，必须全路径 + `DOCKER_HOST=unix:///var/run/docker.sock`
- 源码同步走 SMB `U:\kirameku\backend`，**禁止 scp / ssh "cat >" 写文件**（编码/权限问题）
- 只重建应用容器，不碰 PostgreSQL 容器和数据卷
- 环境变量在 `docker run -e`，改了 env 必须重建容器（restart 不读新 env）
- 重建前打备份镜像 tag
- NAS 路径 `/share/CACHEDEV1_DATA/Container/kirameku/backend`

### 图片
- 体积杠杆是分辨率，不是质量参数（同 1920 降质量只省 4-9%）
- 竖长图（1920×3800+）即使 webp q82 也能到 1.9MB，列表页绝对不能直连母版
- jsDelivr 首次回源 0.9-1.5s，缓存后快；GitHub 仓库更新后 jsDelivr 有缓存刷新延迟（可用 `https://purge.jsdelivr.net/` 刷新）
- BFF `/img/*` 目前只代理 NAS 源，不支持 jsdelivr 远程；要扩展需加白名单 + 安全校验（防 SSRF）

### OAuth / SSE
- GitHub OAuth App 只能一个回调 URL，本地开发另建 dev App
- `scope=read:user` 不含邮箱
- JWT 存 localStorage 有 XSS 风险，后续可升级 httpOnly cookie
- SSE EventSource 不支持自定义 header，鉴权用 query param
- DO 是有状态的，频道多了要按 channel 哈希分片
- 后端调 BFF 要设超时 + try/except，不阻塞主流程

### 搜索 / 文档
- `docs.shirone.mysqil.com` 子页被 robots.txt 禁止自动抓取，需手动浏览
- raw.githubusercontent.com 拉 `src/pages/index.astro` 是 404（首页真身是 `[...page].astro`）
- 升级上游：`node scripts/sync-upstream.mjs main` 评估，确认后改 `PINNED_COMMIT`

---

## 14. 给接手 AI 的启动清单

### 第一步：读文件（30 分钟）
1. 本文（HANDOFF）
2. `docs/方案-v2.0-Shirone1比1复刻与SSE实时.md`
3. `docs/开发过程与踩坑-二次开发指南.md`
4. `_upstream_shirone/src/layouts/Layout.astro` + `MainGridLayout.astro`
5. `_upstream_shirone/src/pages/[...page].astro`
6. `_upstream_shirone/astro.config.mjs`
7. `web/astro.config.mjs` + `web/package.json`
8. `worker-bff/src/index.ts` + `wrangler.toml`
9. `Kirameku-backend/app/config.py` + `app/api/router.py` + `app/api/github_auth.py`

### 第二步：跑通环境
```powershell
# 前端
cd F:\AI\projects\Kirameku2.0\web
pnpm install
pnpm run dev          # http://localhost:4321

# BFF（另一个终端）
cd ..\worker-bff
pnpm install
pnpm exec wrangler dev  # http://localhost:8787，读 .dev.vars

# 后端（本地可选，通常直接用线上 NAS）
cd ..\Kirameku-backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

### 第三步：启动 P1
按第 10 节 P1 工单执行：装依赖 → 改 astro.config → 移植外壳 → 首页 mock → 拆手搓件 → 构建 → 截图对照。

### 第四步：每完成一个 P 阶段
- 跑验证清单（第 12 节）
- 前端 `cd web && git add/commit/push`
- 外仓 `git add/commit/push`（如果改了后端/BFF/文档）
- 更新本文的"已完成工作"章节

---

## 15. 未决事项与风险

| 事项 | 状态 | 影响 |
|:--|:--|:--|
| ~~Pages 环境变量~~ | ✅ 已配置（新 token + env_vars 字段） | 无 |
| ~~正式站内容为 demo 文章~~ | ✅ 已解决（2026-09-12，线上 8 篇真实文章） | 无 |
| ~~根域是 Pages 旧静态版 / 动态路由 404 / 首页旧缓存~~ | ✅ 已解决（Workers 自定义域接管 + purge，见 0.6） | 无 |
| ~~未知路径被 catch-all 渲染成首页（软 404）~~ | ✅ 已修（`[...page].astro` 非数字参直接 404） | 无 |
| ~~P4 实时后端侧（NAS 容器仍是旧镜像）~~ | ✅ 已重建容器并端到端实测通过（见 0.7） | 无 |
| ~~NAS 后端镜像落后于源码（缺 cache_invalidate）~~ | ✅ 已重新 `docker build` | 无 |
| ~~`wrangler secret put` 存入带换行的密钥~~ | ✅ 已改用 CF API 重写并轮换 | 无 |
| 导航/侧栏仍是构建期静态配置（未接 `site_config`） | P2 收尾项：让外壳消费 `/api/site-config/*` | 后台改导航不生效 |
| 7 个历史 island 已无人引用（PostList/HomeFeed/NavigationIsland 等） | 可清理或按需复活 | 代码噪音 |
| 首页/归档/文章详情停留时不自动弹新 | 刷新即时；要停着也弹新需加轻量 island | 体验增强 |
| `/rss.xml`、`/atom.xml`、`/llms.txt` 404 | P6 移植上游同名端点 | 订阅/SEO |
| `/api/albums` 的 slug 为空 | 相册详情页未启用（走 island 内联展开），如需独立详情页要回填 slug | 功能完整性 |
| `astro dev` 依赖优化器崩溃 | P2 修复 | 开发体验（当前用 build+preview 替代） |
| Yozai 15MB TTF 直接入库 | P6 字体子集化解决 | 仓库体积 |
| 音乐挂件运行时 stylus 编译与 workerd 冲突 | P6 启用前解决 | Shirone 全特性 |
| 构建期个别图片 compile 后变大 | P2 图片策略复核 | 性能 |
| ~~GitHub OAuth App 凭据（Client ID/Secret）~~ | ✅ 已配进 NAS 容器 env，`/login` 已 307 到 GitHub（见 0.8） | 无 |
| GitHub 授权那一下需人工点一次 | ⏳ 打开 `/moments` 点「用 GitHub 登录」即完成（OAuth 固有环节） | 无 |
| ~~评论多态关联（说说/相册）~~ | ✅ 已支持 post/chatter/album（说说与文章前端已接，相册差一个 adapter 分支） | 无 |
| ~~点赞防刷（用户维度唯一约束）~~ | ✅ `likes` 表唯一约束 + `/api/likes/toggle`，线上实测不叠加 | 无 |
| ~~相册评论 UI~~ | ✅ 已接入（`CommentsThread` 加 album 分支，挂相册展开卡片） | 无 |
| ~~后台评论管理只覆盖文章评论~~ | ✅ 已升级为「内容评论 / 说说评论」双 Tab + 类型过滤 + 所属内容列（见 0.8） | 无 |
| 后台评论分页 | 可选：当前固定取 100 条、无分页器 | 评论量大时再加 |
| 后端 `github_auth.py` 默认值修正 | 已改代码，待下次重建镜像生效 | 无（env 已覆盖） |
| 旧 CF API Token | 建议用户在 Dashboard 删除 | 安全 |
| fastimage 两级派生图批量生成 | 待用户确认 | P2 图片策略 |
| CF Image Resizing 权益 | 未验证 | P2 图片策略（默认走预生成，不阻塞） |
| 外仓 8 个 commit 未 push | 待用户选择是否推送 | 代码备份 |
| 正式站切换 | ✅ 已完成（2026-09-12 提前切换，用户拍板） | 无 |
| 旧 Vite SPA"NeutronStar 星舰" | 已下线 | 无 |
| 旧 kirameku-fe 容器 | 已不存在 | 无 |
| 文章加密功能 | P6，密钥管理需设计 | 安全 |
| 评论 XSS / 点赞防刷 | P5 实现 | 安全 |
| DO 免费额度 | 个人站足够，需监控 | 成本 |

---

## 16. 关键 ID / 路径速查

- CF Account ID: `d4add8ad549536a77a5b9fcf6d5be733`
- KV CACHE_TAGS: `4959a742fe4d44dbbc0ba8c200bea694`
- 上游 pinned commit: `b79d301e5e6a8ec897e85b042de43187b571dd5b`
- NAS: `192.168.5.4`，SSH `hewll`（Mars）/`hewll-admin`（admin）
- NAS docker: `/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker`
- NAS 源码: `/share/CACHEDEV1_DATA/Container/kirameku/backend`（SMB `U:\kirameku\backend`）
- 容器: `kirameku-backend`(:8100→8000)、`kirameku-pg`(:15432→5432)
- 卷: `kirameku_uploads`、`kirameku_pgdata`
- 域名: `neutronstar.fun`（Pages）、`bff.neutronstar.fun`（Worker）、`kirameku-api.neutronstar.fun`（Tunnel→NAS）
- 预览: `neutronstar-web.pages.dev`
- 图床: `https://cdn.jsdelivr.net/gh/neutron-star77/fastimage@main/2026/08/`
- Everything CLI: `E:\Program Files (x86)\图拉丁工具箱\图吧工具箱202507\tools\其他工具\Everything\es.exe`
- 双端推送脚本: `F:\AI\git-templates\sync_and_publish.ps1`
- 部署踩坑旧档: `F:\AI\部署记录与风险点-2026-08-19.md`（Mizuki 时代，参考价值有限）

---

> 本文档随开发推进持续更新。每个 P 阶段完成后，更新第 3 节（已完成工作）和第 15 节（未决事项）。
> 有疑问先查第 13 节避坑大全，再查对应源码，最后问用户。
