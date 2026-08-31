# Multi-account shops and opt-in DMs

This supersedes the single-account behavior described in private-shop.md.
It remains independent of Henrik match subscriptions and `/reg_val`.

- `/login` adds a different Riot PUUID or reauthorizes the same PUUID, retaining
  other accounts. Up to 25 accounts per Discord owner; no default account.
- `/shop` shares every linked account in the invoking channel; optional `account`
  selects one of that owner's accounts. Failures remain private and other accounts
  still run. Requests are bounded and a long batch stops before interaction expiry.
- `/accounts` privately lists accounts, authorization status and the notification
  toggle; it supports removing a selected account. `/logout account` removes only
  that account. All selector values are resolved inside the requesting owner's vault.
- `/shop_notify` opens the same panel. Notifications default OFF. Enabling first
  probes DMs; failed DMs do not enable the preference. It includes all present and
  future linked accounts, with no per-account subscription choices.
- Enabling/new accounts baseline the first successfully observed store, then send
  after its expiration. There is no immediate backfill. Manual `/shop` is available
  for today's store. Re-enabling resets the baseline.
- Updates are checked every minute, sequentially across users with pacing, using
  returned store expiry rather than a hard-coded reset hour. Exact-time delivery
  is not guaranteed. Per-owner operations are serialized; upstream work is capped
  at three concurrent account fetches. Expiry and a maximum five-minute cache TTL
  bound manual cache reuse.
- DMs contain text only, grouped by account, split below Discord limits. Mentions
  are disabled. Revoked accounts keep only identity metadata and are reported once
  until reauthorized; other accounts continue. A forbidden DM disables the user's
  notification toggle. Generic transient fetch failures retry after five minutes.

## Persistence and delivery guarantees

The existing `credentials(owner, encrypted)` table and encryption key remain.
Each owner now has a version-2 encrypted bundle containing accounts keyed by PUUID,
one notification flag, and per-account scheduling/claim state. Legacy single-account
records migrate lazily under an owner lock; no plaintext credentials or new tracking
records are created. Only one bot process may own this vault, as before.

Claims are committed before sending (at most once). A crash after commit, an ambiguous
HTTP failure, or partial split-message delivery can miss that update; it is deliberately
not replayed after restart. This is not an exactly-once delivery guarantee. Missing
updates remain available through `/shop`. A successful private delivery probe confirms
DM availability only at that time. Other settings are never changed to make DMs work.

Expired refresh credentials are removed, but the account label stays in the management
panel. Removing the last account disables notifications. Logout and refresh use the
same owner lock, preventing in-flight refresh from resurrecting removed credentials.

## Deployment and rollback

No TEST or production deployment is performed by this PR. Before enabling it, stop
all old shop processes and back up the encrypted shop database together with its key
using restricted permissions. Never run the old single-account service against a
migrated bundle. Rollback requires stopping the new process and restoring the matching
pre-migration encrypted database; changes since that backup will be lost. The original
single-account service remains solely for compatibility tests, not live registration.
The notification worker starts once on bot readiness and is cancelled on bot close.

## Validation

Automated tests use synthetic credentials, a temporary vault, fake Riot responses and
mocked Discord sends. They cover migration, owner separation, duplicate login, removal,
rotation, revocation, scheduler baselines, new accounts, toggle behavior, replay safety,
DM failures, UI ownership, and partial shop success. Before production deployment,
validate a real two-account login, a private panel/DM toggle and one real daily reset
in TEST. Do not change production authorization or tracking databases for testing.
