from __future__ import annotations

from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy import func, select

from app.economy import (
    BLOODSUCKER_KILL_HABAR,
    CORRECT_VOTE_HABAR,
    DOCTOR_SAVE_HABAR,
    SCOUT_THREAT_HABAR,
    EconomyService,
)
from app.economy_models import GameHabarEvent
from app.game.rules import HOSTILE_ROLES, MAFIA_ROLES, unique_vote_winner
from app.models import DayVote, Game, NightAction
from app.private_art_service import PrivateArtGameService


class EconomyGameService(PrivateArtGameService):
    """The normal game plus persistent, cosmetic-only habar progression."""

    def __init__(self, *args, economy_service: EconomyService, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.economy = economy_service

    async def _start_zone_game(self, game_id: int, host_user_id: int) -> None:
        await super()._start_zone_game(game_id, host_user_id)
        async with self.session_factory() as session:
            players = await self._players(session, game_id)
        await self.economy.start_game(game_id, [player.user_id for player in players])

    async def _reward_if_under_limit(
        self,
        session,
        *,
        game_id: int,
        user_id: int,
        event_key: str,
        event_type: str,
        amount: int,
        max_events: int,
        target_user_id: int | None = None,
    ) -> int:
        count = int(
            await session.scalar(
                select(func.count(GameHabarEvent.id)).where(
                    GameHabarEvent.game_id == game_id,
                    GameHabarEvent.user_id == user_id,
                    GameHabarEvent.event_type == event_type,
                    GameHabarEvent.amount > 0,
                )
            )
            or 0
        )
        if count >= max_events:
            return 0
        return await self.economy.add_game_reward(
            session,
            game_id=game_id,
            user_id=user_id,
            event_key=event_key,
            event_type=event_type,
            amount=amount,
            target_user_id=target_user_id,
        )

    async def _resolve_night(self, game_id: int) -> None:
        # Reward state is derived from persisted NightAction rows before the base
        # service resolves deaths. Event keys make every award idempotent.
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "active" or game.phase != "night":
                return
            players = await self._players(session, game_id, alive_only=True)
            by_id = {player.user_id: player for player in players}
            actions = list(
                (
                    await session.scalars(
                        select(NightAction).where(
                            NightAction.game_id == game_id,
                            NightAction.day_number == game.day_number,
                        )
                    )
                ).all()
            )

            mafia_ids = [player.user_id for player in players if player.role in MAFIA_ROLES]
            mafia_targets = [
                action.target_user_id for action in actions if action.action_type == "mafia_kill"
            ]
            mafia_target_id: int | None = None
            if mafia_ids and len(mafia_targets) == len(mafia_ids) and len(set(mafia_targets)) == 1:
                mafia_target_id = mafia_targets[0]

            blood_action = next(
                (action for action in actions if action.action_type == "bloodsucker_kill"),
                None,
            )
            doctor_action = next(
                (action for action in actions if action.action_type == "doctor_heal"),
                None,
            )
            doctor_target_id = doctor_action.target_user_id if doctor_action else None
            blood_target_id = blood_action.target_user_id if blood_action else None
            attacked = {target for target in (mafia_target_id, blood_target_id) if target is not None}

            # Scout earns only for a real threat, maximum twice per game.
            for action in actions:
                if action.action_type != "sheriff_check":
                    continue
                target = by_id.get(action.target_user_id)
                if target is None or target.role not in HOSTILE_ROLES:
                    continue
                await self._reward_if_under_limit(
                    session,
                    game_id=game_id,
                    user_id=action.actor_user_id,
                    event_key=f"scout:{game.day_number}:{action.actor_user_id}",
                    event_type="scout_threat",
                    amount=SCOUT_THREAT_HABAR,
                    max_events=2,
                    target_user_id=action.target_user_id,
                )

            # Doctor earns only when the chosen target was actually attacked.
            if doctor_action is not None and doctor_target_id in attacked:
                await self._reward_if_under_limit(
                    session,
                    game_id=game_id,
                    user_id=doctor_action.actor_user_id,
                    event_key=f"doctor:{game.day_number}:{doctor_action.actor_user_id}",
                    event_type="doctor_save",
                    amount=DOCTOR_SAVE_HABAR,
                    max_events=2,
                    target_user_id=doctor_target_id,
                )

            # Bloodsucker earns only for a victim that is not saved by the doctor.
            if (
                blood_action is not None
                and blood_target_id is not None
                and blood_target_id != doctor_target_id
            ):
                await self._reward_if_under_limit(
                    session,
                    game_id=game_id,
                    user_id=blood_action.actor_user_id,
                    event_key=f"blood:{game.day_number}:{blood_action.actor_user_id}",
                    event_type="bloodsucker_kill",
                    amount=BLOODSUCKER_KILL_HABAR,
                    max_events=3,
                    target_user_id=blood_target_id,
                )

            # A successful Bandit consensus steals from the victim's temporary
            # run wallet. Nothing is ever taken from the permanent stash.
            if mafia_target_id is not None and mafia_target_id != doctor_target_id:
                await self.economy.rob_victim(
                    session,
                    game_id=game_id,
                    day_number=game.day_number,
                    victim_user_id=mafia_target_id,
                    bandit_user_ids=mafia_ids,
                )

            await session.commit()

        await super()._resolve_night(game_id)

    async def _resolve_vote(self, game_id: int) -> None:
        # Pay correct votes only when a unique hostile target is actually going
        # to be expelled. A runoff round is handled when that round resolves.
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is not None and game.status == "active" and game.phase in {"voting", "runoff"}:
                players = await self._players(session, game_id, alive_only=True)
                by_id = {player.user_id: player for player in players}
                votes = list(
                    (
                        await session.scalars(
                            select(DayVote).where(
                                DayVote.game_id == game_id,
                                DayVote.day_number == game.day_number,
                                DayVote.vote_round == game.vote_round,
                            )
                        )
                    ).all()
                )
                winner_id, _ = unique_vote_winner([vote.target_user_id for vote in votes])
                winner = by_id.get(winner_id) if winner_id is not None else None
                if winner is not None and winner.role in HOSTILE_ROLES:
                    for vote in votes:
                        if vote.target_user_id != winner_id:
                            continue
                        await self._reward_if_under_limit(
                            session,
                            game_id=game_id,
                            user_id=vote.voter_user_id,
                            event_key=f"vote:{game.day_number}:{vote.voter_user_id}",
                            event_type="correct_vote",
                            amount=CORRECT_VOTE_HABAR,
                            max_events=3,
                            target_user_id=winner_id,
                        )
                    await session.commit()

        await super()._resolve_vote(game_id)

    async def _finish_if_winner(self, game_id: int) -> bool:
        finished = await super()._finish_if_winner(game_id)
        if not finished:
            return False

        settlements = await self.economy.settle_finished_game(game_id)
        for result in settlements:
            if result.amount <= 0:
                continue
            text = (
                "📦 <b>ХОДКА ЗАВЕРШЕНА</b>\n\n"
                f"🎒 Винесено із Зони: <b>+{result.amount} хабару</b>\n"
                f"📦 У схроні: <b>{result.balance}</b>"
            )
            if result.trophy_name:
                text += f"\n\n🧿 Знайдено трофей: <b>{result.trophy_name}</b>"
            try:
                await self.bot.send_message(result.user_id, text)
            except TelegramForbiddenError:
                pass
        return True
