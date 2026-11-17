# Как поднять копию «Городской Паузы» на новом сервере

Инструкция для установки на отдельный сервер (одна установка = один клиент = один домен).
**Важно:** шаги проверены по коду и на пустой папке данных, но на настоящем чистом сервере целиком ещё не прогонялись.
Первую установку лучше делать как пробную и записывать, что пришлось поправить.

## Что нужно заранее
- Сервер (VPS) с Ubuntu 22.04 или 24.04: 1 ядро, 2 ГБ памяти, диск от 30 ГБ (для 1-10 квартир), доступ по SSH.
- Домен, у которого запись **A** (и для `www`) указывает на IP сервера. Подождать, пока обновится (от минут до часов).
- Почтовый ящик, с которого пойдут письма гостям, и **пароль приложения** этого ящика (не обычный пароль).
- Доступ к репозиторию проекта (git clone).

Ниже `example.ru` заменить на домен клиента.

## 1. Пакеты
```
apt update && apt install -y python3-venv python3-pip nginx certbot python3-certbot-nginx git
```

## 2. Код и окружение Python
```
git clone <адрес репозитория> /app
cd /app
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
mkdir -p /data/photos
```
Папка `/data` хранит все данные клиента (база, фото, договоры). В git её нет, и **данные другого клиента или Max туда не переносить**.

## 3. Файл настроек `.env`
```
cp env.example .env
chmod 600 .env
nano .env
```
Заполнить обязательные ключи (подробности в самом файле): `BASE_URL`, `ADMIN_PASSWORD`, `SESSION_SECRET`, `MAIL_FROM`, `MAIL_PASSWORD`, `BACKUP_PASSWORD`.
Пока сайт тестовый, оставить `NOINDEX=1` (поисковики его не покажут). Перед открытием для гостей удалить эту строку.
Telegram-бот не нужен: `BOT_TOKEN` и `ADMIN_IDS` не задавать.

Пароль `BACKUP_PASSWORD` сохранить отдельно: без него копии не открыть, а на почту и в архивы без него ничего не уйдёт.

## 4. Служба systemd
Файл `/etc/systemd/system/apart.service`:
```
[Unit]
Description=Сайт бронирования
After=network.target

[Service]
WorkingDirectory=/app
ExecStart=/app/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8080
Restart=always
RestartSec=5
EnvironmentFile=/app/.env

[Install]
WantedBy=multi-user.target
```
Запуск:
```
systemctl daemon-reload
systemctl enable --now apart
journalctl -u apart -n 30 --no-pager
```
В журнале должна быть строка «APPLICATION STARTED». Строка «BOT_TOKEN не задан» нормальна.
Адрес `127.0.0.1` важен: сайт должен быть доступен только через nginx.

## 5. nginx и https
Файл `/etc/nginx/sites-available/apart` (сначала только порт 80):
```
server {
    listen 80;
    server_name example.ru www.example.ru;
    client_max_body_size 10m;

    location /data/photos/ {
        alias /data/photos/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
```
Включить и получить сертификат:
```
ln -s /etc/nginx/sites-available/apart /etc/nginx/sites-enabled/apart
nginx -t && systemctl reload nginx
certbot --nginx -d example.ru -d www.example.ru
```
Certbot сам добавит https и переадресацию. Паспорта (`/data/passports`) наружу **не отдаются**, и этого менять нельзя: в nginx раздаётся только `/data/photos/`.
Файрвол `ufw` без согласования не включать: можно потерять доступ по SSH.

## 6. Проверка
- `https://example.ru/health` отвечает `{"status":"ok"}`.
- `https://example.ru/` открывается (на пустой установке он выглядит пустым, это нормально).
- Админка: `https://example.ru/static/admin.html`, вход паролем из `ADMIN_PASSWORD`.

## 7. Первая настройка в админке
1. Сменить пароль админа на собственный (форма смены пароля на главной странице админки, «Дашборд»).
2. «Бренд» (название, домен, адрес), «Контакты» (почта арендодателя, телефон).
3. «Договор → Данные объекта для договора»: арендодатель, вид объекта, адрес, имущество, основание.
   Шаблоны договора, согласия и политики конфиденциальности **показать юристу до приёма настоящих гостей**.
4. Фото, цены, тексты, правила, места рядом.
5. «Мониторинг → Тестовое письмо»: письмо должно прийти. «Оплата (СБП)»: реквизиты.
6. «Настройки копий»: как часто делать архивы документов и фото. Нажать «Копия сейчас» и проверить, что копия пришла на почту.
7. Календари площадок (Авито и др.) подключать только когда у клиента уже есть объявления. На тестовой копии не подключать.

## 8. Внешняя проверка и сторож (рекомендуется)
- Бесплатный UptimeRobot: монитор HTTP на `https://example.ru/health/deep` каждые 5 минут. Если сервер упал целиком, письмо о сбое отправить некому, а внешний сервис напишет.
- Необязательный сторож, который перезапускает сайт при зависании: `tools/watchdog.sh` (инструкция в начале файла).

## 9. Обновление
```
cd /app && git pull && systemctl restart apart
```
Если менялись только файлы из `static/`, перезапуск не нужен.

## Список ключей `.env`
| Ключ | Нужен | Что это |
|---|---|---|
| `BASE_URL` | да | адрес сайта для ссылок в письмах |
| `ADMIN_PASSWORD` | да | пароль первого входа в админку |
| `SESSION_SECRET` | да | чтобы входы в админку не сбрасывались при перезапуске |
| `MAIL_FROM`, `MAIL_PASSWORD` | да | ящик, с которого уходят письма |
| `BACKUP_PASSWORD` | да | пароль шифрования копий |
| `MAIL_ADMIN`, `MAIL_FROM_NAME`, `MAIL_SMTP_HOST`, `MAIL_SMTP_PORT` | нет | служебная почта, имя отправителя, другой почтовый сервер |
| `NOINDEX` | нет | `1` = запретить индексацию (тестовая копия) |

## Чего не делать
- Не переносить на сервер клиента `/data`, `.env`, `config.py` с чужими значениями.
- Не присылать никому `.env`, пароли `BACKUP_PASSWORD`, `ADMIN_PASSWORD` и токены календарей.
