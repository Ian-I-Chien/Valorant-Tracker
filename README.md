# Valorant Tracker Bot

A lightweight Discord bot that tracks registered Valorant accounts and posts
an embed when a new match is completed. It is designed to run as a single
process on a Raspberry Pi and uses SQLite for local persistence.

Match and account data come from the
[HenrikDev unofficial Valorant API](https://github.com/Henrik-3/unofficial-valorant-api).

## Features

- Track multiple Valorant accounts across multiple Discord servers.
- Configure one notification channel independently for each Discord server.
- Store subscriptions and match checkpoints in SQLite.
- Avoid historical notifications by using the latest match as the initial
  checkpoint when an account is registered.
- Update a checkpoint only after its Discord notification is delivered.
- Prevent duplicate tracking of the same Valorant account in one server.
- Import the legacy JSON database once and retain a timestamped backup.
- Display match result, map, queue, player statistics, rank, HS%, ACS, and KAST.

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
```

Do not commit `.env`. Discord server notification channels are configured with
commands and stored in SQLite; they do not belong in environment variables.

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

After the bot joins a new Discord server, an administrator must configure the
notification channel before anyone can register an account:

```text
/set_channel channel:#valorant-results
```

This setting is isolated by Discord server. Changing it redirects all existing
subscriptions in that server immediately and does not require a bot restart.

## Commands

| Command | Who can use it | Description |
| --- | --- | --- |
| `/set_channel channel:#channel` | Server manager | Set the server's match notification channel. |
| `/show_config` | Everyone | Show the notification channel for the current server. |
| `/reg_val valorant_account:name#tag` | Everyone | Register and begin tracking a Valorant account. |
| `/del_val valorant_account:name#tag` | Account owner | Stop tracking one of the caller's accounts in this server. |

If `/reg_val` is used before `/set_channel`, registration is rejected with an
instruction to contact a server administrator.

## Persistence

Runtime data is stored in:

```text
database/valorant_tracker.db
```

SQLite WAL and shared-memory files may appear beside it while the bot runs. All
of these files are ignored by Git.

At startup, an existing `database/valorant_data.json` is imported once. The
source is retained, a timestamped backup is created, and the import is recorded
so restarting the bot does not duplicate subscriptions. Existing channel IDs
are also used to initialize the per-server notification settings.

See [the database design](designs/database.md) for the schema, transaction
boundaries, migration behavior, and Raspberry Pi considerations.

## Match Notification

The Discord embed includes:

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

<img src="pic/output_example.png" alt="Discord match notification example" width="360">

## Development

Install the requirements, then run:

```bash
python -m pytest -q
python -m black --check .
```

The main modules are:

```text
bot.py                       Discord client, slash commands, delivery loop
commands.py                  Registration, deletion, and polling workflows
database/storage_sqlite.py   SQLite schema, repositories, and JSON migration
valorant/api.py              HenrikDev HTTP client and rate limiter
valorant/player.py           Account and rank lookups
valorant/match.py            Match lookup, statistics, and embed formatting
designs/database.md          Persistence design and operational notes
```

## Contact

Email: err@csie.io
