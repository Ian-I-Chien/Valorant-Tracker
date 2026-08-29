"""Recent player statistics and Discord-friendly player overview rendering."""

from __future__ import annotations

import io
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageOps

from utils import fix_isoformat
from valorant.match_card import AssetCache, _draw_mixed_text, _font


@dataclass(frozen=True)
class AgentSummary:
    name: str
    icon_url: Optional[str]
    games: int
    win_rate: int
    average_acs: int


@dataclass(frozen=True)
class PartySummary:
    label: str
    games: int
    win_rate: int


@dataclass(frozen=True)
class PlayerInfoData:
    riot_id: str
    rank_name: str
    rank_icon_url: Optional[str]
    current_rr: Optional[int]
    matches: int
    win_rate: int
    competitive_record: tuple[int, int]
    unrated_record: tuple[int, int]
    kd: float
    kda: float
    average_acs: int
    kast: int
    headshot_percentage: int
    adr: int
    recent_form: tuple[bool, ...]
    acs_trend: int
    agents: tuple[AgentSummary, ...]
    parties: tuple[PartySummary, ...]
    rr_changes: tuple[int, ...]
    best_match: str


def _played_at(metadata: dict[str, Any]) -> Optional[datetime]:
    value = metadata.get("started_at")
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(fix_isoformat(value))
            return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
        except ValueError:
            pass
    epoch = metadata.get("game_start")
    if isinstance(epoch, (int, float)):
        if epoch > 10_000_000_000:
            epoch /= 1000
        return datetime.fromtimestamp(epoch, tz=timezone.utc)
    return None


def _players(match: dict[str, Any]) -> list[dict[str, Any]]:
    players = match.get("players") or {}
    if isinstance(players, dict):
        return players.get("all_players") or []
    return players


def _target(match: dict[str, Any], puuid: str) -> Optional[dict[str, Any]]:
    return next(
        (player for player in _players(match) if player.get("puuid") == puuid), None
    )


def _won(match: dict[str, Any], player: dict[str, Any]) -> bool:
    team_id = str(player.get("team") or player.get("team_id") or "").casefold()
    teams = match.get("teams") or {}
    if isinstance(teams, dict):
        team = teams.get(team_id) or {}
        return bool(team.get("has_won"))
    team = next(
        (item for item in teams if str(item.get("team_id", "")).casefold() == team_id),
        {},
    )
    rounds = team.get("rounds") or {}
    return rounds.get("won", 0) > rounds.get("lost", 0)


def _kast_rounds(match: dict[str, Any], puuid: str) -> tuple[int, int]:
    successful = 0
    rounds = match.get("rounds") or []
    kills = match.get("kills") or []
    for round_index, round_data in enumerate(rounds):
        stats = next(
            (
                item
                for item in round_data.get("player_stats") or []
                if item.get("player_puuid") == puuid
            ),
            {},
        )
        events = sorted(
            (event for event in kills if event.get("round") == round_index),
            key=lambda event: event.get("kill_time_in_round", 0),
        )
        killed = bool(stats.get("kills", 0))
        assisted = any(
            any(
                assistant.get("assistant_puuid") == puuid
                for assistant in event.get("assistants") or []
            )
            for event in events
        )
        death = next(
            (event for event in events if event.get("victim_puuid") == puuid), None
        )
        survived = death is None
        traded = False
        if death:
            killer = death.get("killer_puuid")
            death_time = death.get("kill_time_in_round") or 0
            team = death.get("victim_team")
            traded = any(
                event.get("victim_puuid") == killer
                and event.get("killer_team") == team
                and 0 <= (event.get("kill_time_in_round") or 0) - death_time <= 3000
                for event in events
            )
        successful += int(killed or assisted or survived or traded)
    return successful, len(rounds)


def _party_label(match: dict[str, Any], player: dict[str, Any]) -> str:
    party_id = player.get("party_id")
    team = player.get("team") or player.get("team_id")
    if not party_id:
        return "SOLO"
    size = sum(
        candidate.get("party_id") == party_id
        and (candidate.get("team") or candidate.get("team_id")) == team
        for candidate in _players(match)
    )
    return {1: "SOLO", 2: "DUO", 3: "TRIO"}.get(size, "STACK")


def build_player_info(
    riot_id: str,
    puuid: str,
    matches: list[dict[str, Any]],
    rank_history: list[dict[str, Any]],
    now: Optional[datetime] = None,
) -> Optional[PlayerInfoData]:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=30)
    rows = []
    for match in matches:
        metadata = match.get("metadata") or {}
        mode = str(metadata.get("mode") or "")
        played_at = _played_at(metadata)
        player = _target(match, puuid)
        if (
            mode.casefold() not in {"competitive", "unrated"}
            or not played_at
            or played_at < cutoff
            or not player
        ):
            continue
        stats = player.get("stats") or {}
        rounds = max(
            int(metadata.get("rounds_played") or len(match.get("rounds") or []) or 1), 1
        )
        won = _won(match, player)
        shots = sum(stats.get(key, 0) for key in ("headshots", "bodyshots", "legshots"))
        kast_success, kast_total = _kast_rounds(match, puuid)
        agent = player.get("character") or "Unknown"
        assets = player.get("assets") or {}
        rows.append(
            {
                "played_at": played_at,
                "mode": mode,
                "won": won,
                "kills": stats.get("kills", 0),
                "deaths": stats.get("deaths", 0),
                "assists": stats.get("assists", 0),
                "score": stats.get("score", 0),
                "rounds": rounds,
                "acs": stats.get("score", 0) / rounds,
                "damage": player.get("damage_made", 0),
                "headshots": stats.get("headshots", 0),
                "shots": shots,
                "kast_success": kast_success,
                "kast_total": kast_total,
                "agent": agent,
                "agent_icon": (assets.get("agent") or {}).get("small"),
                "party": _party_label(match, player),
            }
        )
    if not rows:
        return None
    rows.sort(key=lambda row: row["played_at"], reverse=True)
    kills = sum(row["kills"] for row in rows)
    deaths = sum(row["deaths"] for row in rows)
    assists = sum(row["assists"] for row in rows)
    rounds = sum(row["rounds"] for row in rows)
    wins = sum(row["won"] for row in rows)
    shots = sum(row["shots"] for row in rows)
    split = max(1, len(rows) // 2)
    newer_acs = sum(row["acs"] for row in rows[:split]) / split
    older_rows = rows[split:]
    older_acs = (
        sum(row["acs"] for row in older_rows) / len(older_rows)
        if older_rows
        else newer_acs
    )

    agent_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    party_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        agent_groups[row["agent"]].append(row)
        party_groups[row["party"]].append(row)
    agents = sorted(agent_groups.items(), key=lambda item: (-len(item[1]), item[0]))[:3]
    agent_summaries = tuple(
        AgentSummary(
            name=name.upper(),
            icon_url=group[0]["agent_icon"],
            games=len(group),
            win_rate=round(sum(row["won"] for row in group) / len(group) * 100),
            average_acs=round(sum(row["acs"] for row in group) / len(group)),
        )
        for name, group in agents
    )
    order = {"SOLO": 0, "DUO": 1, "TRIO": 2, "STACK": 3}
    party_summaries = tuple(
        PartySummary(
            label,
            len(group),
            round(sum(row["won"] for row in group) / len(group) * 100),
        )
        for label, group in sorted(
            party_groups.items(), key=lambda item: order[item[0]]
        )
    )
    latest_rank = rank_history[0] if rank_history else {}
    rr_changes = tuple(
        int(item.get("mmr_change_to_last_game") or 0)
        for item in reversed(rank_history[:5])
    )
    best = max(rows, key=lambda row: row["acs"])
    records = {}
    for mode in ("Competitive", "Unrated"):
        group = [row for row in rows if row["mode"].casefold() == mode.casefold()]
        records[mode] = (
            sum(row["won"] for row in group),
            sum(not row["won"] for row in group),
        )
    return PlayerInfoData(
        riot_id=riot_id,
        rank_name=latest_rank.get("currenttierpatched", "Unrated"),
        rank_icon_url=(latest_rank.get("images") or {}).get("small"),
        current_rr=latest_rank.get("ranking_in_tier"),
        matches=len(rows),
        win_rate=round(wins / len(rows) * 100),
        competitive_record=records["Competitive"],
        unrated_record=records["Unrated"],
        kd=kills / max(deaths, 1),
        kda=(kills + assists) / max(deaths, 1),
        average_acs=round(sum(row["score"] for row in rows) / rounds),
        kast=round(
            sum(row["kast_success"] for row in rows)
            / max(sum(row["kast_total"] for row in rows), 1)
            * 100
        ),
        headshot_percentage=round(
            sum(row["headshots"] for row in rows) / max(shots, 1) * 100
        ),
        adr=round(sum(row["damage"] for row in rows) / rounds),
        recent_form=tuple(row["won"] for row in rows[:5]),
        acs_trend=round(newer_acs - older_acs),
        agents=agent_summaries,
        parties=party_summaries,
        rr_changes=rr_changes,
        best_match=f"{best['kills']} / {best['deaths']} / {best['assists']}  •  ACS {round(best['acs'])}  •  {best['agent'].upper()}",
    )


class PlayerInfoCardRenderer:
    WIDTH = 1000
    HEIGHT = 820

    def __init__(self, assets: Optional[AssetCache] = None):
        self.assets = assets or AssetCache()

    async def render(self, data: PlayerInfoData) -> bytes:
        bg, panel, muted, white = "#0f1923", "#192b37", "#91a6b5", "#f4f4f5"
        red, green, cyan = "#ff4655", "#42d6a4", "#45d6c4"
        image = Image.new("RGB", (self.WIDTH, self.HEIGHT), bg)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 14, self.HEIGHT), fill=red)
        draw.text((55, 38), "PLAYER OVERVIEW", font=_font(22, True), fill=red)
        _draw_mixed_text(draw, (55, 77), data.riot_id, 38, white, True)
        draw.text(
            (55, 128), "LAST 30 DAYS  •  NG / RK ONLY", font=_font(15, True), fill=muted
        )
        draw.rounded_rectangle(
            (670, 42, 945, 153), radius=18, fill=panel, outline="#314754", width=2
        )
        rank_icon = await self.assets.get(data.rank_icon_url)
        if rank_icon:
            rank_icon = ImageOps.contain(rank_icon, (78, 78))
            image.paste(rank_icon, (690, 58), rank_icon)
        draw.text((778, 63), data.rank_name.upper(), font=_font(20, True), fill=white)
        rr = "--" if data.current_rr is None else str(data.current_rr)
        draw.text((778, 102), f"CURRENT RR  {rr}", font=_font(14, True), fill=cyan)

        draw.rounded_rectangle((55, 178, 945, 330), radius=22, fill=panel)
        metrics = (
            ("WIN RATE", f"{data.win_rate}%", green),
            ("MATCHES", str(data.matches), white),
            ("K/D", f"{data.kd:.2f}", white),
            ("KDA", f"{data.kda:.2f}", white),
            ("ACS", str(data.average_acs), cyan),
        )
        for x, (label, value, color) in zip((85, 260, 420, 565, 730), metrics):
            draw.text((x, 205), label, font=_font(14, True), fill=muted)
            draw.text((x, 232), value, font=_font(31, True), fill=color)
        cw, cl = data.competitive_record
        uw, ul = data.unrated_record
        details = (
            (85, f"RK  {cw}W {cl}L", green),
            (260, f"NG  {uw}W {ul}L", white),
            (420, f"KAST  {data.kast}%", white),
            (565, f"HS  {data.headshot_percentage}%", white),
            (730, f"ADR  {data.adr}", white),
        )
        for x, value, color in details:
            draw.text((x, 291), value, font=_font(15, True), fill=color)

        draw.text((55, 370), "RECENT FORM", font=_font(15, True), fill=muted)
        for index, won in enumerate(data.recent_form):
            left = 220 + index * 55
            color = green if won else red
            draw.rounded_rectangle((left, 358, left + 42, 400), radius=9, fill=color)
            draw.text(
                (left + 21, 379),
                "W" if won else "L",
                anchor="mm",
                font=_font(17, True),
                fill=bg,
            )
        trend_color = green if data.acs_trend >= 0 else red
        draw.text((535, 370), "ACS TREND", font=_font(15, True), fill=muted)
        draw.text(
            (680, 365),
            f"{'▲' if data.acs_trend >= 0 else '▼'}  {data.acs_trend:+d}",
            font=_font(21, True),
            fill=trend_color,
        )

        draw.text((55, 446), "TOP AGENTS", font=_font(18, True), fill=white)
        draw.text((570, 446), "RR TREND", font=_font(18, True), fill=white)
        for index, agent in enumerate(data.agents):
            top = 485 + index * 77
            draw.rounded_rectangle((55, top, 515, top + 60), radius=13, fill=panel)
            icon = await self.assets.get(agent.icon_url)
            if icon:
                icon = ImageOps.fit(icon, (56, 56))
                image.paste(icon, (67, top + 2), icon)
            draw.text((135, top + 10), agent.name, font=_font(16, True), fill=white)
            draw.text(
                (135, top + 34),
                f"{agent.games} GAMES",
                font=_font(12, True),
                fill=muted,
            )
            draw.text(
                (295, top + 20),
                f"{agent.win_rate}% WR",
                font=_font(14, True),
                fill=green,
            )
            draw.text(
                (410, top + 20),
                f"ACS {agent.average_acs}",
                font=_font(14, True),
                fill=cyan,
            )

        draw.rounded_rectangle((570, 485, 945, 700), radius=18, fill=panel)
        changes = data.rr_changes[-5:]
        draw.text((605, 505), "LAST 5 RK MATCHES", font=_font(12, True), fill=muted)
        draw.text(
            (910, 503),
            f"NET {sum(changes):+d}",
            anchor="ra",
            font=_font(15, True),
            fill=cyan,
        )
        draw.line((605, 586, 910, 586), fill="#49606d", width=2)
        for index, change in enumerate(changes):
            left = 605 + index * 60
            height = min(abs(change) * 2.3, 70)
            box = (
                (left, 586 - height, left + 38, 586)
                if change >= 0
                else (left, 586, left + 38, 586 + height)
            )
            color = green if change >= 0 else red
            draw.rounded_rectangle(box, radius=6, fill=color)
            draw.text(
                (left + 19, 665),
                f"{change:+d}",
                anchor="mm",
                font=_font(12, True),
                fill=color,
            )

        draw.text((55, 747), "BEST RECENT MATCH", font=_font(14, True), fill=muted)
        draw.text((225, 743), data.best_match, font=_font(18, True), fill=white)
        party_text = "  •  ".join(
            f"{item.label} {item.win_rate}% ({item.games})" for item in data.parties
        )
        draw.text(
            (55, 785), party_text or "NO PARTY DATA", font=_font(13, True), fill=muted
        )
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()
