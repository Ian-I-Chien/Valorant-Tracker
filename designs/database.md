# Database

## Proposed Design
The main idea is to store users' Discord accounts along with their
Valorant accounts. Each user can store one discord cache ID and multiple
Valorant accounts. The goal is to calculate the number of times each user
praises or criticizes others via their nickname. The fields of the
database are as follows.

### DB Table
#### Structure:
```
users {
    Discord Cache ID (Primary Key),
    Discord Account,
    Discord Display Name,
    Valorant Account,
    Valorant PUUID,
}
```
#### Account
Discord Cache ID
- This cached ID can be read from Discord package, this is unique. Hence,
  set it as a primary key.

Discord Account
- This account name can be read from Discord package.

Discord Display Name
- Discord Display Name which can be read by Discord packet.

#### Valorant Table
```
valorant {
    Discord Cache ID (Primary Key),
    Valorant Account,
}
```
Valorant Account
- User's Valorant account, this account should be registered by Discord user.
- The Valorant account can be multiple for the Discord user.

Valorant PUUID
- An unique PUUID for each Valorant account. This ID can be gained from Valorant API.
- When a discord user register the Valorant account, this PUUID should also be added in the data base via Valorant API.

#### Nick Name
```
nick names {
    Discord Cache ID (Primary Key),
    Nick Name,
}
```
Nick Name of the user
- Nick name can be multiple for an Discord account

#### Mention Related:
```
mentions {
    Discord Cache ID (Primary Key),
    Mention ID,
    Mentioned By ID,
    Mention Type,
    Mention Count,
    Mentioned Time,    
}
```
Mention ID
- The Discord user cache ID that you mentioned in your sentence

Mentioned By ID
- An user have mentioned by discord user cache ID in their sentences
  If you mentioned someone, this filed will be yourself

Mention Type
- Praise/Insult

Mention Count
- The mention count that an user mentioned another Discord user

Mentioned Time
- The time that an user mention others.