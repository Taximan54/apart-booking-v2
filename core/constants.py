"""Константы: пути к файлам данных, тексты по умолчанию, стандартные цены."""
import os


DEFAULT_CHECKIN_MEMO = """Добро пожаловать в Городскую Паузу!

Адрес: г. Новосибирск, ул. Дачная, д. 5, кв. 286, 22 этаж

КОД ЗАМКА: {{КОД_ЗАМКА}}

WiFi: название сети и пароль указаны на роутере в прихожей

Заезд с 15:00, выезд до 12:00

Правила проживания:
— Не курить в квартире
— Не приводить дополнительных гостей без согласования
— Соблюдать тишину с 23:00 до 7:00
— Бережно относиться к имуществу

Контакт хозяина: {{ТЕЛЕФОН_ХОЗЯИНА}}

Приятного отдыха!"""

DEFAULT_CHECKOUT_CHECKLIST = """Чек-лист перед выездом

Выезд до 12:00

Пожалуйста, перед уходом:

☐ Вынести мусор в контейнеры на первом этаже
☐ Помыть использованную посуду
☐ Закрыть все окна и балконную дверь
☐ Выключить свет и бытовую технику
☐ Закрыть кран горячей и холодной воды
☐ Убедиться что не забыли личные вещи
☐ Закрыть входную дверь (замок защёлкнется автоматически)

Спасибо что выбрали Городскую Паузу!
Ждём вас снова."""

DEFAULT_REVIEW_TEMPLATE = """Спасибо за ваш визит в Городскую Паузу!

Надеемся, что отдых прошёл комфортно.

Если вам понравилось, пожалуйста, оставьте отзыв на Авито — это очень помогает нам развиваться.

А для вашего следующего визита мы подготовили промокод на скидку {{ПРОЦЕНТ_СКИДКИ}}%:

ПРОМОКОД: {{ПРОМОКОД}}

Бронируйте напрямую на citypause.ru — никаких комиссий сервисов.

До встречи!"""

# =====================================================
# CONSTANTS
# =====================================================

DATA_DIR         = "/data"
PRICE_FILE       = f"{DATA_DIR}/prices.json"
PROMO_FILE       = f"{DATA_DIR}/promo_codes.json"
CODE_FILE        = f"{DATA_DIR}/door_code.json"
DESC_FILE        = f"{DATA_DIR}/description.txt"
DB_FILE          = f"{DATA_DIR}/bookings.db"
CONTRACT_FILE    = f"{DATA_DIR}/contract_template.txt"
CONTRACT_STATIC  = "static/contract_template.txt"
CHECKIN_FILE     = f"{DATA_DIR}/checkin_memo.txt"
CHECKOUT_FILE    = f"{DATA_DIR}/checkout_checklist.txt"
HOUSE_RULES_FILE = f"{DATA_DIR}/house_rules.txt"
SETTINGS_FILE    = f"{DATA_DIR}/settings.json"
REVIEW_FILE      = f"{DATA_DIR}/review_template.txt"
REVIEWS_FILE     = f"{DATA_DIR}/reviews.json"
CONTACTS_FILE    = f"{DATA_DIR}/contacts.json"
LANDLORD_FILE    = f"{DATA_DIR}/landlord.json"   # название бренда, домен сайта, адрес объекта
PAYMENT_FILE     = f"{DATA_DIR}/payment_settings.json"
PAYMENT_QR_PATH  = f"{DATA_DIR}/payment_qr.jpg"
DEFAULT_PAYMENT_SETTINGS = {"sbp_link": "", "sbp_phone": ""}
PLACES_FILE      = f"{DATA_DIR}/places.json"
DISCOUNTS_FILE   = f"{DATA_DIR}/discounts.json"
PHOTOS_DIR       = f"{DATA_DIR}/photos"
PHOTOS_ORDER_FILE = f"{DATA_DIR}/photos_order.json"
CONTRACTS_DIR    = f"{DATA_DIR}/contracts"
CONTRACT_PREVIEW_DIR = f"{DATA_DIR}/contract_preview"  # временный PDF-предпросмотр шаблона, в архив не попадает
AUTH_FILE        = f"{DATA_DIR}/admin_auth.json"
PASSPORT_DIR         = f"{DATA_DIR}/passports"           # ЗАЩИЩЁННАЯ папка — НЕ должна раздаваться nginx как статика!
PASSPORT_MAP_FILE    = f"{DATA_DIR}/passport_photos.json"  # {booking_ref: {"main":.., "reg1":..}}
PROPERTIES_FILE      = f"{DATA_DIR}/properties.json"       # реестр квартир (задел на white-label с несколькими объектами)
DEFAULT_PRICES   = {
    "weekday": 3500, "weekend": 4500, "cleaning": 1500,
    "included_guests": 1, "extra_guest_price": 100, "deposit": 6000,
    "stay_discounts": [
        {"min_nights": 5, "percent": 5},
        {"min_nights": 10, "percent": 10},
        {"min_nights": 14, "percent": 20},
        {"min_nights": 0, "percent": 0},
    ],
    "holiday_periods": [
        {"start": "", "end": "", "price": "", "label": ""},
        {"start": "", "end": "", "price": "", "label": ""},
    ],
}

os.makedirs(CONTRACTS_DIR, exist_ok=True)
MAIL_ADMIN    = os.getenv("MAIL_ADMIN", "citypause@mail.ru")

# =====================================================
# ПОДПИСАНИЕ ДОГОВОРА (ПЭП по 63-ФЗ, по образцу ОкиДоки)
# =====================================================
# Подписание — по персональной ссылке из письма на email гостя (без SMS):
# сам факт перехода по уникальной, известной только гостю ссылке и нажатия
# кнопки «Подписать» является простой электронной подписью.

LANDLORD_EMAIL = "citypause@mail.ru"

# API — SITE SETTINGS (обложка, карта)
# =====================================================

DEFAULT_SETTINGS = {
    "hero_photo": "", "hero_photo_mobile": "", "map_photo": "", "map_url": "", "map_service": "yandex",
    "site_name": "Городская Пауза",
    "hero_title": "Искусство комфортного проживания",
    "hero_subtitle": "Апартаменты премиум-класса · Посуточная аренда",
    "logo_font": "im_fell",
    "logo_bold": False,
    "logo_scale": 1.0,
    "nav_scale": 1.0,
    "color_theme": "gold",
    "background_theme": "black",
    "nav_labels": {
        "gallery": "Галерея",
        "amenities": "Удобства",
        "location": "Расположение",
        "prices": "Цены",
        "house_rules": "Правила проживания",
        "places": "Куда сходить?",
        "contacts": "Контакты",
        "booking": "Забронировать",
    },
    "hero_font": "cormorant",
    "hero_bold": False,
    "hero_title_scale": 1.0,
    "hero_subtitle_scale": 1.0,
    "hero_position": "center",
    "hero_carousel_enabled": True,
    "hero_carousel_seconds": 6,
    "header_opacity_level": 3,
    "header_blur_level": 2,
    "hero_eyebrow": "Апартаменты в городе",
    "nav_extra_label": "",
    "nav_extra_url": "",
    "timezone_offset": 7.0,
    "notify_checklist_time": "10:00",
    "notify_review_time": "14:00",
    "notify_owner_time": "09:00",
    "notify_email": "",
    "notify_telegram_chat_id": "",
    "amenities": [
        {"icon": "📶", "name": "Wi-Fi 300 Мбит"},
        {"icon": "❄️", "name": "Кондиционер"},
        {"icon": "🍳", "name": "Полная кухня"},
        {"icon": "🧺", "name": "Стиральная машина"},
        {"icon": "📺", "name": "Smart TV 43\""},
        {"icon": "🅿️", "name": "Парковка"},
        {"icon": "🔑", "name": "Умный замок"},
        {"icon": "🛁", "name": "Банные принадлежности"},
        {"icon": "", "name": ""},
        {"icon": "", "name": ""},
        {"icon": "", "name": ""},
        {"icon": "", "name": ""},
    ],
    "location_points": [
        {"icon": "🦁", "name": "Новосибирский зоопарк", "distance": "1.2 км · 15 мин пешком", "description": "Один из крупнейших зоопарков России — 770 видов животных"},
        {"icon": "🚇", "name": "Метро Заельцовская", "distance": "700 м · 8 мин пешком", "description": "Площадь Калинина — прямое сообщение с центром города"},
        {"icon": "🛍", "name": "ТЦ Роял Парк", "distance": "700 м · 8 мин пешком", "description": "Крупный торгово-развлекательный центр на Красном проспекте"},
        {"icon": "🍎", "name": "Золотое Яблоко", "distance": "9 мин пешком", "description": "Магазин косметики и парфюмерии премиум-класса"},
        {"icon": "", "name": "", "distance": "", "description": ""},
    ],
}

# =====================================================
# API — CONTACTS
# =====================================================

DEFAULT_CONTACTS = {"phone": "", "email": "", "telegram": "", "whatsapp": "", "max": ""}

# Данные арендодателя по умолчанию (используются, пока в админке не заданы свои)
DEFAULT_LANDLORD = {
    "brand_name": "Городская Пауза",
    "domain": "citypause.ru",
    "address": "г. Новосибирск, ул. Дачная, д. 5, квартира 286, 22 этаж",
}

OWNER_NOTIFY_FILE = f"{DATA_DIR}/owner_notify_log.json"
BACKUP_DIR         = f"{DATA_DIR}/backups"
BACKUP_LOG_FILE     = f"{DATA_DIR}/last_backup.json"
BACKUP_KEEP_COUNT   = 14   # сколько последних резервных копий хранить локально
