#!/bin/sh
export DOCKER_HOST=unix:///var/run/docker.sock
DOCKER=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker
cd /share/CACHEDEV1_DATA/Container/kirameku/backend
echo "=== Building image ==="
$DOCKER build -t kirameku-backend:latest . 2>&1 | tail -8
echo "=== Stopping container ==="
$DOCKER stop kirameku-backend
echo "=== Removing container ==="
$DOCKER rm kirameku-backend
echo "=== Starting new container ==="
$DOCKER run -d --name kirameku-backend --restart unless-stopped \
  -p 8100:8000 \
  -v kirameku_uploads:/app/uploads \
  -v /share/CACHEDEV1_DATA/Container/kirameku/backend/admin/dist:/app/admin/dist:ro \
  --env-file /share/CACHEDEV1_DATA/Container/kirameku/backend/.env \
  kirameku-backend:latest
echo "=== Done ==="
$DOCKER ps --filter name=kirameku-backend --format "{{.Names}} {{.Status}}"
