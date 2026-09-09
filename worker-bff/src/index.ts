/**
 * Kirameku 中间层（边缘 BFF）
 *
 * 职责：缓存 / 聚合 / 图片优化 / 失效。业务规则一律不在这里实现。
 * 前端只跟这一层对话；回源 NAS FastAPI 只发生在缓存未命中或写操作时。
 */

import { Hono } from "hono";
import { cors } from "hono/cors";

type Env = {
  BACKEND_ORIGIN: string;
  DEFAULT_SMAXAGE: string;
  DEFAULT_SWR: string;
  PROXY_PREFIXES: string;
  REVALIDATE_SECRET?: string;
  /** tag → url[] 索引（免费计划没有原生 cache-tag，用 KV 自建） */
  CACHE_TAGS?: KVNamespace;
};

const app = new Hono<{ Bindings: Env }>();

app.use(
  "*",
  cors({
    origin: [
      "https://neutronstar.fun",
      "https://www.neutronstar.fun",
      "https://neutronstar-web.pages.dev",
      "https://bff.neutronstar.fun",
      "http://localhost:4321",
      "http://localhost:5173",
      "http://localhost:3000",
    ],
    allowMethods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allowHeaders: ["Content-Type", "Authorization", "x-cache-tags"],
  })
);

app.get("/health", (c) => c.json({ status: "ok", layer: "bff" }));

/* ------------------------------------------------------------------ *
 * 1. 读接口代理：Cache API 命中即返，未命中回源并写入缓存
 * ------------------------------------------------------------------ */

const CACHEABLE_STATUS = new Set([200, 203, 204, 300, 301, 404, 410]);

/** 由路径推导缓存标签，后端也可用 x-cache-tags 覆盖 */
function tagsForPath(path: string): string[] {
  const tags = new Set<string>();
  if (path.startsWith("/api/chatters")) tags.add("moments");
  if (path.startsWith("/api/messages")) tags.add("messages");
  if (path.startsWith("/api/albums")) tags.add("albums");
  if (path.startsWith("/api/posts")) tags.add("posts");
  if (path.startsWith("/api/categories") || path.startsWith("/api/tags")) tags.add("posts");
  if (path.startsWith("/bff/home")) {
    tags.add("posts");
    tags.add("moments");
    tags.add("albums");
  }
  tags.add("all");
  return [...tags];
}

async function indexTags(env: Env, url: string, tags: string[]) {
  if (!env.CACHE_TAGS) return;
  await Promise.all(
    tags.map(async (tag) => {
      const raw = (await env.CACHE_TAGS!.get(tag)) || "[]";
      let urls: string[] = [];
      try {
        urls = JSON.parse(raw);
      } catch {
        urls = [];
      }
      if (!urls.includes(url)) {
        urls.push(url);
        // 单 tag 下的 URL 数量设上限，避免无限膨胀
        if (urls.length > 500) urls = urls.slice(-500);
        await env.CACHE_TAGS!.put(tag, JSON.stringify(urls));
      }
    })
  );
}

app.get("/api/*", async (c) => {
  const url = new URL(c.req.url);
  const upstream = `${c.env.BACKEND_ORIGIN}${url.pathname}${url.search}`;
  return proxyWithCache(c, upstream, tagsForPath(url.pathname));
});

async function proxyWithCache(c: any, upstream: string, tags: string[]) {
  const cache = caches.default;
  const cacheKey = new Request(c.req.url, { method: "GET" });

  const hit = await cache.match(cacheKey);
  if (hit) {
    const res = new Response(hit.body, hit);
    res.headers.set("X-Cache", "HIT");
    res.headers.set("X-Cache-Tags", tags.join(","));
    return res;
  }

  const upstreamRes = await fetch(upstream, {
    method: "GET",
    headers: forwardHeaders(c.req.raw.headers),
    cf: { cacheTtlByStatus: { "200-299": 60, "404-499": 10, "500-599": 0 } },
  } as RequestInit);

  const res = new Response(upstreamRes.body, upstreamRes);
  res.headers.set("X-Cache", "MISS");
  res.headers.set("X-Upstream", upstream);

  if (!res.headers.has("Cache-Control")) {
    res.headers.set(
      "Cache-Control",
      `public, s-maxage=${c.env.DEFAULT_SMAXAGE}, stale-while-revalidate=${c.env.DEFAULT_SWR}`
    );
  }

  if (CACHEABLE_STATUS.has(upstreamRes.status) && res.headers.get("Cache-Control")?.includes("s-maxage")) {
    const toCache = res.clone();
    toCache.headers.set("X-Cache-Tags", tags.join(","));
    c.executionCtx?.waitUntil(cache.put(cacheKey, toCache));
    c.executionCtx?.waitUntil(indexTags(c.env, c.req.url, tags));
  }
  return res;
}

function forwardHeaders(src: Headers): Headers {
  const h = new Headers();
  const pass = ["authorization", "content-type", "accept", "accept-encoding", "user-agent", "cookie"];
  for (const k of pass) {
    const v = src.get(k);
    if (v) h.set(k, v);
  }
  return h;
}

/* ------------------------------------------------------------------ *
 * 2. 聚合接口：把首屏需要的多个请求压成 1 个 RTT
 * ------------------------------------------------------------------ */

app.get("/bff/home", async (c) => {
  const origin = c.env.BACKEND_ORIGIN;
  const qs = c.req.query();
  const size = qs.size ?? "5";

  const [posts, chatters, albums, config] = await Promise.all([
    fetchJSON(`${origin}/api/posts?status=published&page=1&size=${size}`),
    fetchJSON(`${origin}/api/chatters?status=published&page=1&size=${size}`),
    fetchJSON(`${origin}/api/albums`),
    fetchJSON(`${origin}/api/site-config`),
  ]);

  const body = JSON.stringify({ posts, chatters, albums, config, generatedAt: Date.now() });
  return new Response(body, {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "public, s-maxage=120, stale-while-revalidate=600",
      "x-cache-tags": "posts,moments,albums,all",
    },
  });
});

async function fetchJSON(url: string) {
  try {
    const res = await fetch(url, { cf: { cacheTtlByStatus: { "200-299": 60, "500-599": 0 } } } as RequestInit);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------------ *
 * 3. 图片：格式协商 + 宽度裁剪（CF Image Resizing），边缘长缓存
 * ------------------------------------------------------------------ */

app.get("/img/*", async (c) => {
  const url = new URL(c.req.url);
  const path = url.pathname.replace(/^\/img\//, "");
  const width = Number(url.searchParams.get("w") || 0);
  const accept = c.req.header("accept") || "";
  const format = accept.includes("image/avif") ? "avif" : accept.includes("image/webp") ? "webp" : undefined;

  const res = await fetch(`${c.env.BACKEND_ORIGIN}/${path}`, {
    cf: {
      image: { ...(width ? { width } : {}), ...(format ? { format } : {}), fit: "scale-down", quality: 82 },
      cacheEverything: true,
      cacheTtl: 86400,
    } as any,
  });

  const out = new Response(res.body, res);
  out.headers.set("Cache-Control", "public, max-age=86400, s-maxage=86400, immutable");
  out.headers.set("Vary", "Accept");
  return out;
});

/* ------------------------------------------------------------------ *
 * 4. 写操作与其余路径：直接透传，不缓存
 * ------------------------------------------------------------------ */

app.on(["POST", "PUT", "PATCH", "DELETE"], "/api/*", async (c) => {
  const url = new URL(c.req.url);
  const upstream = `${c.env.BACKEND_ORIGIN}${url.pathname}${url.search}`;
  const body = ["GET", "HEAD"].includes(c.req.method) ? undefined : await c.req.arrayBuffer();
  const res = await fetch(upstream, {
    method: c.req.method,
    headers: forwardHeaders(c.req.raw.headers),
    body,
  });
  return new Response(res.body, res);
});

/* ------------------------------------------------------------------ *
 * 5. 失效：后台发布 → HMAC webhook → 按 tag/URL 清边缘缓存
 * ------------------------------------------------------------------ */

app.post("/internal/revalidate", async (c) => {
  const secret = c.env.REVALIDATE_SECRET;
  if (!secret) return c.json({ error: "revalidate not configured" }, 500);

  const raw = await c.req.text();
  const sig = c.req.header("x-signature") || "";
  if (!(await verifyHmac(secret, raw, sig))) {
    return c.json({ error: "invalid signature" }, 401);
  }

  const payload = JSON.parse(raw) as { tags?: string[]; urls?: string[] };
  const targets = new Set<string>(payload.urls || []);

  for (const tag of payload.tags || []) {
    const urls = await readTagUrls(c.env, tag);
    urls.forEach((u) => targets.add(u));
  }

  const cache = caches.default;
  let purged = 0;
  for (const u of targets) {
    if (await cache.delete(new Request(u, { method: "GET" }))) purged += 1;
  }

  return c.json({ purged, tags: payload.tags || [], urls: [...targets].length });
});

async function readTagUrls(env: Env, tag: string): Promise<string[]> {
  if (!env.CACHE_TAGS) return [];
  try {
    return JSON.parse((await env.CACHE_TAGS.get(tag)) || "[]");
  } catch {
    return [];
  }
}

async function verifyHmac(secret: string, body: string, signature: string): Promise<boolean> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
  const expected = [...new Uint8Array(mac)].map((b) => b.toString(16).padStart(2, "0")).join("");
  return timingSafeEqual(expected, signature);
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export default app;
