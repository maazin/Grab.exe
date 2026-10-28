# Grab

A private web app that downloads a YouTube video as MP4, or its audio as MP3/M4A, from a pasted link. One user, reachable from phone and laptop through a Cloudflare Tunnel, locked behind Cloudflare Access.

```
backend/    FastAPI + SQLite + yt-dlp worker (Python 3.12)
frontend/   React + TypeScript + Vite + Tailwind
compose.yaml  app + cloudflared
```

One container runs the API, the single download worker, the cleanup loop, and the built frontend. A second container runs `cloudflared`.

## Run it locally

Backend (port 8765, dev mode skips the Access check):

```bash
cd backend && uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt
```

```bash
cd backend && DEV_MODE=true DATA_DIR=../.local/data DOWNLOADS_DIR=../.local/downloads .venv/bin/uvicorn main:create_app --factory --port 8765 --reload
```

Frontend with hot reload (proxies `/api` to 8765), then open http://localhost:5173:

```bash
cd frontend && npm install && npm run dev
```

Needs `ffmpeg` on the PATH. Deno is optional locally but required for reliable YouTube downloads (`brew install deno`).

## Tests

```bash
cd backend && .venv/bin/ruff check . && .venv/bin/pytest
```

yt-dlp is faked in every test except one live test against a 19-second public video, which is skipped by default:

```bash
cd backend && .venv/bin/pytest -m live
```

Frontend checks (the same ones CI runs):

```bash
cd frontend && npx eslint . && npx tsc --noEmit
```

## Deploy on the home machine

Any always-on box with Docker and 20 GB free: an old laptop with sleep disabled, a mini PC, or a Raspberry Pi 5. The image includes ffmpeg, Deno, and yt-dlp.

1. Copy this folder to the machine and create the env file:

   ```bash
   cp .env.example .env
   ```

2. First check, without the tunnel: set `DEV_MODE=true` in `.env`, then:

   ```bash
   docker compose up -d --build
   ```

   Open http://127.0.0.1:8000 on that machine and grab a short video. Then set `DEV_MODE=false` again.

### Run it on this Mac with Tailscale

No domain or Cloudflare needed. A `tailscale` container joins your tailnet as its own device, `grab`, separate from any Tailscale already on the machine. `.env` on the Mac:

```
AUTH_MODE=tailscale
ALLOWED_EMAIL=you@your-tailscale-login
GRAB_PORT=8001
COMPOSE_PROFILES=tailscale
```

Start it, then open the login link the container prints and approve the device (once; its state lives in the `grab-tailscale` volume):

```bash
docker compose up -d --build && docker compose logs tailscale | grep login.tailscale.com
```

- **Laptop:** http://localhost:8001. In Chrome, ⋮ → Cast, save, and share → Install page as app.
- **Phone:** install Tailscale, sign in with the same account, open `https://grab.<tailnet>.ts.net` in Safari, then Share → Add to Home Screen.

The container serves the app to your tailnet only ([docker/tailscale-start.sh](docker/tailscale-start.sh), Funnel off). `tailscale serve` adds the signed-in user to each request, and Grab checks it against `ALLOWED_EMAIL`. Requests with no identity get a 401 unless they come straight to localhost on the Mac.

Tailscale expires device keys after 180 days by default. To avoid signing in again, open the `grab` device in the admin console and choose Disable key expiry.

### Cloudflare Tunnel and Access (go live)

Needs `maazin.site`'s DNS on Cloudflare (still an open question; a separate free domain on Cloudflare works the same way).

1. **Tunnel.** Zero Trust → Networks → Tunnels → Create a tunnel (Cloudflared). Copy the token into `TUNNEL_TOKEN` in `.env`.
2. **Route.** On the tunnel, add a public hostname: `grab.maazin.site` → service `http://app:8000`.
3. **Access application.** Zero Trust → Access → Applications → Add → Self-hosted, domain `grab.maazin.site`, session duration 30 days. Policy: Allow, Include → Emails → your email. Login method: One-time PIN.
4. From the application's Overview, copy the **Application Audience (AUD) tag** into `CF_ACCESS_AUD`, and set `CF_ACCESS_TEAM_DOMAIN` to your team domain (e.g. `maazin.cloudflareaccess.com`). Optionally set `ALLOWED_EMAIL`.
5. Uncomment `COMPOSE_PROFILES=tunnel` in `.env` and restart:

   ```bash
   docker compose up -d
   ```

6. Check from phone data (not home Wi-Fi): open https://grab.maazin.site, sign in with the emailed PIN, and save an MP3 to the Files app.

Every `/api` request must carry Cloudflare's `Cf-Access-Jwt-Assertion` header, which the app checks against your team's public keys and the AUD tag. Anything else gets a 401, including direct requests from the home network.

## How it behaves

- **One download at a time**, 5 seconds apart, oldest first. Jobs interrupted by a restart go back to the queue.
- **Files are deleted 24 hours** after finishing. If free disk drops under 5 GB, the oldest finished files go first. Cleanup runs every 10 minutes.
- **No duplicates.** The same video with the same preset returns the existing file (or the job already in progress).
- **Links.** `/playlist?list=…` opens the playlist picker. A watch link with `&list=` downloads just that video.
- **yt-dlp updates** on every container start. Settings → Update yt-dlp installs the newest version, then the app exits and Docker restarts it with the new version loaded.

## Upkeep

| Problem | Fix |
| --- | --- |
| Downloads fail with "blocked as a possible bot" or format errors | Settings → Update yt-dlp. If that doesn't help, wait a few hours. |
| The URL shows a Cloudflare error page | The home machine is asleep or off. Check `docker compose ps`. |
| `disk_full` errors | Delete files in History, or lower `DISK_FLOOR_GB`. |
| Big videos are slow to save away from home | Use 720p or audio; home upload speed is the limit. |

Logs: `docker compose logs -f app`.

For personal use only. YouTube's terms don't allow downloading outside its own features, which is why Grab stays private behind Access.
