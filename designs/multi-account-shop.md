# Multi-account shops and channel notifications

Supersedes single-account behavior in private-shop.md and the initial DM design.
This is independent of Henrik subscriptions and `/reg_val`.

- `/login` adds a different Riot PUUID or reauthorizes the same PUUID. Up to 25
  accounts per Discord owner, no default account.
- `/shop` queries all linked accounts; optional `account` selects one. Successful
  accounts are combined into one vertically stacked JPEG and one public message.
  Image dimensions and upload size are bounded. Rendering failures fall back to
  one text message or one text attachment for a large batch. Retrieval failures
  are summarized privately; a failed public send is never retried as another message.
- Only `/accounts` manages accounts, removals and the all-account notification
  toggle. `/shop_notify` is removed. `/logout account` removes one account.
- Enabling notifications chooses the invoking server channel and requires bot
  send permissions. The panel displays the destination. "Move notifications to
  this channel" explicitly updates it; merely opening the panel does not.
- Notifications are OFF by default and cover all present/future login accounts.
  Old enabled DM preferences WITHOUT a saved channel are disabled on migration:
  private-message consent never authorizes publishing to a server channel.
- No DMs are sent. At delivery time the saved guild/channel, requesting user's
  membership/view permission and bot send permission are checked. Missing/deleted
  destinations or forbidden sends disable notifications, with no alternate target.
- Updates are text, grouped by account, splitting only above message limits. No
  mentions generate pings. Authorization failures appear privately in `/accounts`,
  never in a public update. Expired credentials are removed but identity metadata
  is retained for re-login. Other accounts continue normally.

## Scheduling and concurrency

The first successfully observed shop establishes an expiry baseline; notifications
start with a subsequent observed update. Enabling does not backfill today's store.
New logins baseline automatically; re-enabling resets baselines. Moving the channel
while enabled keeps the current baselines. Manual `/shop` is independent.

Checks run every minute with pacing between users. Exact reset-time delivery is not
guaranteed. Per-owner locks order refresh, logout, settings and delivery. Upstream
shop calls are limited to three concurrent fetches. Per-owner scheduler work and
individual requests have time bounds. Transient fetch errors retry after five minutes.
The worker starts once on readiness and is cancelled when the bot closes.

## Persistence and rollback

Existing `credentials(owner, encrypted)` records use the same encryption key. Legacy
single-account records migrate lazily to version-2 encrypted bundles containing
PUUID-keyed accounts, one notification toggle, a guild/channel destination and
per-account scheduling state. Match tracking storage is untouched. Only one bot
process may own a vault.

Claims are committed before sending (at most once). A crash, ambiguous HTTP failure
or partial split-message send can miss an update; claims are not replayed after
restart. This is not an exactly-once guarantee; manual `/shop` remains available.

Before deployment, stop old shop processes and back up the encrypted vault and key
with restricted permissions. Old single-account code cannot read migrated bundles.
Rollback requires stopping the new process and restoring the matching pre-migration
vault, losing changes made since that backup. The original single-account service
is kept for compatibility tests only; live registration uses MultiShopService.

## Verification

Tests use temporary encrypted vaults and fake Riot/Discord responses. Validate real
multi-account login, the combined card, channel selection/move, destination permission
loss and a real daily reset in TEST before product rollout. Never use production
credentials or tracking storage for these tests.
