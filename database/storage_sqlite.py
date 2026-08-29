import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite


BASE_DIR = Path(__file__).resolve().parent
DATABASE_FILE = BASE_DIR / "valorant_tracker.db"
LEGACY_JSON_FILE = BASE_DIR / "valorant_data.json"


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS discord_users (
    server_id TEXT NOT NULL,
    discord_user_id TEXT NOT NULL,
    global_name TEXT,
    display_name TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (server_id, discord_user_id)
);

CREATE TABLE IF NOT EXISTS guild_settings (
    server_id TEXT PRIMARY KEY,
    notification_channel_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS valorant_accounts (
    puuid TEXT PRIMARY KEY,
    game_name TEXT NOT NULL COLLATE NOCASE,
    tag TEXT NOT NULL COLLATE NOCASE,
    region TEXT NOT NULL DEFAULT 'ap',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (game_name, tag, region)
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY,
    server_id TEXT NOT NULL,
    discord_user_id TEXT NOT NULL,
    valorant_puuid TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    last_polled_match_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (server_id, discord_user_id)
        REFERENCES discord_users(server_id, discord_user_id) ON DELETE CASCADE,
    FOREIGN KEY (valorant_puuid)
        REFERENCES valorant_accounts(puuid) ON DELETE CASCADE,
    UNIQUE (server_id, valorant_puuid, channel_id)
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_owner
    ON subscriptions (server_id, discord_user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_polling
    ON subscriptions (valorant_puuid, last_polled_match_id);

CREATE TABLE IF NOT EXISTS legacy_imports (
    source_path TEXT PRIMARY KEY,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    backup_path TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class MigrationResult:
    imported: int = 0
    skipped: int = 0
    invalid: int = 0
    backup_path: Optional[Path] = None


@dataclass(frozen=True)
class SubscriptionRecord:
    id: int
    server_id: str
    discord_user_id: str
    valorant_account: str
    valorant_puuid: str
    last_polled_match_id: Optional[str]


class DuplicateSubscriptionError(ValueError):
    """Raised when the same account is already tracked in a Discord server."""


@dataclass(frozen=True)
class GuildSettingsRecord:
    server_id: str
    notification_channel_id: str


async def _configure(connection: aiosqlite.Connection) -> None:
    await connection.execute("PRAGMA foreign_keys = ON")
    await connection.execute("PRAGMA busy_timeout = 5000")


async def initialize_database(database_file: Path = DATABASE_FILE) -> None:
    database_file.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(database_file) as connection:
        await _configure(connection)
        await connection.execute("PRAGMA journal_mode = WAL")
        await connection.execute("PRAGMA synchronous = NORMAL")
        await connection.executescript(SCHEMA)
        await connection.execute(
            "INSERT OR IGNORE INTO schema_migrations(version) VALUES (1)"
        )
        # Existing installations used the channel stored on subscriptions.
        # Preserve one current channel per guild as the initial server setting.
        await connection.execute(
            """
            INSERT OR IGNORE INTO guild_settings(server_id, notification_channel_id)
            SELECT server_id, MIN(channel_id)
            FROM subscriptions
            GROUP BY server_id
            """
        )
        await connection.execute(
            "INSERT OR IGNORE INTO schema_migrations(version) VALUES (2)"
        )
        await connection.commit()


class UserSQLiteDB:
    def __init__(self, database_file: Path = DATABASE_FILE):
        self.database_file = Path(database_file)
        self.connection: Optional[aiosqlite.Connection] = None

    async def __aenter__(self):
        await initialize_database(self.database_file)
        self.connection = await aiosqlite.connect(self.database_file)
        self.connection.row_factory = aiosqlite.Row
        await _configure(self.connection)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.connection is None:
            return
        if exc_type is None:
            await self.connection.commit()
        else:
            await self.connection.rollback()
        await self.connection.close()

    async def register_user(
        self,
        dc_id: str,
        dc_global_name: str,
        dc_display_name: str,
        dc_server_id: str,
        dc_channel_id: str,
        val_account: str,
        val_puuid: str,
        region: str = "ap",
    ) -> None:
        game_name, tag = val_account.rsplit("#", 1)
        connection = self._connection()
        await connection.execute("SAVEPOINT register_subscription")
        try:
            await connection.execute(
                """
                INSERT OR IGNORE INTO guild_settings(
                    server_id, notification_channel_id
                ) VALUES (?, ?)
                """,
                (dc_server_id, dc_channel_id),
            )
            await connection.execute(
                """
                INSERT INTO discord_users(
                    server_id, discord_user_id, global_name, display_name
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(server_id, discord_user_id) DO UPDATE SET
                    global_name = excluded.global_name,
                    display_name = excluded.display_name,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (dc_server_id, dc_id, dc_global_name, dc_display_name),
            )
            await connection.execute(
                """
                INSERT INTO valorant_accounts(puuid, game_name, tag, region)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(puuid) DO UPDATE SET
                    game_name = excluded.game_name,
                    tag = excluded.tag,
                    region = excluded.region,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (val_puuid, game_name, tag, region),
            )
            cursor = await connection.execute(
                """
                SELECT 1 FROM subscriptions
                WHERE server_id = ? AND valorant_puuid = ?
                """,
                (dc_server_id, val_puuid),
            )
            if await cursor.fetchone():
                raise DuplicateSubscriptionError(
                    "Valorant account already registered in this server"
                )
            await connection.execute(
                """
                INSERT INTO subscriptions(
                    server_id, discord_user_id, valorant_puuid, channel_id
                ) VALUES (?, ?, ?, ?)
                """,
                (dc_server_id, dc_id, val_puuid, dc_channel_id),
            )
        except (aiosqlite.IntegrityError, DuplicateSubscriptionError) as exc:
            await connection.execute("ROLLBACK TO register_subscription")
            if isinstance(exc, DuplicateSubscriptionError):
                raise
            raise DuplicateSubscriptionError(
                "Valorant account already registered in this server"
            ) from exc
        finally:
            await connection.execute("RELEASE register_subscription")

    async def list_subscriptions(self) -> list[SubscriptionRecord]:
        cursor = await self._connection().execute(
            """
            SELECT s.id AS subscription_id, s.server_id AS dc_server_id,
                   s.discord_user_id AS dc_id,
                   s.last_polled_match_id, a.puuid AS valorant_puuid,
                   a.game_name || '#' || a.tag AS valorant_account
            FROM subscriptions AS s
            JOIN valorant_accounts AS a ON a.puuid = s.valorant_puuid
            ORDER BY s.id
            """
        )
        rows = await cursor.fetchall()
        return [
            SubscriptionRecord(
                id=row["subscription_id"],
                server_id=row["dc_server_id"],
                discord_user_id=row["dc_id"],
                valorant_account=row["valorant_account"],
                valorant_puuid=row["valorant_puuid"],
                last_polled_match_id=row["last_polled_match_id"],
            )
            for row in rows
        ]

    async def find_subscription(
        self, server_id: str, account_query: str
    ) -> Optional[SubscriptionRecord]:
        """Find a registered Riot ID by full ID or an unambiguous game name."""
        query = account_query.strip()
        if not query:
            return None
        if "#" in query:
            game_name, tag = query.rsplit("#", 1)
            condition = "a.game_name = ? COLLATE NOCASE AND a.tag = ? COLLATE NOCASE"
            parameters = (server_id, game_name, tag)
        else:
            condition = "a.game_name = ? COLLATE NOCASE"
            parameters = (server_id, query)
        cursor = await self._connection().execute(
            f"""
            SELECT s.id AS subscription_id, s.server_id AS dc_server_id,
                   s.discord_user_id AS dc_id, s.last_polled_match_id,
                   a.puuid AS valorant_puuid,
                   a.game_name || '#' || a.tag AS valorant_account
            FROM subscriptions AS s
            JOIN valorant_accounts AS a ON a.puuid = s.valorant_puuid
            WHERE s.server_id = ? AND {condition}
            ORDER BY s.id
            LIMIT 2
            """,
            parameters,
        )
        rows = await cursor.fetchall()
        if len(rows) != 1:
            return None
        row = rows[0]
        return SubscriptionRecord(
            id=row["subscription_id"],
            server_id=row["dc_server_id"],
            discord_user_id=row["dc_id"],
            valorant_account=row["valorant_account"],
            valorant_puuid=row["valorant_puuid"],
            last_polled_match_id=row["last_polled_match_id"],
        )

    async def set_guild_notification_channel(
        self, server_id: str, channel_id: str
    ) -> GuildSettingsRecord:
        await self._connection().execute(
            """
            INSERT INTO guild_settings(server_id, notification_channel_id)
            VALUES (?, ?)
            ON CONFLICT(server_id) DO UPDATE SET
                notification_channel_id = excluded.notification_channel_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (server_id, channel_id),
        )
        return GuildSettingsRecord(server_id, channel_id)

    async def get_guild_settings(self, server_id: str) -> Optional[GuildSettingsRecord]:
        cursor = await self._connection().execute(
            """
            SELECT server_id, notification_channel_id
            FROM guild_settings
            WHERE server_id = ?
            """,
            (server_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return GuildSettingsRecord(
            server_id=row["server_id"],
            notification_channel_id=row["notification_channel_id"],
        )

    async def update_last_polled_match(
        self,
        subscription_id: int,
        expected_match_id: Optional[str],
        match_id: str,
    ) -> bool:
        cursor = await self._connection().execute(
            """
            UPDATE subscriptions
            SET last_polled_match_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND last_polled_match_id IS ?
            """,
            (match_id, subscription_id, expected_match_id),
        )
        return cursor.rowcount == 1

    async def remove_valorant_account(
        self, dc_id: str, dc_server_id: str, valorant_account: str
    ) -> bool:
        game_name, tag = valorant_account.rsplit("#", 1)
        cursor = await self._connection().execute(
            """
            DELETE FROM subscriptions
            WHERE server_id = ? AND discord_user_id = ?
              AND valorant_puuid IN (
                  SELECT puuid FROM valorant_accounts
                  WHERE game_name = ? COLLATE NOCASE AND tag = ? COLLATE NOCASE
              )
            """,
            (dc_server_id, dc_id, game_name, tag),
        )
        return cursor.rowcount > 0

    def _connection(self) -> aiosqlite.Connection:
        if self.connection is None:
            raise RuntimeError("Database context has not been entered")
        return self.connection


async def migrate_legacy_json(
    json_file: Path = LEGACY_JSON_FILE,
    database_file: Path = DATABASE_FILE,
) -> MigrationResult:
    json_file = Path(json_file)
    if not json_file.exists():
        return MigrationResult()

    await initialize_database(database_file)
    source_path = str(json_file.resolve())
    async with aiosqlite.connect(database_file) as connection:
        await _configure(connection)
        cursor = await connection.execute(
            "SELECT 1 FROM legacy_imports WHERE source_path = ?", (source_path,)
        )
        if await cursor.fetchone():
            return MigrationResult()

    with json_file.open("r", encoding="utf8") as source:
        data = json.load(source)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = json_file.with_name(f"{json_file.name}.{timestamp}.bak")
    shutil.copy2(json_file, backup_path)

    imported = skipped = invalid = 0
    async with UserSQLiteDB(database_file) as repository:
        users = data.get("users", {}) if isinstance(data, dict) else {}
        if not isinstance(users, dict):
            raise ValueError("Legacy JSON 'users' must be an object")
        for user in users.values():
            if not isinstance(user, dict):
                invalid += 1
                continue
            for account in user.get("valorant_accounts") or []:
                try:
                    await repository.register_user(
                        dc_id=str(user["dc_id"]),
                        dc_global_name=user.get("dc_global_name"),
                        dc_display_name=user.get("dc_display_name"),
                        dc_server_id=str(user["dc_server_id"]),
                        dc_channel_id=str(user["dc_channel_id"]),
                        val_account=account["valorant_account"],
                        val_puuid=str(account["valorant_puuid"]),
                    )
                    cursor = await repository._connection().execute(
                        """
                        UPDATE subscriptions SET last_polled_match_id = ?
                        WHERE id = last_insert_rowid()
                        """,
                        (account.get("last_polled_match_id"),),
                    )
                    imported += cursor.rowcount
                except DuplicateSubscriptionError:
                    skipped += 1
                except (KeyError, TypeError, ValueError):
                    invalid += 1
        await repository._connection().execute(
            """
            INSERT INTO legacy_imports(source_path, backup_path) VALUES (?, ?)
            """,
            (source_path, str(backup_path)),
        )

    return MigrationResult(imported, skipped, invalid, backup_path)
