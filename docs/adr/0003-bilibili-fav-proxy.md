# ADR-0003：B 站收藏夹数据的代理架构（悬浮音乐播放器取数）

- 状态：已采纳（2026-09-13）
- 关联：`docs/HANDOFF-续开发交接文档.md` §4.11.4、`docs/坑大全.md` 6.3.19、`Kirameku-backend/app/api/bili_fav.py`

## 背景

音乐悬浮播放器（ADR-0002 的落地功能）需要在浏览器里拿到用户 B 站收藏夹的视频列表
（`api.bilibili.com/x/v3/fav/resource/list`）。实测 B 站对该接口的访问限制矩阵：

| 途径 | 结果 |
|:--|:--|
| 浏览器直连（带 Origin 头） | 403 —— CORS 不可用 |
| JSONP（callback 参数，旧 HewllBlog 时代的方案） | 403 —— JSONP 已下线 |
| Cloudflare Worker 出口 IP（BFF 代理） | 412 —— 数据中心 IP 风控 |
| NAS 后端代拉（家宽国内 IP + 浏览器 UA） | 200 ✅ |

另外两个硬约束：接口 `ps` 上限 20（传更大值返回 code -400）；封面图 CDN `i*.hdslb.com`
有防盗链（带外站 Referer 403，无 Referer 200 → 前端 `<img referrerPolicy="no-referrer">`）。

## 决策

1. **代理放在 NAS FastAPI 后端**（`/api/bili-fav`），不放 BFF（Worker IP 被 412），
   不放前端（CORS）。
2. 服务端按 `ps=20` **自动翻页聚合**（最多 5 页 = 100 首），客户端一次请求拿全量。
3. 响应带 `Cache-Control: s-maxage=600, stale-while-revalidate=1800`，让 BFF 边缘缓存
   10 分钟——对 B 站的真实请求频率被压到每 colo 每 10 分钟至多一批。
4. 只回传播放器需要的字段（bvid/title/cover/duration/author），封面升级 https，
   剔除失效视频（无 bvid）。

## 后果

- 优点：绕开全部风控；BFF 现有 `/api/*` 缓存与 CORS 链路直接复用；失效视频自动剔除。
- 代价：后端承担对 B 站的出站请求（有边缘缓存兜底，量级可忽略）。
- 风险：B 站接口/风控策略若变化（如连家宽 IP 也要求 wbi 签名或 cookie），需要升级
  `bili_fav.py`——变化时优先怀疑 code -400/-412/403 的含义是否漂移。
- 已否决的替代方案：BFF 代理（412）、JSONP（已下线）、站内自建音频源（版权与复杂度）。
