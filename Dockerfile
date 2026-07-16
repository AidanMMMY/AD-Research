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

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    rsync \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (use domestic PyPI mirror for Colima/China networks)
COPY pyproject.toml poetry.lock ./
RUN pip install poetry -i https://pypi.tuna.tsinghua.edu.cn/simple && \
    poetry config virtualenvs.create false && \
    poetry config repositories.pypi https://pypi.tuna.tsinghua.edu.cn/simple && \
    poetry install --without dev --no-root

# Copy backend code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/ ./scripts/

# Copy frontend build output to a staging directory; it is copied into the
# shared volume at runtime so Nginx always serves the latest build.
COPY --from=frontend-build /app/web/dist /app/web/dist-image
RUN mkdir -p web/dist

# Create reports directory
RUN mkdir -p reports

EXPOSE 8000

CMD ["poetry", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
