from aiogram import Router, types
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.filters import Command

from services.booking_service import (
    get_all_bookings,
    cancel_booking,
    block_dates,
    create_booking
)

router = Router()


# =====================================================
# SETTINGS
# =====================================================

BOOKINGS_PER_PAGE = 5


# =====================================================
# PAGINATION KEYBOARD
# =====================================================

def pagination_keyboard(page, total_pages):

    buttons = []

    row = []

    if page > 0:

        row.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"page_{page - 1}"
            )
        )

    if page < total_pages - 1:

        row.append(
            InlineKeyboardButton(
                text="➡️ Далее",
                callback_data=f"page_{page + 1}"
            )
        )

    if row:
        buttons.append(row)

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


# =====================================================
# BUILD BOOKINGS TEXT
# =====================================================

def build_bookings_text(bookings):

    text = "📋 Брони:\n\n"

    confirmed = 0
    cancelled = 0
    blocked = 0

    for row in bookings:

        status = row["status"]

        if status == "confirmed":
            confirmed += 1

        elif status == "cancelled":
            cancelled += 1

        elif status == "blocked":
            blocked += 1

        status_emoji = {
            "confirmed": "✅",
            "cancelled": "❌",
            "blocked": "⛔"
        }.get(status, "•")

        text += (
            f"#{row['id']}\n"
            f"📅 {row['check_in']} → {row['check_out']}\n"
            f"👤 @{row['username']}\n"
            f"👥 {row['guests']} гостей\n"
            f"{status_emoji} {status}\n\n"
        )

    text += (
        "──────────────\n"
        f"✅ Активных: {confirmed}\n"
        f"❌ Отменено: {cancelled}\n"
        f"⛔ Блоков: {blocked}\n"
    )

    return text


# =====================================================
# BUILD CANCEL BUTTONS
# =====================================================

def build_cancel_buttons(bookings):

    keyboard = []

    for row in bookings:

        if row["status"] != "cancelled":

            keyboard.append([

                InlineKeyboardButton(
                    text=f"❌ Отменить #{row['id']}",
                    callback_data=f"cancel_{row['id']}"
                )

            ])

    return keyboard


# =====================================================
# ADMIN PANEL
# =====================================================

@router.message(lambda m: m.text == "🛠 Админка")
async def admin_panel(message: types.Message):

    page = 0

    await show_bookings_page(
        message,
        page
    )


# =====================================================
# SHOW BOOKINGS PAGE
# =====================================================

async def show_bookings_page(message, page):

    bookings = get_all_bookings()

    if not bookings:

        await message.answer(
            "Броней пока нет"
        )

        return

    total_pages = (
        len(bookings) + BOOKINGS_PER_PAGE - 1
    ) // BOOKINGS_PER_PAGE

    start = page * BOOKINGS_PER_PAGE

    end = start + BOOKINGS_PER_PAGE

    current_bookings = bookings[start:end]

    text = build_bookings_text(
        current_bookings
    )

    keyboard = build_cancel_buttons(
        current_bookings
    )

    nav_markup = pagination_keyboard(
        page,
        total_pages
    )

    if nav_markup.inline_keyboard:

        keyboard.extend(
            nav_markup.inline_keyboard
        )

    markup = InlineKeyboardMarkup(
        inline_keyboard=keyboard
    )

    await message.answer(
        text,
        reply_markup=markup
    )


# =====================================================
# PAGINATION HANDLER
# =====================================================

@router.callback_query(
    lambda c: c.data.startswith("page_")
)
async def pagination_handler(
    callback: types.CallbackQuery
):

    page = int(
        callback.data.split("_")[1]
    )

    bookings = get_all_bookings()

    total_pages = (
        len(bookings) + BOOKINGS_PER_PAGE - 1
    ) // BOOKINGS_PER_PAGE

    start = page * BOOKINGS_PER_PAGE

    end = start + BOOKINGS_PER_PAGE

    current_bookings = bookings[start:end]

    text = build_bookings_text(
        current_bookings
    )

    keyboard = build_cancel_buttons(
        current_bookings
    )

    nav_markup = pagination_keyboard(
        page,
        total_pages
    )

    if nav_markup.inline_keyboard:

        keyboard.extend(
            nav_markup.inline_keyboard
        )

    markup = InlineKeyboardMarkup(
        inline_keyboard=keyboard
    )

    await callback.message.edit_text(
        text,
        reply_markup=markup
    )

    await callback.answer()


# =====================================================
# CANCEL BOOKING
# =====================================================

@router.callback_query(
    lambda c: c.data.startswith("cancel_")
)
async def cancel_booking_handler(
    callback: types.CallbackQuery
):

    booking_id = int(
        callback.data.split("_")[1]
    )

    cancel_booking(booking_id)

    await callback.answer(
        "Бронь отменена"
    )

    await callback.message.edit_text(
        f"❌ Бронь #{booking_id} отменена"
    )


# =====================================================
# ADMIN CALENDAR
# =====================================================

@router.message(Command("calendar"))
async def admin_calendar(message: types.Message):

    bookings = get_all_bookings()

    if not bookings:

        await message.answer(
            "Броней нет"
        )

        return

    text = "📅 Календарь:\n\n"

    for row in bookings:

        status_emoji = {
            "confirmed": "✅",
            "cancelled": "❌",
            "blocked": "⛔"
        }.get(row["status"], "•")

        text += (
            f"{status_emoji} "
            f"{row['check_in']} → "
            f"{row['check_out']}\n"
        )

    await message.answer(text)


# =====================================================
# BLOCK DATES COMMAND
# =====================================================

@router.message(Command("block"))
async def admin_block(message: types.Message):

    args = message.text.split()

    if len(args) != 3:

        await message.answer(
            "Пример:\n"
            "/block 2026-06-01 2026-06-05"
        )

        return

    check_in = args[1]
    check_out = args[2]

    block_dates(
        check_in,
        check_out
    )

    await message.answer(
        f"⛔ Даты заблокированы:\n"
        f"{check_in} → {check_out}"
    )