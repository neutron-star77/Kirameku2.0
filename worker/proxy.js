// Kirameku API 代理 Worker
// 将前端 /api、/uploads 请求转发到 NAS 上的 FastAPI 后端
// 部署：wrangler deploy 或 CF Dashboard Workers

// NAS 后端公网地址（Tunnel 域名 或 NAS 公网 IP:端口）
const NAS_BACKEND = "https://kirameku-api.neutronstar.fun";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;

    // 仅代理 API 与上传资源
    if (path.startsWith("/api/") || path.startsWith("/uploads/") || path === "/api") {
      const target = NAS_BACKEND + path + url.search;
      const headers = new Headers(request.headers);
      headers.set("Host", new URL(NAS_BACKEND).host);

      const resp = await fetch(target, {
        method: request.method,
        headers,
        body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
        redirect: "manual",
      });

      const newResp = new Response(resp.body, resp);
      // 统一 CORS，允许前端域名访问
      newResp.headers.set("Access-Control-Allow-Origin", "*");
      newResp.headers.set("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS");
      newResp.headers.set("Access-Control-Allow-Headers", "Content-Type,Authorization");
      return newResp;
    }

    // OPTIONS 预检
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type,Authorization",
        },
      });
    }

    // 其余路径直接回源（由 Pages 处理）
    return fetch(request);
  },
};
