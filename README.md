# Valorant-Tracker-Bot

## Description
Valorant Tracker Bot [Discord Bot](https://discord.com/developers/docs/intro) - monitoring the matches info of Valoarnt

### Key Features:
- By integrating with the Valorant API, Valorant-Tracker-Bot can automatically track the match records of players registered in the database. Players can register by using the /reg_val command.

We have integrated the [Valorant API from Henrik-3](https://github.com/Henrik-3/unofficial-valorant-api) so that the bot can also check personal stats and other related information.

## Environment:
This bot is running on R-PI3 with python version 3.11.2

**The Token should be set in .env file.**
**The Token should be set in .env file.**
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



## Tree:
```
Bully/
├── config/
│   └── constants.json
├── data/
│   └── user_data.json
├── database/
│   └── const.py
│   └── database.py
│   └── models.py
│   └── model_orm.py
├── model/
│   └── toxic_detector.py
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
├── file_manager.py
├── valorant.py
├── .env
├── requirements.txt
```

## Contact

If you have any questions or feedback, feel free to reach out!

- **Email:** err@csie.io

