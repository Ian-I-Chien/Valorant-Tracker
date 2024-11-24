# NoMoreBully

NoBully is a Discord bot designed to prevent bullying and toxic behavior during gaming sessions, particularly in games like Valorant.
It aims to foster a healthier and more respectful gaming environment by tracking player interactions and providing useful features to manage mentions and interactions.

Currently, it can only track mentions of specific users, but in the future, we hope to allow each user to have their own individual mention count.

We calculate both daily and historical counts, and use the historical counts for rankings. The daily count is reset at the start of each day.

Environment:
This bot is running on R-PI3 with python version 3.11.2

Needs to set a Token of discord which is set in .env file
```
BOT_TOKEN= "TOKEN"
```

To run the Bot:
```
python3 main.py
```


Bot commands on discord:
```
!rank
```

Tree:
```
Bully/
├── config/
│   └── constants.json
├── data/
│   └── user_data.json
├── main.py
├── bot.py
├── commands.py
├── file_manager.py
├── .env
├── requirements.txt
```
