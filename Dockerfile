# ============================================================
# 多阶段构建（2026-08-17 瘦身改造）
#   1. frontend-build : node 构建前端静态资源
#   2. python-build   : gcc + poetry 把依赖装进独立 venv (/app/.venv)
#   3. runtime        : python:3.11-slim，只拷 venv + 应用代码
# 背景：旧单阶段镜像 2.67GB，gcc/poetry/pip 缓存全留在运行时镜像里，
# 是 2026-08-05 磁盘满全栈停摆事故的元凶之一。运行时阶段不再安装
# gcc / poetry，ENTRYPOINT/CMD/环境变量语义保持不变。
# ============================================================

# ── Stage 1: frontend build ──
FROM node:20-alpine AS frontend-build
WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ── Stage 2: python dependency builder ──
# gcc 只存在于本阶段：编译无 wheel 的 sdist 依赖用，不进运行时镜像。
FROM python:3.11-slim AS python-build
WORKDIR /app

# Allow overriding PyPI mirror at build time. Defaults keep the existing
# domestic mirror for Colima/China networks.
ARG PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
ARG POETRY_REPOSITORIES_PYPI_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
ENV POETRY_REPOSITORIES_PYPI_URL=${POETRY_REPOSITORIES_PYPI_URL}

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# poetry 版本与 CI (.github/workflows/backend-ci.yml) 对齐，保证 lock 解析一致。
# virtualenvs.in-project：依赖装进 /app/.venv，runtime 阶段整目录拷贝即可。
# venv 内 shebang/路径硬编码为 /app/.venv，两阶段 WORKDIR 必须一致。
RUN pip install --no-cache-dir "poetry==1.8.4" -i ${PIP_INDEX_URL}
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.in-project true && \
    poetry config repositories.pypi ${POETRY_REPOSITORIES_PYPI_URL} && \
    poetry install --without dev --no-root --no-interaction --no-ansi

# ── Stage 3: runtime ──
FROM python:3.11-slim

WORKDIR /app

# Build-time metadata: GIT_SHA is injected by CI/update.sh so /health can
# report the exact commit the image was built from. Falls back to "unknown"
# when not provided (legacy/local builds).
ARG GIT_SHA=""
ENV GIT_SHA=${GIT_SHA}

# Avoid writing .pyc files and ensure stdout/stderr are not buffered.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 保留镜像源 ENV（与旧镜像语义一致），运行时 pip 已不存在，仅供排障参考。
ARG PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
ARG POETRY_REPOSITORIES_PYPI_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
ENV POETRY_REPOSITORIES_PYPI_URL=${POETRY_REPOSITORIES_PYPI_URL}

# Runtime system dependencies（不再装 gcc —— 无编译需求）:
# - gosu: used by entrypoint to drop to non-root while preserving group
#   memberships needed for the docker socket.
# - postgresql-client / rsync: entrypoint 与运维脚本沿用（语义不变）。
RUN apt-get update && apt-get install -y --no-install-recommends \
    gosu \
    postgresql-client \
    rsync \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user. The entrypoint will dynamically add it to the
# host's docker group when /var/run/docker.sock is mounted.
RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

# Python dependencies: copy the pre-built venv from the builder stage and
# put it on PATH so `python` / `uvicorn` / `celery` / `alembic` all resolve
# to the venv (compose healthcheck 与 update.sh 直接调用这些命令)。
COPY --from=python-build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:${PATH}"

# Copy backend code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/docker-entrypoint.sh ./scripts/docker-entrypoint.sh
# seed_users.py is invoked by deploy.sh inside the container to create the
# initial admin — without this COPY a fresh production install failed after
# the DB migration (deploy audit 2026-08-06).
COPY scripts/seed_users.py ./scripts/seed_users.py
RUN chmod +x /app/scripts/docker-entrypoint.sh

# Copy frontend build output to a staging directory; it is copied into the
# shared volume at runtime so Nginx always serves the latest build.
COPY --from=frontend-build /app/web/dist /app/web/dist-image
RUN mkdir -p web/dist && chown -R app:app /app/web/dist /app/web/dist-image

# Create reports directory
RUN mkdir -p reports && chown -R app:app /app/reports

EXPOSE 8000

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
