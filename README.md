# DBot-Notifications

A Discord bot that watches MyAnimeList's [Just Added](https://myanimelist.net/anime.php?o=9&c%5B0%5D=a&c%5B1%5D=d&cv=2&w=1)
feed and posts a rich embed to a configured Discord channel whenever a new anime
entry is approved on MAL.

Originally based on [purarue/mal-notify-bot](https://github.com/purarue/mal-notify-bot),
rewritten as the `mal-notify-bot` feature of this bot.

## How it works

- Every `POLL_MINUTES` minutes (default 5), the bot fetches the current list of
  approved anime ids from the community-maintained
  [purarue/mal-id-cache](https://github.com/purarue/mal-id-cache) JSON mirror of
  MAL's "Just Added" feed (no scraping/HTML parsing needed).
- New ids (not seen on a previous poll) are looked up individually via the free,
  unauthenticated [Jikan API](https://docs.api.jikan.moe/) (`GET /anime/{id}`) --
  no MAL API Client ID or OAuth required.
- A Discord embed (title, type, status, score, episodes, image, synopsis, and a
  link back to the MAL page) is posted to `ANNOUNCEMENT_CHANNEL_ID` for each one.
- Posted ids are persisted to `STATE_PATH` (a JSON file) after each successful
  post, so restarting the bot doesn't repost old entries.
- On the very first run (no state file yet), the current id list is recorded
  without posting anything, so you don't get flooded with the entire back
  catalog. Set `PRIME_ON_FIRST_RUN=false` if you actually want that.
- Manga entries can be fetched the same way via `services/jikan_client.py`'s
  `get_manga()` (`GET /manga/{id}`); manga polling isn't wired into the loop yet,
  only anime.

## Project structure

```
bot.py                    # entry point: loads config, starts the bot, loads the cog
config.py                 # loads settings from environment variables / .env
cogs/
  mal_notify.py            # background polling loop + embed builder
services/
  mal_source.py             # fetches the current approved-id list (mal-id-cache)
  jikan_client.py            # rate-limited Jikan API client with retry/backoff
storage/
  state.py                   # persists the set of already-posted ids to disk
requirements.txt
.env.example
```

## Setup

1. Create a Discord application & bot at the
   [Discord Developer Portal](https://discord.com/developers/applications), under
   **Bot** click **Reset Token** to get your bot token, and
   [invite it to your server](https://github.com/reactiflux/discord-irc/wiki/Creating-a-discord-bot-&-getting-a-token).
   No privileged intents are required.
2. Clone this repo and install dependencies:

   ```powershell
   git clone https://github.com/h-kakar11/DBot-Notifications
   cd DBot-Notifications
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in the values:

   ```powershell
   Copy-Item .env.example .env
   ```

   | Variable | Required | Default | Description |
   |---|---|---|---|
   | `DISCORD_TOKEN` | yes | - | Your bot's token |
   | `ANNOUNCEMENT_CHANNEL_ID` | yes | - | The channel id to post new-entry embeds to (enable Developer Mode in Discord, right-click the channel -> Copy Channel ID) |
   | `POLL_MINUTES` | no | `5` | How often to poll for new entries |
   | `STATE_PATH` | no | `data/seen_entries.json` | Where the set of already-posted ids is persisted |
   | `PRIME_ON_FIRST_RUN` | no | `true` | If `true`, the first run records existing ids without posting them |

4. Run it:

   ```powershell
   python bot.py
   ```

## Logs

The bot logs (to stdout) when it starts polling, how many new entries it found,
each successful/failed post, and any errors reaching MAL/Jikan or Discord -- so
you can tell at a glance whether polling, detection, or posting is the problem
if something looks wrong.

## Manual test checklist

- [ ] `python bot.py` starts without prompting for anything besides what's in `.env`, and logs `Logged in as ...`.
- [ ] With no `data/seen_entries.json` yet, the first poll logs "priming" and does **not** post anything (with the default `PRIME_ON_FIRST_RUN=true`).
- [ ] `data/seen_entries.json` now exists and contains a large list of ids.
- [ ] Temporarily remove a real, currently-approved anime id from `data/seen_entries.json` and wait for the next poll (or lower `POLL_MINUTES` to `1` while testing) -- an embed for that anime should appear in `ANNOUNCEMENT_CHANNEL_ID` with title, image, status, score, episodes, and a working MAL link.
- [ ] Restart the bot -- the same entry is **not** posted again.
- [ ] Temporarily set `ANNOUNCEMENT_CHANNEL_ID` to an invalid id -- the bot logs an error instead of crashing, and keeps polling on the next interval.
- [ ] Disconnect from the internet (or block `api.jikan.moe`) -- the bot logs a warning/error and retries/skips gracefully instead of crashing.
