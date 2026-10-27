# syntax=docker/dockerfile:1

# 1. Build the frontend.
FROM node:24-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# 2. Deno, which current yt-dlp needs to solve YouTube's JavaScript challenges.
FROM denoland/deno:bin-2.9.6 AS deno

# 3. The app: Python, ffmpeg, Deno, yt-dlp, and the built frontend.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    DATA_DIR=/data \
    DOWNLOADS_DIR=/downloads \
    STATIC_DIR=/app/static \
    RESTART_ON_UPDATE=true

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg tini ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=deno /deno /usr/local/bin/deno

# A non-root user owns the venv so "Update yt-dlp" can pip install into it.
RUN useradd --uid 1000 --create-home grab \
 && python -m venv /opt/venv \
 && mkdir -p /app /data /downloads \
 && chown -R grab:grab /opt/venv /app /data /downloads

USER grab
WORKDIR /app
COPY --chown=grab:grab backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY --chown=grab:grab backend/*.py ./
COPY --chown=grab:grab --from=web /web/dist ./static
COPY --chown=grab:grab --chmod=755 docker/entrypoint.sh /entrypoint.sh

EXPOSE 8000
VOLUME ["/data", "/downloads"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"
ENTRYPOINT ["tini", "--", "/entrypoint.sh"]
