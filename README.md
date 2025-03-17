# NoMoreBully

## Description
NoBully [Discord Bot](https://discord.com/developers/docs/intro) - Preventing Bullying and Toxic Behavior in Gaming

NoBully is a Discord bot designed to reduce bullying and toxic behavior during gaming sessions, especially in competitive games like Valorant. Its goal is to create a healthier and more respectful gaming environment by tracking player interactions and providing tools to manage mentions and interactions.

Currently, NoBully tracks mentions of specific users and calculates both daily and historical mention counts. The daily count resets at the beginning of each day, while the historical count is used for player rankings.

### Key Features:
- Tracks mentions between players to help identify potential bullying behavior.
Daily Counts & Historical Rankings (In Progress):
- Provides daily mention statistics and uses historical data for player rankings.
Valorant Match Records (Functional):
- By integrating with the Valorant API, NoBully can automatically track the match records of players registered in the database. Players can register by using the /reg_val command.

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
[INFO](https://github.com/Ian-I-Chien/Valorant-Discord-Bot/blob/main/designs/info.md)
```
/info Valorant-User-Name#User-Tag
```
<p>
    <img src="https://github.com/Ian-I-Chien/Valorant-Discord-Bot/blob/main/pic/output_example.png" alt="Output Example" width="300"/>
</p>

```
/lm Valorant-User-Name#User-Tag
```
<p>
    <img src="https://github.com/Ian-I-Chien/Valorant-Discord-Bot/blob/main/pic/lm_output_example.png" alt="Output Example" width="300"/>
</p>

```
/reg_val Valorant-User-Name#User-Tag
```
Register a Valorant account with your Discord account to automatically track matches.

```
/whoami
```
To check Valorant account info which is linked to the discord account in the database.
This command can only used after a discord user is registered (/reg_val) valorant account.


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

