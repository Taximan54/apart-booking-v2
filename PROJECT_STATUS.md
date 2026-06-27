# Городская Пауза — статус проекта и roadmap

> Обновлено: 27 июня 2026. Используй этот файл чтобы быстро ввести нового Claude в контекст в новом чате — просто прикрепи его в начале разговора.

## Что это
Полноценная система бронирования квартиры посуточно: сайт с календарём и онлайн-договором, Telegram-бот, веб-админка, email-уведомления, T-Bank оплата, промокоды, отзывы, архив договоров.

## Инфраструктура

- **Сервер:** AdminVPS, IP `138.16.227.241`, Ubuntu 24.04, hostname Taximan54.com
- **Домен:** citypause.ru (+ www), SSL через certbot, истекает 2026-09-06 (автообновление настроено)
- **Проект на сервере:** `/app`, виртуальное окружение `/app/.venv`
- **Персистентные данные:** `/data/` (bookings.db, prices.json, promo_codes.json, door_code.json, description.txt, contract_template.txt, checkin_memo.txt, checkout_checklist.txt, review_template.txt, contacts.json, reviews.json, photos_order.json, admin_auth.json, contracts/, photos/)
- **GitHub:** `https://github.com/Taximan54/apart-booking-v2.git` — единственный источник правды. Правим локально → git add/commit/push → на сервере `cd /app && git pull && systemctl restart apart`
- **Systemd:** сервис `apart.service`, автозапуск включён, автоперезапуск при крахе
- **Nginx:** reverse proxy 80/443 → 127.0.0.1:8080, статика `/data/photos/` отдаётся напрямую через nginx (location /data/photos/ → alias /data/photos/, expires 30d)
- **Email:** mail.ru SMTP, `citypause@mail.ru`, пароль приложения в `.env` (`MAIL_PASSWORD`)
- **Бот:** Telegram токен и admin ID в `.env` + `config.py` (`BOT_TOKEN`, `ADMIN_IDS`, `BASE_URL=https://citypause.ru`)

### Команды для деплоя
```bash
# Локально
git add <файлы>
git commit -m "описание"
git push

# На сервере
cd /app && git pull && systemctl restart apart
systemctl status apart
journalctl -u apart -f
```

### Синтаксис перед деплоем (обязательно)
```bash
python3 -c "import ast; ast.parse(open('main.py').read()); print('OK')"
```

## КРИТИЧЕСКИ ВАЖНО: Telegram заблокирован на сервере (РКН)

`api.telegram.org` недоступен с VPS — ни polling, ни webhook. Telegram = best-effort уведомления, обёрнуты в `asyncio.wait_for(timeout=3-5s)` + try/except. Падение бота не блокирует сайт/email/БД.

## Статусы броней (полный флоу)

```
waiting_payment  → бронь создана, ждём предоплату 20%
payment_pending  → гость нажал "Я оплатил" предоплату
confirmed        → админ подтвердил предоплату → гость получает договор + инструкцию по остатку
fully_paid       → админ подтвердил полную оплату → гость получает памятку + код замка
cancelled        → отменена
```

**Оплата:** предоплата 20% онлайн (T-Bank), остаток + депозит 6000₽ наличными или переводом при заселении.

## Автоматические письма (планировщик, UTC+7 Новосибирск)

- **10:00** в день выезда → чек-лист выезда (`/data/checkout_checklist.txt`)
- **14:00** на следующий день после выезда → просьба об отзыве + промокод `RETURN****` на 10% (автоматически добавляется в `/data/promo_codes.json`)

## Номера броней

Формат: `GP-XXXXXX` (латиница). Старые тестовые брони имеют префикс `ГП-` (кириллица) — код поддерживает оба варианта при поиске в БД.

## Структура файлов проекта

- **main.py** (~1630 строк) — FastAPI приложение, все API-эндпоинты, email-функции, планировщик
- **config.py** — BOT_TOKEN, ADMIN_IDS, BASE_URL, load_dotenv()
- **services/booking_service.py** — функции работы с БД броней, get_bookings_checkout_today/yesterday
- **static/index.html** (~1450 строк, ~75KB) — публичный сайт. Фото вынесены из base64 в `/data/photos/`, загружаются через `/api/photos`
- **static/admin.html** (~1800 строк) — веб-админка с Bearer-токен авторизацией
- **static/privacy.html** — политика конфиденциальности (152-ФЗ)
- **static/contract_template.txt** — шаблон договора (копия `/data/contract_template.txt`)

## Плейсхолдеры в договоре

`{{ФИО}}`, `{{ПАСПОРТ}}`, `{{ДАТА_ДОГОВОРА}}`, `{{ДАТА_ЗАЕЗДА}}`, `{{ДАТА_ВЫЕЗДА}}`, `{{НОЧЕЙ}}`, `{{ГОСТЕЙ}}`, `{{ЦЕНА_В_СУТКИ}}`, `{{ИТОГО}}`, `{{ДЕПОЗИТ}}`, `{{EMAIL}}`, `{{САЙТ}}`, `{{НОМЕР_БРОНИ}}`

Дата договора — по часовому поясу Новосибирска (UTC+7). Депозит фиксирован — 6000₽.

## Вкладки админки

Дашборд, Все брони, Календарь, Цены, Промокоды, Договор, **Архив договоров**, Памятка гостю, Чек-лист выезда, Отзывы, Контакты, Фотографии, Настройки

## API-эндпоинты (ключевые)

**Публичные:**
- `GET /api/bookings` — занятые даты для календаря
- `GET /api/prices` — цены
- `GET /api/photos` — список фото галереи
- `GET /api/reviews` — отзывы (только visible:true)
- `GET /api/contacts` — контакты
- `GET /api/description` — описание квартиры
- `POST /api/bookings` — создать бронь
- `POST /api/payment-notify` — гость нажал "Я оплатил"
- `POST /api/promo-codes/validate` — проверить промокод

**Админские (Bearer-токен):**
- `POST /api/admin/login` — вход
- `POST /api/admin/change-password` — смена пароля
- `GET /api/bookings?admin=1` — все брони
- `POST /api/bookings/{ref}/confirm` — подтвердить предоплату
- `POST /api/bookings/{ref}/full-payment` — подтвердить полную оплату
- `POST /api/bookings/{ref}/cancel` — отменить
- `GET/POST /api/prices`, `/api/promo-codes`, `/api/door-code`, `/api/description`
- `GET/POST /api/contract-template`, `/api/checkin-memo`, `/api/checkout-checklist`, `/api/review-template`
- `GET /api/contracts` — список договоров
- `GET /api/contracts/{ref}` — скачать договор
- `GET /api/reviews/all`, `POST /api/reviews`, `PUT /api/reviews/{id}`, `DELETE /api/reviews/{id}`
- `GET /api/contacts`, `POST /api/contacts`
- `GET /api/photos`, `POST /api/photos/upload`, `DELETE /api/photos/{filename}`, `POST /api/photos/reorder`, `POST /api/photos/{filename}/label`

## Решённые проблемы (хронология)

1. Railway не принимал российские карты → переехали на AdminVPS
2. Telegram заблокирован РКН → best-effort уведомления с таймаутом
3. Бесконечный календарь → event delegation через grid.onmouseover
4. CORS, старый Railway URL → исправлено
5. SQLite автомиграция колонок через PRAGMA table_info + ALTER TABLE
6. Договор обрезался в письме → .txt вложение через MIMEBase
7. Сайт весил 2.3MB из-за base64-фото → фото вынесены в `/data/photos/`, nginx отдаёт статически
8. Главная страница отдавала заглушку → `GET /` читает реальный index.html
9. Кириллица `ГП-` в именах файлов ломала URL → переименованы в `GP-`, код поддерживает оба варианта
10. SESSION_SECRET рандомизировался при каждом перезапуске → зафиксирован в `.env`
11. Авторизация в admin.html была JS-паролем → переделана на Bearer-токен с сервером
12. Расхождение GitHub ↔ сервер из-за прямых SSH-правок → всегда правим локально и пушим

## Roadmap (приоритеты)

### Этап 1 — Полировка (текущий фокус)
- [ ] Доработка внешнего вида сайта
- [ ] Мелкие баги и UX-улучшения

### Этап 2 — Интеграции
- [ ] SMS-подписание договора (кандидаты: СМSC.ru, СМС.ру, Exolve)
- [ ] Telegram-бот как дополнительный канал броней (бот вызывает те же API-эндпоинты что и сайт, не работает с БД напрямую)

### Этап 3 — Внешние площадки
- [ ] Avito и Суточно.ру через iCal-синхронизацию (экспорт/импорт календаря)
- [ ] Channel Manager для синхронизации между площадками

### Этап 4 — White-label SaaS (мультитенантность)
Концепция: один FastAPI, одна БД, каждый арендодатель на своём поддомене `{name}.citypause.ru`.
- [ ] Добавить `owner_id` / `property_id` в структуру данных
- [ ] Данные каждого объекта в `/data/properties/{id}/`
- [ ] Поддомены через nginx + wildcard SSL
- [ ] Суперадминка для управления всеми объектами
- [ ] Биллинг для арендодателей

Текущая квартира становится `property_id=1`, ничего не ломается.

## Общие договорённости по стилю работы

- Макс — самостоятельно работает в SSH-терминале (PowerShell/CMD на Windows), нужны точные команды для copy-paste
- Перед деплоем: `python3 -c "import ast; ast.parse(open('main.py').read()); print('OK')"`
- Макс не светит ФИО/самозанятость публично — только email citypause@mail.ru
- Бюджет: VPS Promo на AdminVPS ~386₽/мес, домен ~203₽/год
- requirements.txt: fastapi, uvicorn, aiogram, python-multipart, python-dotenv
