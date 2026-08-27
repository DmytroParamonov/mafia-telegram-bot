#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "☢️ Перший запуск «Мафії в Зоні»"
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
MAX_PLAYERS=10
NIGHT_SECONDS=90
DISCUSSION_SECONDS=180
VOTING_SECONDS=90
RUNOFF_SECONDS=60
PHASE_POLL_SECONDS=2
EOF

  chmod 600 .env 2>/dev/null || true
  echo "✅ .env створено."
fi

# A fresh ZIP intentionally has no .env. Configure the economy owner here so
# nobody has to reveal hidden Finder files or edit .env by hand. A value passed
# as ADMIN_USER_IDS=... ./run.sh is also persisted automatically.
CURRENT_ADMIN_IDS="$(grep '^ADMIN_USER_IDS=' .env 2>/dev/null | tail -n 1 | cut -d= -f2- || true)"
if [ -z "$CURRENT_ADMIN_IDS" ]; then
  ADMIN_IDS="${ADMIN_USER_IDS:-}"
  if [ -z "$ADMIN_IDS" ]; then
    echo
    echo "🛡 Налаштування адмін-панелі економіки"
    printf "Встав свій Telegram ID (Enter — пропустити): "
    IFS= read -r ADMIN_IDS
  fi

  if [ -n "$ADMIN_IDS" ]; then
    if [[ "$ADMIN_IDS" =~ ^[0-9]+(,[0-9]+)*$ ]]; then
      grep -v '^ADMIN_USER_IDS=' .env > .env.tmp || true
      printf 'ADMIN_USER_IDS=%s\n' "$ADMIN_IDS" >> .env.tmp
      mv .env.tmp .env
      chmod 600 .env 2>/dev/null || true
      echo "✅ Адмін ID збережено в .env: $ADMIN_IDS"
    else
      echo "⚠️ Telegram ID має складатися з цифр. Адмінку поки пропущено."
      echo "   Просто запусти ./run.sh ще раз — скрипт запитає ID знову."
    fi
  else
    echo "ℹ️ Адмінку пропущено. ./run.sh запитає Telegram ID при наступному запуску."
  fi
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
echo "✅ Бот запускається. Для зупинки натисни Ctrl+C."
exec python -m app.main
