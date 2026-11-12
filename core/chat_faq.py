"""
Чат-помощник на странице квартиры: популярные вопросы и ответы (без ИИ).
У каждого объекта свой набор. Вопросы гостей наш сервер не принимает и не хранит:
«Другой вопрос» открывает мессенджер или почту самого гостя (контакты берутся из раздела «Контакты»).
"""
import json
import os
import re
import secrets

from core.constants import DATA_DIR
from core.logger import get_logger
from core.properties import property_file

logger = get_logger(__name__)

CHAT_FAQ_FILE = os.path.join(DATA_DIR, "chat_faq.json")   # у основного объекта; у остальных: /data/properties/<номер>/chat_faq.json
MAX_ITEMS, TITLE_MAX, GREETING_MAX, QUESTION_MAX, ANSWER_MAX = 30, 40, 300, 120, 1000
DEFAULT_TITLE = "Помощник"
DEFAULT_GREETING = "Здравствуйте! Выберите вопрос, а если не нашли ответ, напишите нам."

# Готовый набор вопросов. Ответы по умолчанию пустые (вопрос без ответа гостю не показывается).
# hint: подсказка в админке; example=True: это готовый пример ответа, который можно вставить кнопкой и поправить.
DEFAULT_QUESTIONS = [
    {"id": "pets", "question": "Можно с животными?", "example": True,
     "hint": "К сожалению, с животными мы не размещаем: так в квартире остаётся комфортно и чисто для всех гостей."},
    {"id": "guests", "question": "Сколько человек можно?", "example": True,
     "hint": "В квартире комфортно размещаются до 2 гостей. Если вас больше, напишите нам, подскажем, что можно придумать."},
    {"id": "times", "question": "Во сколько заезд и выезд?", "example": True,
     "hint": "Заезд с 15:00, выезд до 12:00. Нужно раньше или позже? Напишите нам, посмотрим, что можно сделать."},
    {"id": "remote", "question": "Как проходит заезд?", "example": True,
     "hint": "Встречаться лично не нужно. После оплаты вы подписываете договор онлайн, и мы присылаем инструкцию по заселению и код от замка."},
    {"id": "documents", "question": "Нужны ли документы?", "example": True,
     "hint": "Для договора аренды нужны паспортные данные и фото паспорта. Мы попросим их при оформлении брони."},
    {"id": "kids", "question": "Можно с детьми?", "example": False,
     "hint": "Напишите, можно ли с детьми и есть ли детская кроватка или другие условия."},
    {"id": "smoking", "question": "Можно курить?", "example": False,
     "hint": "Напишите ваше правило про курение (в том числе на балконе) и коротко объясните причину."},
    {"id": "parties", "question": "Можно ли устраивать вечеринки?", "example": False,
     "hint": "Напишите, можно ли принимать гостей и шумные мероприятия. Часы тишины можно взять из правил проживания."},
    {"id": "parking", "question": "Есть ли парковка?", "example": False,
     "hint": "Напишите, где можно оставить машину и платно ли это."},
    {"id": "payment", "question": "Как оплатить бронь?", "example": False,
     "hint": "Напишите, как оплачивать (например, по СБП после выбора дат) и когда бронь считается подтверждённой."},
    {"id": "cancel", "question": "Можно отменить бронь?", "example": False,
     "hint": "Напишите ваши условия возврата предоплаты: когда она возвращается, а когда нет. Согласуйте с договором."},
    {"id": "amenities", "question": "Что есть в квартире?", "example": False,
     "hint": "Перечислите главное: Wi-Fi, кухня, постельное бельё, полотенца, техника и т.д."},
]
_DEFAULT_IDS = {q["id"] for q in DEFAULT_QUESTIONS}
_ID_RE = re.compile(r"^[a-z0-9_]{1,24}$")


def _default_settings() -> dict:
    return {"enabled": False, "title": DEFAULT_TITLE, "greeting": DEFAULT_GREETING,
            "items": [{"id": q["id"], "visible": True, "question": q["question"], "answer": ""} for q in DEFAULT_QUESTIONS]}


def clean_settings(data) -> dict:
    """Приводит настройки к безопасному виду: обрезает длину, чинит номера вопросов, убирает пустые вопросы."""
    data = data if isinstance(data, dict) else {}
    result = {
        "enabled": bool(data.get("enabled")),
        "title": str(data.get("title") or "").strip()[:TITLE_MAX] or DEFAULT_TITLE,
        "greeting": str(data.get("greeting") or "").strip()[:GREETING_MAX] or DEFAULT_GREETING,
        "items": [],
    }
    seen = set()
    for raw in (data.get("items") or [])[:MAX_ITEMS]:
        if not isinstance(raw, dict):
            continue
        question = re.sub(r"\s+", " ", str(raw.get("question") or "").strip())[:QUESTION_MAX]
        if not question:
            continue
        item_id = str(raw.get("id") or "")
        if not _ID_RE.match(item_id) or item_id in seen:
            item_id = "c_" + secrets.token_hex(3)
            while item_id in seen:
                item_id = "c_" + secrets.token_hex(3)
        seen.add(item_id)
        result["items"].append({"id": item_id, "visible": raw.get("visible", True) is not False,
                                "question": question, "answer": str(raw.get("answer") or "").strip()[:ANSWER_MAX]})
    return result


def load_settings(property_id: int = 1) -> dict:
    path = property_file(CHAT_FAQ_FILE, property_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return clean_settings(json.load(f))
        except Exception as e:
            logger.warning("Не удалось прочитать чат-помощник объекта %s: %s", property_id, e)
    return clean_settings(_default_settings())


def save_settings(property_id: int, data) -> dict:
    cleaned = clean_settings(data)
    path = property_file(CHAT_FAQ_FILE, property_id)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False)
    os.replace(tmp, path)
    return cleaned


def public_view(property_id: int = 1) -> dict:
    """Для сайта: только включённый чат, только показываемые вопросы с непустым ответом."""
    s = load_settings(property_id)
    items = [{"id": i["id"], "question": i["question"], "answer": i["answer"]}
             for i in s["items"] if i["visible"] and i["answer"]]
    if not s["enabled"] or not items:
        return {"enabled": False}
    return {"enabled": True, "title": s["title"], "greeting": s["greeting"], "items": items}


def admin_view(property_id: int = 1) -> dict:
    return {"settings": load_settings(property_id),
            "defaults": {q["id"]: {"hint": q["hint"], "example": q["example"]} for q in DEFAULT_QUESTIONS},
            "limits": {"items": MAX_ITEMS, "title": TITLE_MAX, "greeting": GREETING_MAX,
                       "question": QUESTION_MAX, "answer": ANSWER_MAX}}
