# TESTCASES

This directory allows users to directly call the Valorant API to view desired data and debug purposes.

## Usage

Run the test script using the following format:

```
python3 test_val_api.py [-h] [command] [account] [tag] [optional match_id]
```

## Help Message
```
usage: test_val_api.py [-h] command account tag [match_id]

Valorant API Test CLI

positional arguments:
  command     API command to execute. Available commands:
                  - get_account                : Retrieve account information
                  - get_rank                   : Get current rank
                  - get_last_match_id          : Get the last match ID
                  - get_last_match             : Retrieve details of the last match
                  - get_match_by_id [MATCH_ID] : Fetch match details by match ID
                  - get_melee_killer [MATCH_ID]: Retrieve melee kill stats for a match
  account     Valorant account name (e.g., MyAccount)
  tag         Valorant account tag (e.g., 1234)
  match_id    Optional Match ID (required for some commands)

optional arguments:
  -h, --help  show this help message and exit
```

