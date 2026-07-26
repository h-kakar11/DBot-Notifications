# DBot-Notifications

A Discord bot that checks the [Just Added](https://myanimelist.net/anime.php?o=9&c%5B0%5D=a&c%5B1%5D=d&cv=2&w=1) page on [MAL](https://myanimelist.net/), reporting any newly approved anime entries, and lets you track countdowns to specific shows' next episode or next season.

<img src="https://i.imgur.com/pEVk0iw.png" alt="" width=400>

Originally based on [purarue/mal-notify-bot](https://github.com/purarue/mal-notify-bot).

#### Data source:

Embeds are built from the free, unauthenticated [Jikan API](https://docs.api.jikan.moe/) (a REST wrapper around MyAnimeList) — no MAL API Client ID, OAuth, or app approval is required to run this bot; the only credential you need is your Discord bot token.

#### Commands:

Prefix commands (mention the bot first, e.g. `@notify help`):

| Command | Description |
|---|---|
| `help` | Shows the list of commands |
| `add_new` | Checks for newly-approved entries immediately, instead of waiting for the next poll |
| `source <mal_id> <links...\|remove>` | Adds/removes a source link on a posted embed |
| `export` | Creates a backup of all sources as a JSON file |
| `refresh <mal_id>` | Re-fetches an entry's metadata and updates its embed |
| `restart` | Restarts the bot |
| `index <pages>` | Asks a [checker_mal](https://github.com/Hiyori-API/checker_mal) instance to index more pages |

Slash commands:

| Command | Description |
|---|---|
| `/track <name>` | Searches for an anime by name and, once you pick a result from the dropdown, tracks it — posting an embed with a countdown to its next episode (if airing) or next announced season (if a sequel has been announced) |
| `/untrack <mal_id>` | Stops tracking an anime |
| `/tracked` | Lists everything currently being tracked |

Tracked anime get a fresh countdown embed posted once a day to a channel named `tracker` (falls back to `announcements` if you don't have one).

#### Install:

To create your own instance of the bot, create a server which has a channel named `announcements` (and optionally one named `tracker`), [add the bot to it](https://github.com/reactiflux/discord-irc/wiki/Creating-a-discord-bot-&-getting-a-token), and then:

```
git clone https://github.com/h-kakar11/DBot-Notifications
cd DBot-Notifications
python3 -m pip install pipenv  # if you don't have pipenv already
pipenv install
pipenv shell
git clone https://github.com/purarue/mal-id-cache
touch token.yaml
```

This uses a file in this directory called `old` which caches the already printed entries; if one was to start this on a new server, it would send every entry since it hasn't sent any yet (it doesn't know which ones are 'new'). You can use my [`mal-id-cache`](https://github.com/purarue/mal-id-cache) repository as a base, by reading in the SFW/NSFW IDs for anime, and saving those to a file named `old`. The format is just a text file, with one entry per line.

Could create the initial 'old' file by running:

`curl -s 'https://raw.githubusercontent.com/purarue/mal-id-cache/master/cache/anime_cache.json' | jq -r '.sfw + .nsfw | .[]' >'old'`

put your bots token in `token.yaml` with contents like:

`token: !!str EU*#3eiSzEr7i4L36FaTlrV0*RtuGOBVNrcteyrtt$GPAwNtkJKQg*dweSLy`

`tracked.json` (the list of anime being tracked with `/track`) is created automatically the first time you use the command.

#### Run:

`python3 bot.py`

This is run on `python 3.10.2`. You can use [pyenv](https://github.com/pyenv/pyenv) to install another version of python if needed.
