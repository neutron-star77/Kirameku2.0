#!/bin/sh
# Kirameku2.0 cloudflared 隧道启动脚本（token 托管模式）
cd /share/CACHEDEV1_DATA/kirameku/bin || exit 1
if ! pgrep -f "cloudflared tunnel.*run" >/dev/null 2>&1; then
    setsid ./cloudflared --no-autoupdate tunnel run --token "$(cat /share/CACHEDEV1_DATA/kirameku/bin/tunnel.token)" >> /share/CACHEDEV1_DATA/kirameku/bin/cloudflared.log 2>&1 < /dev/null &
    echo "$(date) started cloudflared" >> /share/CACHEDEV1_DATA/kirameku/bin/cloudflared.log
else
    echo "$(date) cloudflared already running" >> /share/CACHEDEV1_DATA/kirameku/bin/cloudflared.log
fi