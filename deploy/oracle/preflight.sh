#!/usr/bin/env bash
# Read-only preflight on the approved Ubuntu ARM64 VM. Never prints .env or config output.
set -euo pipefail
cd "${FRACXION_ROOT:?Set the absolute checkout directory}"
test "$(uname -m)" = aarch64 || { echo 'Expected aarch64 VM.' >&2; exit 1; }
test -z "$(git status --porcelain)" || { echo 'Checkout has uncommitted changes.' >&2; exit 1; }
test -s .env || { echo 'Missing private .env.' >&2; exit 1; }
test "$(stat -c '%a' .env)" = 600 || { echo '.env must have mode 600.' >&2; exit 1; }
docker version --format '{{.Server.Version}}'
docker compose version
docker buildx version
docker compose --project-name fracxion-demo -f compose.yaml -f compose.oracle.yaml config --quiet
echo 'Existing Docker networks (verify no conflict with 172.29.33.0/24):'
docker network ls --format '{{.Name}}'
free -m
df -h .
timedatectl show -p NTPSynchronized
printf 'Commit candidate: '
git rev-parse HEAD
