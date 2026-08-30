import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from help_command import build_help_embed, show_help


def test_help_covers_registered_slash_commands_and_embed_limits():
    from bot import bot

    embed = build_help_embed()
    text = "\n".join(field.value for field in embed.fields)
    for command in bot.tree.get_commands():
        assert f"`/{command.name}" in text
    assert bot.tree.get_command("help") is not None
    assert len(embed) <= 6000
    assert len(embed.fields) <= 25
    assert all(len(field.value) <= 1024 for field in embed.fields)
    assert "do not enable match tracking" in text
    assert "requires Manage Server" in text


@pytest.mark.parametrize("guild", [None, SimpleNamespace(id=123)])
def test_help_is_private_and_works_without_guild_or_player_data(guild):
    interaction = SimpleNamespace(
        guild=guild, response=SimpleNamespace(send_message=AsyncMock())
    )
    asyncio.run(show_help(interaction))
    interaction.response.send_message.assert_awaited_once()
    kwargs = interaction.response.send_message.call_args.kwargs
    assert kwargs["ephemeral"] is True
    assert kwargs["embed"].title == "Valorant Tracker — Help"
