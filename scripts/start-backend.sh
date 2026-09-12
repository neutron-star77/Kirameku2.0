#!/bin/sh
export DOCKER_HOST=unix:///var/run/docker.sock
DOCKER=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker

$DOCKER run -d --name kirameku-backend --restart unless-stopped \
  -p 8100:8000 \
  -v kirameku_uploads:/app/uploads \
  -v /share/CACHEDEV1_DATA/Container/kirameku/backend/admin/dist:/app/admin/dist:ro \
  -e DATABASE_URL="postgresql://postgres:Q9z4lN6pHcobiSusXkMU28ZB@10.0.3.2:5432/kirameku" \
  -e SECRET_KEY="WdPtzeiXq2SCIsbwF7h4rUgGYKnOTmp5okaJVuDQHZN3cl0f" \
  -e CORS_ORIGINS="https://neutronstar.fun,https://www.neutronstar.fun,http://localhost:3000,http://localhost:4321" \
  -e FRONTEND_ORIGIN="https://neutronstar.fun" \
  -e BFF_ORIGIN="https://bff.neutronstar.fun" \
  kirameku-backend:latest

echo "=== Container started ==="
sleep 3
$DOCKER ps --filter name=kirameku-backend --format "{{.Names}} {{.Status}}"
echo "=== Logs ==="
$DOCKER logs kirameku-backend --tail 15
