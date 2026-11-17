#!/bin/bash
# Необязательный сторож: раз в 5 минут проверяет сайт и перезапускает сервис, если сайт не отвечает.
# Подключение: chmod +x /app/tools/watchdog.sh
#   crontab -e  и добавить строку:  */5 * * * * /app/tools/watchdog.sh >> /app/watchdog.log 2>&1
# Адрес сайта берётся из BASE_URL в /app/.env. Оповещения в Telegram необязательны:
# если в .env нет BOT_TOKEN и WATCHDOG_CHAT_ID, сообщения не отправляются, но перезапуск работает.
cd /app || exit 1

env_value() { grep -oP "(?<=^$1=).*" .env 2>/dev/null | tr -d "\"' \r" | head -n1; }

BOT_TOKEN=$(env_value BOT_TOKEN)
CHAT_ID=$(env_value WATCHDOG_CHAT_ID)
BASE_URL=$(env_value BASE_URL)
BASE_URL=${BASE_URL%/}

[ -z "$BASE_URL" ] && { echo "$(date): в .env не задан BASE_URL"; exit 1; }

SITE_URL="${BASE_URL}/api/prices"
SERVICE_NAME="apart"

send_alert() {
  if [ -z "$BOT_TOKEN" ] || [ -z "$CHAT_ID" ]; then return; fi
  curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    -d chat_id="${CHAT_ID}" \
    -d text="$1" > /dev/null
}

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$SITE_URL")

if [ "$HTTP_CODE" != "200" ]; then
  echo "$(date): сайт не отвечает (код: $HTTP_CODE) — пробую перезапустить"
  send_alert "⚠️ Сайт не отвечает (код $HTTP_CODE). Перезапускаю сервис..."
  systemctl restart "$SERVICE_NAME"
  sleep 15
  HTTP_CODE_AFTER=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$SITE_URL")
  if [ "$HTTP_CODE_AFTER" == "200" ]; then
    send_alert "✅ Сайт снова работает после перезапуска."
  else
    send_alert "🛑 Сайт всё ещё не отвечает после перезапуска (код $HTTP_CODE_AFTER). Нужна ручная проверка сервера!"
  fi
else
  echo "$(date): всё ок"
fi
