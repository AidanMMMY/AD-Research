#!/bin/sh
# ============================================================
# AD-Research backend/celery entrypoint
#
# Responsibilities:
#   1. If /var/run/docker.sock is mounted, dynamically join the host's
#      docker group so the app user can read it.
#   2. Ensure runtime directories are writable by the app user.
#   3. For the default uvicorn CMD: rsync frontend dist + run alembic upgrade.
#   4. Drop privileges and exec the provided command as `app`.
# ============================================================

set -e

# Dynamic docker group membership for the mounted socket.
if [ -S /var/run/docker.sock ]; then
    DOCKER_GID=$(stat -c '%g' /var/run/docker.sock 2>/dev/null || true)
    if [ -n "$DOCKER_GID" ]; then
        if ! getent group "$DOCKER_GID" > /dev/null 2>&1; then
            groupadd -g "$DOCKER_GID" hostdocker > /dev/null 2>&1 || true
        fi
        usermod -aG "$DOCKER_GID" app > /dev/null 2>&1 || true
    fi
fi

# Make sure runtime directories are writable.
mkdir -p /app/web/dist /app/reports "${CNINFO_PDF_DIR:-/data/alloy-research/cninfo_pdfs}"
chown -R app:app /app/web/dist /app/web/dist-image /app/reports "${CNINFO_PDF_DIR:-/data/alloy-research/cninfo_pdfs}" 2>/dev/null || true
chmod -R u+w "${CNINFO_PDF_DIR:-/data/alloy-research/cninfo_pdfs}" 2>/dev/null || true

# Default CMD is uvicorn: prepare frontend dist and run migrations.
if [ "$1" = "uvicorn" ]; then
    rsync -a --delete /app/web/dist-image/ /app/web/dist/
    alembic upgrade head
fi

exec gosu app "$@"
