import os
import json
import logging
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import aiofiles  # type: ignore[import]
import discord  # type: ignore[import]

from .embeds import JIKAN_BASE_URL, jikan_get, english_title, jikan_image

# maps a MAL "season" string to the (approximate) month it starts in
SEASON_START_MONTH = {"winter": 1, "spring": 4, "summer": 7, "fall": 10}

_WEEKDAYS = [
    "Mondays",
    "Tuesdays",
    "Wednesdays",
    "Thursdays",
    "Fridays",
    "Saturdays",
    "Sundays",
]


async def search_anime(
    query: str, limit: int = 5, logger: Optional[logging.Logger] = None
) -> List[Dict[str, Any]]:
    """Searches Jikan for anime matching `query`, returns up to `limit` results"""
    url = f"{JIKAN_BASE_URL}/anime?q={urllib.parse.quote(query)}&limit={limit}"
    results = await jikan_get(url, logger=logger)
    return list(results) if isinstance(results, list) else []


async def fetch_full(mal_id: int, logger: Optional[logging.Logger] = None) -> Dict[str, Any]:
    """Fetches the full Jikan record for a single anime"""
    data = await jikan_get(f"{JIKAN_BASE_URL}/anime/{mal_id}/full", logger=logger)
    return dict(data)


def _season_start_date(season: str, year: int) -> datetime:
    month = SEASON_START_MONTH.get(season.lower(), 1)
    return datetime(year, month, 1, tzinfo=timezone.utc)


def _next_broadcast_days(broadcast: Dict[str, Any]) -> Tuple[Optional[int], str]:
    """Estimates days until the next weekly episode, based on Jikan's broadcast day"""
    day_name = broadcast.get("day")
    if day_name not in _WEEKDAYS:
        return None, ""
    target_weekday = _WEEKDAYS.index(day_name)
    days_ahead = (target_weekday - datetime.now(timezone.utc).weekday()) % 7
    return days_ahead, str(broadcast.get("string") or day_name)


async def find_sequel(
    data: Dict[str, Any], logger: Optional[logging.Logger] = None
) -> Optional[Dict[str, Any]]:
    """Looks through a Jikan anime's `relations` for an announced sequel"""
    for relation in data.get("relations") or []:
        if relation.get("relation") != "Sequel":
            continue
        for entry in relation.get("entry") or []:
            if entry.get("type") == "anime" and entry.get("mal_id"):
                return await fetch_full(int(entry["mal_id"]), logger=logger)
    return None


@dataclass
class Countdown:
    title: str
    url: str
    image: Optional[str]
    message: str
    days_left: Optional[int]


def _days_until(target: datetime) -> int:
    return (target.date() - datetime.now(timezone.utc).date()).days


async def compute_countdown(
    mal_id: int, logger: Optional[logging.Logger] = None
) -> Countdown:
    """
    Figures out what to show for a tracked anime:
    - if it's currently airing, a countdown to its next (weekly) episode
    - otherwise, if an announced sequel exists, a countdown to that season's release
    - otherwise, a message saying there's nothing upcoming right now
    """
    data = await fetch_full(mal_id, logger=logger)
    title = english_title(data)
    url = str(data.get("url") or f"https://myanimelist.net/anime/{mal_id}")
    image = jikan_image(data)
    status = data.get("status")

    if status == "Currently Airing":
        broadcast = data.get("broadcast") or {}
        days_left, when = _next_broadcast_days(broadcast)
        if days_left is not None:
            return Countdown(
                title=title,
                url=url,
                image=image,
                message=(
                    f"The next episode of **{title}** airs in "
                    f"{days_left} day{'s' if days_left != 1 else ''} ({when})."
                ),
                days_left=days_left,
            )

    sequel = await find_sequel(data, logger=logger)
    if sequel is not None:
        seq_title = english_title(sequel)
        seq_url = str(sequel.get("url") or "")
        seq_image = jikan_image(sequel) or image
        aired_from = (sequel.get("aired") or {}).get("from")
        if aired_from:
            target_date = datetime.fromisoformat(aired_from.replace("Z", "+00:00"))
            days_left = max(_days_until(target_date), 0)
            return Countdown(
                title=seq_title,
                url=seq_url,
                image=seq_image,
                message=(
                    f"There are {days_left} day{'s' if days_left != 1 else ''} "
                    f"until **{seq_title}** drops!"
                ),
                days_left=days_left,
            )
        season, year = sequel.get("season"), sequel.get("year")
        if season and year:
            days_left = max(_days_until(_season_start_date(season, year)), 0)
            return Countdown(
                title=seq_title,
                url=seq_url,
                image=seq_image,
                message=(
                    f"**{seq_title}** is announced for {str(season).capitalize()} "
                    f"{year} (~{days_left} days)."
                ),
                days_left=days_left,
            )
        return Countdown(
            title=seq_title,
            url=seq_url,
            image=seq_image,
            message=f"**{seq_title}** has been announced, but no release date yet.",
            days_left=None,
        )

    return Countdown(
        title=title,
        url=url,
        image=image,
        message=f"No upcoming episodes or announced sequel for **{title}** right now.",
        days_left=None,
    )


def build_tracker_embed(countdown: Countdown) -> discord.Embed:
    embed = discord.Embed(
        title=countdown.title,
        url=countdown.url or None,
        description=countdown.message,
        color=discord.Colour.dark_blue(),
    )
    if countdown.image:
        embed.set_thumbnail(url=countdown.image)
    return embed


class TrackedStore:
    """JSON file backed store of {mal_id: title} anime being tracked"""

    def __init__(self, filepath: str):
        self.filepath = filepath

    async def read(self) -> Dict[str, str]:
        if not os.path.exists(self.filepath):
            return {}
        async with aiofiles.open(self.filepath, mode="r") as f:
            contents = await f.read()
        if not contents.strip():
            return {}
        return dict(json.loads(contents))

    async def add(self, mal_id: int, title: str) -> None:
        data = await self.read()
        data[str(mal_id)] = title
        await self._write(data)

    async def remove(self, mal_id: int) -> bool:
        data = await self.read()
        was_present = data.pop(str(mal_id), None) is not None
        if was_present:
            await self._write(data)
        return was_present

    async def _write(self, data: Dict[str, str]) -> None:
        async with aiofiles.open(self.filepath, mode="w") as f:
            await f.write(json.dumps(data, indent=2, sort_keys=True))
