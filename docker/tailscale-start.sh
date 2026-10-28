#!/bin/sh
# Joins the tailnet as "grab" and serves the app to it (tailnet only, never Funnel).
# The image's own entrypoint gives up on the first login after 60 seconds and makes a new link each
# time, so this waits for as long as the login takes. The login and serve config persist in the state volume.
set -eu

SOCK=/tmp/tailscaled.sock
ts() { tailscale --socket="$SOCK" "$@"; }

tailscaled --tun=userspace-networking --statedir=/var/lib/tailscale --socket="$SOCK" &
daemon=$!
while [ ! -S "$SOCK" ]; do sleep 1; done

ts up --hostname=grab ${TS_AUTHKEY:+--auth-key="$TS_AUTHKEY"}
ts serve --bg --https=443 http://app:8000
ts serve status

wait "$daemon"
