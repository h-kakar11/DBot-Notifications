"""
Loads bot configuration from environment variables (and a local .env file, if
present). See .env.example for the full list of supported variables.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Config:
    discord_token: str
    announcement_channel_id: int
    poll_minutes: float
    state_path: str
    prime_on_first_run: bool


def load_config() -> Config:
    """Reads and validates required configuration from the environment"""
    token = os.environ.get("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "DISCORD_TOKEN environment variable is required. "
            "Copy .env.example to .env and fill it in."
        )

    channel_id_raw = os.environ.get("ANNOUNCEMENT_CHANNEL_ID", "").strip()
    if not channel_id_raw:
        raise RuntimeError(
            "ANNOUNCEMENT_CHANNEL_ID environment variable is required. "
            "Copy .env.example to .env and fill it in."
        )
    try:
        announcement_channel_id = int(channel_id_raw)
    except ValueError as e:
        raise RuntimeError(
            f"ANNOUNCEMENT_CHANNEL_ID must be an integer Discord channel id, got {channel_id_raw!r}"
        ) from e

    try:
        poll_minutes = float(os.environ.get("POLL_MINUTES", "5"))
    except ValueError as e:
        raise RuntimeError("POLL_MINUTES must be a number") from e
    if poll_minutes <= 0:
        raise RuntimeError("POLL_MINUTES must be greater than 0")

    state_path = os.environ.get("STATE_PATH", "data/seen_entries.json").strip()
    prime_on_first_run = _get_bool("PRIME_ON_FIRST_RUN", True)

    return Config(
        discord_token=token,
        announcement_channel_id=announcement_channel_id,
        poll_minutes=poll_minutes,
        state_path=state_path,
        prime_on_first_run=prime_on_first_run,
    )
