import asyncio
import json

from database.storage_sqlite import (
    DuplicateSubscriptionError,
    UserSQLiteDB,
    migrate_legacy_json,
)


def run(coroutine):
    return asyncio.run(coroutine)


def test_register_checkpoint_and_owner_scoped_delete(tmp_path):
    database_file = tmp_path / "tracker.db"

    async def scenario():
        async with UserSQLiteDB(database_file) as repository:
            await repository.register_user(
                "user-1", "one", "One", "server-1", "channel-1", "Ace#AP", "p1"
            )
            await repository.register_user(
                "user-2", "two", "Two", "server-2", "channel-2", "Ace#AP", "p1"
            )
        async with UserSQLiteDB(database_file) as repository:
            subscriptions = await repository.list_subscriptions()
            first = subscriptions[0]
            assert await repository.update_last_polled_match(first.id, None, "match-1")
            assert not await repository.update_last_polled_match(
                first.id, None, "stale-match"
            )
            assert await repository.remove_valorant_account(
                "user-1", "server-1", "ace#ap"
            )
        async with UserSQLiteDB(database_file) as repository:
            remaining = await repository.list_subscriptions()
            assert len(remaining) == 1
            assert remaining[0].discord_user_id == "user-2"

    run(scenario())


def test_legacy_migration_is_idempotent_and_keeps_source(tmp_path):
    json_file = tmp_path / "valorant_data.json"
    database_file = tmp_path / "tracker.db"
    payload = {
        "users": {
            "user-1": {
                "dc_id": "user-1",
                "dc_global_name": "one",
                "dc_display_name": "One",
                "dc_server_id": "server-1",
                "dc_channel_id": "channel-1",
                "valorant_accounts": [
                    {
                        "valorant_account": "Ace#AP",
                        "valorant_puuid": "p1",
                        "last_polled_match_id": "match-1",
                    }
                ],
            }
        }
    }
    json_file.write_text(json.dumps(payload), encoding="utf8")

    first = run(migrate_legacy_json(json_file, database_file))
    second = run(migrate_legacy_json(json_file, database_file))

    assert first.imported == 1
    assert first.backup_path and first.backup_path.exists()
    assert second.imported == 0
    assert json_file.exists()

    async def read_rows():
        async with UserSQLiteDB(database_file) as repository:
            return await repository.list_subscriptions()

    subscriptions = run(read_rows())
    assert subscriptions[0].last_polled_match_id == "match-1"


def test_duplicate_subscription_rolls_back_entire_registration(tmp_path):
    database_file = tmp_path / "tracker.db"

    async def scenario():
        async with UserSQLiteDB(database_file) as repository:
            await repository.register_user(
                "owner", "owner", "Owner", "server", "channel", "Ace#AP", "p1"
            )
            try:
                await repository.register_user(
                    "other", "other", "Other", "server", "channel", "Ace#AP", "p1"
                )
            except DuplicateSubscriptionError:
                pass
            else:
                raise AssertionError("duplicate registration should fail")

        async with UserSQLiteDB(database_file) as repository:
            cursor = await repository._connection().execute(
                "SELECT COUNT(*) FROM discord_users"
            )
            assert (await cursor.fetchone())[0] == 1

    run(scenario())
