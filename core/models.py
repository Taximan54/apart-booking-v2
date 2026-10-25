"""Pydantic-модели запросов API."""
import copy
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from core.constants import DEFAULT_SETTINGS


# =====================================================
# PYDANTIC MODELS
# =====================================================

class Prices(BaseModel):
    weekday: int
    weekend: int
    cleaning: int
    included_guests: int = 1      # сколько гостей включено в базовую цену без доплаты
    extra_guest_price: int = 100  # доплата за каждого гостя сверх included_guests (₽/сутки)
    deposit: int = 6000           # депозит по умолчанию (₽) — можно переопределить для конкретной ручной брони
    stay_discounts: List[Dict[str, int]] = Field(default_factory=lambda: [
        {"min_nights": 5, "percent": 5},
        {"min_nights": 10, "percent": 10},
        {"min_nights": 14, "percent": 20},
        {"min_nights": 0, "percent": 0},
    ])  # скидка за длительность проживания — 4 настраиваемых порога (min_nights=0 — ячейка не используется)
    holiday_periods: List[Dict[str, str]] = Field(default_factory=lambda: [
        {"start": "", "end": "", "price": "", "label": ""},
        {"start": "", "end": "", "price": "", "label": ""},
    ])  # праздничные периоды с фиксированной ценой за ночь (даты в формате YYYY-MM-DD),


        # перекрывают обычную цену будни/выходные на эти конкретные даты

class PromoCodes(BaseModel):
    codes: Dict[str, int]   # {"SUMMER10": 10} — код -> процент скидки

class PromoValidate(BaseModel):
    code: str

class AdminLogin(BaseModel):
    password: str

class Review(BaseModel):
    id: Optional[str] = None
    author: str
    text: str
    rating: int = 5
    date: str = ""
    visible: bool = True

class Contacts(BaseModel):
    phone: str = ""
    email: str = ""
    telegram: str = ""
    whatsapp: str = ""
    max: str = ""
    instagram: str = ""

class ReviewPromoUpdate(BaseModel):
    percent: int           # размер скидки в промокоде после выезда (0 — письмо без промокода)
    subject: str = ""      # тема письма (можно использовать {{ИМЯ}})
    text: str              # текст письма


class ReviewPromoTest(BaseModel):
    email: str = ""        # куда отправить пробное письмо (пусто — на почту из «Контактов»)


class ReviewPromoSend(BaseModel):
    email: str             # кому отправить письмо с промокодом
    name: str = ""         # имя получателя (необязательно)
    code: str = ""         # существующий промокод (пусто — создать новый личный)
    percent: int = 10      # скидка для нового промокода
    subject: str = ""      # своя тема письма (пусто — тема из настроек письма после выезда)
    text: str = ""         # свой текст письма (пусто — стандартный текст письма после выезда)


class CatalogItemSettings(BaseModel):
    id: int                # номер объекта
    visible: bool = True   # показывать ли объект в каталоге
    title: str = ""        # название в каталоге (пусто — название сайта объекта)
    caption: str = ""      # короткая подпись, например «Центр, рядом с оперным»
    site_url: str = ""     # свой адрес сайта (если у объекта отдельный домен)


class CatalogFonts(BaseModel):
    # для каждой группы: шрифт (пусто — по умолчанию), жирность, размер (масштаб 0,5–2,5)
    brand_font: str = ""
    brand_bold: bool = False
    brand_scale: float = 1.0
    title_font: str = ""
    title_bold: bool = False
    title_scale: float = 1.0
    subtitle_font: str = ""
    subtitle_bold: bool = False
    subtitle_scale: float = 1.0
    card_font: str = ""
    card_bold: bool = False
    card_scale: float = 1.0
    text_font: str = ""
    text_scale: float = 1.0


class CatalogSettings(BaseModel):
    brand: str = ""              # название сети в шапке страницы (пусто — название бренда из «Данных арендодателя»)
    title: str = ""
    subtitle: str = ""
    background_theme: str = ""   # пусто — как у основного сайта
    color_theme: str = ""
    button_label: str = ""       # название кнопки перехода в каталог на страницах сайта (пусто — «Квартиры»)
    button_scale: float = 1.0    # размер шрифта этой кнопки (масштаб 0,5–2,5)
    columns: str = "auto"        # сетка карточек: auto / 1 / 2 / 3 / 4 в ряд
    fonts: CatalogFonts = Field(default_factory=CatalogFonts)
    items: List[CatalogItemSettings] = Field(default_factory=list)   # порядок в списке = порядок в каталоге


class PropertyCreate(BaseModel):
    name: str
    address: str = ""
    slug: str = ""         # адрес страницы объекта (латиница); если пусто — создаётся автоматически
    copy_settings: bool = False   # скопировать настройки (цены, описание, правила и т.д.) из основного объекта


class PropertyUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    active: Optional[bool] = None
    slug: Optional[str] = None


class CalendarPlatformCreate(BaseModel):
    name: str              # название площадки (Авито, Яндекс Путешествия, Суточно.ру или своё)
    source: str = ""       # короткий код площадки (латиница); если пусто — создаётся автоматически


class CalendarPlatformUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None        # ссылка на календарь площадки (пустая — выключает получение дат)
    enabled: Optional[bool] = None   # забирать ли календарь площадки автоматически


class LandlordSettings(BaseModel):
    brand_name: str = ""   # название бренда в письмах и документах
    domain: str = ""       # домен сайта, например example.ru
    address: str = ""      # адрес объекта для договора

class PaymentSettings(BaseModel):
    sbp_link: str = ""    # ссылка на приём оплаты по СБП (из банковского приложения)
    sbp_phone: str = ""   # номер телефона для перевода по СБП (может отличаться от контактного)

class SiteSettings(BaseModel):
    hero_photo: str = ""        # имя файла из /data/photos/
    hero_photo_mobile: str = ""  # отдельное фото hero для мобильных экранов (если пусто — используется hero_photo)
    map_photo: str = ""         # имя файла из /data/photos/
    map_url: str = ""           # ссылка на карту (Яндекс/2ГИС/Google)
    map_service: str = "yandex" # yandex / 2gis / google
    site_name: str = "Городская Пауза"
    hero_title: str = "Искусство комфортного проживания"
    hero_subtitle: str = "Апартаменты премиум-класса · Посуточная аренда"
    logo_font: str = "im_fell"  # im_fell(=PT Serif) / playfair / unifraktur(=Yeseva One) / tangerine(=Marck Script) / pacifico / great_vibes / berkshire(=Bad Script) / poiret — ключи исторические, реальные шрифты см. FONT_OPTIONS в admin.html
    logo_bold: bool = False
    logo_scale: float = 1.0     # 0.5 / 0.7 / 1.0 / 1.5 / 2.0 / 2.5 — размер логотипа и кнопки "Забронировать"
    nav_scale: float = 1.0      # 1.0–1.8 — размер пунктов меню (навигации)
    color_theme: str = "gold"   # gold / emerald / sapphire / burgundy / amethyst / dusty_rose / teal / copper / graphite
    background_theme: str = "black"  # black / white / pistachio / cream / midnight / charcoal — фон сайта
    nav_labels: Dict[str, str] = Field(default_factory=lambda: copy.deepcopy(DEFAULT_SETTINGS["nav_labels"]))
    hero_font: str = "cormorant"    # cormorant / im_fell / playfair / unifraktur / tangerine / pacifico / bebas
    hero_bold: bool = False
    hero_title_scale: float = 1.0    # 0.5 / 0.7 / 1.0 / 1.5 / 2.0 — размер hero-заголовка
    hero_subtitle_scale: float = 1.0 # 0.5 / 0.7 / 1.0 / 1.5 / 2.0 — размер hero-подзаголовка
    hero_position: str = "center"   # left / center / right — расположение текста на hero-фото
    hero_carousel_enabled: bool = True  # можно полностью выключить смену слайдов hero (даже если есть акции)
    hero_carousel_seconds: int = 6  # 3..15 — сколько секунд держится каждый слайд hero-карусели (обложка/акции) перед сменой
    header_opacity_level: int = 3   # 1..10 — прозрачность шапки навигации (1 = 10% непрозрачности, 10 = полностью непрозрачная)
    header_blur_level: int = 2      # 1..10 — размытие фона под шапкой (1 = 2px, 10 = 20px)
    hero_eyebrow: str = "Апартаменты в городе"  # надпись над заголовком (с чёрточками); пусто = скрыть строку целиком
    nav_extra_label: str = ""       # 8-й (опциональный) пункт меню — если пусто, не отображается
    nav_extra_url: str = ""         # ссылка для 8-го пункта меню
    timezone_offset: float = 7.0    # часовой пояс объекта (UTC+N) — влияет на время автоматических рассылок
    notify_checklist_time: str = "10:00"  # время отправки чек-листа выезда (в день выезда)
    notify_review_time: str = "14:00"     # время отправки запроса отзыва (на след. день после выезда)
    notify_owner_time: str = "09:00"       # время отправки владельцу сводки выездов (планирование уборки)
    notify_email: str = ""                # email владельца для уведомлений (о выездах и т.д.)
    notify_telegram_chat_id: str = ""      # Telegram Chat ID владельца для уведомлений
    amenities: List[Dict[str, str]] = Field(default_factory=lambda: copy.deepcopy(DEFAULT_SETTINGS["amenities"]))
    location_points: List[Dict[str, str]] = Field(default_factory=lambda: copy.deepcopy(DEFAULT_SETTINGS["location_points"]))

class HouseRulesText(BaseModel):
    text: str = ""

class Place(BaseModel):
    id: Optional[str] = None
    name: str
    category: str = ""
    photo: str = ""
    description: str = ""
    distance: str = ""
    visible: bool = True

class Discount(BaseModel):
    id: Optional[str] = None
    name: str
    photo: str = ""
    photo_mobile: str = ""  # отдельное фото для мобильной версии (если пусто — используется photo)
    description: str = ""
    visible: bool = True

class PhotoOrder(BaseModel):
    order: list   # список имён файлов в нужном порядке

class PhotoLabel(BaseModel):
    label: str = ""

class ChangePassword(BaseModel):
    old_password: str
    new_password: str

class DoorCode(BaseModel):
    code: str

class Description(BaseModel):
    text: str

class ContractTemplate(BaseModel):
    text: str

class CheckinMemo(BaseModel):
    text: str

class BookingCreate(BaseModel):
    check_in: str
    check_out: str
    nights: int
    guest_name: str
    guest_phone: str
    guest_email: str
    guests_count: int = 2
    notes: str = ""
    passport: str = ""
    passport_photo_main: str = ""   # разворот паспорта (фото, ФИО, серия/номер)
    passport_photo_reg1: str = ""   # страница прописки
    payment_method: str = "tbank"
    total_price: int = 0
    contract_signed: bool = False
    promo_code: str = ""

class ManualBookingCreate(BaseModel):
    source: str = "avito"   # площадка (avito / yandex / sutochno / свои из «Интеграций») / phone / other
    check_in: str
    check_out: str
    guest_name: str = ""    # необязательно — если площадка не даёт ФИО, гость впишет сам по ссылке
    guest_phone: str = ""
    guest_email: str = ""   # необязательно — если площадка (Авито и т.п.) не даёт email/телефон,
                            # ссылку на подписание можно скопировать и отправить в чат вручную
    guests_count: int = 2
    notes: str = ""
    passport: str = ""      # если заполнено админом — гостю не нужно будет вводить его самому
    total_price: int = 0
    deposit: int = 0        # 0 = использовать значение по умолчанию из Тарифов

class ResendContract(BaseModel):
    email: str

class BookingUpdate(BaseModel):
    status: str

class BlockDatesRequest(BaseModel):
    dates: List[str]
    reason: str = ""

class UnblockDatesRequest(BaseModel):
    start: str
    end: str

class PaymentNotify(BaseModel):
    booking_ref: str
    guest_name: str
    guest_phone: str
    guest_email: str
    total_price: int
    check_in: str
    check_out: str
