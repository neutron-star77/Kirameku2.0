#!/bin/sh
export DOCKER_HOST=unix:///var/run/docker.sock
DOCKER=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker
echo "=== PG env ==="
$DOCKER inspect kirameku-pg --format '{{json .Config.Env}}'
echo ""
echo "=== Networks ==="
$DOCKER network ls
echo ""
echo "=== PG inspect network ==="
$DOCKER inspect kirameku-pg --format '{{json .NetworkSettings.Networks}}'
echo ""
echo "=== All containers ==="
$DOCKER ps -a --format "{{.Names}} {{.Status}} {{.Ports}}"
