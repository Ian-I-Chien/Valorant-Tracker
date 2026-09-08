import asyncio
import os
import stat
from types import SimpleNamespace

import health_command


class FakeRepository:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def _connection(self):
        return self

    async def execute(self, query):
        return self

    async def fetchone(self):
        return (1,)


class RunningLoop:
    def is_running(self):
        return True


def test_health_report_contains_core_services(monkeypatch):
    monkeypatch.setattr(health_command, "UserSQLiteDB", FakeRepository)
    monkeypatch.setattr(
        health_command,
        "KEY_POOL",
        SimpleNamespace(states=[SimpleNamespace(disabled=False)]),
    )
    bot = SimpleNamespace(is_ready=lambda: True)

    report = asyncio.run(health_command.build_health_report(bot, RunningLoop()))

    assert "✅ Discord" in report
    assert "✅ Match polling" in report
    assert "✅ Riot API keys" in report
    assert "✅ Database" in report


def test_sensitive_file_permissions_are_owner_only(tmp_path):
    path = tmp_path / "secret"
    path.write_text("secret")

    health_command.enforce_private_file(path)

    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
