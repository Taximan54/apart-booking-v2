import json

from aiogram import Router, types
from aiogram.filters import CommandStart

from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
    FSInputFile,
    InputMediaPhoto,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from config import WEBAPP_URL, ADMIN_IDS

from services.booking_service import (
    create_booking,
    block_dates
)


router = Router()


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
🏠 Городская Пауза

✨ Современные апартаменты
📍 Удобное расположение
🛏 Комфортное проживание
📶 Быстрый Wi-Fi
🍳 Полноценная кухня
❄️ Кондиционер
📺 Smart TV

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
# MAIN KEYBOARD
# =====================================================

def main_keyboard():

    return ReplyKeyboardMarkup(

        keyboard=[

            [
                KeyboardButton(
                    text="📅 Забронировать",
                    web_app=WebAppInfo(
                        url=WEBAPP_URL
                    )
                )
            ],

            [
                KeyboardButton(
                    text="📸 Фото квартиры"
                ),

                KeyboardButton(
                    text="📋 Описание"
                )
            ],

            [
                KeyboardButton(
                    text="🛠 Админка"
                )
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
            ]
        ]
    )


# =====================================================
# START
# =====================================================

@router.message(CommandStart())
async def start(message: types.Message):

    await message.answer(

        "Добро пожаловать в «Городская Пауза» ✨",

        reply_markup=main_keyboard()
    )


# =====================================================
# PHOTOS
# =====================================================

@router.message(lambda m: m.text == "📸 Фото квартиры")
async def photos(message: types.Message):

    await send_photos(message)


# =====================================================
# DESCRIPTION
# =====================================================

@router.message(lambda m: m.text == "📋 Описание")
async def description(message: types.Message):

    await message.answer(
        """
🏠 Городская Пауза

✨ Современная квартира
🛏 До 2 гостей
📶 Высокоскоростной Wi-Fi
❄️ Кондиционер
🛁 Ванная комната
🍳 Полностью оборудованная кухня
📺 Smart TV
☕ Уютная атмосфера

📅 Для просмотра свободных дат
нажмите «Забронировать»
"""
    )


# =====================================================
# WEBAPP DATA — единый обработчик для всех Mini App
# =====================================================

@router.message(lambda m: m.web_app_data)
async def webapp_handler(message: Message):

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
                "🛠 Панель администратора",
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

    # ─── БРОНИРОВАНИЕ (для всех пользователей) ────
    try:

        booking_id = create_booking(

            user_id=message.from_user.id,

            username=message.from_user.username or "unknown",

            check_in=data["check_in"],

            check_out=data["check_out"],

            guests=data.get("guests", 2)
        )

        await message.answer(
            f"✅ Бронь #{booking_id}\n\n"
            f"📅 {data['check_in']} → {data['check_out']}\n"
            f"👥 {data.get('guests', 2)} гостей\n\n"
            f"Спасибо за бронирование ✨",
            reply_markup=main_keyboard()
        )

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
