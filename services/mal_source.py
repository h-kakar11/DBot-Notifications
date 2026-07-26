"""
Determines which MAL anime/manga entries currently exist ("Just Added"/approved),
by reading the community-maintained purarue/mal-id-cache JSON mirror instead of
scraping MAL's "Just Added" HTML page directly (far more reliable, and avoids
needing BeautifulSoup/lxml or worrying about MAL blocking scrapers).
"""

import asyncio
import logging
from typing import Any, Dict, Optional, Set

import aiohttp

logger = logging.getLogger(__name__)

ANIME_CACHE_URL = (
    "https://raw.githubusercontent.com/purarue/mal-id-cache/master/cache/anime_cache.json"
)
MANGA_CACHE_URL = (
    "https://raw.githubusercontent.com/purarue/mal-id-cache/master/cache/manga_cache.json"
)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)
MAX_ATTEMPTS = 3


async def _fetch_json(url: str) -> Dict[str, Any]:
    async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
        last_error: Optional[BaseException] = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    # mal-id-cache's raw.githubusercontent.com response is served
                    # as text/plain, not application/json
                    return await resp.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                logger.warning(
                    f"Failed to fetch {url} (attempt {attempt}/{MAX_ATTEMPTS}): {e}"
                )
                await asyncio.sleep(min(2**attempt, 10))
    raise RuntimeError(f"Could not fetch {url} after {MAX_ATTEMPTS} attempts") from last_error


async def fetch_all_anime_ids() -> Set[str]:
    """Returns every currently-approved anime MAL id (sfw + nsfw)"""
    data = await _fetch_json(ANIME_CACHE_URL)
    return {str(mal_id) for mal_id in (data.get("sfw", []) + data.get("nsfw", []))}


async def fetch_all_manga_ids() -> Set[str]:
    """Returns every currently-approved manga MAL id (sfw + nsfw)"""
    data = await _fetch_json(MANGA_CACHE_URL)
    return {str(mal_id) for mal_id in (data.get("sfw", []) + data.get("nsfw", []))}
