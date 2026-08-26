from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LiveZoneEffect:
    code: str
    title: str
    text: str
    phase: str
    seconds_delta: int


NIGHT_EFFECTS = (
    LiveZoneEffect(
        code="long_dark",
        title="🌫 Затяжна ніч",
        text="Туман ліг щільною стіною. Нічний етап отримує <b>+30 секунд</b>.",
        phase="night",
        seconds_delta=30,
    ),
    LiveZoneEffect(
        code="psi_flash",
        title="🧠 Пси-спалах",
        text="Короткий пси-імпульс змушує діяти швидше. На ніч <b>-30 секунд</b>.",
        phase="night",
        seconds_delta=-30,
    ),
)

DISCUSSION_EFFECTS = (
    LiveZoneEffect(
        code="emission",
        title="☢️ Наближається викид",
        text=(
            "ПДА попереджають про небезпечний фронт. Сходку доведеться завершити швидше: "
            "<b>-60 секунд</b> до обговорення."
        ),
        phase="discussion",
        seconds_delta=-60,
    ),
    LiveZoneEffect(
        code="psi_noise",
        title="🧠 Пси-перешкоди",
        text="У голові гуде, думки плутаються. На обговорення <b>-30 секунд</b>.",
        phase="discussion",
        seconds_delta=-30,
    ),
)

VOTING_EFFECTS = (
    LiveZoneEffect(
        code="pda_noise",
        title="📟 Збій мережі ПДА",
        text="Канал нестабільний. На таємне голосування цього разу <b>-30 секунд</b>.",
        phase="voting",
        seconds_delta=-30,
    ),
)


def _rng(game_id: int, day_number: int, phase: str) -> random.Random:
    payload = f"live-zone:{game_id}:{day_number}:{phase}".encode()
    seed = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return random.Random(seed)


def live_zone_effect(
    game_id: int,
    day_number: int,
    phase: str,
    *,
    chance: float = 0.45,
) -> LiveZoneEffect | None:
    """Return a deterministic effect for a phase so restarts keep the same event."""
    pools = {
        "night": NIGHT_EFFECTS,
        "discussion": DISCUSSION_EFFECTS,
        "voting": VOTING_EFFECTS,
    }
    pool = pools.get(phase)
    if not pool:
        return None
    rng = _rng(game_id, day_number, phase)
    if rng.random() >= chance:
        return None
    return rng.choice(pool)


def phase_seconds(base_seconds: int, effect: LiveZoneEffect | None, *, minimum: int = 30) -> int:
    if effect is None:
        return base_seconds
    return max(minimum, base_seconds + effect.seconds_delta)
