"""
Entry point: python bot.py

Loads config from the environment (see .env.example), starts the bot, and
loads the mal_notify cog, which runs the background polling loop.
"""

import asyncio
import logging

import discord
from discord.ext import commands

from config import load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    config = load_config()

    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)

    @bot.event
    async def on_ready() -> None:
        user = bot.user
        logger.info(f"Logged in as {user} (id={user.id if user else 'unknown'})")

    async with bot:
        await bot.load_extension("cogs.mal_notify")
        await bot.start(config.discord_token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
