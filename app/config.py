from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(alias="BOT_TOKEN")
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/mafia.db",
        alias="DATABASE_URL",
    )
    min_players: int = Field(default=5, alias="MIN_PLAYERS", ge=4, le=20)
    max_players: int = Field(default=20, alias="MAX_PLAYERS", ge=5, le=30)
    night_seconds: int = Field(default=60, alias="NIGHT_SECONDS", ge=15, le=600)
    discussion_seconds: int = Field(default=180, alias="DISCUSSION_SECONDS", ge=30, le=1800)
    voting_seconds: int = Field(default=60, alias="VOTING_SECONDS", ge=15, le=600)
    runoff_seconds: int = Field(default=45, alias="RUNOFF_SECONDS", ge=15, le=600)
    phase_poll_seconds: int = Field(default=2, alias="PHASE_POLL_SECONDS", ge=1, le=30)
