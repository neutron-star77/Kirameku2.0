#!/bin/sh
# 重启 cloudflared 隧道
echo "Killing old cloudflared..."
kill $(ps aux | grep '[c]loudflared' | awk '{print $1}') 2>/dev/null
sleep 2
echo "Starting cloudflared..."
cd /share/CACHEDEV1_DATA/kirameku/bin
./cloudflared --no-autoupdate tunnel --protocol http2 run --token eyJhIjoiZDRhZGQ4YWQ1NDk1MzZhNzdhNWI5ZmNmNmQ1YmU3MzMiLCJ0IjoiNzEwYmZhZTgtYWU0Zi00ZmJmLTg5MDMtMTZlZGI4NTRjNmU2IiwicyI6InRrRjNycjNQMnNPOUVYZ0kzM1V5WTVxWFZKN2N6dnA3QzNnNmVxbUU5dzRHTHU4cC9BSnZaZVhXcExTS3VUbVRody9UTkdXWUhvQmFna3NCVGRrcXl3PT0ifQ== > /tmp/cloudflared.log 2>&1 &
echo "Started PID: $!"
sleep 5
echo "--- cloudflared log ---"
tail -15 /tmp/cloudflared.log
echo "--- process ---"
ps aux | grep '[c]loudflared'
