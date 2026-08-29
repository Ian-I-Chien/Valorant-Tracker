import asyncio
from types import SimpleNamespace

import commands


class FakeRepository:
    subscription = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def find_subscription(self, server_id, account_query):
        return self.subscription

    async def register_user(self, **kwargs):
        raise AssertionError("an ad-hoc lookup must not create a subscription")


def test_registered_player_uses_subscription_without_account_lookup(monkeypatch):
    FakeRepository.subscription = SimpleNamespace(
        valorant_account="Registered#TW1", valorant_puuid="registered-puuid"
    )
    monkeypatch.setattr(commands, "UserSQLiteDB", FakeRepository)

    async def unexpected_fetch(self):
        raise AssertionError("registered players should use the stored PUUID")

    monkeypatch.setattr(commands.ValorantPlayer, "fetch_account", unexpected_fetch)

    result = asyncio.run(commands.resolve_player_query("guild-1", "Registered"))

    assert result == commands.ResolvedPlayer("Registered#TW1", "registered-puuid")


def test_unregistered_full_riot_id_is_resolved_without_registration(monkeypatch):
    FakeRepository.subscription = None
    monkeypatch.setattr(commands, "UserSQLiteDB", FakeRepository)

    async def fetch_account(self):
        self.player_name = "Canonical Name"
        self.player_tag = "APAC"
        return {"puuid": "lookup-puuid"}

    monkeypatch.setattr(commands.ValorantPlayer, "fetch_account", fetch_account)

    result = asyncio.run(
        commands.resolve_player_query("guild-1", "  lookup name # tag  ")
    )

    assert result == commands.ResolvedPlayer("Canonical Name#APAC", "lookup-puuid")


def test_unregistered_short_name_is_not_sent_to_account_api(monkeypatch):
    FakeRepository.subscription = None
    monkeypatch.setattr(commands, "UserSQLiteDB", FakeRepository)

    async def unexpected_fetch(self):
        raise AssertionError("an unregistered lookup requires name#tag")

    monkeypatch.setattr(commands.ValorantPlayer, "fetch_account", unexpected_fetch)

    assert asyncio.run(commands.resolve_player_query("guild-1", "unknown")) is None
