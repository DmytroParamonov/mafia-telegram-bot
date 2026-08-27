from __future__ import annotations

import html

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import BufferedInputFile

from app.game.rules import MAFIA_ROLES, ROLE_DESCRIPTIONS, ROLE_FACTIONS, ROLE_TITLES, Role
from app.keyboards import role_card_help_keyboard
from app.playtest_service import PlaytestGameService
from app.private_role_art import ROLE_ART, load_private_role_art, role_art_assignments


class PrivateArtGameService(PlaytestGameService):
    """Playtest service with authored role art kept strictly inside personal PDAs."""

    async def _send_role_cards(self, game_id: int) -> None:
        async with self.session_factory() as session:
            players = await self._players(session, game_id)

        labels = self._labels(game_id, players)
        bandits = [player for player in players if player.role in MAFIA_ROLES]

        authored_art = {}
        for art_role in ROLE_ART:
            role_user_ids = [
                player.user_id
                for player in players
                if (Role.MAFIA.value if player.role in MAFIA_ROLES else player.role) == art_role
            ]
            authored_art.update(role_art_assignments(game_id, art_role, role_user_ids))

        for player in players:
            role = player.role or Role.CIVILIAN.value
            caption = (
                f"📟 <b>{html.escape(labels[player.user_id])}</b>\n\n"
                f"Твоя роль: <b>{ROLE_TITLES[role]}</b>\n"
                f"Фракція: <b>{ROLE_FACTIONS[role]}</b>\n\n"
                f"{ROLE_DESCRIPTIONS[role]}"
            )
            if role in MAFIA_ROLES:
                allies = [ally for ally in bandits if ally.user_id != player.user_id]
                if allies:
                    caption += "\n\n🤝 <b>Твоя братва:</b>\n" + "\n".join(
                        f"• {html.escape(labels[ally.user_id])}" for ally in allies
                    )
                else:
                    caption += "\n\n🤝 Цієї ходки працюєш один."
            caption += "\n\n📵 Не світи ПДА іншим."
            markup = role_card_help_keyboard(game_id)

            art = authored_art.get(player.user_id)
            if art is not None:
                try:
                    image = load_private_role_art(art)
                    await self.bot.send_photo(
                        player.user_id,
                        BufferedInputFile(image, filename=f"pda_{art.role}_{art.asset_key}.jpg"),
                        caption=caption,
                        reply_markup=markup,
                    )
                    continue
                except (OSError, ValueError, TelegramBadRequest, TelegramForbiddenError):
                    # Missing/invalid authored art must never break role delivery.
                    pass

            # No procedural picture fallback: if a local authored portrait is absent,
            # send the role as text so it is obvious which server file still needs fixing.
            try:
                await self.bot.send_message(player.user_id, caption, reply_markup=markup)
            except TelegramForbiddenError:
                pass
