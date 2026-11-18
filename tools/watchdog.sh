#!/bin/bash
# Необязательный сторож: раз в 5 минут проверяет, отвечает ли приложение, и перезапускает сервис, если нет.
# Подключение: chmod +x /app/tools/watchdog.sh, затем crontab -e и строка:
#   */5 * * * * /app/tools/watchdog.sh >> /app/watchdog.log 2>&1
# Приложение проверяется напрямую на 127.0.0.1 (без сети и DNS). Перезапуск только если оно не ответило
# дважды подряд с паузой. Если приложение работает, а снаружи (по адресу сайта) нет, это только запись в лог:
# причина в сети или nginx, перезапуск приложения тут не поможет и только создаст простой.
# Оповещения в Telegram необязательны: без BOT_TOKEN и WATCHDOG_CHAT_ID сообщения не отправляются.
APP_DIR=${APP_DIR:-/app}
cd "$APP_DIR" || exit 1

env_value() { grep -oP "(?<=^$1=).*" .env 2>/dev/null | tr -d "\"' \r" | head -n1; }

BOT_TOKEN=$(env_value BOT_TOKEN)
CHAT_ID=$(env_value WATCHDOG_CHAT_ID)
BASE_URL=$(env_value BASE_URL)
BASE_URL=${BASE_URL%/}
APP_PORT=$(env_value APP_PORT)
APP_PORT=${APP_PORT:-8080}

LOCAL_URL="http://127.0.0.1:${APP_PORT}/api/prices"
SERVICE_NAME="apart"
RECHECK_PAUSE=${RECHECK_PAUSE:-20}
AFTER_RESTART_PAUSE=${AFTER_RESTART_PAUSE:-15}

http_code() { curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$1"; }

send_alert() {
  if [ -z "$BOT_TOKEN" ] || [ -z "$CHAT_ID" ]; then return; fi
  curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    -d chat_id="${CHAT_ID}" \
    -d text="$1" > /dev/null
}

LOCAL=$(http_code "$LOCAL_URL")
if [ "$LOCAL" != "200" ]; then
  # одна неудача может быть случайной: ждём и проверяем ещё раз
  sleep "$RECHECK_PAUSE"
  LOCAL=$(http_code "$LOCAL_URL")
fi

if [ "$LOCAL" != "200" ]; then
  echo "$(date): приложение не отвечает дважды подряд (код: $LOCAL) — перезапускаю"
  send_alert "⚠️ Сайт не отвечает (код $LOCAL). Перезапускаю сервис..."
  systemctl restart "$SERVICE_NAME"
  sleep "$AFTER_RESTART_PAUSE"
  AFTER=$(http_code "$LOCAL_URL")
  if [ "$AFTER" == "200" ]; then
    echo "$(date): после перезапуска приложение отвечает"
    send_alert "✅ Сайт снова работает после перезапуска."
  else
    echo "$(date): после перезапуска приложение всё ещё не отвечает (код: $AFTER)"
    send_alert "🛑 Сайт всё ещё не отвечает после перезапуска (код $AFTER). Нужна ручная проверка сервера!"
  fi
  exit 0
fi

if [ -n "$BASE_URL" ]; then
  PUBLIC=$(http_code "${BASE_URL}/api/prices")
  if [ "$PUBLIC" != "200" ]; then
    echo "$(date): приложение работает, но по адресу сайта не отвечает (код: $PUBLIC) — перезапуск не нужен, смотрите сеть или nginx"
    exit 0
  fi
fi
echo "$(date): всё ок"
