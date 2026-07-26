"""
Watches MAL's "Just Added" feed (via mal_source) for newly-approved anime
entries, fetches details from the free Jikan API, and posts a Discord embed
for each one to the configured announcements channel.
"""

import logging
from typing import Any, Dict, Optional

import discord
from discord.ext import commands, tasks

from config import Config, load_config
from services.jikan_client import JikanClient
from services.mal_source import fetch_all_anime_ids
from storage.state import SeenEntriesStore

logger = logging.getLogger(__name__)


def build_embed(entry_type: str, data: Dict[str, Any]) -> discord.Embed:
    """Builds a Discord embed for a single Jikan anime/manga entry"""
    title = str(data.get("title") or "Unknown Title")
    url = data.get("url") or None
    embed = discord.Embed(title=title, url=url, color=discord.Colour.blurple())

    images = data.get("images") or {}
    jpg = images.get("jpg") or {}
    image = jpg.get("large_image_url") or jpg.get("image_url")
    if image:
        embed.set_thumbnail(url=image)

    embed.add_field(
        name="Type", value=str(data.get("type") or entry_type.capitalize()), inline=True
    )
    embed.add_field(name="Status", value=str(data.get("status") or "Unknown"), inline=True)

    score = data.get("score")
    if score is not None:
        scored_by = data.get("scored_by")
        score_text = f"{score}" + (f" ({scored_by:,} votes)" if scored_by else "")
        embed.add_field(name="Score", value=score_text, inline=True)

    if entry_type == "anime":
        episodes = data.get("episodes")
        if episodes is not None:
            embed.add_field(name="Episodes", value=str(episodes), inline=True)
    else:
        chapters = data.get("chapters")
        if chapters is not None:
            embed.add_field(name="Chapters", value=str(chapters), inline=True)

    synopsis = data.get("synopsis")
    if synopsis:
        synopsis = synopsis.strip().replace("\r", "")
        if len(synopsis) > 400:
            synopsis = synopsis[:400].rstrip() + "..."
        embed.add_field(name="Synopsis", value=synopsis, inline=False)

    return embed


class MalNotifyCog(commands.Cog):
    """Polls MAL for newly-approved anime and announces them to a channel"""

    def __init__(self, bot: commands.Bot, config: Config) -> None:
        self.bot = bot
        self.config = config
        self.jikan = JikanClient()
        self.state = SeenEntriesStore(config.state_path)
        self.poll_loop.change_interval(minutes=config.poll_minutes)

    async def cog_load(self) -> None:
        self.poll_loop.start()

    async def cog_unload(self) -> None:
        self.poll_loop.cancel()
        await self.jikan.close()

    @tasks.loop(minutes=5)
    async def poll_loop(self) -> None:
        try:
            await self._poll_once()
        except Exception:
            logger.exception("Unhandled error while polling MAL for new entries")

    @poll_loop.before_loop
    async def before_poll_loop(self) -> None:
        await self.bot.wait_until_ready()

    def _get_channel(self) -> Optional[discord.abc.Messageable]:
        channel = self.bot.get_channel(self.config.announcement_channel_id)
        if channel is None:
            logger.error(
                f"Could not find channel with id {self.config.announcement_channel_id}; "
                "check ANNOUNCEMENT_CHANNEL_ID and that the bot has access to it"
            )
        return channel

    async def _poll_once(self) -> None:
        logger.info("Polling MAL's 'Just Added' feed for new anime entries...")
        try:
            current_ids = await fetch_all_anime_ids()
        except Exception as e:
            logger.error(f"Failed to fetch the current anime id list, skipping this poll: {e}")
            return

        seen_ids = self.state.load()

        if not self.state.exists():
            if self.config.prime_on_first_run:
                logger.info(
                    f"No prior state file found; priming with {len(current_ids)} existing "
                    "ids without posting them (PRIME_ON_FIRST_RUN=true)"
                )
                self.state.save(current_ids)
                return
            logger.info(
                "No prior state file found and PRIME_ON_FIRST_RUN=false; "
                "every currently-approved entry will be posted"
            )

        new_ids = sorted(current_ids - seen_ids, key=int)
        if not new_ids:
            logger.info("No new anime entries found")
            return

        logger.info(
            f"Found {len(new_ids)} new anime entr{'y' if len(new_ids) == 1 else 'ies'}: {new_ids}"
        )

        channel = self._get_channel()
        if channel is None:
            return

        posted_ids = set(seen_ids)
        for mal_id in new_ids:
            try:
                data = await self.jikan.get_anime(int(mal_id))
                if data is None:
                    logger.warning(f"Jikan returned no data for anime {mal_id}, will retry next poll")
                    continue
                embed = build_embed("anime", data)
                await channel.send(embed=embed)
                logger.info(f"Posted anime {mal_id} ('{data.get('title')}') to the announcements channel")
            except discord.HTTPException as e:
                logger.error(f"Failed to post embed for anime {mal_id} to Discord: {e}")
                continue
            except Exception:
                logger.exception(f"Unexpected error handling anime {mal_id}, will retry next poll")
                continue
            # only mark as seen (and persist) once it's successfully posted, so a
            # mid-batch crash or Discord outage doesn't cause it to be skipped forever
            posted_ids.add(mal_id)
            self.state.save(posted_ids)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MalNotifyCog(bot, load_config()))
