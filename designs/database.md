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
CREATE TABLE discord_users (
    DiscordCacheID VARCHAR(255) PRIMARY KEY,
    DiscordAccount VARCHAR(255),
    DiscordDisplayName VARCHAR(255)
    DiscordServerID    VARCHAR(255)
    DiscordChannelID   VARCHAR(255)
);
```
#### Account
Discord Cache ID
- This cached ID can be read from Discord package, this is unique. Hence,
  set it as a primary key.

Discord Account
- This account name can be read from Discord package.

Discord Display Name
- Discord Display Name which can be read by Discord packet.

Discord Server ID
– The Discord server where a user is registered.

Discord Channel ID
– The Discord channel where the bot responded.

#### Valorant Table
```
CREATE TABLE valorant_accounts (
    DiscordCacheID VARCHAR(255),
    ValorantAccount VARCHAR(255),
    ValorantPUUID VARCHAR(255),
    PRIMARY KEY (DiscordCacheID, ValorantAccount),
    FOREIGN KEY (DiscordCacheID) REFERENCES discord_users(DiscordCacheID)
)
```
Valorant Account
- User's Valorant account, this account should be registered by Discord user.
- The Valorant account can be multiple for the Discord user.

Valorant PUUID
- An unique PUUID for each Valorant account. This ID can be gained from Valorant API.
- When a discord user register the Valorant account, this PUUID should also be added in the data base via Valorant API.

#### Valorant Match Table
```
CREATE TABLE valorant_matches (
    MatchID VARCHAR(255) PRIMARY KEY,
    ValorantPUUID VARCHAR(255),
    MatchData JSON,
    MatchDate TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ValorantPUUID) REFERENCES valorant_accounts(ValorantPUUID)
);
```
MatchID
- Match PUUID

Valorant PUUID
- reference valorant accounts PUUID

Match Data
- match data from [match](https://api.henrikdev.xyz/valorant/v4/match/{region}/{matchid})

Match Date
- timestamp


#### Nick Name
```
CREATE TABLE nick_names (
    NickNameID INT AUTO_INCREMENT PRIMARY KEY,
    DiscordCacheID VARCHAR(255),
    NickName VARCHAR(255),
    FOREIGN KEY (DiscordCacheID) REFERENCES discord_users(DiscordCacheID)
);
```
Nick Name of the user
- Nick name can be multiple for an Discord account

#### Mention Related:
```
CREATE TABLE mentions (
    ID INT AUTO_INCREMENT PRIMARY KEY,
    MentionToID VARCHAR(255),
    MentionedByID VARCHAR(255),
    MentionType ENUM('PRAISE', 'INSULT') NOT NULL,
    MentionCount INT,
    MentionedTime TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (MentionedByID) REFERENCES discord_users(DiscordCacheID),
    FOREIGN KEY (MentionToID) REFERENCES discord_users(DiscordCacheID)
);
```
Mention to ID
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