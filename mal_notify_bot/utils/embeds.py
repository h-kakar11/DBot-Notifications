import re
import time
import logging
import asyncio
from dataclasses import dataclass
from typing import List

import aiohttp
import discord  # type: ignore[import]

from typing import Optional, Dict, Any, Tuple

from . import log


JIKAN_BASE_URL = "https://api.jikan.moe/v4"

# Jikan's public instance allows ~3 requests/second and 60/minute; serialize all
# outbound requests through a lock with a minimum gap between them so batches of
# newly-approved entries don't get throttled
JIKAN_MIN_REQUEST_INTERVAL = 1.0

_jikan_lock = asyncio.Lock()
_jikan_last_request_time: float = 0.0
_jikan_session: Optional[aiohttp.ClientSession] = None


async def _get_jikan_session() -> aiohttp.ClientSession:
    global _jikan_session
    if _jikan_session is None or _jikan_session.closed:
        _jikan_session = aiohttp.ClientSession()
    return _jikan_session


async def jikan_get(url: str, logger: Optional[logging.Logger] = None) -> Any:
    """
    GETs a Jikan API url, serializing requests through a rate limiter and
    retrying on HTTP 429 by waiting for the duration in the Retry-After header.
    Returns whatever is under the response's "data" key (a dict for "/full"
    endpoints, a list for search/list endpoints).
    """
    global _jikan_last_request_time
    session = await _get_jikan_session()
    while True:
        async with _jikan_lock:
            elapsed = time.monotonic() - _jikan_last_request_time
            if elapsed < JIKAN_MIN_REQUEST_INTERVAL:
                await asyncio.sleep(JIKAN_MIN_REQUEST_INTERVAL - elapsed)
            async with session.get(url) as resp:
                _jikan_last_request_time = time.monotonic()
                status = resp.status
                if status == 429:
                    retry_after = float(resp.headers.get("Retry-After", "3"))
                else:
                    resp.raise_for_status()
                    body = await resp.json()
        if status == 429:
            if logger:
                logger.warning(
                    f"Jikan rate-limited us on {url}, waiting {retry_after}s before retrying"
                )
            await asyncio.sleep(retry_after)
            continue
        return body["data"]


def english_title(data: Dict[str, Any]) -> str:
    """Prefer the English title, falling back to the default/romaji title"""
    for entry in data.get("titles") or []:
        if entry.get("type") == "English" and entry.get("title"):
            return str(entry["title"])
    return str(data.get("title") or "Unknown Title")


def jikan_image(data: Dict[str, Any]) -> Optional[str]:
    """Gets the cover image from a Jikan response"""
    images = data.get("images") or {}
    jpg = images.get("jpg") or {}
    return jpg.get("large_image_url") or jpg.get("image_url")


def _is_sfw(data: Dict[str, Any]) -> bool:
    genre_names = [
        g.get("name")
        for g in (data.get("genres") or []) + (data.get("explicit_genres") or [])
    ]
    return "Hentai" not in genre_names


@dataclass
class EntryData:
    title: str
    url: str
    image: Optional[str]
    synopsis: Optional[str]
    sfw: bool
    airdate: Optional[str]
    status: str
    score: Optional[float]
    scored_by: Optional[int]
    episode_count: Optional[int]
    episode_label: str  # "Episodes" for anime, "Chapters" for manga


@log
async def get_data(
    mal_id: int,
    ignore_image: bool = False,
    entry_type: str = "anime",
    **kwargs: logging.Logger,
) -> EntryData:
    """Fetches anime/manga details from the free, unauthenticated Jikan API"""
    logger: Optional[logging.Logger] = kwargs.get("logger", None)
    assert entry_type in ("anime", "manga")

    data: Dict[str, Any] = await jikan_get(
        f"{JIKAN_BASE_URL}/{entry_type}/{mal_id}/full", logger=logger
    )

    title = english_title(data)
    image = None if ignore_image else jikan_image(data)

    # return something so that the form POST has value in case synopsis is empty
    synopsis: Optional[str] = data.get("synopsis") or "No Synopsis"
    synopsis = synopsis.replace("\r", "")
    synopsis = re.sub(r"\n\s*\n", "\n", synopsis.strip()).strip()
    if len(synopsis) > 400:
        synopsis = synopsis[:400].strip() + "..."
    if synopsis.strip() == "":
        synopsis = "No Synopsis"

    status = str(data.get("status") or "Unknown")
    if entry_type == "anime":
        airdate = (data.get("aired") or {}).get("string") or "No Air Date"
        episode_count = data.get("episodes")
        episode_label = "Episodes"
    else:
        airdate = (data.get("published") or {}).get("string") or "No Publish Date"
        episode_count = data.get("chapters")
        episode_label = "Chapters"

    sfw = _is_sfw(data)

    return EntryData(
        title=title,
        url=str(data.get("url") or f"https://myanimelist.net/{entry_type}/{mal_id}"),
        image=image,
        synopsis=synopsis,
        sfw=sfw,
        airdate=airdate,
        status=status,
        score=data.get("score"),
        scored_by=data.get("scored_by"),
        episode_count=episode_count,
        episode_label=episode_label,
    )


def embed_value_helper(embed_dict: Any, name: str) -> Any:
    """Only call this when you know that the value is in the embed, returns the value for the name"""
    for f in embed_dict.fields:
        if f.name == name:
            return f.value
    raise RuntimeError("Could not find {} on embed object".format(name))


def add_to_embed(
    discord_embed_object: discord.Embed,
    embed_dict: Any,
    name: str,
    value: Any,
    inline: bool,
) -> discord.Embed:
    if embed_dict is not None:
        # this was already in the embed_dict
        if name in [f.name for f in embed_dict.fields]:
            if value is not None:
                # prefer the recent value from MAL, if it exists
                discord_embed_object.add_field(name=name, value=value, inline=inline)
            else:
                # get it from the previous embed message
                discord_embed_object.add_field(
                    name=name, value=embed_value_helper(embed_dict, name), inline=inline
                )
        # if this field wasn't in the fields previously, add it to the embed object
        else:
            if value is not None:
                discord_embed_object.add_field(name=name, value=value, inline=inline)
    # if there is no embed_dict, this is a new embed object
    else:
        discord_embed_object.add_field(name=name, value=value, inline=inline)
    return discord_embed_object


def _score_display(entry: EntryData) -> str:
    scored_by_text = f" ({entry.scored_by:,} votes)" if entry.scored_by else ""
    return f"{entry.score}{scored_by_text}"


@log
async def create_embed(
    mal_id: int, logger: logging.Logger, entry_type: str = "anime"
) -> Tuple[discord.Embed, bool]:
    entry = await get_data(mal_id, False, entry_type=entry_type, logger=logger)
    embed = discord.Embed(
        title=entry.title,
        url=entry.url,
        color=discord.Colour.dark_blue(),
    )
    if entry.image is not None:
        embed.set_thumbnail(url=entry.image)
    embed = add_to_embed(embed, None, "Status", entry.status, inline=True)
    embed = add_to_embed(embed, None, "Air Date", entry.airdate, inline=True)
    embed = add_to_embed(embed, None, "MAL ID", mal_id, inline=True)
    if entry.score is not None:
        embed = add_to_embed(embed, None, "Score", _score_display(entry), inline=True)
    if entry.episode_count is not None:
        embed = add_to_embed(
            embed, None, entry.episode_label, entry.episode_count, inline=True
        )
    embed = add_to_embed(embed, None, "Synopsis", entry.synopsis, inline=False)
    return embed, entry.sfw


@log
async def refresh_embed(
    embed: discord.Embed,
    mal_id: int,
    remove_image: bool,
    logger: logging.Logger,
    entry_type: str = "anime",
) -> discord.Embed:
    entry = await get_data(mal_id, remove_image, entry_type=entry_type, logger=logger)
    new_embed = discord.Embed(
        title=entry.title,
        url=entry.url,
        color=discord.Color.dark_blue(),
    )
    if not remove_image and entry.image is not None:
        new_embed.set_thumbnail(url=entry.image)
    new_embed = add_to_embed(new_embed, embed, "Status", entry.status, inline=True)
    new_embed = add_to_embed(new_embed, embed, "Air Date", entry.airdate, inline=True)
    new_embed = add_to_embed(new_embed, embed, "MAL ID", mal_id, inline=True)
    new_embed = add_to_embed(
        new_embed,
        embed,
        "Score",
        _score_display(entry) if entry.score is not None else None,
        inline=True,
    )
    new_embed = add_to_embed(
        new_embed, embed, entry.episode_label, entry.episode_count, inline=True
    )
    new_embed = add_to_embed(new_embed, embed, "Synopsis", entry.synopsis, inline=False)
    new_embed = add_to_embed(new_embed, embed, "Source", None, inline=False)
    return new_embed


@log
async def add_source(
    embed: discord.Embed, valid_links: List[str]
) -> Tuple[discord.Embed, bool]:
    new_embed = discord.Embed(
        title=embed.title, url=embed.url, color=discord.Color.dark_blue()
    )
    if hasattr(embed, "thumbnail"):
        new_embed.set_thumbnail(url=embed.thumbnail.url)
    is_new_source = "Source" not in [f.name for f in embed.fields]
    new_embed = add_to_embed(new_embed, embed, "Status", None, inline=True)
    new_embed = add_to_embed(new_embed, embed, "Air Date", None, inline=True)
    new_embed = add_to_embed(new_embed, embed, "MAL ID", None, inline=True)
    new_embed = add_to_embed(new_embed, embed, "Synopsis", None, inline=True)
    new_embed = add_to_embed(
        new_embed, embed, "Source", " ".join(valid_links), inline=False
    )
    return new_embed, is_new_source


@log
async def remove_source(embed: discord.Embed) -> discord.Embed:
    new_embed = discord.Embed(
        title=embed.title, url=embed.url, color=discord.Color.dark_blue()
    )

    if hasattr(embed, "thumbnail"):
        new_embed.set_thumbnail(url=embed.thumbnail.url)
    new_embed = add_to_embed(new_embed, embed, "Status", None, inline=True)
    new_embed = add_to_embed(new_embed, embed, "Air Date", None, inline=True)
    new_embed = add_to_embed(new_embed, embed, "MAL ID", None, inline=True)
    new_embed = add_to_embed(new_embed, embed, "Synopsis", None, inline=False)
    return new_embed


def get_source(embed: discord.Embed) -> Optional[str]:
    for embed_proxy in embed.fields:
        if embed_proxy.name == "Source":
            return str(embed_proxy.value)
    return None
