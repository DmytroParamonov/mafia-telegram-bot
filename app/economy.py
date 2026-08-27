from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.economy_models import (
    EconomyAccount,
    EconomyTransaction,
    GameEconomy,
    GameHabarEvent,
    ShopItem,
    TrophyCatalog,
    UserInventory,
    UserShowcase,
    UserTrophy,
)
from app.game.rules import team_for_role
from app.models import DayVote, Game, GamePlayer, User, utc_ts

GAME_START_HABAR = 20
GAME_WIN_HABAR = 50
GAME_SURVIVE_HABAR = 15
SCOUT_THREAT_HABAR = 15
DOCTOR_SAVE_HABAR = 20
CORRECT_VOTE_HABAR = 10
BLOODSUCKER_KILL_HABAR = 20
GAME_MINT_CAP = 150
BANDIT_LOOT_PERCENT = 50
BANDIT_LOOT_CAP = 30

RANKS: tuple[tuple[int, str], ...] = (
    (0, "Новачок"),
    (500, "Бродяга"),
    (1_500, "Сталкер"),
    (3_500, "Досвідчений"),
    (7_500, "Ветеран"),
    (15_000, "Майстер"),
    (30_000, "Легенда Зони"),
)

SHOP_CATALOG: tuple[dict[str, object], ...] = (
    {"key": "pda_military", "category": "theme", "name": "🪖 Військовий ПДА", "description": "Суворе польове оформлення ПДА.", "price": 600},
    {"key": "pda_dark", "category": "theme", "name": "🌑 Темний ПДА", "description": "Темний інтерфейс без зайвого світла.", "price": 1_000},
    {"key": "pda_red", "category": "theme", "name": "🔴 Аварійний ПДА", "description": "Червоний тривожний стиль.", "price": 1_500},
    {"key": "pda_field", "category": "theme", "name": "☢️ Польовий ПДА", "description": "Потертий інтерфейс досвідченого ходока.", "price": 2_500},
    {"key": "pda_black", "category": "theme", "name": "⬛ Чорний ПДА", "description": "Рідкісне мінімалістичне оформлення.", "price": 4_000},
    {"key": "pda_legend", "category": "theme", "name": "⭐ ПДА Легенди", "description": "Престижне оформлення для найупертіших.", "price": 10_000},
    {"key": "title_looter", "category": "title", "name": "«Мисливець за хабаром»", "description": "Косметичний титул під званням.", "price": 800},
    {"key": "title_detector", "category": "title", "name": "«Шукач артефактів»", "description": "Косметичний титул під званням.", "price": 1_200},
    {"key": "title_stash", "category": "title", "name": "«Хазяїн схрону»", "description": "Косметичний титул під званням.", "price": 2_500},
    {"key": "title_zoneborn", "category": "title", "name": "«Породжений Зоною»", "description": "Дорогий косметичний титул.", "price": 5_000},
    {"key": "showcase_2", "category": "slot", "name": "🧿 Другий слот вітрини", "description": "Дозволяє виставити 2 трофеї.", "price": 1_000, "effect_value": 2},
    {"key": "showcase_3", "category": "slot", "name": "🧿 Третій слот вітрини", "description": "Дозволяє виставити 3 трофеї.", "price": 2_500, "effect_value": 3},
    {"key": "showcase_4", "category": "slot", "name": "🧿 Четвертий слот вітрини", "description": "Дозволяє виставити 4 трофеї.", "price": 5_000, "effect_value": 4},
)

TROPHY_CATALOG: tuple[dict[str, str], ...] = (
    {"key": "rusty_case", "name": "⚪ Іржава гільза", "description": "Нічого особливого. Але вона пережила більше ходок, ніж дехто зі сталкерів.", "rarity": "common"},
    {"key": "empty_medkit", "name": "⚪ Порожня аптечка", "description": "Колись комусь допомогла. Можливо.", "rarity": "common"},
    {"key": "broken_dosimeter", "name": "⚪ Зламаний дозиметр", "description": "Мовчить навіть там, де краще було б пищати.", "rarity": "common"},
    {"key": "old_patch", "name": "⚪ Стара нашивка", "description": "Вицвіла настільки, що вже не зрозуміти, кому належала.", "rarity": "common"},
    {"key": "map_piece", "name": "⚪ Клапоть карти", "description": "На краю олівцем намальований хрестик.", "rarity": "common"},
    {"key": "unknown_tag", "name": "🔵 Жетон невідомого сталкера", "description": "Ім'я стерте. Номер ще читається.", "rarity": "rare"},
    {"key": "mutant_tooth", "name": "🔵 Зуб мутанта", "description": "Надто великий, щоб хотілося знати власника.", "rarity": "rare"},
    {"key": "damaged_pda", "name": "🔵 Пошкоджений ПДА", "description": "Екран мертвий, пам'ять зашифрована.", "rarity": "rare"},
    {"key": "artifact_case", "name": "🔵 Контейнер для артефакту", "description": "Порожній. І все одно важкий.", "rarity": "rare"},
    {"key": "black_detector", "name": "🟣 Чорний детектор", "description": "Модель без маркування, якої немає в каталогах.", "rarity": "epic"},
    {"key": "bloody_tag", "name": "🟣 Закривавлений жетон", "description": "Кров давно висохла. Ім'я навмисно подряпане.", "rarity": "epic"},
    {"key": "strange_artifact", "name": "🟣 Дивний артефакт", "description": "Навіть крізь контейнер від нього стає не по собі.", "rarity": "epic"},
    {"key": "gold_tag", "name": "🟡 Золотий жетон", "description": "Таких не видають. Саме тому він такий цікавий.", "rarity": "legendary"},
    {"key": "ghost_pda", "name": "🟡 ПДА «Привид»", "description": "Іноді вмикається сам. Ненадовго.", "rarity": "legendary"},
    {"key": "black_artifact", "name": "🟡 Чорний артефакт", "description": "Ніхто не знає, що він робить. І перевіряти не поспішають.", "rarity": "legendary"},
)

THEME_LABELS = {
    "pda_standard": "📟 Стандартний ПДА",
    **{str(item["key"]): str(item["name"]) for item in SHOP_CATALOG if item["category"] == "theme"},
}


@dataclass(frozen=True, slots=True)
class Settlement:
    user_id: int
    amount: int
    balance: int
    trophy_name: str | None = None


def rank_for_earned(total: int) -> str:
    rank = RANKS[0][1]
    for threshold, name in RANKS:
        if total >= threshold:
            rank = name
    return rank


def next_rank(total: int) -> tuple[str, int] | None:
    for threshold, name in RANKS:
        if threshold > total:
            return name, threshold - total
    return None


class EconomyService:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self.session_factory = session_factory
        raw = os.getenv("ADMIN_USER_IDS", "")
        self.admin_user_ids = {
            int(part.strip()) for part in raw.split(",") if part.strip().lstrip("-").isdigit()
        }

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_user_ids

    async def seed_catalog(self) -> None:
        async with self.session_factory() as session:
            for spec in SHOP_CATALOG:
                row = await session.get(ShopItem, str(spec["key"]))
                if row is None:
                    row = ShopItem(key=str(spec["key"]))
                    session.add(row)
                row.category = str(spec["category"])
                row.name = str(spec["name"])
                row.description = str(spec["description"])
                row.price = int(spec["price"])
                row.effect_value = int(spec["effect_value"]) if spec.get("effect_value") else None
                row.enabled = True
            for spec in TROPHY_CATALOG:
                row = await session.get(TrophyCatalog, spec["key"])
                if row is None:
                    row = TrophyCatalog(key=spec["key"])
                    session.add(row)
                row.name = spec["name"]
                row.description = spec["description"]
                row.rarity = spec["rarity"]
            await session.commit()

    async def _account(self, session: AsyncSession, user_id: int) -> EconomyAccount:
        account = await session.get(EconomyAccount, user_id)
        if account is None:
            account = EconomyAccount(user_id=user_id)
            session.add(account)
            await session.flush()
        return account

    async def ensure_account(self, user_id: int) -> EconomyAccount:
        async with self.session_factory() as session:
            account = await self._account(session, user_id)
            await session.commit()
            return account

    async def profile_data(self, user_id: int) -> dict[str, object]:
        async with self.session_factory() as session:
            account = await self._account(session, user_id)
            user = await session.get(User, user_id)
            title_name = None
            if account.active_title:
                title_item = await session.get(ShopItem, account.active_title)
                title_name = title_item.name if title_item else None
            trophy_count = int(
                await session.scalar(
                    select(func.count(UserTrophy.id)).where(UserTrophy.user_id == user_id)
                )
                or 0
            )
            showcase = list(
                (
                    await session.execute(
                        select(UserShowcase, TrophyCatalog)
                        .join(TrophyCatalog, TrophyCatalog.key == UserShowcase.trophy_key)
                        .where(UserShowcase.user_id == user_id)
                        .order_by(UserShowcase.slot)
                    )
                ).all()
            )
            await session.commit()
            return {
                "name": user.display_name if user else str(user_id),
                "balance": account.balance,
                "lifetime_earned": account.lifetime_earned,
                "rank": rank_for_earned(account.lifetime_earned),
                "next_rank": next_rank(account.lifetime_earned),
                "theme": THEME_LABELS.get(account.active_theme, account.active_theme),
                "title": title_name,
                "showcase_slots": account.showcase_slots,
                "trophy_count": trophy_count,
                "showcase": [(slot.slot, trophy.name) for slot, trophy in showcase],
            }

    async def shop_for_user(self, user_id: int, category: str) -> tuple[list[ShopItem], set[str], int]:
        async with self.session_factory() as session:
            account = await self._account(session, user_id)
            items = list(
                (
                    await session.scalars(
                        select(ShopItem)
                        .where(ShopItem.category == category, ShopItem.enabled.is_(True))
                        .order_by(ShopItem.price, ShopItem.key)
                    )
                ).all()
            )
            owned = set(
                (
                    await session.scalars(
                        select(UserInventory.item_key).where(UserInventory.user_id == user_id)
                    )
                ).all()
            )
            await session.commit()
            return items, owned, account.balance

    async def purchase(self, user_id: int, item_key: str) -> tuple[ShopItem, int]:
        async with self.session_factory() as session:
            account = await self._account(session, user_id)
            item = await session.get(ShopItem, item_key)
            if item is None or not item.enabled:
                raise ValueError("Товар не знайдено.")
            existing = await session.scalar(
                select(UserInventory).where(
                    UserInventory.user_id == user_id,
                    UserInventory.item_key == item_key,
                )
            )
            if existing is not None:
                raise ValueError("Цей предмет уже придбано.")
            if account.balance < item.price:
                raise ValueError(f"Не вистачає хабару. Потрібно ще {item.price - account.balance}.")

            account.balance -= item.price
            account.lifetime_spent += item.price
            account.updated_at = utc_ts()
            session.add(UserInventory(user_id=user_id, item_key=item_key))
            session.add(
                EconomyTransaction(
                    user_id=user_id,
                    amount=-item.price,
                    kind="shop_purchase",
                    item_key=item_key,
                    note=item.name,
                )
            )
            if item.category == "slot" and item.effect_value:
                account.showcase_slots = max(account.showcase_slots, item.effect_value)
            await session.commit()
            return item, account.balance

    async def activate(self, user_id: int, item_key: str) -> str:
        async with self.session_factory() as session:
            account = await self._account(session, user_id)
            item = await session.get(ShopItem, item_key)
            owned = await session.scalar(
                select(UserInventory).where(
                    UserInventory.user_id == user_id,
                    UserInventory.item_key == item_key,
                )
            )
            if item is None or owned is None:
                raise ValueError("Спочатку придбай цей предмет у магазині.")
            if item.category == "theme":
                account.active_theme = item.key
            elif item.category == "title":
                account.active_title = item.key
            else:
                raise ValueError("Цей предмет не потрібно активувати.")
            await session.commit()
            return item.name

    async def inventory(self, user_id: int, category: str) -> list[ShopItem]:
        async with self.session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(ShopItem)
                        .join(UserInventory, UserInventory.item_key == ShopItem.key)
                        .where(UserInventory.user_id == user_id, ShopItem.category == category)
                        .order_by(ShopItem.price)
                    )
                ).all()
            )

    async def trophies(self, user_id: int) -> list[tuple[UserTrophy, TrophyCatalog]]:
        async with self.session_factory() as session:
            return list(
                (
                    await session.execute(
                        select(UserTrophy, TrophyCatalog)
                        .join(TrophyCatalog, TrophyCatalog.key == UserTrophy.trophy_key)
                        .where(UserTrophy.user_id == user_id)
                        .order_by(TrophyCatalog.rarity, TrophyCatalog.name)
                    )
                ).all()
            )

    async def set_showcase(self, user_id: int, slot: int, trophy_key: str) -> None:
        async with self.session_factory() as session:
            account = await self._account(session, user_id)
            if slot < 1 or slot > account.showcase_slots:
                raise ValueError("Цей слот вітрини ще не відкрито.")
            trophy = await session.scalar(
                select(UserTrophy).where(
                    UserTrophy.user_id == user_id,
                    UserTrophy.trophy_key == trophy_key,
                )
            )
            if trophy is None:
                raise ValueError("У твоїй колекції немає цього трофея.")
            row = await session.scalar(
                select(UserShowcase).where(UserShowcase.user_id == user_id, UserShowcase.slot == slot)
            )
            if row is None:
                row = UserShowcase(user_id=user_id, slot=slot, trophy_key=trophy_key)
                session.add(row)
            else:
                row.trophy_key = trophy_key
            await session.commit()

    async def start_game(self, game_id: int, user_ids: list[int]) -> None:
        async with self.session_factory() as session:
            for user_id in user_ids:
                wallet = await session.scalar(
                    select(GameEconomy).where(
                        GameEconomy.game_id == game_id,
                        GameEconomy.user_id == user_id,
                    )
                )
                if wallet is None:
                    session.add(
                        GameEconomy(
                            game_id=game_id,
                            user_id=user_id,
                            run_habar=GAME_START_HABAR,
                            minted_habar=GAME_START_HABAR,
                        )
                    )
                    session.add(
                        GameHabarEvent(
                            game_id=game_id,
                            user_id=user_id,
                            event_key=f"start:{user_id}",
                            event_type="participation",
                            amount=GAME_START_HABAR,
                        )
                    )
            await session.commit()

    async def _wallet(self, session: AsyncSession, game_id: int, user_id: int) -> GameEconomy:
        wallet = await session.scalar(
            select(GameEconomy).where(
                GameEconomy.game_id == game_id,
                GameEconomy.user_id == user_id,
            )
        )
        if wallet is None:
            wallet = GameEconomy(game_id=game_id, user_id=user_id, run_habar=0, minted_habar=0)
            session.add(wallet)
            await session.flush()
        return wallet

    async def add_game_reward(
        self,
        session: AsyncSession,
        *,
        game_id: int,
        user_id: int,
        event_key: str,
        event_type: str,
        amount: int,
        target_user_id: int | None = None,
    ) -> int:
        existing = await session.scalar(
            select(GameHabarEvent).where(
                GameHabarEvent.game_id == game_id,
                GameHabarEvent.event_key == event_key,
            )
        )
        if existing is not None:
            return 0
        wallet = await self._wallet(session, game_id, user_id)
        allowed = max(0, GAME_MINT_CAP - wallet.minted_habar)
        granted = min(max(amount, 0), allowed)
        wallet.run_habar += granted
        wallet.minted_habar += granted
        session.add(
            GameHabarEvent(
                game_id=game_id,
                user_id=user_id,
                event_key=event_key,
                event_type=event_type,
                amount=granted,
                target_user_id=target_user_id,
            )
        )
        return granted

    async def rob_victim(
        self,
        session: AsyncSession,
        *,
        game_id: int,
        day_number: int,
        victim_user_id: int,
        bandit_user_ids: list[int],
    ) -> int:
        if not bandit_user_ids:
            return 0
        marker = f"loot:{day_number}:{victim_user_id}:loss"
        if await session.scalar(
            select(GameHabarEvent).where(
                GameHabarEvent.game_id == game_id,
                GameHabarEvent.event_key == marker,
            )
        ):
            return 0
        victim = await self._wallet(session, game_id, victim_user_id)
        amount = min(victim.run_habar * BANDIT_LOOT_PERCENT // 100, BANDIT_LOOT_CAP)
        if amount <= 0:
            return 0
        victim.run_habar -= amount
        session.add(
            GameHabarEvent(
                game_id=game_id,
                user_id=victim_user_id,
                event_key=marker,
                event_type="bandit_loot_lost",
                amount=-amount,
            )
        )
        bandits = sorted(set(bandit_user_ids))
        base, remainder = divmod(amount, len(bandits))
        for index, user_id in enumerate(bandits):
            share = base + (1 if index < remainder else 0)
            wallet = await self._wallet(session, game_id, user_id)
            wallet.run_habar += share
            session.add(
                GameHabarEvent(
                    game_id=game_id,
                    user_id=user_id,
                    event_key=f"loot:{day_number}:{victim_user_id}:{user_id}",
                    event_type="bandit_loot",
                    amount=share,
                    target_user_id=victim_user_id,
                )
            )
        return amount

    def _trophy_drop(self, game_id: int, user_id: int) -> dict[str, str] | None:
        digest = hashlib.sha256(f"trophy:{game_id}:{user_id}".encode()).digest()
        roll = int.from_bytes(digest[:4], "big") % 10_000
        if roll < 20:
            rarity = "legendary"      # 0.2%
        elif roll < 120:
            rarity = "epic"           # 1.0%
        elif roll < 620:
            rarity = "rare"           # 5.0%
        elif roll < 2_120:
            rarity = "common"         # 15.0%
        else:
            return None
        pool = [item for item in TROPHY_CATALOG if item["rarity"] == rarity]
        pick = int.from_bytes(digest[4:8], "big") % len(pool)
        return pool[pick]

    async def settle_finished_game(self, game_id: int) -> list[Settlement]:
        results: list[Settlement] = []
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "finished" or game.winner not in {"city", "mafia", "bloodsucker"}:
                return results
            players = list(
                (await session.scalars(select(GamePlayer).where(GamePlayer.game_id == game_id))).all()
            )
            vote_count = int(
                await session.scalar(select(func.count(DayVote.id)).where(DayVote.game_id == game_id)) or 0
            )
            eligible = vote_count > 0 and len(players) >= 5

            for player in players:
                wallet = await self._wallet(session, game_id, player.user_id)
                if wallet.settled:
                    continue
                if eligible:
                    if team_for_role(player.role) == game.winner:
                        await self.add_game_reward(
                            session,
                            game_id=game_id,
                            user_id=player.user_id,
                            event_key=f"win:{player.user_id}",
                            event_type="win",
                            amount=GAME_WIN_HABAR,
                        )
                    if player.alive:
                        await self.add_game_reward(
                            session,
                            game_id=game_id,
                            user_id=player.user_id,
                            event_key=f"survive:{player.user_id}",
                            event_type="survival",
                            amount=GAME_SURVIVE_HABAR,
                        )

                account = await self._account(session, player.user_id)
                # GAME_MINT_CAP limits only newly created reward currency.
                # Bandit loot is a transfer between run wallets and therefore
                # must remain fully withdrawable instead of disappearing here.
                payout = max(wallet.run_habar, 0) if eligible else 0
                trophy_name = None
                if payout:
                    account.balance += payout
                    account.lifetime_earned += payout
                    account.updated_at = utc_ts()
                    session.add(
                        EconomyTransaction(
                            user_id=player.user_id,
                            amount=payout,
                            kind="game_settlement",
                            game_id=game_id,
                            note=f"Ходка #{game_id}",
                        )
                    )
                    drop = self._trophy_drop(game_id, player.user_id)
                    if drop is not None:
                        owned = await session.scalar(
                            select(UserTrophy).where(
                                UserTrophy.user_id == player.user_id,
                                UserTrophy.trophy_key == drop["key"],
                            )
                        )
                        if owned is None:
                            session.add(UserTrophy(user_id=player.user_id, trophy_key=drop["key"]))
                        else:
                            owned.quantity += 1
                        trophy_name = drop["name"]
                wallet.settled = True
                results.append(Settlement(player.user_id, payout, account.balance, trophy_name))
            await session.commit()
        return results

    async def adjust_balance(self, target_user_id: int, amount: int, note: str) -> int:
        if amount == 0:
            raise ValueError("Сума не може бути нульовою.")
        async with self.session_factory() as session:
            user = await session.get(User, target_user_id)
            if user is None:
                raise ValueError("Гравця ще немає в базі бота.")
            account = await self._account(session, target_user_id)
            if account.balance + amount < 0:
                raise ValueError("Не можна списати більше хабару, ніж є у схроні.")
            account.balance += amount
            if amount > 0:
                account.lifetime_earned += amount
            account.updated_at = utc_ts()
            session.add(
                EconomyTransaction(
                    user_id=target_user_id,
                    amount=amount,
                    kind="admin_adjustment",
                    note=note[:255],
                )
            )
            await session.commit()
            return account.balance

    async def find_user(self, value: str) -> User | None:
        value = value.strip()
        async with self.session_factory() as session:
            if value.lstrip("-").isdigit():
                return await session.get(User, int(value))
            username = value.removeprefix("@").lower()
            return await session.scalar(
                select(User).where(func.lower(User.username) == username).order_by(User.updated_at.desc())
            )

    async def recent_users(self, limit: int = 10) -> list[User]:
        async with self.session_factory() as session:
            return list((await session.scalars(select(User).order_by(User.updated_at.desc()).limit(limit))).all())

    async def transaction_history(self, user_id: int, limit: int = 10) -> list[EconomyTransaction]:
        async with self.session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(EconomyTransaction)
                        .where(EconomyTransaction.user_id == user_id)
                        .order_by(EconomyTransaction.id.desc())
                        .limit(limit)
                    )
                ).all()
            )
