#!/bin/sh
# YouTube changes often; start every run on the newest yt-dlp.
echo "Updating yt-dlp..."
pip install -q -U "yt-dlp[default]" || echo "yt-dlp update failed; starting with the installed version"

exec uvicorn main:create_app --factory \
  --host 0.0.0.0 --port 8000 \
  --proxy-headers --forwarded-allow-ips='*' \
  --timeout-graceful-shutdown 5
