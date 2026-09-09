# kirameku-bff（中间层）

Cloudflare Workers + Hono。前端只跟它对话，回源 NAS FastAPI 只在缓存未命中时发生。

## 路由

| 路由 | 说明 |
|:--|:--|
| `GET /health` | 健康检查 |
| `GET /api/*` | 单接口代理，Cache API 命中即返 |
| `GET /bff/home` | 聚合：文章 + 说说 + 相册 + 站点配置，1 个 RTT |
| `GET /img/*?w=800` | 图片：AVIF/WebP 协商 + 宽度裁剪，边缘缓存 1 天 |
| `POST|PUT|PATCH|DELETE /api/*` | 透传，不缓存 |
| `POST /internal/revalidate` | HMAC 校验后按 tag/URL 清缓存 |

## 本地开发

```bash
pnpm install
cp .dev.vars.example .dev.vars   # 填 BACKEND_ORIGIN / REVALIDATE_SECRET
pnpm dev                          # http://localhost:8787
pnpm typecheck
```

## 部署

```bash
# 首次：创建 KV（用于 tag → url 索引）
wrangler kv:namespace create CACHE_TAGS      # 把 id 填进 wrangler.toml

# 设密钥
wrangler secret put REVALIDATE_SECRET

pnpm deploy
```

部署后在 CF 面板绑定自定义域 `kirameku-api.neutronstar.fun`，源站改用隧道子域（如 `origin.neutronstar.fun`）。

## 缓存失效

后端发布时调用：

```bash
BODY='{"tags":["moments"]}'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$REVALIDATE_SECRET" -hex | awk '{print $2}')
curl -X POST https://kirameku-api.neutronstar.fun/internal/revalidate \
  -H "Content-Type: application/json" -H "x-signature: $SIG" -d "$BODY"
```

后端也可用响应头 `x-cache-tags` 自定义标签；未给时按路径推导（见 `tagsForPath`）。

## 注意

- 免费计划没有原生 `cache-tag`，用 KV 自建 tag → URL 索引；升级 Workers Paid 后可切原生 `cacheTags`
- Workers runtime 无 Node fs/原生模块，勿引入依赖它的库
- `/img/*` 的 CF Image Resizing 只在 Cloudflare 上生效，本地 dev 原样返回
