"""
Письмо гостю после выезда: просьба об отзыве и промокод на следующий заезд.
Размер скидки, тема и текст письма настраиваются в админке (раздел «Промокоды»).
Письмо оформлено как обычное личное письмо (без рекламного оформления), чтобы почтовые
сервисы не относили его к рассылкам.
"""
import html as html_lib
import json
import os
import re

from core.constants import (
    DEFAULT_REVIEW_SUBJECT,
    DEFAULT_REVIEW_TEMPLATE,
    PROMO_FILE,
    REVIEW_FILE,
    REVIEW_PROMO_FILE,
)
from core.landlord import landlord_brand, landlord_domain, site_url
from core.logger import get_logger

logger = get_logger(__name__)

DEFAULT_PERCENT = 10
MAX_PERCENT = 90


# ---------------------------------------------------------------------------
# Настройки (размер скидки, тема письма)
# ---------------------------------------------------------------------------

def get_review_settings() -> dict:
    data = {}
    if os.path.exists(REVIEW_PROMO_FILE):
        try:
            with open(REVIEW_PROMO_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning("Не удалось прочитать настройки письма после выезда: %s", e)
    try:
        percent = int(data.get("percent", DEFAULT_PERCENT))
    except (TypeError, ValueError):
        percent = DEFAULT_PERCENT
    return {
        "percent": min(max(percent, 0), MAX_PERCENT),
        "subject": (data.get("subject") or "").strip() or DEFAULT_REVIEW_SUBJECT,
    }


def save_review_settings(percent: int, subject: str) -> dict:
    if not 0 <= percent <= MAX_PERCENT:
        raise ValueError(f"Скидка должна быть от 0 до {MAX_PERCENT}% (0 — письмо без промокода)")
    subject = (subject or "").strip()
    if len(subject) > 150:
        raise ValueError("Тема письма слишком длинная (макс. 150 символов)")
    with open(REVIEW_PROMO_FILE, "w", encoding="utf-8") as f:
        json.dump({"percent": percent, "subject": subject or DEFAULT_REVIEW_SUBJECT}, f, ensure_ascii=False)
    return get_review_settings()


# ---------------------------------------------------------------------------
# Решение админа по письму после выезда (по каждой брони)
# ---------------------------------------------------------------------------
# promo — отправить с промокодом, nopromo — только просьба об отзыве, skip — ничего не отправлять.
# Нет решения — письмо не уходит.

REVIEW_DECISIONS_FILE = os.path.join(os.path.dirname(REVIEW_PROMO_FILE), "review_decisions.json")
REVIEW_DECISIONS = ("promo", "nopromo", "skip")


def load_review_decisions() -> dict:
    if not os.path.exists(REVIEW_DECISIONS_FILE):
        return {}
    try:
        with open(REVIEW_DECISIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("Не удалось прочитать решения по письму после выезда: %s", e)
        return {}
    return data if isinstance(data, dict) else {}


def set_review_decision(ref, decision: str) -> None:
    if decision not in REVIEW_DECISIONS:
        raise ValueError("Неверное решение: ожидается promo, nopromo или skip")
    data = load_review_decisions()
    data[str(ref)] = decision
    tmp = REVIEW_DECISIONS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, REVIEW_DECISIONS_FILE)


# ---------------------------------------------------------------------------
# Промокод
# ---------------------------------------------------------------------------

def issue_promo_code(booking_ref, percent: int) -> str:
    """Создаёт личный промокод гостя (RETURN + 4 последних символа номера брони) и сохраняет его."""
    code = "RETURN" + str(booking_ref)[-4:].upper()
    codes = {}
    if os.path.exists(PROMO_FILE):
        with open(PROMO_FILE, "r", encoding="utf-8") as f:
            codes = json.load(f)
    codes[code] = percent
    with open(PROMO_FILE, "w", encoding="utf-8") as f:
        json.dump(codes, f, ensure_ascii=False)
    return code


# ---------------------------------------------------------------------------
# Текст и письмо
# ---------------------------------------------------------------------------

def load_review_template_text() -> str:
    if os.path.exists(REVIEW_FILE):
        with open(REVIEW_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return DEFAULT_REVIEW_TEMPLATE


def _fill(text: str, guest_name: str, promo_code: str, percent: int) -> str:
    return (text.replace("{{ИМЯ}}", (guest_name or "").strip() or "гость")
                .replace("{{ПРОМОКОД}}", promo_code or "")
                .replace("{{ПРОЦЕНТ_СКИДКИ}}", str(percent))
                .replace("{{САЙТ}}", landlord_domain()))


def build_review_email(guest_name: str, promo_code: str, percent: int, template_text: str = None, subject: str = None):
    """
    Возвращает (тема, html, обычный_текст). Если промокода нет (скидка 0%), строка с промокодом не добавляется.
    Если в тексте письма нет метки {{ПРОМОКОД}}, промокод добавляется отдельной строкой в конце.
    """
    raw = load_review_template_text() if template_text is None else template_text
    has_promo = bool(promo_code) and percent > 0
    if not has_promo:
        # без промокода (скидка 0%) строки с меткой промокода или процента убираются из текста
        kept = [ln for ln in raw.split("\n") if "{{ПРОМОКОД}}" not in ln and "{{ПРОЦЕНТ_СКИДКИ}}" not in ln]
        raw = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip("\n")
    body = _fill(raw, guest_name, promo_code if has_promo else "", percent)
    if has_promo and "{{ПРОМОКОД}}" not in raw:
        body += f"\n\nВаш промокод: {promo_code} (скидка {percent}% на следующее бронирование)."
    subject_text = _fill(subject if subject is not None else get_review_settings()["subject"], guest_name, promo_code if has_promo else "", percent)
    brand = landlord_brand()
    text = f"{body}\n\n--\n{brand}\n{site_url()}\n"
    html = (
        "<div style=\"font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.6;color:#222222\">"
        "<div style=\"white-space:pre-wrap\">" + html_lib.escape(body) + "</div>"
        "<p style=\"margin-top:24px;color:#555555\">С уважением,<br>" + html_lib.escape(brand) + "<br>"
        "<a href=\"" + html_lib.escape(site_url()) + "\" style=\"color:#555555\">" + html_lib.escape(landlord_domain()) + "</a></p>"
        "</div>"
    )
    return subject_text, html, text
