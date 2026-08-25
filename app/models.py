from __future__ import annotations

import secrets
from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_ts() -> int:
    return int(datetime.now(UTC).timestamp())


def new_join_code() -> str:
    return secrets.token_urlsafe(6)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[int] = mapped_column(Integer, default=utc_ts)
    updated_at: Mapped[int] = mapped_column(Integer, default=utc_ts, onupdate=utc_ts)


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    chat_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    host_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    lobby_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    join_code: Mapped[str] = mapped_column(String(24), default=new_join_code)

    status: Mapped[str] = mapped_column(String(32), default="lobby", index=True)
    phase: Mapped[str] = mapped_column(String(32), default="lobby")
    day_number: Mapped[int] = mapped_column(Integer, default=0)
    vote_round: Mapped[int] = mapped_column(Integer, default=0)
    phase_deadline: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    winner: Mapped[str | None] = mapped_column(String(32), nullable=True)

    enable_don: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_sheriff: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_doctor: Mapped[bool] = mapped_column(Boolean, default=True)
    reveal_roles: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[int] = mapped_column(Integer, default=utc_ts)
    started_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finished_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class GamePlayer(Base):
    __tablename__ = "game_players"
    __table_args__ = (UniqueConstraint("game_id", "user_id", name="uq_game_player"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    alive: Mapped[bool] = mapped_column(Boolean, default=True)
    joined_at: Mapped[int] = mapped_column(Integer, default=utc_ts)


class NightAction(Base):
    __tablename__ = "night_actions"
    __table_args__ = (
        UniqueConstraint(
            "game_id",
            "day_number",
            "actor_user_id",
            "action_type",
            name="uq_night_action",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"), index=True)
    day_number: Mapped[int] = mapped_column(Integer)
    actor_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    action_type: Mapped[str] = mapped_column(String(32))
    target_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    created_at: Mapped[int] = mapped_column(Integer, default=utc_ts)


class DayVote(Base):
    __tablename__ = "day_votes"
    __table_args__ = (
        UniqueConstraint(
            "game_id",
            "day_number",
            "vote_round",
            "voter_user_id",
            name="uq_day_vote",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"), index=True)
    day_number: Mapped[int] = mapped_column(Integer)
    vote_round: Mapped[int] = mapped_column(Integer)
    voter_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    target_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    created_at: Mapped[int] = mapped_column(Integer, default=utc_ts)
