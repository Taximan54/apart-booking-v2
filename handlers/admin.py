from aiogram import Router, types

from config import ADMIN_IDS

from services.booking_service import (
    get_all_bookings,
    cancel_booking,
    block_dates
)

router = Router()


# =====================================================
# ADMIN PANEL
# =====================================================

@router.message(lambda m: m.text == "🛠 Админка")
async def admin_panel(message: types.Message):

    if message.from_user.id not in ADMIN_IDS:
        return

    text = """
🛠 ADMIN PANEL

📋 /bookings — все брони
❌ /cancel ID — отмена
🚫 /block YYYY-MM-DD YYYY-MM-DD
"""

    await message.answer(text)


# =====================================================
# ALL BOOKINGS
# =====================================================

@router.message(lambda m: m.text.startswith("/bookings"))
async def bookings(message: types.Message):

    if message.from_user.id not in ADMIN_IDS:
        return

    rows = get_all_bookings()

    if not rows:
        await message.answer("Броней нет")
        return

    text = "📋 БРОНИ:\n\n"

    for row in rows:

        text += f"""
ID: {row[0]}
USER: {row[1]}
DATES: {row[2]} → {row[3]}
GUESTS: {row[4]}
STATUS: {row[5]}

"""

    await message.answer(text)


# =====================================================
# CANCEL BOOKING
# =====================================================

@router.message(lambda m: m.text.startswith("/cancel"))
async def cancel(message: types.Message):

    if message.from_user.id not in ADMIN_IDS:
        return

    try:

        booking_id = int(message.text.split()[1])

        cancel_booking(booking_id)

        await message.answer(
            f"❌ Бронь #{booking_id} отменена"
        )

    except Exception as e:

        await message.answer(
            f"Ошибка: {e}"
        )


# =====================================================
# BLOCK DATES
# =====================================================

@router.message(lambda m: m.text.startswith("/block"))
async def block(message: types.Message):

    if message.from_user.id not in ADMIN_IDS:
        return

    try:

        parts = message.text.split()

        check_in = parts[1]
        check_out = parts[2]

        block_dates(check_in, check_out)

        await message.answer(
            f"🚫 Даты заблокированы:\n{check_in} → {check_out}"
        )

    except Exception as e:

        await message.answer(
            f"Ошибка: {e}"
        )