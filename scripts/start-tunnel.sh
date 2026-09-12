#!/bin/sh
# cloudflared 开机自启（幂等）：已在运行则跳过，否则用 http2 协议拉起。
# 由 QNAP autorun.sh 在开机后调用；也可手动 sh 执行。
# 注意：QUIC/UDP 在本机 NAS 持续超时，必须 --protocol http2。

BIN=/share/CACHEDEV1_DATA/kirameku/bin/cloudflared
LOG=/tmp/cloudflared.log
TOKEN="eyJhIjoiZDRhZGQ4YWQ1NDk1MzZhNzdhNWI5ZmNmNmQ1YmU3MzMiLCJ0IjoiNzEwYmZhZTgtYWU0Zi00ZmJmLTg5MDMtMTZlZGI4NTRjNmU2IiwicyI6InRrRjNycjNQMnNPOUVYZ0kzM1V5WTVxWFZKN2N6dnA3QzNnNmVxbUU5dzRHTHU4cC9BSnZaZVhXcExTS3VUbVRody9UTkdXWUhvQmFna3NCVGRrcXl3PT0ifQ=="

# 已存在 cloudflared 进程则直接退出（幂等，避免开机+手动重复执行起多个）。
# 注意：本机 QNAP 无 pgrep/pidof 匹配全名不可靠，统一用 ps | grep（[c] 技巧排除 grep 自身）。
if ps w 2>/dev/null | grep -q '[c]loudflared'; then
    echo "[start-tunnel] cloudflared already running, skip."
    exit 0
fi

# 等网络就绪（最多 60 秒）：能解析公网再启动
i=0
while [ $i -lt 30 ]; do
    if ping -c1 -W2 1.1.1.1 >/dev/null 2>&1; then break; fi
    i=$((i+1))
    sleep 2
done

echo "[start-tunnel] starting cloudflared at $(date)" >> "$LOG"
# 本机无 nohup，用 setsid 让进程在新会话运行，脱离 SSH 控制终端不被 SIGHUP 带走
cd "$(dirname "$BIN")"
setsid "$BIN" --no-autoupdate tunnel --protocol http2 run --token "$TOKEN" >> "$LOG" 2>&1 < /dev/null &
echo "[start-tunnel] started PID $!"
