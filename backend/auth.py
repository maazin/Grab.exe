"""Checks the Cloudflare Access token on every /api request."""

from __future__ import annotations

import logging

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from config import Settings
from errors import GrabError

log = logging.getLogger("grab.auth")

HEADER = "Cf-Access-Jwt-Assertion"


class AccessVerifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._jwks: jwt.PyJWKClient | None = None
        if settings.cf_team_domain:
            self._jwks = jwt.PyJWKClient(
                f"https://{settings.cf_team_domain}/cdn-cgi/access/certs",
                cache_keys=True,
                lifespan=3600,
            )

    def verify(self, token: str) -> dict:
        """Return the token's claims, or raise GrabError("unauthorized")."""
        if not self._jwks or not self.settings.cf_aud:
            log.error("CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD must be set when DEV_MODE is off")
            raise GrabError("unauthorized", "Grab is missing its Cloudflare Access settings.")
        try:
            key = self._jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=self.settings.cf_aud,
                issuer=f"https://{self.settings.cf_team_domain}",
            )
        except (jwt.PyJWTError, jwt.PyJWKClientError) as exc:
            log.info("Rejected Access token: %s", exc)
            raise GrabError("unauthorized") from exc
        if self.settings.allowed_email and claims.get("email", "").lower() != self.settings.allowed_email:
            raise GrabError("unauthorized")
        return claims


TAILSCALE_LOGIN = "Tailscale-User-Login"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}


def tailscale_allows(settings: Settings, request: Request) -> bool:
    """`tailscale serve` adds the signed-in user's login to tailnet requests (never to Funnel ones).

    With no login header, only direct requests to localhost on this machine get through; the port is
    published on 127.0.0.1 only, so nothing else on the network can reach it.
    """
    login = request.headers.get(TAILSCALE_LOGIN, "").strip().lower()
    if login:
        return not settings.allowed_email or login == settings.allowed_email
    if request.headers.get("x-forwarded-for"):
        return False  # came through a proxy (e.g. Funnel) without a tailnet identity
    host = (request.headers.get("host") or "").rsplit(":", 1)[0].lower()
    return host in LOCAL_HOSTS


def access_middleware(settings: Settings, verifier: AccessVerifier):
    async def middleware(request: Request, call_next):
        if settings.dev_mode or not request.url.path.startswith("/api"):
            return await call_next(request)
        if settings.auth_mode == "tailscale":
            if tailscale_allows(settings, request):
                return await call_next(request)
            return JSONResponse(
                GrabError("unauthorized", "Open Grab from a device signed in to your Tailscale.").body(), status_code=401
            )
        token = request.headers.get(HEADER)
        if not token:
            err = GrabError("unauthorized")
            return JSONResponse(err.body(), status_code=401)
        try:
            await run_in_threadpool(verifier.verify, token)
        except GrabError as err:
            return JSONResponse(err.body(), status_code=401)
        return await call_next(request)

    return middleware
