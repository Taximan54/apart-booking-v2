import json
import os

from aiogram import Router, types, F
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_IDS, BASE_URL

from services.booking_service import (
    get_all_bookings,
    cancel_booking,
    block_dates,
)

ADMIN_WEBAPP_URL = f"{BASE_URL}/static/admin_calendar.html"

router = Router()


# =====================================================
# PRICE STORAGE (файл рядом с проектом)
# =====================================================

PRICE_FILE = "data/prices.json"

DEFAULT_PRICES = {
    "weekday": 120,
    "weekend": 150,
    "cleaning": 30
}

def load_prices():
    if os.path.exists(PRICE_FILE):
        with open(PRICE_FILE, "r") as f:
            return json.load(f)
    return DEFAULT_PRICES.copy()

def save_prices(prices):
    os.makedirs("data", exist_ok=True)
    with open(PRICE_FILE, "w") as f:
        json.dump(prices, f)


# =====================================================
# FSM STATES
# =====================================================

class BlockDatesState(StatesGroup):
    waiting_check_in  = State()
    waiting_check_out = State()

class PriceState(StatesGroup):
    waiting_price_type  = State()
    waiting_price_value = State()


# =====================================================
# SETTINGS
# =====================================================

BOOKINGS_PER_PAGE = 5


# =====================================================
# ADMIN CHECK
# =====================================================

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# =====================================================
# MAIN ADMIN MENU
# =====================================================

def admin_menu_markup():

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


def admin_menu_markup_reply():
    """Reply-клавиатура для возврата в меню после блокировки."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🛠 Админка")]],
        resize_keyboard=True
    )


# =====================================================
# ADMIN PANEL ENTRY
# =====================================================

@router.message(lambda m: m.text == "🛠 Админка")
async def admin_panel(message: types.Message):

    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "🛠 Панель администратора",
        reply_markup=admin_menu_markup()
    )


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
                callback_data=f"admin_bookings_{page - 1}"
            )
        )

    if page < total_pages - 1:
        row.append(
            InlineKeyboardButton(
                text="➡️ Далее",
                callback_data=f"admin_bookings_{page + 1}"
            )
        )

    if row:
        buttons.append(row)

    # Кнопка возврата в меню
    buttons.append([
        InlineKeyboardButton(
            text="🏠 Главное меню",
            callback_data="admin_menu"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# =====================================================
# BUILD BOOKINGS TEXT
# =====================================================

def build_bookings_text(bookings, page, total_pages):

    text = f"📋 Брони (стр. {page + 1}/{total_pages}):\n\n"

    for row in bookings:

        status_emoji = {
            "confirmed": "✅",
            "cancelled": "❌",
            "blocked":   "⛔"
        }.get(row["status"], "•")

        text += (
            f"{status_emoji} #{row['id']}\n"
            f"📅 {row['check_in']} → {row['check_out']}\n"
            f"👤 @{row['username']}\n"
            f"👥 {row['guests']} гостей\n\n"
        )

    return text


# =====================================================
# BUILD CANCEL BUTTONS (с подтверждением)
# =====================================================

def build_cancel_buttons(bookings):

    keyboard = []

    for row in bookings:

        if row["status"] == "confirmed":

            keyboard.append([
                InlineKeyboardButton(
                    text=f"❌ Отменить #{row['id']} ({row['check_in']} → {row['check_out']})",
                    callback_data=f"confirm_cancel_{row['id']}"
                )
            ])

    return keyboard


# =====================================================
# SHOW BOOKINGS PAGE
# =====================================================

async def show_bookings_page(target, page: int):

    bookings = get_all_bookings()

    # Только не удалённые
    active = [b for b in bookings if b["status"] != "cancelled"]

    if not active:
        text = "📋 Активных броней нет"
        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_menu")
        ]])
        if hasattr(target, "edit_text"):
            await target.edit_text(text, reply_markup=markup)
        else:
            await target.answer(text, reply_markup=markup)
        return

    total_pages = (len(active) + BOOKINGS_PER_PAGE - 1) // BOOKINGS_PER_PAGE
    page = max(0, min(page, total_pages - 1))

    start = page * BOOKINGS_PER_PAGE
    end   = start + BOOKINGS_PER_PAGE
    current = active[start:end]

    text     = build_bookings_text(current, page, total_pages)
    keyboard = build_cancel_buttons(current)
    nav      = pagination_keyboard(page, total_pages)

    keyboard.extend(nav.inline_keyboard)

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    if hasattr(target, "edit_text"):
        await target.edit_text(text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


# =====================================================
# BOOKINGS CALLBACK
# =====================================================

@router.callback_query(lambda c: c.data.startswith("admin_bookings_"))
async def bookings_page_handler(callback: types.CallbackQuery):

    if not is_admin(callback.from_user.id):
        return

    page = int(callback.data.split("_")[-1])

    await show_bookings_page(callback.message, page)
    await callback.answer()


# =====================================================
# CONFIRM CANCEL (подтверждение перед отменой)
# =====================================================

@router.callback_query(lambda c: c.data.startswith("confirm_cancel_"))
async def confirm_cancel(callback: types.CallbackQuery):

    if not is_admin(callback.from_user.id):
        return

    booking_id = int(callback.data.split("_")[-1])

    bookings = get_all_bookings()
    booking  = next((b for b in bookings if b["id"] == booking_id), None)

    if not booking:
        await callback.answer("Бронь не найдена", show_alert=True)
        return

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да, отменить",
                callback_data=f"do_cancel_{booking_id}"
            ),
            InlineKeyboardButton(
                text="🔙 Нет, назад",
                callback_data="admin_bookings_0"
            )
        ]
    ])

    await callback.message.edit_text(
        f"⚠️ Отменить бронь #{booking_id}?\n\n"
        f"📅 {booking['check_in']} → {booking['check_out']}\n"
        f"👤 @{booking['username']}\n"
        f"👥 {booking['guests']} гостей\n\n"
        f"Это действие нельзя отменить.",
        reply_markup=markup
    )

    await callback.answer()


# =====================================================
# DO CANCEL
# =====================================================

@router.callback_query(lambda c: c.data.startswith("do_cancel_"))
async def do_cancel(callback: types.CallbackQuery):

    if not is_admin(callback.from_user.id):
        return

    booking_id = int(callback.data.split("_")[-1])

    cancel_booking(booking_id)

    await callback.answer("✅ Бронь отменена", show_alert=True)

    # Возвращаемся к списку
    await show_bookings_page(callback.message, 0)


# =====================================================
# STATISTICS
# =====================================================

@router.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):

    if not is_admin(callback.from_user.id):
        return

    bookings  = get_all_bookings()
    prices    = load_prices()

    confirmed = [b for b in bookings if b["status"] == "confirmed"]
    cancelled = [b for b in bookings if b["status"] == "cancelled"]
    blocked   = [b for b in bookings if b["status"] == "blocked"]

    # Считаем доход
    total_revenue = 0
    total_nights  = 0

    for b in confirmed:
        from datetime import datetime
        try:
            ci = datetime.strptime(b["check_in"],  "%Y-%m-%d")
            co = datetime.strptime(b["check_out"], "%Y-%m-%d")
            nights = (co - ci).days
            total_nights   += nights
            total_revenue  += nights * prices["weekday"]
        except Exception:
            pass

    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🏠 Главное меню",
            callback_data="admin_menu"
        )
    ]])

    await callback.message.edit_text(
        f"📊 Статистика\n\n"
        f"✅ Активных броней: {len(confirmed)}\n"
        f"❌ Отменённых: {len(cancelled)}\n"
        f"⛔ Заблокировано: {len(blocked)}\n\n"
        f"🌙 Всего ночей: {total_nights}\n"
        f"💰 Ожидаемый доход: €{total_revenue}\n\n"
        f"💵 Текущие цены:\n"
        f"  Будни: €{prices['weekday']}/ночь\n"
        f"  Выходные: €{prices['weekend']}/ночь\n"
        f"  Уборка: €{prices['cleaning']}",
        reply_markup=markup
    )

    await callback.answer()


# =====================================================
# PRICES MENU
# =====================================================

@router.callback_query(lambda c: c.data == "admin_prices")
async def admin_prices(callback: types.CallbackQuery):

    if not is_admin(callback.from_user.id):
        return

    prices = load_prices()

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"📅 Будни: €{prices['weekday']}",
                callback_data="set_price_weekday"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"🎉 Выходные: €{prices['weekend']}",
                callback_data="set_price_weekend"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"🧹 Уборка: €{prices['cleaning']}",
                callback_data="set_price_cleaning"
            )
        ],
        [
            InlineKeyboardButton(
                text="🏠 Главное меню",
                callback_data="admin_menu"
            )
        ]
    ])

    await callback.message.edit_text(
        f"💰 Управление ценами\n\n"
        f"Нажми на строку чтобы изменить цену.\n\n"
        f"Будни: €{prices['weekday']}/ночь\n"
        f"Выходные: €{prices['weekend']}/ночь\n"
        f"Уборка: €{prices['cleaning']}",
        reply_markup=markup
    )

    await callback.answer()


# =====================================================
# SET PRICE — выбор типа
# =====================================================

@router.callback_query(lambda c: c.data.startswith("set_price_"))
async def set_price_start(
    callback: types.CallbackQuery,
    state: FSMContext
):

    if not is_admin(callback.from_user.id):
        return

    price_type = callback.data.replace("set_price_", "")

    labels = {
        "weekday":  "будни",
        "weekend":  "выходные",
        "cleaning": "уборка"
    }

    await state.set_state(PriceState.waiting_price_value)
    await state.update_data(price_type=price_type)

    await callback.message.edit_text(
        f"💰 Введи новую цену для «{labels.get(price_type, price_type)}» (только число, €):\n\n"
        f"Например: 130"
    )

    await callback.answer()


# =====================================================
# SET PRICE — получаем значение
# =====================================================

@router.message(PriceState.waiting_price_value)
async def set_price_value(
    message: types.Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        return

    try:
        value = int(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Введи число. Например: 130"
        )
        return

    data       = await state.get_data()
    price_type = data["price_type"]

    prices = load_prices()
    prices[price_type] = value
    save_prices(prices)

    await state.clear()

    labels = {
        "weekday":  "Будни",
        "weekend":  "Выходные",
        "cleaning": "Уборка"
    }

    await message.answer(
        f"✅ Цена обновлена!\n\n"
        f"{labels.get(price_type, price_type)}: €{value}",
        reply_markup=admin_menu_markup()
    )


# =====================================================
# BLOCK DATES — открываем Mini App календарь
# =====================================================

@router.callback_query(lambda c: c.data == "admin_block_open")
async def block_open(
    callback: types.CallbackQuery
):

    if not is_admin(callback.from_user.id):
        return

    markup = ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(
                text="📅 Выбрать даты для блокировки",
                web_app=WebAppInfo(url=ADMIN_WEBAPP_URL)
            )
        ]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await callback.message.answer(
        "⛔ Выберите даты для блокировки в календаре:",
        reply_markup=markup
    )

    await callback.answer()


# =====================================================
# BLOCK DATES — получаем данные из Mini App
# =====================================================

@router.message(lambda m: m.web_app_data and m.web_app_data.data)
async def handle_webapp_data(message: types.Message):

    try:
        data = json.loads(message.web_app_data.data)
    except Exception:
        return

    # Блокировка от админа
    if data.get("action") == "block" and is_admin(message.from_user.id):

        check_in  = data["check_in"]
        check_out = data["check_out"]

        try:

            block_dates(check_in, check_out)

            await message.answer(
                f"⛔ Даты заблокированы\n\n"
                f"📅 {check_in} → {check_out}",
                reply_markup=admin_menu_markup_reply()
            )

        except Exception as e:

            error = str(e)

            if error == "DATES_ALREADY_BOOKED":
                await message.answer(
                    "❌ Эти даты уже заняты бронью.\n"
                    "Сначала отмените существующую бронь."
                )
            else:
                await message.answer(
                    "😔 Не удалось заблокировать даты. Попробуйте ещё раз."
                )


# =====================================================
# BACK TO MENU
# =====================================================

@router.callback_query(lambda c: c.data == "admin_menu")
async def back_to_menu(callback: types.CallbackQuery):

    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "🛠 Панель администратора",
        reply_markup=admin_menu_markup()
    )

    await callback.answer()