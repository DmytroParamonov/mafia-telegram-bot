#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "🎭 Первый запуск Mafia Bot"
  printf "Вставь токен от BotFather: "
  IFS= read -r BOT_TOKEN

  if [ -z "$BOT_TOKEN" ]; then
    echo "❌ Токен пустой. Запусти ./run.sh ещё раз."
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
  echo "✅ .env создан."
fi

mkdir -p data

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo "🐳 Docker найден — запускаю бота в фоне..."
  docker compose up -d --build
  echo
  echo "✅ Бот запущен."
  echo "Логи: docker compose logs -f mafia-bot"
  echo "Остановить: docker compose down"
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
  echo "❌ Не найден Python 3.12+ и не найден Docker."
  echo "Установи Python 3.12+ или Docker Desktop и снова запусти ./run.sh."
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' >/dev/null 2>&1; then
  echo "❌ Найденный Python слишком старый. Нужен Python 3.12+."
  exit 1
fi

echo "🐍 Docker не найден — запускаю через $PYTHON_BIN..."

if [ ! -d .venv ]; then
  "$PYTHON_BIN" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .

echo
 echo "✅ Бот запускается. Для остановки нажми Ctrl+C."
exec python -m app.main
