"""Private operational health reporting for server administrators."""

import os
import stat
from pathlib import Path

import discord

from database.storage_sqlite import UserSQLiteDB
from valorant.api import KEY_POOL


def enforce_private_file(path: Path) -> None:
    """Restrict a sensitive existing file to its owner on POSIX hosts."""
    if os.name == "posix" and path.exists():
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def task_running(task) -> bool:
    if task is None:
        return False
    if hasattr(task, "is_running"):
        return bool(task.is_running())
    return not task.done()


async def build_health_report(bot, match_polling, shop_service=None) -> str:
    checks = {
        "Discord": bool(bot.is_ready()),
        "Match polling": task_running(match_polling),
        "Riot API keys": any(not state.disabled for state in KEY_POOL.states),
    }
    try:
        async with UserSQLiteDB() as repository:
            await (await repository._connection().execute("SELECT 1")).fetchone()
        checks["Database"] = True
    except Exception:
        checks["Database"] = False

    details = []
    if shop_service is not None:
        checks["Shop polling"] = task_running(
            getattr(bot, "shop_notification_task", None)
        )
        try:
            await shop_service.vault.initialize()
            health = await shop_service.credential_health()
            details.append(
                f"Shop logins: {health['active']} active, "
                f"{health['expired']} need /login again"
            )
        except Exception:
            checks["Shop credentials"] = False

    lines = [f"{'✅' if healthy else '❌'} {name}" for name, healthy in checks.items()]
    lines.extend(details)
    return "**Valorant Tracker health**\n" + "\n".join(lines)


async def show_health(interaction: discord.Interaction, bot, match_polling) -> None:
    await interaction.response.defer(ephemeral=True)
    report = await build_health_report(
        bot, match_polling, getattr(bot, "shop_service", None)
    )
    await interaction.edit_original_response(content=report)
