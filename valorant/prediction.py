"""Lightweight, explainable pre-match prediction and image rendering."""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from PIL import Image, ImageDraw

from utils import fix_isoformat
from valorant.match_card import _font, _draw_mixed_text


@dataclass(frozen=True)
class RecentPerformance:
    played_at: datetime
    won: bool
    acs: float
    kd: float


@dataclass(frozen=True)
class PredictionResult:
    riot_id: str
    win_probability: int
    confidence: str
    match_count: int
    recent_form: tuple[bool, ...]
    average_acs: int
    average_kd: float
    acs_trend: float
    reasons: tuple[str, ...]


def _timestamp(match: dict[str, Any]) -> Optional[datetime]:
    metadata = match.get("metadata") or {}
    value = metadata.get("started_at") or metadata.get("game_start_patched")
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


def _find_player(match: dict[str, Any], puuid: str) -> Optional[dict[str, Any]]:
    players = match.get("players") or {}
    if isinstance(players, dict):
        candidates = players.get("all_players") or []
    else:
        candidates = players
    return next((player for player in candidates if player.get("puuid") == puuid), None)


def _won(match: dict[str, Any], player: dict[str, Any]) -> Optional[bool]:
    team_id = str(player.get("team_id") or player.get("team") or "").lower()
    teams = match.get("teams") or {}
    if isinstance(teams, dict):
        team = teams.get(team_id) or teams.get(team_id.capitalize())
        return bool(team.get("has_won")) if isinstance(team, dict) else None
    for team in teams:
        if str(team.get("team_id", "")).lower() != team_id:
            continue
        if "won" in team:
            return bool(team["won"])
        rounds = team.get("rounds") or {}
        return rounds.get("won", 0) > rounds.get("lost", 0)
    return None


def extract_recent_performances(
    matches: list[dict[str, Any]],
    puuid: str,
    now: Optional[datetime] = None,
    days: int = 30,
) -> list[RecentPerformance]:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    results = []
    for match in matches:
        metadata = match.get("metadata") or {}
        queue = metadata.get("queue") or {}
        queue_name = queue.get("name") if isinstance(queue, dict) else queue
        mode = str(metadata.get("mode") or queue_name or "")
        if mode.casefold() not in {"competitive", "unrated"}:
            continue
        played_at = _timestamp(match)
        player = _find_player(match, puuid)
        if not played_at or played_at.astimezone(timezone.utc) < cutoff or not player:
            continue
        won = _won(match, player)
        if won is None:
            continue
        stats = player.get("stats") or {}
        rounds = (match.get("metadata") or {}).get("rounds_played")
        if not isinstance(rounds, (int, float)) or rounds <= 0:
            rounds = max(stats.get("kills", 0) + stats.get("deaths", 0), 1)
        kills = stats.get("kills", 0)
        deaths = stats.get("deaths", 0)
        results.append(
            RecentPerformance(
                played_at=played_at,
                won=won,
                acs=stats.get("score", 0) / rounds,
                kd=kills / max(deaths, 1),
            )
        )
    return sorted(results, key=lambda item: item.played_at, reverse=True)


def predict_next_match(
    riot_id: str, performances: list[RecentPerformance]
) -> Optional[PredictionResult]:
    if not performances:
        return None
    recent = performances[:20]
    wins = sum(item.won for item in recent)
    win_rate = wins / len(recent)
    average_acs = sum(item.acs for item in recent) / len(recent)
    average_kd = sum(item.kd for item in recent) / len(recent)
    split = max(1, len(recent) // 2)
    newer_acs = sum(item.acs for item in recent[:split]) / split
    older = recent[split:]
    older_acs = sum(item.acs for item in older) / len(older) if older else newer_acs
    acs_trend = newer_acs - older_acs

    probability = 50
    probability += (win_rate - 0.5) * 36
    probability += max(-8, min(8, (average_acs - 200) / 10))
    probability += max(-6, min(6, (average_kd - 1) * 12))
    probability += max(-4, min(4, acs_trend / 12))
    probability = round(max(25, min(75, probability)))

    reasons = []
    reasons.append(f"Recent record: {wins}W {len(recent) - wins}L")
    if average_acs >= 220:
        reasons.append("ACS is above the 220 baseline")
    elif average_acs < 180:
        reasons.append("ACS is below the 180 baseline")
    if acs_trend >= 15:
        reasons.append("Recent ACS is trending upward")
    elif acs_trend <= -15:
        reasons.append("Recent ACS is trending downward")
    if len(reasons) < 3:
        reasons.append("Performance is relatively stable")

    confidence = "LOW" if len(recent) < 5 else "MEDIUM" if len(recent) < 10 else "HIGH"
    return PredictionResult(
        riot_id=riot_id,
        win_probability=probability,
        confidence=confidence,
        match_count=len(recent),
        recent_form=tuple(item.won for item in recent[:5]),
        average_acs=round(average_acs),
        average_kd=average_kd,
        acs_trend=acs_trend,
        reasons=tuple(reasons[:3]),
    )


class PredictionCardRenderer:
    WIDTH = 920
    HEIGHT = 620

    def render(self, result: PredictionResult) -> bytes:
        image = Image.new("RGB", (self.WIDTH, self.HEIGHT), "#0f1923")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 14, self.HEIGHT), fill="#ff4655")
        draw.text(
            (55, 38), "NEXT MATCH PREDICTION", font=_font(24, True), fill="#ff4655"
        )
        _draw_mixed_text(draw, (55, 82), result.riot_id, 36, "#f4f4f5", True)

        draw.rounded_rectangle((55, 145, 865, 294), radius=22, fill="#172733")
        draw.text((85, 173), "WIN CHANCE", font=_font(18, True), fill="#91a6b5")
        draw.text(
            (85, 205),
            f"{result.win_probability}%",
            font=_font(58, True),
            fill="#f4f4f5",
        )
        bar_left, bar_top, bar_right = 320, 211, 820
        draw.rounded_rectangle(
            (bar_left, bar_top, bar_right, bar_top + 30), radius=15, fill="#293946"
        )
        fill_right = bar_left + int(
            (bar_right - bar_left) * result.win_probability / 100
        )
        draw.rounded_rectangle(
            (bar_left, bar_top, fill_right, bar_top + 30), radius=15, fill="#ff4655"
        )
        draw.text(
            (320, 254),
            f"CONFIDENCE  {result.confidence}",
            font=_font(17, True),
            fill="#d6e0e6",
        )

        labels = (
            ("MATCHES / 30D", str(result.match_count)),
            ("AVG ACS", str(result.average_acs)),
            ("AVG K/D", f"{result.average_kd:.2f}"),
        )
        for index, (label, value) in enumerate(labels):
            left = 55 + index * 270
            draw.text((left, 330), label, font=_font(15, True), fill="#91a6b5")
            draw.text((left, 360), value, font=_font(30, True), fill="#f4f4f5")

        draw.text((55, 423), "RECENT FORM", font=_font(15, True), fill="#91a6b5")
        for index, won in enumerate(result.recent_form):
            left = 210 + index * 54
            color = "#42d6a4" if won else "#ff4655"
            draw.rounded_rectangle((left, 414, left + 40, 454), radius=8, fill=color)
            draw.text(
                (left + 20, 434),
                "W" if won else "L",
                anchor="mm",
                font=_font(17, True),
                fill="#0f1923",
            )

        for index, reason in enumerate(result.reasons):
            color = (
                "#42d6a4" if index == 0 and result.win_probability >= 50 else "#d6e0e6"
            )
            draw.text((55, 486 + index * 31), "• " + reason, font=_font(17), fill=color)
        draw.text(
            (55, 584),
            "Entertainment prediction • Based only on the last 30 days",
            font=_font(14),
            fill="#6f8594",
        )
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()
