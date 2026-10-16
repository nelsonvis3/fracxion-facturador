#!/usr/bin/env bash
# Run only on the approved VM. Configuration comes from a root-readable EnvironmentFile.
set -euo pipefail
umask 077
: "${RESTIC_REPOSITORY:?Configure the approved external repository}"
: "${RESTIC_PASSWORD_FILE:?Store the repository password outside Git}"
: "${FRACXION_ROOT:?Set the absolute checkout directory}"
case "$RESTIC_REPOSITORY" in s3:https://*|sftp:*) ;; *) echo 'An approved off-host repository is required.' >&2; exit 1;; esac
cd "$FRACXION_ROOT"
for file in .env release-commit.txt; do test -s "$file" || { echo "Missing required file: $file" >&2; exit 1; }; done
exec 9>/var/lib/fracxion/backup.lock
flock -n 9 || exit 1
compose=(docker compose --project-name fracxion-demo -f compose.yaml -f compose.oracle.yaml)
# --stdin-from-command refuses to publish a snapshot if pg_dump fails.
restic backup --host fracxion-demo --tag fracxion-db --stdin-filename fracxion-postgres.dump \
  --stdin-from-command -- "${compose[@]}" exec -T database pg_dump -U facturador -d facturador --format=custom --no-owner --no-acl
restic dump latest --host fracxion-demo --tag fracxion-db /fracxion-postgres.dump | \
  "${compose[@]}" exec -T database pg_restore --list >/dev/null
restic backup --host fracxion-demo --tag fracxion-config -- .env release-commit.txt compose.yaml compose.oracle.yaml deploy/Caddyfile
restic backup --host fracxion-demo --tag fracxion-tls --stdin-filename caddy-data.tar \
  --stdin-from-command -- "${compose[@]}" exec -T proxy tar -C /data -cf - caddy
# No forget/prune here: retention must be separately approved and reviewed.
restic check
