# Experimental shop

Status: opt-in test implementation. Not enabled in production. The manual probe
verified a code exchange, one refresh, and a four-offer shop response; this does
not validate indefinite refresh, all regions, or a production-safe integration.

## Boundaries

- Uses an unofficial Riot client authorization flow, not Henrik keys or official
  third-party RSO. Riot currently lists online store tracking as an unapproved
  use case: https://developer.riotgames.com/docs/valorant#game-policy
- First login requires the user to paste a sensitive callback URL into a Discord
  modal after explicit disclosure. Discord and the bot receive this code.
- Tokens are not guaranteed to be shop-only. No passwords or MFA codes accepted.
- One linked shop account per Discord user; not per guild. Login, logout, and
  errors are private. Successful `/shop` cards and text fallbacks are public
  in the invoking channel and include the linked Riot ID. No credentials
  appear in public output.
- Shop linking never registers a match subscription or changes tracking checkpoints.
- Commands, refresh, and logout are serialized in one process. Never share a vault
  between multiple running bot processes. Test and production must use separate
  vaults AND different Riot test accounts (refresh tokens may rotate).

## Storage and lifecycle

Fernet encrypts the entire credential record before SQLite sees it. Owner Discord
IDs remain visible in the database. Store the encryption key outside the checkout
and outside database backups; Linux vault/key permissions are 0600. Encryption
does not protect against compromise of the running host, process memory, or both
key and database. Do not enable HTTP debug logs, core dumps, or capture modal data.

Login sessions expire after five minutes, are owner-bound and one-use, and check
the returned nonce. The nonce check is not JWT signature verification; identity
comes from Riot's authenticated userinfo endpoint. A fresh login replaces the
previous shop account only after the new account has been resolved successfully.

Refresh is on demand, before expiry, not a background login loop. Rotated tokens
are saved before fetching the store. Explicit invalid authorization removes the
local record; transient failures preserve it. No blind retries after token exchange.
All requests have timeouts and redirects disabled. Quota failures introduce cooldown.

Shop results are memory-cached per owner until the reported rotation deadline
(capped at 24 hours). Images come from a restricted public asset host. Failed
asset lookups fall back to skin IDs and prices without losing the store response.
The shop renders one 2x2 image with Riot ID, prices, and refresh time.
Missing artwork and prices are explicit; card failures use a text fallback.
Public artwork downloads are restricted to media.valorant-api.com, disallow
redirects, and enforce time, byte, and decoded-pixel limits.
Old encrypted records missing the Riot tag are upgraded on shop lookup without
requiring a new login; metadata lookup failure does not hide valid shop data.

`/logout` removes the current encrypted record, cache, and pending login. It does
not revoke Riot sessions, erase previously created backups, delete previously
shared store messages, or affect match tracking.

## Test deployment

Install requirements in the test environment. Create a key using
`python tools/init_shop_key.py /absolute/private/path/shop.key`; the directory
must already exist. This refuses to overwrite a key and never prints its contents.

Set only in the test environment:

```dotenv
SHOP_ENABLED=1
SHOP_ALLOWED_USER_IDS=your_numeric_discord_user_id
SHOP_KEY_FILE=/absolute/private/path/shop.key
SHOP_DB_PATH=/absolute/private/path/shop-test.db
```

The allowlist is mandatory (1–100 IDs). Missing settings disable the feature;
`SHOP_ENABLED` defaults to off. Restart to change settings. Use `/login`, then
`/shop`, then `/logout` to verify deletion. Verify persistence by restarting the
test bot with the same key and vault. Losing the key requires relinking; do not
generate a replacement over it. No purchases, friend-shop lookup, automatic
notifications, or night market in this first version.

## References

Protocol investigation: https://github.com/mistralwz/Ministral (GPLv3).
This implementation was written separately; do not copy its code/assets without
reviewing license obligations. Static assets: https://valorant-api.com/.
