# Database

## Description
TBD

## Requirements
TBD

## Proposed Design
1. The main idea is to store users' discord account with valorant account. Each user can store one discord account with multiple valorant accounts.
2. To calculate the number of times each user praises or criticizes each other.

The fields of the database are as follows.

### DB Table
#### Structure:
```
users {
    DC Account (PRIMARY),
    DC Display Name,
    Valorant Account,
    Valorant PUUID,
}
```
#### Accounnt
Discord Account (PRIMARY ID)
- It is unique, so it will be different for each person and is used to identify your account.
  This can be read from Discord packet.

Discord Disply Name
- Discord Disply Name which can be read by Discord packet.

Valorant Account
- User's Valorant account, this account should be registered by Discord user.
- The Valorant account can be multiple for the Discrod user.

Valorant PUUID
- An unique PUUID for each Valorant account. This ID can be gained from Valorant API.
- When a discord user register the Valorant account, this PUUID should also be added in the data base via Valorant API.

#### Nick Name
```
nick names {
    Nick Name ID (PRIMARY),
    DC Account,
    Nick Name,
}
```

Nick Name of the user
- Nick name can be multiple for an Discord account

DC account
- Described on above

#### Mention Related:
```
mentions {
    DC Account (PRIMARY),
    Mention ID,
    Mentioned By ID,
    Mentione Type,
    Mention Count,
    Last Mentioned Time,    
}
```
Mention ID
- The Discord User ID that you mentioned in your sentence

Mentioned By ID
- An user have mentioned by Discord User ID in their sentences
  If you mentioend someone, this filed will be yourself

Mention Type
- Will be parise/insult

Mention Count
- The mention count that an user mentioned another Discord user

Last Mentioned Time


....TBD