# Valorant-Tracker-Bot

## Description
Valorant Tracker Bot [Discord Bot](https://discord.com/developers/docs/intro) - monitoring the matches info of Valorant

### Key Features:
By integrating with the Valorant API, Valorant-Tracker-Bot can automatically track the match records of players registered in the database. Players can register by using the /reg_val command.

We have integrated the [Valorant API from Henrik-3](https://github.com/Henrik-3/unofficial-valorant-api) so that the bot can also check personal stats and other related information.

## Environment:
This bot is running on R-PI3 with python version 3.11.2

**The Token should be set in .env file.**

[Discord Token](https://discord.com/developers/docs/quick-start/getting-started)
```
BOT_TOKEN= "TOKEN"
```
If you have multiple **BOT_TOKENS**, you should separate them using a comma.


[API_Token](https://github.com/Henrik-3/unofficial-valorant-api)
```
API_TOKEN= "API_TOKEN"
```

To run the Bot:
```
python3 main.py
```


## Bot Usage Example
To use the bot, simply type the following commands in your Discord server where the bot is active:

## Bot Commands on Discord

```
/reg_val Valorant-User-Name#User-Tag
```
Register a Valorant account with your Discord account to automatically track matches.

## Output

### OutPut Architecture:

| Field         | Description                              |
|---------------|------------------------------------------|
| Match Date    | Date and time of the match               |
| Map           | The map played (e.g. Pearl)              |
| Match Type    | Type of match (Unrated, Ranked, etc.)    |
| Result        | Win or Lose, with score if available     |
| Player Name   | In-game name and tag                     |
| Rank          | Player's rank at the time of the match   |
| Agent         | The agent used in the match              |
| K             | Kills                                    |
| D             | Deaths                                   |
| A             | Assists                                  |
| K/D/A         | Combined stat format                     |
| HS%           | Head shoot percentage                      |
| ACS           | Average Combat Score                     |
| KAST          | Percentage of rounds with kill, assist, survived, or traded |

### Output Example on Discord

<p>
    <img src="https://github.com/Ian-I-Chien/Valorant-Tracker/blob/main/pic/output_example.png" alt="Output Example" width="300"/>
</p>


## Tree:
```
Valorant-Tracker/
├── database/
│   └── storage_json.py
├── valorant/
│   └── __init__.py
│   └── api.py
│   └── player.py
│   └── match_stats.py
│   └── match.py
├── utils/
│   └── __init__.py
│   └── utils.py
├── main.py
├── bot.py
├── commands.py
├── valorant.py
├── .env
├── requirements.txt
```

Future Plans
- Add SQLite support for persistent data storage
- Provide visualized match statistics for a better overview of match

## Contact

If you have any questions or feedback, feel free to reach out!

- **Email:** err@csie.io

