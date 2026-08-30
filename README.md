# Valorant Tracker Bot

A lightweight Discord bot that tracks registered Valorant accounts and posts
a graphical scoreboard when a new match is completed. It is designed to run as
a single process on a Raspberry Pi and uses SQLite for local persistence.

Match and account data come from the
[HenrikDev unofficial Valorant API](https://github.com/Henrik-3/unofficial-valorant-api).

## Features

- Show an English `/help` guide privately, without API calls or registration.
- Track multiple Valorant accounts across multiple Discord servers.
- Configure one notification channel independently for each Discord server.
- Store subscriptions and match checkpoints in SQLite.
- Avoid historical notifications by using the latest match as the initial
  checkpoint when an account is registered.
- Update a checkpoint only after its Discord notification is delivered.
- Prevent duplicate tracking of the same Valorant account in one server.
- Import the legacy JSON database once and retain a timestamped backup.
- Render a graphical scoreboard with agent and rank icons, match result, map,
  queue, player statistics, HS%, ACS, KAST, and RR changes.
- Highlight registered players and label premade DUO, TRIO, and stack groups
  without exposing HenrikDev party IDs.
- Generate an explainable pre-match prediction card from a registered player's
  recent Competitive and Unrated matches.
- Render a 30-day player overview with rank and agent icons, core performance
  metrics, recent form, party results, and an RR trend chart.
- Fall back to the text embed if the graphical scoreboard cannot be rendered.
- Emit operational information and errors through Python logging, suitable for
  systemd journal monitoring on a Raspberry Pi.

## Requirements

- Python 3.11 or newer
- A Discord application and bot token
- A HenrikDev API key
- A local filesystem for the SQLite database

The live SQLite files should remain on the Raspberry Pi's local storage rather
than a network filesystem.

## Installation

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/Ian-I-Chien/Valorant-Tracker.git
cd Valorant-Tracker
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create `.env` in the repository root:

```dotenv
BOT_TOKEN=your_discord_bot_token
API_KEY=your_henrikdev_api_key
LOG_LEVEL=INFO
API_REQUESTS_PER_MINUTE=60
API_CACHE_MAX_ENTRIES=256
```

Do not commit `.env`. Discord server notification channels are configured with
commands and stored in SQLite; they do not belong in environment variables.

`API_REQUESTS_PER_MINUTE` defaults to 60 to retain headroom below a 90-request
HenrikDev key. This limit applies **per key, per process**; lower it for keys
with smaller quotas. `API_CACHE_MAX_ENTRIES` bounds the in-memory response cache for
Raspberry Pi deployments.

### Multiple Henrik API keys

For independently provisioned keys permitted for use by the same application,
replace `API_KEY` with a comma-separated list:

```dotenv
API_KEYS="first_key,second_key,third_key"
API_REQUESTS_PER_MINUTE=60
```

Keys are read once at startup. After editing `.env`, restart the bot/service.
Whitespace and empty entries are ignored; duplicate keys count only once.
A nonempty `API_KEYS` list takes precedence; otherwise `API_KEY` remains supported.
No keys means API requests fail with a configuration error, without unauthenticated calls.

- Cache hits do not consume a key or advance rotation. Polling and commands share
  one pool and cache; polling frequency does not increase when keys are added.
- Requests rotate across usable keys, reserving each key's independent sliding-window
  budget before sending. One request per key may be in flight; different keys can run concurrently.
- HTTP 401 disables that key until restart. A personal HTTP 429 (remaining quota is
  zero) cools only that key. `Retry-After` takes precedence over reset headers;
  missing or invalid reset information falls back conservatively to 60 seconds.
- HTTP 403 can indicate maintenance; a 429 without personal exhaustion can be
  global. Both back off the entire pool rather than cycling through credentials.
  Network errors and HTTP 5xx use shared exponential backoff (2–60 seconds).
- One request waits at most 5 seconds for a key, tries at most 3 keys, and has a
  30-second total deadline. Exhaustion/failure uses eligible stale cache or reports
  temporary unavailability. HTTP connections retain their 8-second connect and
  20-second total timeouts.
- Logs identify keys only as `key-1`, `key-2`, etc.; credentials are never logged.
  Test and production must use distinct keys (or budget for their combined traffic):
  counters are not shared between processes, machines, or other applications.

See [key pool design](designs/api-key-pool.md) for response handling details.

Start the bot:

```bash
python3 main.py
```

## Discord Setup

When inviting the bot, enable the `bot` and `applications.commands` scopes. In
the notification channel, the bot needs these permissions:

- View Channel
- Send Messages
- Embed Links
- Attach Files

After the bot joins a new Discord server, an administrator must configure the
notification channel before anyone can register an account:

```text
/set_channel channel:#valorant-results
```

This setting is isolated by Discord server. Changing it redirects all existing
subscriptions in that server immediately and does not require a bot restart.

## Commands

Use `/help` for an English command guide visible only to you. It explains
player lookup, tracking, and server setup without making any Henrik API requests.

| Command | Who can use it | Description |
| --- | --- | --- |
| `/help` | Everyone | Show a private guide to player lookup, tracking, and server settings. |
| `/set_channel channel:#channel` | Server manager | Set the server's match notification channel. |
| `/show_config` | Everyone | Show the notification channel for the current server. |
| `/reg_val valorant_account:name#tag` | Everyone | Register and begin tracking a Valorant account. |
| `/del_val valorant_account:name#tag` | Account owner | Stop tracking one of the caller's accounts in this server. |
| `/predict username:name#tag` | Everyone | Generate an entertainment-only pre-match prediction; no registration required. |
| `/info username:name#tag` | Everyone | Show a graphical 30-day overview; no registration required. |

### Quick start

- **Just looking up a player?** Use `/info username:Player#TAG` or
  `/predict username:Player#TAG`. Neither command enables tracking.
- **Want automatic match notifications?** A member with **Manage Server**
  permission first runs `/set_channel channel:#valorant-results`, then you run
  `/reg_val valorant_account:Player#TAG`.
- **Want to stop tracking?** Use `/del_val valorant_account:Player#TAG` for an
  account you registered in the current server.
- **Need help or settings?** Use `/help` for the guide or `/show_config` to
  check the current server's notification channel.

`/help` works in servers and direct messages, responds only to the caller,
and does not access Henrik or modify subscriptions. Use the player, tracking,
and server-settings commands inside a Discord server. The guide includes
command syntax, permission requirements, and a documentation link.

If `/reg_val` is used before `/set_channel`, registration is rejected with an
instruction to contact a server administrator.

`/predict` and `/info` accept either an unambiguous registered game name or a
complete `name#tag`. A complete Riot ID can be queried even when the player is
not registered; this one-time lookup does not subscribe the player, create a
polling checkpoint, or track future matches. They only consider Competitive
(RK) and Unrated (NG) matches from the
previous 30 days; Swiftplay, Deathmatch, Team Deathmatch, Spike Rush, and other
modes are excluded. If the player has no eligible match in that period, the bot
reports that there is not enough recent data instead of producing a prediction.

`/info` uses the same player lookup and 30-day RK/NG filter. Its
dashboard includes win rate, match count, K/D, KDA, ACS, KAST, HS%, ADR, recent
form, top agents, party-size performance, current rank/RR, and recent RR
changes. If card rendering fails, the command returns a compact text summary.

## Persistence

### Experimental shop (off by default)

An opt-in `/login`, `/shop`, and `/logout` flow supports either an explicit
Discord user allowlist or open registration with `SHOP_ALLOWED_USER_IDS=*`.
Each bot environment reads its own settings; the default remains disabled.
It stores encrypted Riot authorization separately from match tracking. `/login`, `/logout`, and errors stay private. `/shop` shares a 2x2
card with the linked Riot ID, daily skins, prices, and refresh time publicly
in the invoking channel; rendering failures fall back to public text.
When an active Night Market is returned, the same `/shop` card appends its
six offers, original prices, discounts, final prices, and separate end time.
Without an active event, the entire Night Market section is omitted.
This integration awaits live event verification before merge/deployment; see
[the validation checklist](designs/night-market.md). This is an unofficial client flow, not an approved Riot
store API. Login callback URLs and tokens are sensitive; no account-safety or
long-term availability guarantee is made.

Read [the setup and security boundaries](designs/private-shop.md) before enabling
it. A separate key file and tester allowlist are required. Do not enable it on
production merely by updating the code. Shop lookup does not use Henrik quota.

### Match tracking database

Runtime data is stored in:

```text
database/valorant_tracker.db
```

SQLite WAL and shared-memory files may appear beside it while the bot runs. All
of these files are ignored by Git.

HenrikDev match lists, rank data, and MMR history use short in-memory TTLs.
Concurrent requests for the same resource share one upstream request, and a
recent stale response is used when HenrikDev is temporarily unavailable. The
poller uses a 60-second match-list TTL; interactive statistics use five minutes.

At startup, an existing `database/valorant_data.json` is imported once. The
source is retained, a timestamped backup is created, and the import is recorded
so restarting the bot does not duplicate subscriptions. Existing channel IDs
are also used to initialize the per-server notification settings.

See [the database design](designs/database.md) for the schema, transaction
boundaries, migration behavior, and Raspberry Pi considerations.

## Match Notification

The bot renders a scoreboard PNG and uploads it to Discord. Valorant map,
agent, and rank assets are downloaded on first use and cached under
`data/assets/`; the cache is ignored by Git. If an individual asset cannot be
loaded, the card is still rendered without that icon. If rendering the card
fails, the bot sends the original text embed instead.

The notification includes:

| Field | Description |
| --- | --- |
| Match date | Completion date and time |
| Map and queue | Map and game mode |
| Result | Win/loss and score |
| Player | Riot ID and agent |
| K/D/A | Kills, deaths, and assists |
| HS% | Headshot percentage |
| ACS | Average Combat Score |
| KAST | Percentage of rounds with a kill, assist, survival, or trade |
| Rank | Competitive rank when available |
| Party | Team-local DUO, TRIO, or stack label for shared party IDs |

<img src="pic/match_scoreboard_example.png" alt="Graphical Discord match notification with party labels" width="780">

## Pre-Match Prediction

The prediction card is an explainable entertainment baseline, not an LLM and
not a guaranteed outcome. It uses eligible recent win rate, ACS, K/D, and ACS
trend, then bounds the displayed probability between 25% and 75%. The card also
shows the sample size, confidence level, recent form, and the strongest reasons
behind the estimate. If image rendering fails, the command returns the same
result as text.

HenrikDev currently returns at most ten recent matches to this workflow, so the
30-day filter can only evaluate the eligible matches present in that response.

<img src="pic/prediction_example.png" alt="Pre-match prediction card example" width="600">

## Player Overview

The `/info` dashboard combines recent match data with rank history. Agent and
rank artwork are downloaded through the shared asset cache; missing remote
artwork does not prevent the rest of the card from rendering. Only Competitive
and Unrated matches completed in the previous 30 days contribute to the
performance metrics.

<img src="pic/player_info_example.png" alt="Graphical 30-day player overview example" width="780">

## Development

Install the requirements, then run:

```bash
python -m pytest -q
python -m black --check .
```

Developers with shell access can build the latest graphical match card without
sending it or changing the polling checkpoint:

```bash
python -m tools.match_output --account "Name#Tag"
```

To manually deliver a known match to the channel configured for a Discord
server, add the explicit `--send` flag:

```bash
python -m tools.match_output \
  --account "Name#Tag" \
  --match-id "MATCH_ID" \
  --server-id "DISCORD_SERVER_ID" \
  --send
```

Manual outputs are marked as developer tests and never advance a subscription's
`last_polled_match_id`.

To render a real match locally for visual review without sending it:

```bash
python -m tools.render_match_card \
  --account "Name#Tag" \
  --match-id "MATCH_ID" \
  --output match-scoreboard.png
```

The main modules are:

```text
bot.py                       Discord client, slash commands, delivery loop
commands.py                  Registration, deletion, and polling workflows
database/storage_sqlite.py   SQLite schema, repositories, and JSON migration
valorant/api.py              HenrikDev HTTP client and rate limiter
valorant/player.py           Account and rank lookups
valorant/match.py            Match lookup, statistics, and embed formatting
valorant/match_card.py       Cached assets and graphical scoreboard rendering
valorant/prediction.py       Prediction features, baseline, and card rendering
valorant/player_info.py      Player overview aggregation and card rendering
designs/database.md          Persistence design and operational notes
```

Pull requests run Black and pytest through `.github/workflows/ci.yaml`.

For a systemd deployment, inspect live bot logs with:

```bash
journalctl -u valorant-tracker.service -f
```

## Contact

Email: err@csie.io
