"""Фоновые рассылки и уведомления по расписанию."""
import asyncio
import json
import os

from config import ADMIN_IDS
from core.backup import (
    get_last_backup_date,
    create_backup_zip,
    send_backup_everywhere,
    set_last_backup_date,
)
from core.constants import PROMO_FILE
from core.data_store import (
    get_site_settings_dict,
    get_last_owner_notify_date,
    load_properties,
    set_last_owner_notify_date,
)
from core.db import get_db
from core.runtime import now_nsk, bot
from core.signing import (
    email_owner_checkout_reminder,
    email_checkout_checklist,
    email_review_request,
)
from services.booking_service import get_bookings_checkout_today, get_bookings_checkout_yesterday


# =====================================================
# SCHEDULER
# =====================================================

async def send_notifications():
    while True:
        now    = now_nsk()
        hour   = now.hour
        minute = now.minute
        try:
            settings = get_site_settings_dict()
            try:
                checklist_hour = int(str(settings.get("notify_checklist_time", "10:00")).split(":")[0])
            except Exception:
                checklist_hour = 10
            try:
                review_hour = int(str(settings.get("notify_review_time", "14:00")).split(":")[0])
            except Exception:
                review_hour = 14
            try:
                owner_hour = int(str(settings.get("notify_owner_time", "09:00")).split(":")[0])
            except Exception:
                owner_hour = 9

            # Уведомление владельцу (владельцам) о выездах сегодня — чтобы
            # спланировать уборку/горничную. Отправляется один раз в день.
            today_str = now.strftime("%Y-%m-%d")
            if hour == owner_hour and minute < 30 and get_last_owner_notify_date() != today_str:
                checkouts_today = get_bookings_checkout_today()
                if checkouts_today:
                    properties_map = {p["id"]: p["name"] for p in load_properties()}
                    lines = [f"\U0001f9f9 \u0421\u0435\u0433\u043e\u0434\u043d\u044f \u0432\u044b\u0435\u0437\u0436\u0430\u044e\u0442 ({len(checkouts_today)}):"]
                    for b in checkouts_today:
                        prop_name = properties_map.get(b.get("property_id", 1), "\u041a\u0432\u0430\u0440\u0442\u0438\u0440\u0430")
                        guest = b.get("guest_name") or "\u0413\u043e\u0441\u0442\u044c"
                        lines.append(f"\u2014 {prop_name}: {guest} (\u0434\u043e 12:00)")
                    owner_message = "\n".join(lines)

                    # Telegram: и жёстко прописанные ADMIN_IDS, и Chat ID из настроек (без дублей)
                    telegram_targets = set(ADMIN_IDS)
                    configured_chat_id = settings.get("notify_telegram_chat_id", "").strip()
                    if configured_chat_id:
                        try:
                            telegram_targets.add(int(configured_chat_id))
                        except ValueError:
                            pass
                    for admin_id in telegram_targets:
                        try:
                            await asyncio.wait_for(bot.send_message(admin_id, owner_message), timeout=5.0)
                        except Exception:
                            pass

                    # Email — на случай если Telegram недоступен/заблокирован
                    configured_email = settings.get("notify_email", "").strip()
                    if configured_email:
                        try:
                            import threading
                            threading.Thread(
                                target=email_owner_checkout_reminder,
                                args=(configured_email, checkouts_today, properties_map)
                            ).start()
                        except Exception:
                            pass
                set_last_owner_notify_date(today_str)

            # Чек-лист гостям кто выезжает сегодня (время настраивается в админке)
            if hour == checklist_hour and minute < 30:
                bookings = get_bookings_checkout_today()
                for b in bookings:
                    # Email — главный канал
                    if b.get("guest_email") and not b.get("checklist_sent"):
                        import threading
                        threading.Thread(target=email_checkout_checklist, args=(
                            b.get("guest_name",""),
                            b["guest_email"],
                            b.get("username") or b.get("id",""),
                            b.get("check_out","")
                        )).start()
                        conn2 = get_db()
                        conn2.execute("UPDATE bookings SET checklist_sent=1 WHERE id=? OR username=?",
                                      (b.get("id"), b.get("username")))
                        conn2.commit()
                        conn2.close()
                    # Telegram — best-effort
                    if b.get("user_id") and b["user_id"] != 0:
                        try:
                            await asyncio.wait_for(bot.send_message(
                                b["user_id"],
                                "\u0427\u0435\u043a-\u043b\u0438\u0441\u0442 \u043f\u0435\u0440\u0435\u0434 \u0432\u044b\u0435\u0437\u0434\u043e\u043c \u2014 \u0441\u0435\u0433\u043e\u0434\u043d\u044f \u0434\u043e 12:00\n\n"
                                "\u2610 \u0412\u044b\u043d\u0435\u0441\u0442\u0438 \u043c\u0443\u0441\u043e\u0440\n"
                                "\u2610 \u041f\u043e\u043c\u044b\u0442\u044c \u043f\u043e\u0441\u0443\u0434\u0443\n"
                                "\u2610 \u0417\u0430\u043a\u0440\u044b\u0442\u044c \u043e\u043a\u043d\u0430\n"
                                "\u2610 \u0412\u044b\u043a\u043b\u044e\u0447\u0438\u0442\u044c \u0441\u0432\u0435\u0442 \u0438 \u0442\u0435\u0445\u043d\u0438\u043a\u0443\n"
                                "\u2610 \u0417\u0430\u043f\u0440\u0435\u0442\u044c \u0434\u0432\u0435\u0440\u044c"
                            ), timeout=5.0)
                        except Exception:
                            pass

            # Отзыв + промокод гостям кто выехал вчера (время настраивается в админке)
            if hour == review_hour and minute < 30:
                bookings = get_bookings_checkout_yesterday()
                for b in bookings:
                    if b.get("guest_email") and not b.get("review_sent"):
                        # Генерируем персональный промокод для возврата гостя
                        guest_ref = (b.get("username") or b.get("id") or "")
                        promo_code = "RETURN" + str(guest_ref)[-4:].upper()
                        discount_pct = 10
                        # Сохраняем промокод в файл промокодов
                        try:
                            codes = {}
                            if os.path.exists(PROMO_FILE):
                                with open(PROMO_FILE, "r", encoding="utf-8") as pf:
                                    codes = json.load(pf)
                            codes[promo_code] = discount_pct
                            with open(PROMO_FILE, "w", encoding="utf-8") as pf:
                                json.dump(codes, pf, ensure_ascii=False)
                        except Exception:
                            pass
                        import threading
                        threading.Thread(target=email_review_request, args=(
                            b.get("guest_name",""),
                            b["guest_email"],
                            b.get("username") or b.get("id",""),
                            promo_code,
                            discount_pct
                        )).start()
                        conn2 = get_db()
                        conn2.execute("UPDATE bookings SET review_sent=1 WHERE id=? OR username=?",
                                      (b.get("id"), b.get("username")))
                        conn2.commit()
                        conn2.close()
                    # Telegram — best-effort
                    if b.get("user_id") and b["user_id"] != 0:
                        try:
                            await asyncio.wait_for(bot.send_message(
                                b["user_id"],
                                "\ud83d\ude4f \u0421\u043f\u0430\u0441\u0438\u0431\u043e \u0437\u0430 \u0432\u0438\u0437\u0438\u0442!\n\n"
                                "\u0411\u0443\u0434\u0435\u043c \u0440\u0430\u0434\u044b \u0432\u0438\u0434\u0435\u0442\u044c \u0432\u0430\u0441 \u0441\u043d\u043e\u0432\u0430! \ud83c\udfe0\u2728"
                            ), timeout=5.0)
                        except Exception:
                            pass

            # Резервное копирование БД + ключевых настроек — раз в сутки, в 04:00
            # (минимум нагрузки на сайт), отправляется админам в Telegram и
            # хранится локально (последние BACKUP_KEEP_COUNT копий)
            if hour == 4 and minute < 30 and get_last_backup_date() != today_str:
                try:
                    zip_path = create_backup_zip()
                    await send_backup_everywhere(zip_path)
                except Exception as e:
                    print("Backup error: " + str(e))
                set_last_backup_date(today_str)

        except Exception as e:
            print("Scheduler error: " + str(e))
        await asyncio.sleep(30 * 60)
