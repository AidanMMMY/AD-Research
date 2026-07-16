# Multi-stage build for frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Python backend
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

# Allow overriding PyPI mirror at build time. Defaults keep the existing
# domestic mirror for Colima/China networks.
ARG PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
ARG POETRY_REPOSITORIES_PYPI_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
ENV POETRY_REPOSITORIES_PYPI_URL=${POETRY_REPOSITORIES_PYPI_URL}

# Install system dependencies
# - gosu: used by entrypoint to drop to non-root while preserving group
#   memberships needed for the docker socket.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    gosu \
    postgresql-client \
    rsync \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user. The entrypoint will dynamically add it to the
# host's docker group when /var/run/docker.sock is mounted.
RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

# Install Python dependencies
COPY pyproject.toml poetry.lock ./
RUN pip install poetry -i ${PIP_INDEX_URL} && \
    poetry config virtualenvs.create false && \
    poetry config repositories.pypi ${POETRY_REPOSITORIES_PYPI_URL} && \
    poetry install --without dev --no-root

# Copy backend code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/docker-entrypoint.sh ./scripts/docker-entrypoint.sh
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
