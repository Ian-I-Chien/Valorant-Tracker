# Database Design

## Decision

Valorant Tracker uses SQLite as its persistent store. The bot runs as a single
process on a Raspberry Pi, has a low write rate, and keeps its data on the same
device. SQLite provides transactions, constraints, and atomic updates without a
separate database service.

The async application layer should use `aiosqlite`. It keeps SQLite operations
off the Discord event loop while preserving a small deployment footprint. A
full ORM is intentionally not required; repository classes should own the SQL
and map rows to application data.

The database file is stored at:

```text
database/valorant_tracker.db
```

The file must remain on the Raspberry Pi's local filesystem. Do not place a
live SQLite database on a network filesystem.

## Goals

- Isolate data by Discord server.
- Allow a Discord user to track multiple Valorant accounts.
- Allow the same Valorant account to be tracked in different servers or
  channels without sending duplicate notifications to one channel.
- Store the notification checkpoint with the subscription it belongs to.
- Enforce ownership and uniqueness in the database.
- Make registration, deletion, and checkpoint updates transactional.
- Support schema migrations and an idempotent import from the legacy JSON file.

## Connection Settings

Every connection must enable foreign keys and a busy timeout. Database
initialization should enable write-ahead logging once.

```sql
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
```

`synchronous = NORMAL` reduces unnecessary SD-card synchronization while WAL is
enabled. Deployments that prefer maximum durability for the latest committed
checkpoint may use `FULL` instead.

Keep transactions short. Never hold a database transaction open while calling
the Valorant API or sending a Discord message.

## Schema

### Schema migrations

The application records each applied migration. Migration files are applied in
ascending version order during startup and each migration runs in a transaction.

```sql
CREATE TABLE schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### Discord users

A Discord user is scoped to a server because display information and bot usage
may differ between servers.

```sql
CREATE TABLE discord_users (
    server_id       TEXT NOT NULL,
    discord_user_id TEXT NOT NULL,
    global_name     TEXT,
    display_name    TEXT,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (server_id, discord_user_id)
);
```

### Valorant accounts

PUUID is the stable account identity. Game name and tag are display and lookup
fields and may change over time.

```sql
CREATE TABLE valorant_accounts (
    puuid       TEXT PRIMARY KEY,
    game_name   TEXT NOT NULL,
    tag         TEXT NOT NULL,
    region      TEXT NOT NULL DEFAULT 'ap',
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (game_name, tag, region)
);
```

Account comparisons should use normalized game name and tag values for lookup,
but PUUID remains the authoritative identity.

### Subscriptions

A subscription connects an owner, a Valorant account, and the Discord channel
that receives notifications. The checkpoint belongs here rather than on the
Discord user or global Valorant account.

```sql
CREATE TABLE subscriptions (
    id                     INTEGER PRIMARY KEY,
    server_id              TEXT NOT NULL,
    discord_user_id        TEXT NOT NULL,
    valorant_puuid         TEXT NOT NULL,
    channel_id             TEXT NOT NULL,
    last_polled_match_id   TEXT,
    created_at             TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at             TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (server_id, discord_user_id)
        REFERENCES discord_users(server_id, discord_user_id)
        ON DELETE CASCADE,
    FOREIGN KEY (valorant_puuid)
        REFERENCES valorant_accounts(puuid)
        ON DELETE CASCADE,
    UNIQUE (server_id, valorant_puuid, channel_id)
);

CREATE INDEX idx_subscriptions_owner
    ON subscriptions (server_id, discord_user_id);

CREATE INDEX idx_subscriptions_polling
    ON subscriptions (valorant_puuid, last_polled_match_id);
```

The uniqueness rule prevents two users from creating duplicate notifications
for the same Valorant account in the same server channel. The owner fields still
make deletion authorization explicit.

## Operation Boundaries

### Register an account

1. Parse and normalize `game_name#tag`.
2. Fetch the Valorant account outside a database transaction.
3. Begin a transaction.
4. Upsert the Discord user by `(server_id, discord_user_id)`.
5. Upsert the Valorant account by PUUID.
6. Insert the subscription with its channel.
7. Commit.

The first successful poll sets `last_polled_match_id` to the current latest
match without sending it. Only later match IDs produce notifications.

### Poll matches

1. Read subscriptions and their checkpoints.
2. Fetch and format match information outside a transaction.
3. Send the Discord notification.
4. After delivery succeeds, run a short transaction that updates the matching
   subscription checkpoint.

The update must identify the subscription and expected previous checkpoint so
that stale workers cannot overwrite newer progress:

```sql
UPDATE subscriptions
SET last_polled_match_id = ?,
    updated_at = CURRENT_TIMESTAMP
WHERE id = ?
  AND last_polled_match_id IS ?;
```

If no row is updated, reload the subscription before deciding whether to retry.

### Delete an account

Delete only a subscription owned by the requesting Discord user and server.
Never delete by Valorant name across all users.

```sql
DELETE FROM subscriptions
WHERE server_id = ?
  AND discord_user_id = ?
  AND valorant_puuid = ?;
```

An unreferenced row in `valorant_accounts` may be removed separately as cleanup;
it is not required for the user-facing delete operation.

## JSON Migration

The legacy source is `database/valorant_data.json`. Migration must be safe to
run more than once.

1. Create a timestamped backup of the JSON file.
2. Create the SQLite schema and begin one import transaction.
3. Upsert each JSON user into `discord_users`.
4. Upsert each account into `valorant_accounts` using its PUUID.
5. Create a subscription using the user's existing server and channel values.
6. Copy `last_polled_match_id` into that subscription.
7. Report imported, skipped, and invalid record counts.
8. Commit only when every valid record has been processed.
9. Compare source and destination counts before enabling SQLite in production.

The importer must not delete or rewrite the JSON source. Keep the backup until
the SQLite deployment has run successfully through multiple polling cycles.

## Backup and Recovery

- Back up with SQLite's backup API or `VACUUM INTO`; do not copy a live database
  file while a write may be in progress.
- Keep the database, WAL, and shared-memory files together during recovery.
- Store backups outside the repository and rotate them by age or count.
- Run `PRAGMA integrity_check;` as a maintenance or recovery diagnostic, not on
  every polling cycle.

## Not Selected

- PostgreSQL and MySQL require a separate service and more Raspberry Pi
  administration than this workload needs.
- DuckDB is optimized for analytical workloads rather than transactional bot
  state.
- One SQLite file per Discord server adds migration and backup complexity
  without a current need; `server_id` provides logical isolation in one file.
- SQLAlchemy adds an abstraction layer that is unnecessary for this small,
  explicit schema.
