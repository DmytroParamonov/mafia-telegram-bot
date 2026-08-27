from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, utc_ts


class EconomyAccount(Base):
    __tablename__ = "economy_accounts"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), primary_key=True)
    balance: Mapped[int] = mapped_column(Integer, default=0)
    lifetime_earned: Mapped[int] = mapped_column(Integer, default=0)
    lifetime_spent: Mapped[int] = mapped_column(Integer, default=0)
    active_theme: Mapped[str] = mapped_column(String(64), default="pda_standard")
    active_title: Mapped[str | None] = mapped_column(String(64), nullable=True)
    showcase_slots: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[int] = mapped_column(Integer, default=utc_ts)
    updated_at: Mapped[int] = mapped_column(Integer, default=utc_ts, onupdate=utc_ts)


class EconomyTransaction(Base):
    __tablename__ = "economy_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    game_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("games.id"), nullable=True, index=True)
    item_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, default=utc_ts, index=True)


class GameEconomy(Base):
    __tablename__ = "game_economy"
    __table_args__ = (UniqueConstraint("game_id", "user_id", name="uq_game_economy_player"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    run_habar: Mapped[int] = mapped_column(Integer, default=20)
    minted_habar: Mapped[int] = mapped_column(Integer, default=20)
    settled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class GameHabarEvent(Base):
    __tablename__ = "game_habar_events"
    __table_args__ = (UniqueConstraint("game_id", "event_key", name="uq_game_habar_event"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    event_key: Mapped[str] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    target_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, default=utc_ts)


class ShopItem(Base):
    __tablename__ = "shop_items"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(255))
    price: Mapped[int] = mapped_column(Integer)
    effect_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class UserInventory(Base):
    __tablename__ = "user_inventory"
    __table_args__ = (UniqueConstraint("user_id", "item_key", name="uq_user_inventory_item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    item_key: Mapped[str] = mapped_column(String(64), ForeignKey("shop_items.key"), index=True)
    purchased_at: Mapped[int] = mapped_column(Integer, default=utc_ts)


class TrophyCatalog(Base):
    __tablename__ = "trophy_catalog"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(255))
    rarity: Mapped[str] = mapped_column(String(20), index=True)


class UserTrophy(Base):
    __tablename__ = "user_trophies"
    __table_args__ = (UniqueConstraint("user_id", "trophy_key", name="uq_user_trophy"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    trophy_key: Mapped[str] = mapped_column(String(64), ForeignKey("trophy_catalog.key"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    first_found_at: Mapped[int] = mapped_column(Integer, default=utc_ts)


class UserShowcase(Base):
    __tablename__ = "user_showcase"
    __table_args__ = (UniqueConstraint("user_id", "slot", name="uq_user_showcase_slot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    slot: Mapped[int] = mapped_column(Integer)
    trophy_key: Mapped[str] = mapped_column(String(64), ForeignKey("trophy_catalog.key"))
