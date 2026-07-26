"""
Thin async wrapper around the free, unauthenticated Jikan API (v4) -- no MAL
OAuth/Client ID needed. Serializes requests through a small rate limiter
(Jikan's public instance allows ~3 requests/second and 60/minute) and retries
on HTTP 429 / network errors / 5xx responses with backoff.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)

JIKAN_BASE_URL = "https://api.jikan.moe/v4"

MIN_REQUEST_INTERVAL_SECONDS = 1.0
MAX_ATTEMPTS = 4
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


class JikanClient:
    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()
        self._last_request_time = 0.0

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=REQUEST_TIMEOUT)
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def _get(self, url: str) -> Optional[Dict[str, Any]]:
        """
        GETs a Jikan url, returning the parsed "data" payload, or None if every
        retry attempt failed (callers should treat that as "skip for now").
        """
        session = await self._get_session()
        for attempt in range(1, MAX_ATTEMPTS + 1):
            async with self._lock:
                elapsed = time.monotonic() - self._last_request_time
                if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
                    await asyncio.sleep(MIN_REQUEST_INTERVAL_SECONDS - elapsed)
                try:
                    async with session.get(url) as resp:
                        self._last_request_time = time.monotonic()
                        if resp.status == 429:
                            retry_after = float(resp.headers.get("Retry-After", "3"))
                            logger.warning(
                                f"Jikan rate-limited us on {url}, waiting {retry_after}s "
                                f"(attempt {attempt}/{MAX_ATTEMPTS})"
                            )
                            await asyncio.sleep(retry_after)
                            continue
                        if resp.status >= 500:
                            logger.warning(
                                f"Jikan returned HTTP {resp.status} for {url} "
                                f"(attempt {attempt}/{MAX_ATTEMPTS})"
                            )
                        else:
                            resp.raise_for_status()
                            body = await resp.json()
                            return body.get("data")
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.warning(
                        f"Error requesting {url} (attempt {attempt}/{MAX_ATTEMPTS}): {e}"
                    )
            # exponential backoff before the next attempt (outside the lock, so
            # other callers aren't blocked while we wait)
            await asyncio.sleep(min(2**attempt, 10))
        logger.error(f"Giving up on {url} after {MAX_ATTEMPTS} attempts")
        return None

    async def get_anime(self, mal_id: int) -> Optional[Dict[str, Any]]:
        """Fetches a single anime entry: GET /anime/{id}"""
        return await self._get(f"{JIKAN_BASE_URL}/anime/{mal_id}")

    async def get_manga(self, mal_id: int) -> Optional[Dict[str, Any]]:
        """Fetches a single manga entry: GET /manga/{id}"""
        return await self._get(f"{JIKAN_BASE_URL}/manga/{mal_id}")
