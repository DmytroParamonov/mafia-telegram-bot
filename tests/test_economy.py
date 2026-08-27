from sqlalchemy import select

from app.db import init_db, make_engine, make_session_factory
from app.economy import EconomyService, rank_for_earned
from app.economy_models import EconomyAccount, GameEconomy
from app.game.rules import Role
from app.models import DayVote, Game, GamePlayer, User


def test_habar_ranks_are_long_term_progression() -> None:
    assert rank_for_earned(0) == "Новачок"
    assert rank_for_earned(499) == "Новачок"
    assert rank_for_earned(500) == "Бродяга"
    assert rank_for_earned(7_499) == "Досвідчений"
    assert rank_for_earned(7_500) == "Ветеран"
    assert rank_for_earned(30_000) == "Легенда Зони"


async def _fresh_economy():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    factory = make_session_factory(engine)
    economy = EconomyService(factory)
    await economy.seed_catalog()
    return engine, factory, economy


async def test_admin_grant_purchase_and_activation_are_persistent() -> None:
    engine, factory, economy = await _fresh_economy()
    try:
        async with factory() as session:
            session.add(User(id=100, username="stalker", display_name="Stalker"))
            await session.commit()

        balance = await economy.adjust_balance(100, 1_500, "test grant")
        assert balance == 1_500

        item, balance = await economy.purchase(100, "pda_dark")
        assert item.price == 1_000
        assert balance == 500
        assert await economy.activate(100, "pda_dark") == "🌑 Темний ПДА"

        data = await economy.profile_data(100)
        assert data["balance"] == 500
        assert data["lifetime_earned"] == 1_500
        assert data["rank"] == "Сталкер"
        assert "Темний" in str(data["theme"])

        history = await economy.transaction_history(100)
        assert [row.amount for row in history[:2]] == [-1_000, 1_500]
    finally:
        await engine.dispose()


async def test_bandits_steal_only_temporary_run_habar() -> None:
    engine, factory, economy = await _fresh_economy()
    try:
        async with factory() as session:
            for user_id in range(1, 6):
                session.add(User(id=user_id, display_name=f"P{user_id}"))
            session.add(Game(id=1, chat_id=-100, host_user_id=1, status="active", phase="night"))
            await session.commit()

        await economy.start_game(1, [1, 2, 3, 4, 5])
        async with factory() as session:
            stolen = await economy.rob_victim(
                session,
                game_id=1,
                day_number=1,
                victim_user_id=5,
                bandit_user_ids=[1, 2],
            )
            await session.commit()
            wallets = {
                row.user_id: row.run_habar
                for row in (
                    await session.scalars(select(GameEconomy).where(GameEconomy.game_id == 1))
                ).all()
            }
            accounts = list((await session.scalars(select(EconomyAccount))).all())

        assert stolen == 10
        assert wallets[5] == 10
        assert wallets[1] == 25
        assert wallets[2] == 25
        assert accounts == []  # permanent stash is untouched until settlement
    finally:
        await engine.dispose()


async def test_completed_real_game_banks_habar_once() -> None:
    engine, factory, economy = await _fresh_economy()
    try:
        async with factory() as session:
            for user_id in range(1, 6):
                session.add(User(id=user_id, display_name=f"P{user_id}"))
            game = Game(
                id=7,
                chat_id=-700,
                host_user_id=1,
                status="finished",
                phase="finished",
                winner="city",
                day_number=2,
            )
            session.add(game)
            roles = [
                Role.CIVILIAN.value,
                Role.SHERIFF.value,
                Role.DOCTOR.value,
                Role.CIVILIAN.value,
                Role.MAFIA.value,
            ]
            for user_id, role in enumerate(roles, start=1):
                session.add(
                    GamePlayer(
                        game_id=7,
                        user_id=user_id,
                        display_name=f"P{user_id}",
                        role=role,
                        alive=user_id != 5,
                    )
                )
            session.add(
                DayVote(
                    game_id=7,
                    day_number=1,
                    vote_round=1,
                    voter_user_id=1,
                    target_user_id=5,
                )
            )
            await session.commit()

        await economy.start_game(7, [1, 2, 3, 4, 5])
        first = await economy.settle_finished_game(7)
        second = await economy.settle_finished_game(7)

        assert len(first) == 5
        assert second == []
        city = {row.user_id: row.amount for row in first}
        assert city[1] == 85  # 20 participation + 50 win + 15 survival
        assert city[2] == 85
        assert city[3] == 85
        assert city[4] == 85
        assert city[5] == 20
    finally:
        await engine.dispose()
