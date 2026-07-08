# Agent worker image for AD-Research data collection tasks.
# Path 2 of the AD-Research plan: host-agnostic worker runtime that
# shares /root/.playwright-profile/ via a bind mount.
#
# Build:   docker build -t ad-research/agent:latest -f Dockerfile.agent .
# Run:     docker run --rm -it \
#              -v /root/.playwright-profile:/profile \
#              -v /root/ad-research/agents/workers:/workspace/workers:ro \
#              -v /data/ad-research:/data \
#              ad-research/agent:latest \
#              python /workspace/workers/cls.py --hours 24 --output /data/cls/today.json

FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Asia/Shanghai

# System deps:
#   - curl/wget/git/ca-certificates: fetching + repo ops
#   - tini: clean signal handling for long-running scrapers
#   - tzdata: deterministic timestamps
#   - Chromium runtime deps (minimal set used by Playwright)
#   - fonts-liberation + fonts-noto-cjk: page rendering w/o tofu
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl wget git ca-certificates tini tzdata \
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
        libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
        libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
        libatspi2.0-0 libxshmfence1 fonts-liberation fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Install Python deps first for better layer caching.
COPY requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r /workspace/requirements.txt

# Pre-install Playwright Chromium binary + system deps.
RUN playwright install --with-deps chromium

# Default mount points:
#   /workspace -> code, worker scripts (bind-mounted read-only by launcher)
#   /profile   -> shared Playwright browser profile (named volume)
#   /data      -> agent output directory (bind-mounted by launcher)
VOLUME ["/workspace", "/profile", "/data"]

# tini -> clean signal forwarding for long-running scrapes.
ENTRYPOINT ["/usr/bin/tini", "--"]
# Empty default CMD; launcher always passes `python <worker> ...`.
CMD ["bash"]
