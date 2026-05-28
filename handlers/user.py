import json
import math
import os
from datetime import datetime, timezone, timedelta

from aiogram import Router, types, Bot
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
    FSInputFile,
    InputMediaPhoto,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove
)

from config import WEBAPP_URL, ADMIN_IDS

from services.booking_service import (
    create_booking,
    cancel_booking,
    block_dates,
    get_booking_by_id
)


router = Router()


# =====================================================
# TIMEZONE — Новосибирск UTC+7
# =====================================================

NSK = timezone(timedelta(hours=7))

def today_nsk() -> str:
    return datetime.now(NSK).strftime("%Y-%m-%d")


# =====================================================
# ССЫЛКА НА ОПЛАТУ Т-БАНК
# =====================================================

TBANK_PAYMENT_URL = "https://www.tbank.ru/cf/8TqKOl5vEpK"


# =====================================================
# ЗАГРУЗКА ОПИСАНИЯ ИЗ ФАЙЛА
# =====================================================

DESCRIPTION_FILE = "data/description.txt"

def load_description() -> str:
    if os.path.exists(DESCRIPTION_FILE):
        with open(DESCRIPTION_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return "Описание временно недоступно."


# =====================================================
# ИНСТРУКЦИЯ ПО ЗАСЕЛЕНИЮ С КОДОМ ЗАМКА
# =====================================================

def get_checkin_instructions(door_code: str = None) -> str:
    code_line = f"🔐 Код замка: {door_code}\n\n" if door_code else ""
    return (
        f"🏠 Инструкция по заселению — «Городская Пауза»\n\n"
        f"📍 Адрес:\n"
        f"Улица Дачная, дом 5, квартира 286\n\n"
        f"🚪 Домофон:\n"
        f"Открою через приложение при заселении\n\n"
        f"🔑 Ключи в почтовом ящике\n\n"
        f"{code_line}"
        f"🛗 Лифт: 22 этаж\n\n"
        f"📱 Перед заездом:\n"
        f"Пришлите фото паспорта для регистрации\n\n"
        f"💰 Оплата:\n"
        f"Полная оплата + депозит 6 000 ₽ при заселении\n\n"
        f"📞 Если возникли вопросы:\n"
        f"Пишите сюда — на связи 🤗"
    )


# =====================================================
# FSM STATES
# =====================================================

class ContactState(StatesGroup):
    waiting_message = State()


# =====================================================
# PHOTOS
# =====================================================

PHOTOS = [

    "static/images/1.jpg",
    "static/images/2.jpg",
    "static/images/3.jpg",
    "static/images/4.jpg",
    "static/images/5.jpg",

    "static/images/6.jpg",
    "static/images/7.jpg",
    "static/images/8.jpg",
    "static/images/9.jpg",
    "static/images/10.jpg"

]


# =====================================================
# PHOTO SENDER
# =====================================================

async def send_photos(message):

    media = []

    for i, photo in enumerate(PHOTOS):

        if i == 0:

            media.append(

                InputMediaPhoto(

                    media=FSInputFile(photo),

                    caption="""
🏠 Городская Пауза — квартира комфорт-класса

✨ Новый качественный ремонт
📍 Площадь Калинина, рядом с центром Новосибирска
🏢 Высокий этаж, панорамное остекление
🛏 Двухспальная кровать 160 см
📶 Wi-Fi, Smart TV, кондиционер

📅 Для бронирования:
нажмите кнопку «Забронировать»
"""
                )
            )

        else:

            media.append(
                InputMediaPhoto(
                    media=FSInputFile(photo)
                )
            )

    await message.answer_media_group(media)


# =====================================================
# KEYBOARDS
# =====================================================

def main_keyboard():

    return ReplyKeyboardMarkup(

        keyboard=[

            [
                KeyboardButton(
                    text="📅 Забронировать",
                    web_app=WebAppInfo(url=WEBAPP_URL)
                )
            ],

            [
                KeyboardButton(text="📸 Фото квартиры"),
                KeyboardButton(text="📋 Описание")
            ],

            [
                KeyboardButton(text="💬 Связь"),
                KeyboardButton(text="🛠 Админка")
            ]

        ],

        resize_keyboard=True
    )


def admin_inline_menu():

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Все брони",
                    callback_data="admin_bookings_0"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 Статистика",
                    callback_data="admin_stats"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⛔ Заблокировать даты",
                    callback_data="admin_block_open"
                ),
                InlineKeyboardButton(
                    text="💰 Цены",
                    callback_data="admin_prices"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔐 Код замка",
                    callback_data="admin_door_code"
                )
            ]
        ]
    )


# =====================================================
# HELPERS
# =====================================================

def calculate_nights(check_in: str, check_out: str) -> int:
    ci = datetime.strptime(check_in, "%Y-%m-%d")
    co = datetime.strptime(check_out, "%Y-%m-%d")
    return (co - ci).days


def get_price_for_range(check_in: str, check_out: str, prices: dict) -> int:
    ci = datetime.strptime(check_in, "%Y-%m-%d")
    co = datetime.strptime(check_out, "%Y-%m-%d")
    total = 0
    current = ci
    while current < co:
        day = current.weekday()
        if day >= 4:
            total += prices.get("weekend", 4500)
        else:
            total += prices.get("weekday", 3500)
        current = current.replace(day=current.day + 1)
    return total


def load_prices() -> dict:
    price_file = "/data/prices.json"
    if os.path.exists(price_file):
        with open(price_file, "r") as f:
            return json.load(f)
    return {"weekday": 3500, "weekend": 4500, "cleaning": 1500}


def format_price(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " ₽"


# =====================================================
# START
# =====================================================

@router.message(CommandStart())
async def start(message: types.Message):

    await message.answer(
        "Добро пожаловать в «Городская Пауза» ✨\n\n"
        "Квартира комфорт-класса в Новосибирске на площади Калинина.\n"
        "Выберите действие 👇",
        reply_markup=main_keyboard()
    )


# =====================================================
# PHOTOS
# =====================================================

@router.message(lambda m: m.text == "📸 Фото квартиры")
async def photos(message: types.Message):
    await send_photos(message)


# =====================================================
# DESCRIPTION — читаем из файла
# =====================================================

@router.message(lambda m: m.text == "📋 Описание")
async def description(message: types.Message):
    await message.answer(load_description())


# =====================================================
# АДМИНКА
# =====================================================

@router.message(lambda m: m.text == "🛠 Админка")
async def admin_entry(message: types.Message):

    if message.from_user.id not in ADMIN_IDS:
        return

    await message.answer(
        "🛠 Панель администратора",
        reply_markup=main_keyboard()
    )

    await message.answer(
        "Выберите действие:",
        reply_markup=admin_inline_menu()
    )


# =====================================================
# СВЯЗЬ — вход в режим
# =====================================================

@router.message(lambda m: m.text == "💬 Связь")
async def contact_start(
    message: types.Message,
    state: FSMContext
):

    if message.from_user.id in ADMIN_IDS:
        await message.answer("Вы администратор — пишите напрямую гостям.")
        return

    await state.set_state(ContactState.waiting_message)

    await message.answer(
        "💬 Напишите ваш вопрос или сообщение — "
        "мы ответим в ближайшее время.\n\n"
        "Для отмены нажмите /cancel",
        reply_markup=ReplyKeyboardRemove()
    )


# =====================================================
# СВЯЗЬ — пересылаем админам
# =====================================================

@router.message(ContactState.waiting_message)
async def contact_message(
    message: types.Message,
    state: FSMContext,
    bot: Bot
):

    await state.clear()

    user      = message.from_user
    username  = f"@{user.username}" if user.username else "без username"
    full_name = user.full_name or "Гость"

    reply_markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="↩️ Ответить",
            url=f"tg://user?id={user.id}"
        )
    ]])

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💬 Новое сообщение от гостя\n\n"
                f"👤 {full_name} ({username})\n"
                f"🆔 ID: {user.id}\n\n"
                f"📝 {message.text}",
                reply_markup=reply_markup
            )
        except Exception:
            pass

    await message.answer(
        "✅ Сообщение отправлено!\n\n"
        "Мы свяжемся с вами в ближайшее время. 🤗",
        reply_markup=main_keyboard()
    )


# =====================================================
# ОТМЕНА
# =====================================================

@router.message(lambda m: m.text == "/cancel")
async def cancel(
    message: types.Message,
    state: FSMContext
):
    await state.clear()
    await message.answer("Отменено.", reply_markup=main_keyboard())


# =====================================================
# ПОДТВЕРЖДЕНИЕ ОПЛАТЫ — callback от админа
# =====================================================

@router.callback_query(lambda c: c.data.startswith("payment_confirm_"))
async def payment_confirm(
    callback: types.CallbackQuery,
    bot: Bot
):

    if callback.from_user.id not in ADMIN_IDS:
        return

    parts      = callback.data.split("_")
    booking_id = int(parts[2])
    user_id    = int(parts[3])

    from handlers.admin import load_door_code
    door_code = load_door_code()
    booking   = get_booking_by_id(booking_id)

    try:
        if booking and booking["check_in"] == today_nsk():
            # Заезд сегодня — отправляем код замка сразу
            await bot.send_message(
                user_id,
                f"✅ Оплата подтверждена!\n\n"
                f"Бронь #{booking_id} подтверждена.\n\n"
                f"Так как ваш заезд сегодня — отправляем инструкцию сразу:\n\n"
                f"{get_checkin_instructions(door_code)}"
            )
        else:
            # Заезд не сегодня — код придёт за сутки
            await bot.send_message(
                user_id,
                f"✅ Оплата подтверждена!\n\n"
                f"Бронь #{booking_id} подтверждена.\n\n"
                f"За сутки до заезда в 12:00 вы получите инструкцию по заселению с кодом замка. 🏠"
            )
    except Exception:
        pass

    await callback.message.edit_text(
        callback.message.text + "\n\n✅ Оплата подтверждена, сообщение отправлено гостю."
    )

    await callback.answer("✅ Подтверждено!")


# =====================================================
# ОТКЛОНЕНИЕ ОПЛАТЫ — callback от админа
# =====================================================

@router.callback_query(lambda c: c.data.startswith("payment_reject_"))
async def payment_reject(
    callback: types.CallbackQuery,
    bot: Bot
):

    if callback.from_user.id not in ADMIN_IDS:
        return

    parts      = callback.data.split("_")
    booking_id = int(parts[2])
    user_id    = int(parts[3])

    cancel_booking(booking_id)

    try:
        await bot.send_message(
            user_id,
            f"❌ Оплата не подтверждена\n\n"
            f"Бронь #{booking_id} отменена.\n\n"
            f"Если это ошибка — напишите нам через кнопку «💬 Связь»."
        )
    except Exception:
        pass

    await callback.message.edit_text(
        callback.message.text + "\n\n❌ Оплата отклонена, бронь отменена."
    )

    await callback.answer("❌ Отклонено, бронь отменена.")


# =====================================================
# WEBAPP DATA — единый обработчик
# =====================================================

@router.message(lambda m: m.web_app_data)
async def webapp_handler(message: Message, bot: Bot):

    try:
        data = json.loads(message.web_app_data.data)
    except Exception:
        return

    action = data.get("action")

    # ─── БЛОКИРОВКА ДАТ (только для админа) ───────
    if action == "block":

        if message.from_user.id not in ADMIN_IDS:
            return

        check_in  = data["check_in"]
        check_out = data["check_out"]

        try:

            block_dates(check_in, check_out)

            await message.answer(
                f"⛔ Даты заблокированы\n\n"
                f"📅 {check_in} → {check_out}",
                reply_markup=main_keyboard()
            )

            await message.answer(
                "Выберите действие:",
                reply_markup=admin_inline_menu()
            )

        except Exception as e:

            error = str(e)

            if error == "DATES_ALREADY_BOOKED":
                await message.answer(
                    "❌ Эти даты уже заняты бронью.\n"
                    "Сначала отмените существующую бронь.",
                    reply_markup=main_keyboard()
                )
            else:
                await message.answer(
                    "😔 Не удалось заблокировать даты. Попробуйте ещё раз.",
                    reply_markup=main_keyboard()
                )

        return

    # ─── БРОНИРОВАНИЕ ────────────────────────────
    try:

        check_in  = data["check_in"]
        check_out = data["check_out"]
        guests    = data.get("guests", 2)

        booking_id = create_booking(
            user_id=message.from_user.id,
            username=message.from_user.username or "unknown",
            check_in=check_in,
            check_out=check_out,
            guests=guests
        )

        prices     = load_prices()
        nights     = calculate_nights(check_in, check_out)
        total      = get_price_for_range(check_in, check_out, prices)
        prepayment = math.ceil(total * 0.2)

        user      = message.from_user
        username  = f"@{user.username}" if user.username else "без username"
        full_name = user.full_name or "Гость"

        await message.answer(
            f"✅ Бронь #{booking_id} создана!\n\n"
            f"📅 {check_in} → {check_out}\n"
            f"🌙 Ночей: {nights}\n"
            f"👥 Гостей: {guests}\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💰 Стоимость: {format_price(total)}\n"
            f"💳 Предоплата 20%: {format_price(prepayment)}\n\n"
            f"Переведите предоплату по кнопке ниже.\n"
            f"В комментарии к переводу укажите: Бронь #{booking_id}\n\n"
            f"После проверки оплаты вы получите инструкцию по заселению.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"💳 Оплатить {format_price(prepayment)}",
                        url=TBANK_PAYMENT_URL
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="✅ Я оплатил",
                        callback_data=f"paid_{booking_id}"
                    )
                ]
            ])
        )

        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"🆕 Новая бронь #{booking_id}\n\n"
                    f"👤 {full_name} ({username})\n"
                    f"🆔 ID: {user.id}\n"
                    f"📅 {check_in} → {check_out}\n"
                    f"🌙 Ночей: {nights}\n"
                    f"👥 Гостей: {guests}\n\n"
                    f"💰 Сумма: {format_price(total)}\n"
                    f"💳 Ожидаем предоплату: {format_price(prepayment)}"
                )
            except Exception:
                pass

    except Exception as e:

        error = str(e)

        if error == "DATES_NOT_AVAILABLE":
            await message.answer(
                "📅 Эти даты уже заняты\n\n"
                "Пожалуйста, выберите другой период — "
                "кто-то успел забронировать раньше."
            )
        else:
            await message.answer(
                "😔 Что-то пошло не так\n\n"
                "Попробуйте ещё раз или напишите нам напрямую."
            )


# =====================================================
# КЛИЕНТ НАЖАЛ "Я ОПЛАТИЛ"
# =====================================================

@router.callback_query(lambda c: c.data.startswith("paid_"))
async def client_paid(
    callback: types.CallbackQuery,
    bot: Bot
):

    booking_id = int(callback.data.split("_")[1])
    user       = callback.from_user
    username   = f"@{user.username}" if user.username else "без username"
    full_name  = user.full_name or "Гость"

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💳 Гость сообщил об оплате\n\n"
                f"👤 {full_name} ({username})\n"
                f"🆔 ID: {user.id}\n"
                f"📋 Бронь #{booking_id}\n\n"
                f"Проверьте поступление предоплаты и подтвердите:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Подтвердить оплату",
                            callback_data=f"payment_confirm_{booking_id}_{user.id}"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="❌ Не оплачено",
                            callback_data=f"payment_reject_{booking_id}_{user.id}"
                        )
                    ]
                ])
            )
        except Exception:
            pass

    await callback.message.edit_reply_markup(reply_markup=None)

    await callback.answer("✅ Уведомили администратора!")

    await bot.send_message(
        user.id,
        "⏳ Администратор проверяет оплату.\n\n"
        "Обычно это занимает несколько минут.\n"
        "После подтверждения вы получите инструкцию по заселению. 🤗"
    )