#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "☢️ Перший запуск STALKER Bot"
  printf "Встав токен від BotFather: "
  IFS= read -r BOT_TOKEN

  if [ -z "$BOT_TOKEN" ]; then
    echo "❌ Токен порожній. Запусти ./run.sh ще раз."
    exit 1
  fi

  cat > .env <<EOF
BOT_TOKEN=$BOT_TOKEN
DATABASE_URL=sqlite+aiosqlite:///./data/mafia.db
MIN_PLAYERS=5
MAX_PLAYERS=20
NIGHT_SECONDS=60
DISCUSSION_SECONDS=180
VOTING_SECONDS=60
RUNOFF_SECONDS=45
PHASE_POLL_SECONDS=2
EOF

  chmod 600 .env 2>/dev/null || true
  echo "✅ .env створено."
fi

mkdir -p data

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo "🐳 Docker знайдено — запускаю бота у фоні..."
  docker compose up -d --build
  echo
  echo "✅ Бота запущено."
  echo "Логи: docker compose logs -f mafia-bot"
  echo "Зупинити: docker compose down"
  exit 0
fi

PYTHON_BIN=""
for candidate in python3.13 python3.12 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON_BIN="$candidate"
    break
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  echo "❌ Не знайдено Python 3.12+ і не знайдено Docker."
  echo "Встанови Python 3.12+ або Docker Desktop і знову запусти ./run.sh."
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' >/dev/null 2>&1; then
  echo "❌ Знайдений Python занадто старий. Потрібен Python 3.12+."
  exit 1
fi

echo "🐍 Docker не знайдено — запускаю через $PYTHON_BIN..."

if [ ! -d .venv ]; then
  "$PYTHON_BIN" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -c 'import greenlet' >/dev/null 2>&1 || python -m pip install 'greenlet>=3.1,<4'

echo
echo "✅ Бота запущено. Для зупинки натисни Ctrl+C."
exec python -m app.main
