"""Settings, read once from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_VERSION = "1.0.0"

GB = 1024**3


def _bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    data_dir: Path = Path("/data")
    downloads_dir: Path = Path("/downloads")
    static_dir: Path | None = None
    dev_mode: bool = False
    # "cloudflare" checks the Access JWT; "tailscale" trusts `tailscale serve` identity headers.
    auth_mode: str = "cloudflare"
    # Cloudflare Access: team domain like "maazin.cloudflareaccess.com" and the
    # application's audience (AUD) tag.
    cf_team_domain: str = ""
    cf_aud: str = ""
    # Optional extra check on the email inside the Access token.
    allowed_email: str = ""
    expiry_hours: float = 24
    disk_floor_bytes: int = 5 * GB
    min_free_to_start_bytes: int = 1 * GB
    cleanup_interval_s: float = 600
    # Pause between back-to-back jobs, so a playlist doesn't hammer YouTube.
    job_gap_s: float = 5
    restart_on_update: bool = False
    app_version: str = APP_VERSION

    @property
    def db_path(self) -> Path:
        return self.data_dir / "grab.db"

    @classmethod
    def from_env(cls) -> Settings:
        static = os.environ.get("STATIC_DIR")
        return cls(
            data_dir=Path(os.environ.get("DATA_DIR", "/data")),
            downloads_dir=Path(os.environ.get("DOWNLOADS_DIR", "/downloads")),
            static_dir=Path(static) if static else None,
            dev_mode=_bool("DEV_MODE"),
            auth_mode=os.environ.get("AUTH_MODE", "cloudflare").strip().lower(),
            cf_team_domain=os.environ.get("CF_ACCESS_TEAM_DOMAIN", "").strip().removeprefix("https://").rstrip("/"),
            cf_aud=os.environ.get("CF_ACCESS_AUD", "").strip(),
            allowed_email=os.environ.get("ALLOWED_EMAIL", "").strip().lower(),
            expiry_hours=float(os.environ.get("EXPIRY_HOURS", "24")),
            disk_floor_bytes=int(float(os.environ.get("DISK_FLOOR_GB", "5")) * GB),
            cleanup_interval_s=float(os.environ.get("CLEANUP_INTERVAL_S", "600")),
            job_gap_s=float(os.environ.get("JOB_GAP_S", "5")),
            restart_on_update=_bool("RESTART_ON_UPDATE"),
        )
