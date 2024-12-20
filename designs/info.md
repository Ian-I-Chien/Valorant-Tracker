# Valorant Player Information

## Proposed Design
The INFO command is used to show a Discord user's recent Valorant gaming information. Currently, the INFO command requires the Valorant user ID and Valorant tag to be passed. In the future, we plan to add a registration command for Discord users to register their own Valorant account. Through this command, a Discord user will be able to retrieve their own recent Valorant gaming information via the INFO command without needing to provide their Valorant user ID and tag.
This project uses the [Valorant API from Henrik-3](https://github.com/Henrik-3/unofficial-valorant-api) for the Valorant related information.

### INFO Output
#### Valorant Player ID and Tag
  Get from [Account API V1](https://api.henrikdev.xyz/valorant/v1/account/{player_name}/{player_tag})
#### Valorant Account Level
  Get from [Account API V1](https://api.henrikdev.xyz/valorant/v1/account/{player_name}/{player_tag})
#### Average Kill/Death/Assistant (10 Competitive games)
  TBD.
#### Average Scores (10 Competitive games)
  TBD. Get from [Match V4](https://api.henrikdev.xyz/valorant/v4/match/{region}/{matchid})
#### Average Head Shot Rate (10 Competitive games)
  Get from [Get Stored Match V1](https://api.henrikdev.xyz/valorant/v1/stored-matches/{region}/{player_name}/{player_tag})
#### Average First Kill (10 Competitive games)
  TBD.
#### Highest Kill in history
  Get from [Get Stored Match V1](https://api.henrikdev.xyz/valorant/v1/stored-matches/{region}/{player_name}/{player_tag})
#### Rank in Tier
  Get from [Get MMR V1](https://api.henrikdev.xyz/valorant/v1/mmr/{region}/{player_name}/{player_tag})
#### Last MMR change
  Get from [Get MMR V1](https://api.henrikdev.xyz/valorant/v1/mmr/{region}/{player_name}/{player_tag})