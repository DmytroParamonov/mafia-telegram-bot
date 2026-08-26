from __future__ import annotations

import html

from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import BufferedInputFile

from app.game.rules import MAFIA_ROLES, ROLE_DESCRIPTIONS, ROLE_FACTIONS, ROLE_TITLES, Role
from app.keyboards import role_card_help_keyboard
from app.playtest_service import PlaytestGameService
from app.private_role_art import bandit_art_assignments, load_private_role_art
from app.role_cards import load_ready_role_card
from app.zone_features import callsigns_for


class PrivateArtGameService(PlaytestGameService):
    """Playtest service with authored role art kept strictly inside personal PDAs."""

    async def _send_role_cards(self, game_id: int) -> None:
        async with self.session_factory() as session:
            players = await self._players(session, game_id)

        labels = self._labels(game_id, players)
        callsigns = callsigns_for(game_id, [player.user_id for player in players])
        bandits = [player for player in players if player.role in MAFIA_ROLES]
        bandit_art = bandit_art_assignments(game_id, [player.user_id for player in bandits])

        for player in players:
            role = player.role or Role.CIVILIAN.value
            callsign = callsigns[player.user_id]
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

            try:
                if role in MAFIA_ROLES:
                    # The authored bandit portrait is sent only to this Telegram user.
                    # It never appears in the group lobby, public roster or death text.
                    try:
                        image = load_private_role_art(bandit_art[player.user_id])
                    except (OSError, ValueError):
                        image = load_ready_role_card(role, callsign)
                    filename = "pda_bandit.jpg"
                else:
                    image = load_ready_role_card(role, callsign)
                    filename = f"pda_{role}_{callsign}.jpg"

                await self.bot.send_photo(
                    player.user_id,
                    BufferedInputFile(image, filename=filename),
                    caption=caption,
                    reply_markup=markup,
                )
            except (OSError, ValueError):
                try:
                    await self.bot.send_message(player.user_id, caption, reply_markup=markup)
                except TelegramForbiddenError:
                    pass
            except TelegramForbiddenError:
                pass
