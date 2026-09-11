# 新博客方案 v1.3：三层架构（前端 / 中间层 / 后端）

> 状态：**决策已定 + T0/T1 已完成**，T2 起按三层架构实施
> 更新：2026-09-09 · 仓库 Kirameku2.0（`neutron-star77/Kirameku2.0`）

---

## 0. 决策记录

| # | 决策项 | 结论 |
|:--|:--|:--|
| D1 | 前端架构 | **单轨 Astro**（工具箱/小游戏已删除，书架延后 P1），Next 仅作迁移参考源 |
| D2 | 部署 | 前端 **Cloudflare Pages** 绑 `https://neutronstar.fun`；**后端放 NAS 192.168.5.4** |
| D3 | 范围 | 默认一级导航：首页、文章、归档、说说、相册、友链、杂谈、小说、关于。**删除工具箱、小游戏、实验页、Live2D**；`novel`、`music`、`projects`、`bookmark` 作为后续功能保留，其中音乐改为可开关的悬浮卡片 |
| D4 | 风格 | **整站复刻 Shirone**（Material 3 + 侧栏外壳 + 卡片层级 + 大写标题） |
| D5 | 工程配置 | mp-engineering 已初始化（`AGENTS.md` + `docs/agents/*`） |
| **D6** | **架构形态** | **三层：前端（Pages）→ 中间层（边缘 BFF / Workers）→ 后端（NAS FastAPI）**。中间层负责聚合、边缘缓存、图片优化、缓存失效；**前端加载速度优先** |
| **D7** | **导航** | 后台可配置一级菜单、二级菜单、顺序、显示状态、内部/外部链接和打开方式；默认导航为首页、文章、归档、说说、相册、友链、杂谈、小说、关于 |
| **D8** | **音乐** | 音乐不占用一级导航，改为后台可开关的悬浮卡片播放器；默认关闭，不阻塞首屏 |

### 进度（2026-09-09）

- **T0 后端加固 ✅**：鉴权落库校验、访客删除补鉴权、CORS、`python-dotenv`、Alembic 基线、7 个鉴权测试全绿
- **T1 NAS 部署 ✅**：容器重建 + `admin/dist` 挂载；`https://kirameku-api.neutronstar.fun/api/health` → 200，`/admin/` → 200（详见 `docs/DEPLOY-NAS.md`）
- **T-W1 中间层骨架 ✅**：`worker-bff/`（Hono on Workers）已部署到 `bff.neutronstar.fun`，`/health`、`/api/*`、`/bff/home` 与 KV 缓存链路已验证
- **T2 / T3 ✅**：Astro 7 骨架 + M3 设计系统已完成；Cloudflare Pages 项目 `neutronstar-web` 已绑定 `neutronstar.fun`
- **T4 取数层 ✅**：`src/lib/api/{types,client,hooks}.ts` + `components/islands/*`；字段与 kirameku-api 对齐（列表返回裸数组、详情按 slug、Chatter.images 已解析为数组；后端无 total 头，前端用返回长度==size 判 hasMore）
- **T5 起步 ✅**：首页 Hero 静态渲染 + `HomeFeed` island（`client:visible`）拉真实 posts/chatters；`/posts/[slug]` on-demand SSR（Markdown 暂以预格式化展示，T8 做 MD→高亮+批注）；后端 CORS 已加 `neutronstar-web.pages.dev`，跨域取数已通
- 下一步：补齐 `/archive`、`/moments`、`/albums` 的真实数据与动画细节，并在管理后台初始化导航/音乐配置

### 根域现状（免密钥探测）

```
neutronstar.fun      → 172.67.163.157 / 104.21.10.151（CF 代理）
www.neutronstar.fun  → 同上
blog.neutronstar.fun → NXDOMAIN
页面 = Vite 打包的 React SPA：<title>NeutronStar 星舰</title> / #root
```

---

## 1. 为什么必须加中间层

后端在 NAS（家庭宽带，上行小、跨区回源 200~500ms）。若前端直连 NAS，每次动态内容都要跨洋回源，TTFB 不可控。

**中间层（边缘 BFF）解决三件事**：

1. **读多写少**：90% 请求在边缘命中缓存，回源只在未命中时发生
2. **聚合**：首页需要 posts + chatters + albums 三个接口 → 中间层合并成一次 `/bff/home`，省 2 个 RTT
3. **图片**：AVIF/WebP 转换 + 尺寸裁剪在边缘完成，源站只存原图

---

## 2. 三层架构

```
┌──────────── 前端（Cloudflare Pages / Astro 7）────────────┐
│  静态壳（预渲染 HTML + 内联关键 CSS + 子集字体）            │
│  React islands：动画组件 client:visible 按需水合            │
│  所有数据请求 → 中间层（同源 /api、/bff、/img）             │
└───────────────────────┬───────────────────────────────────┘
                        │ HTTPS（边缘内，~10ms）
┌───────────────────────▼─── 中间层（Cloudflare Workers + Hono）──┐
│  /bff/*     聚合接口（home / archive / post / album）           │
│  /api/*     单接口代理：Cache API 命中即返，未命中回源          │
│  /img/*     图片优化（CF Image Resizing，AVIF/WebP + 尺寸）     │
│  /internal/revalidate  HMAC webhook → 按 tag/URL 精确失效       │
│  KV         tag→URL 索引、站点配置、统计计数                    │
│  写操作（POST/PUT/DELETE）直接透传，不缓存                      │
└───────────────────────┬────────────────────────────────────────┘
                        │ 仅未命中时回源（经 CF Tunnel）
┌───────────────────────▼─── 后端（NAS 192.168.5.4）─────────────┐
│  FastAPI :8000（Docker）+ PostgreSQL :5432 + /admin + /uploads  │
│  发布时 → 计算 cache tags → 调 /internal/revalidate → 边缘失效  │
└─────────────────────────────────────────────────────────────────┘
```

### 职责边界（不可越界）

| 层 | 只许做 | 不许做 |
|:--|:--|:--|
| 前端 | 渲染、动画、交互、SWR 重校验 | 直连 NAS、写业务逻辑 |
| 中间层 | 缓存、聚合、图片、失效、限流 | 写业务规则、存业务数据（除 KV 计数） |
| 后端 | 业务、持久化、鉴权、上传 | 关心 CDN/缓存细节 |

---

## 3. 技术选型

| 层 | 选型 | 理由 |
|:--|:--|:--|
| **前端** | **Astro 7 + Vite 8**（`output: server` hybrid + `@astrojs/cloudflare`）+ React 19 islands + `motion` + Tailwind 4 | Shirone 同生态；静态壳 + 内容实时 |
| **中间层** | **Hono on Cloudflare Workers** + Cache API + KV（+ 后续 R2 / Queues） | 极轻（~20KB）、冷启动近 0、原生边缘；比 Pages Functions 更独立可控 |
| **后端** | FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL（NAS Docker） | 现有 18 表复用 |
| 存储 | NAS `/uploads` → 后续 **R2**（零出网费） | 经中间层 `/img/*` 统一出口 |
| 搜索 | Pagefind（静态）+ 后续 Meilisearch | MVP 后置 |

---

## 4. 中间层设计

### 路由

| 路由 | 行为 | 缓存 |
|:--|:--|:--|
| `GET /bff/home` | 聚合：最新文章 + 说说 + 相册 + 站点配置，一次返回 | `s-maxage=120, swr=600` |
| `GET /bff/archive?page=&tag=` | 聚合文章列表 + 分类/标签计数 | `s-maxage=300, swr=86400` |
| `GET /api/*` | 单接口代理回源 | 按上游 `Cache-Control`；默认 `s-maxage=60, swr=300` |
| `GET /img/*` | 图片：格式协商 + 宽度裁剪 + 长缓存 | `s-maxage=86400, immutable` |
| `POST /internal/revalidate` | HMAC 校验 → 按 tag 查 KV → 逐个 `caches.delete` | — |
| 其它方法 | 透传（写操作不缓存） | — |

### 缓存失效（免费计划无 cache-tag 的替代方案）

后端返回/计算 `x-cache-tags: moments,post:slug` → 中间层把 `tag → [url...]` 写进 **KV** → revalidate 时按 tag 取出 URL 列表 → 逐个 `caches.default.delete(url)` + 通知前端 Pages purge。
> 升级 Workers Paid 后可切原生 `cacheTags`，删掉 KV 索引。

### 实时性

后台发布 → FastAPI → `POST /internal/revalidate`（HMAC）→ 边缘缓存秒删 → 前端下次请求即新数据；在线页面由 SSE/轮询静默刷新。**零 rebuild**。

---

## 5. 页面清单

| 页面 | 路由 | 渲染 | 聚合接口 |
|:--|:--|:--|:--|
| 首页 | `/` | on-demand（边缘缓存 120s） | `/bff/home` |
| 文章 | `/archive`、`/posts/[slug]` | on-demand | `/bff/archive`、`/api/posts/{slug}` |
| 说说 | `/moments` | on-demand（60s） | `/api/chatters` |
| 相册 | `/albums`、`/albums/[id]` | on-demand | `/api/albums*` |
| 杂谈 | `/messages` | on-demand（60s） | `/api/messages` |
| 友链 | `/friends` | on-demand | `/api/friend-links` |
| 小说 | `/novel` | 应用区入口 | 后续 reader 服务 |
| 关于 | `/about` | prerender | — |
| 项目 | `/projects` | 后续功能 | `/api/projects` |
| 收藏 | `/bookmark` | 后续功能 | `/api/bookmarks` |
| 音乐 | 悬浮卡片 | 后台开关 | `/api/music` |

---

## 6. 性能优化清单（前端加载速度优先）

### 性能预算（硬指标，上线前必须达标）

| 指标 | 目标 | 手段 |
|:--|:--|:--|
| **TTFB** | ≤ 100ms（边缘） | HTML 预渲染/边缘缓存；回源只发生在未命中 |
| **LCP** | ≤ 1.5s（4G 模拟） | 首屏图片 AVIF + 显式宽高 + preload；关键 CSS 内联 |
| **CLS** | ≤ 0.05 | 图片/字体预留尺寸；动画只动 transform/opacity |
| **INP** | ≤ 200ms | islands 按需水合；动画库 dynamic import |
| **首屏 JS** | ≤ 120KB gzip | 动画/灯箱/播放器按需加载，不进首包 |
| **首屏图片** | ≤ 200KB | AVIF/WebP + 响应式 `srcset` + LQIP 占位 |
| **字体** | ≤ 60KB 或系统字体 | 按内容子集化 + `unicode-range` 分片 + `font-display: swap` |

### 实施要点

1. **静态优先**：能预渲染的页面一律预渲染；内容页用边缘缓存兜底，不做"纯客户端取数"
2. **islands 最小化**：只有需要交互的组件才 island；动画组件 `client:visible`，首屏外的不水合
3. **按需加载**：`Lightbox`、`motion` 重组件和音乐悬浮播放器按需加载；Live2D 完全删除
4. **图片**：统一走 `/img/*`；`loading="lazy"` + `decoding="async"` + 显式 `width/height`；LQIP 模糊占位
5. **预取**：Astro 内置 `prefetch`（视口内链接 hover 预取）；关键路由 `preload`
6. **数据**：SWR + `stale-while-revalidate` + 聚焦重校验；写操作乐观更新
7. **第三方**：评论/OAuth/统计延后到 `requestIdleCallback`，不阻塞 LCP
8. **传输**：Brotli、HTTP/2、早期提示（`Early-Hints`）由 CF 自动

---

## 7. 动画规格（Kirameku → islands）

### 说说 `/moments`
- 按日期分组；同日多条 `absolute top: i*18px`、`zIndex: len-i`
- 倾斜 `rotations = [-2, 1.5, -1, 2, -1.5, 1, -0.5, 1.5]` + `x: ±4`
- 展开：`layout` + `rotate/x→0` + `y:-4` + `zIndex:50`，spring(300, 25)
- 入场：分组 `delay: idx*0.1`、卡片 `delay: i*0.05`；补 `whileInView`
- 评论：`AnimatePresence` 高度折叠 + 递归树拍平

### 相册 `/albums`
- 列表：大写标题 + 描述 + 日期 + 徽标 + hashtags
- 详情：真瀑布流 `columns-1 sm:columns-2 lg:columns-3` + `break-inside-avoid`
- 卡片：拍立得（白边 + 胶带），旋转由 `photo.id` 确定性派生 `((seed%7)-3)*0.8`°
- `Lightbox`：spring 缩放 + 键盘 + 锁滚动（按需加载）

### 友链 `/friends`
- 采用相册式卡片布局与错位动画
- 卡片展示头像、名称、简介、标签和站点链接
- 支持分类筛选、悬浮展开、键盘焦点和移动端降级
- 数据全部来自后端 API，后台可实时新增、编辑、隐藏和排序

### 全局约束
- 统一 `variants.ts`（`staggerContainer`/`fadeUp`/`cardSpring`）
- `prefers-reduced-motion` 全量降级
- 禁止渲染期 `Math.random()`；移动端默认关重特效

---

## 8. 部署

| 主机 | 指向 |
|:--|:--|
| `neutronstar.fun` / `www` | CF Pages（Astro 主站；www 301 到根域） |
| `bff.neutronstar.fun` | **中间层 Workers**（对外 API 入口）→ 未命中回源 NAS FastAPI |
| `kirameku-api.neutronstar.fun` | NAS FastAPI 源站（仅由 BFF/管理链路访问） |
| 源站 NAS | 仅被中间层访问（隧道），不直接对外（写操作除外） |

> 当前保留 `kirameku-api.neutronstar.fun` 作为 NAS FastAPI 源站，Worker 使用独立的 `bff.neutronstar.fun`，避免切换期间影响管理后台与历史接口。

后端与后台部署细节见 `docs/DEPLOY-NAS.md`。

### 国内加速（2026-09 调研结论）

| 平台 | 免费？ | 国内速度 | 关键限制 |
|:--|:--|:--|:--|
| **EdgeOne Pages**（腾讯云） | ✅ **免费版 $0/月**，官方称永久提供；超量在收费版推出前不中断 | 快（中国大陆可用区 / 全球含大陆） | 加速区域含大陆时**必须 ICP 备案**（本站已有：赣 ICP 备 2025078417 号）；必须用自定义域名访问（平台域名的预览链接仅 3 小时有效）；支持 Git 导入 + Edge Functions |
| 阿里云 OSS 静态托管 | ❌ 按量：存储 ~0.09 元/GB/月 + 外网流量 ~0.5 元/GB + 请求费，小站约几元/月 | 快 | 自定义域名的 HTTPS 需再挂 CDN，等于两道钱 |
| 腾讯云 CloudBase 静态托管 | ⚠️ 计费已改为「资源套餐 + 按量」，无明确长期免费额度 | 快 | 更适合带后端的一体化场景 |
| GitHub Pages | ✅ 免费 | 慢且不稳 | 国内无加速 |
| Cloudflare Pages（当前） | ✅ 免费 | **慢**（实测 TTFB 0.6~1.9s） | 全球快、国内慢 |

**推荐：分线路部署（免费且国内外都快）**

- 前端**同时**部署到 EdgeOne Pages 与 CF Pages
- DNS 用**分线路解析**：境内 → EdgeOne，境外 → CF
  - 需把 DNS 从 CF 迁到 DNSPod/阿里云 DNS（支持境内/境外线路）；现有隧道记录（dashboard / hermes / news / kirameku-api）在 DNSPod 里照配 CNAME 即可
- API / 中间层：先保留 CF Workers（已写好 Hono，且有边缘缓存，回源少）；若实测国内 API 延迟仍高，再把中间层移植一份到 EdgeOne 边缘函数

**落地顺序**：T5 接完真实数据 → 切根域 → 再上 EdgeOne 分线路（切域与加速分两步做，避免一次改太多变量）。

### 旧站下线清单
1. 查 `neutronstar.fun` 归属的 Pages 项目（现为 Vite SPA「NeutronStar 星舰」）
2. **查 zone 的 Worker routes**（历史坑：优先级高于 Pages），有抢占先删
3. 删旧 Pages 自定义域绑定
4. 新 Pages 绑 `neutronstar.fun` + `www`
5. Purge Everything，`curl -I` 校验

---

## 9. 数据模型

复用现有 18 表；增量：`webhook_log`（revalidate 审计）、`site_config` 扩 key（M3 主题色/导航/Hero/公告）；P1 加 `post.encrypted/ciphertext`、`anime*`。

必修项已在 T0 完成：Alembic、权限、CORS、`python-dotenv`。

---

## 10. 工单

| # | 内容 | 状态 |
|:--|:--|:--|
| T0 | 后端加固（鉴权/Alembic/CORS/依赖） | ✅ |
| T1 | NAS 部署（镜像重建 + admin 挂载 + 隧道） | ✅ |
| **T-W1** | 中间层骨架：Hono Worker（代理 + Cache API + 图片 + HMAC 失效） | ✅ 已部署 `bff.neutronstar.fun` |
| **T-W2** | 聚合接口 `/bff/*` + KV tag 索引 + `/internal/revalidate` | 待做 |
| **T-W3** | `/img/*` 图片优化 + 长缓存；部署到 Workers + 域名切换 | ✅ 已部署并完成域名切换 |
| **T2** | Astro 工程骨架（cloudflare 适配器、Tailwind 4、React island）+ GitHub + Pages 占位 | ✅ 已上线 `https://neutronstar-web.pages.dev` |
| **T3** | M3 设计令牌 + 布局外壳（顶栏/侧栏/页头/卡片）+ `variants.ts` | ✅ 已上线（`/`、`/about`） |
| **T4** | 取数层：TS 类型 + SWR hooks + 统一 fetch（字段对齐真实后端） | ✅ 已上线 |
| **T5–T8** | 文章 / 说说 / 相册 / 首页+杂谈+关于 | 🟡 进行中（首页+文章页已接真数据，moments/albums/archive 待做，动画 T6/T7） |
| T9 | 实时链路打通（发布 → 边缘失效） | 待做 |
| **T10** | **切根域**（T5 完成后执行）+ 旧站下线；随后上 EdgeOne 分线路 | 待做（T5 后） |

---

## 11. 风险

1. **Workers runtime**：无 fs/原生模块；图片与字体处理须边缘/构建期完成
2. **免费计划无 cache-tag**：用 KV tag 索引替代；升级后可切原生
3. **回源延迟**：只影响未命中；靠预热（发布后主动请求一次）进一步消除
4. **切域风险**：先查 Worker routes；切前留回滚
5. **NAS 隧道改配置需 root**：走 autorun.sh 借权流程
6. **Hydration**：随机值确定性派生；islands 延迟水合
7. **SEO**：内容页必须 SSR 出 HTML

---

## 12. 待确认

1. **CF API Token**（Zone.Zone:Read / DNS:Read / Pages:Read / Workers Routes:Read；切换时加 Edit）—— 用于确认根域归属与部署 Workers
2. 中间层上线时，源站是否改为**仅隧道可达**（更安全）还是继续公网可达
3. 书架（P1）是否仍要 reader-master 容器
