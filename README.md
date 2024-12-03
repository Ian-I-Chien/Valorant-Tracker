# NoMoreBully

## Description
NoBully is a [Discord bot](https://discord.com/developers/docs/intro) designed to prevent bullying and toxic behavior during gaming sessions, particularly in games like Valorant.
It aims to foster a healthier and more respectful gaming environment by tracking player interactions and providing useful features to manage mentions and interactions.

Currently, it can only track mentions of specific users, but in the future, we hope to allow each user to have their own individual mention count.
We calculate both daily and historical counts, and use the historical counts for rankings. The daily count is reset at the start of each day.

In the future, we plan to integrate the [Valorant API from Henrik-3](https://github.com/Henrik-3/unofficial-valorant-api) so that the bot can also check personal stats and other related information.

## Environment:
This bot is running on R-PI3 with python version 3.11.2

The Token should be set in .env file.

[Discord Token](https://discord.com/developers/docs/quick-start/getting-started)
```
BOT_TOKEN= "TOKEN"
```

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
/info Valorant-User-Name#User-Tage
```
<p>
    <img src="https://github.com/Ian-I-Chien/Valorant-Discord-Bot/blob/main/pic/output_example.png" alt="Output Example" width="300"/>
</p>

## Bot Commands on Discord
```
/lm Valorant-User-Name#User-Tage
```
<p>
    <img src="https://github.com/Ian-I-Chien/Valorant-Discord-Bot/blob/main/pic/lm_output_example.png" alt="Output Example" width="300"/>
</p>



### Insult a User:
```
user toxic
```
This command will track when a user insults someone, and the bot will increment the "insult mentions" count for that user. The bot will also respond with a message letting the user know how many times they've been "insulted".

### Praise a User:
```
user awesome
```
Similarly, this command tracks when a user praises someone, and it increments the "praise mentions" count. The bot will respond with a message showing how many times they've been "praised".

## Rank Commands
The bot also provides ranking for both insults and praises. You can use the following slash commands:
```
/rank
```
Displays the top users with the most insults and praises in your server. It will show two rankings:
Insult Rank - The top users who insult the most.
Praise Rank - The top users who praise the most.

## Example Output:
```
Insult Rank:
Congrats! [User123] Total Insult: 15 times.
You're going straight to hell.

1. User456 - 10 times
2. User789 - 5 times

Praise Rank:
Congrats! [User456] Total Praise: 20 times.
You're going to heaven!

1. User123 - 15 times
2. User789 - 5 times

```

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
│   └── last_match.py
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
