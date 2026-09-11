/**
 * RealtimeRoom —— SSE 扇出用的 Durable Object（方案 A：DO 频道扇出）。
 *
 * 架构：一个频道 = 一个 DO 实例（BFF 用 `idFromName(channel)` 取 stub），
 * 实例内存里维护该频道所有在线浏览器的 SSE 写入端，后端发布内容时
 * BFF 收到 HMAC webhook → 清缓存 → `POST /broadcast` 把事件扇出给每个连接。
 *
 * 为什么用 SSE 而不是 WebSocket：单向推送足够、浏览器原生 `EventSource`
 * 自带断线重连、服务端就是普通流式 Response，Workers 里最省事。
 *
 * 边界（不做的事）：不存业务数据、不做鉴权（频道内容本来就是公开数据）、
 * 不保证 at-least-once 投递 —— DO 被回收时连接断开，前端 EventSource 会重连，
 * 且页面本身有 SWR 兜底（下次聚焦/刷新照样拿到最新数据）。
 *
 * 二次开发提示：
 *  - 新增频道：在 `worker-bff/src/index.ts` 的 `TAG_CHANNELS` 里登记 tag→channel 即可，
 *    本文件不需要改动（频道名对 DO 只是一个隔离键）。
 *  - 心跳间隔：`HEARTBEAT_MS`。太长会被中间链路判空闲断开，太短浪费请求。
 *  - 免费计划必须用 SQLite 存储后端 → wrangler.toml 里用 `new_sqlite_classes`。
 */

const encoder = new TextEncoder();

/** 心跳间隔：CF/浏览器链路对空闲连接有 100s 级超时，25s 留足余量 */
const HEARTBEAT_MS = 25_000;

/**
 * 单条连接写入超时。
 *
 * ⚠️ 这是本模块最重要的一行防御：Durable Object 单实例串行处理请求，
 * 只要有一个客户端"连上了但不再读"（标签页被挂起 / 代理缓冲满了），
 * `writer.write()` 就会永远不 resolve —— 整个 DO 会被这一个 await 卡死，
 * 后续 `/broadcast`、`/subscribe` 全部排队 → BFF 的 revalidate webhook 也超时。
 * 因此每次写都必须带超时，超时就判定该客户端已死并摘掉。
 */
const WRITE_TIMEOUT_MS = 2_000;

export interface RealtimeEvent {
  /** 频道名（posts / moments / albums / friends / messages / nav / all） */
  channel: string;
  /** 事件类型，前端按需扩展（当前统一发 "change"，语义靠 action+channel） */
  type: string;
  action?: "created" | "updated" | "deleted" | "published" | string;
  id?: string | number | null;
  at?: number;
}

/** 带超时的写入；返回 false 表示这条连接已经废了（应摘除） */
async function writeWithTimeout(
  writer: WritableStreamDefaultWriter<Uint8Array>,
  chunk: Uint8Array
): Promise<boolean> {
  let timer: ReturnType<typeof setTimeout> | null = null;
  try {
    await Promise.race([
      writer.write(chunk),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error("sse write timeout")), WRITE_TIMEOUT_MS);
      }),
    ]);
    return true;
  } catch {
    return false;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export class RealtimeRoom implements DurableObject {
  private readonly clients = new Map<string, WritableStreamDefaultWriter<Uint8Array>>();
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;

  constructor(private readonly state: DurableObjectState, _env: unknown) {}

  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);
    switch (url.pathname) {
      case "/subscribe":
        return this.subscribe(url.searchParams.get("channel") || "all");
      case "/broadcast": {
        const event = (await req.json()) as RealtimeEvent;
        const delivered = await this.broadcast(event);
        return Response.json({ delivered, clients: this.clients.size });
      }
      case "/status":
        return Response.json({ clients: this.clients.size, channel: url.searchParams.get("channel") });
      default:
        return new Response("not found", { status: 404 });
    }
  }

  /** 建立一条 SSE 长连接：把写入端留在内存里，返回可读流给客户端 */
  private subscribe(channel: string): Response {
    const id = crypto.randomUUID();
    const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>();
    const writer = writable.getWriter();
    this.clients.set(id, writer);

    // retry: 浏览器断线后的重连间隔；注释帧让连接立刻"有数据"，避免代理缓冲
    void writeWithTimeout(writer, encoder.encode(`retry: 3000\n: connected channel=${channel}\n\n`)).then(
      (ok) => {
        if (!ok) this.clients.delete(id);
      }
    );
    this.startHeartbeat();

    return new Response(readable, {
      headers: {
        "content-type": "text/event-stream; charset=utf-8",
        "cache-control": "no-cache, no-transform",
        connection: "keep-alive",
        "x-accel-buffering": "no",
      },
    });
  }

  /** 扇出事件：并发写 + 逐条超时，任何一条卡住都不拖累其它连接与本次请求 */
  private async broadcast(event: RealtimeEvent): Promise<number> {
    const frame = encoder.encode(
      `event: change\ndata: ${JSON.stringify({ ...event, at: event.at ?? Date.now() })}\n\n`
    );
    const entries = [...this.clients.entries()];
    const results = await Promise.all(
      entries.map(async ([id, writer]) => ({ id, ok: await writeWithTimeout(writer, frame) }))
    );
    for (const { id, ok } of results) {
      if (!ok) this.clients.delete(id);
    }
    return this.clients.size;
  }

  private startHeartbeat() {
    if (this.heartbeatTimer) return;
    this.heartbeatTimer = setInterval(() => void this.heartbeat(), HEARTBEAT_MS);
  }

  /** 空频道自动停表，避免没人看的时候还在烧 CPU 时间 */
  private async heartbeat() {
    if (this.clients.size === 0) {
      if (this.heartbeatTimer) {
        clearInterval(this.heartbeatTimer);
        this.heartbeatTimer = null;
      }
      return;
    }
    const ping = encoder.encode(`: ping ${Date.now()}\n\n`);
    const entries = [...this.clients.entries()];
    const results = await Promise.all(
      entries.map(async ([id, writer]) => ({ id, ok: await writeWithTimeout(writer, ping) }))
    );
    for (const { id, ok } of results) {
      if (!ok) this.clients.delete(id);
    }
  }
}
