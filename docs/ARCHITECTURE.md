# Architecture

The bot is intentionally split into a thin Telegram layer and a persistent game service.

- `app/handlers.py` contains Telegram commands and callback parsing only.
- `app/service.py` owns lobby lifecycle, phase transitions, persistence and Telegram orchestration.
- `app/game/rules.py` contains deterministic, Telegram-independent game rules.
- `app/models.py` stores every durable piece of game state in SQLite.
- `Game.phase_deadline` is persisted as a Unix timestamp. The scheduler polls expired games, so a process restart does not reset or lose a match.
- Callback payloads include game/day/phase identifiers so old buttons cannot mutate a later phase.
- Every player joins through a private deep link before the game starts, ensuring the bot can deliver roles and secret actions.

## State machine

`lobby -> night -> discussion -> voting -> [runoff] -> night ... -> finished`

The game ends when all mafia-team roles are dead or when living mafia members reach parity with the remaining city.
