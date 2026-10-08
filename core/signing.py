"""Подписание договора (ПЭП): подписанные документы, подпись, фото паспортов в PDF."""
import hashlib
import json
import os
from PIL import Image

from core.constants import CONTACTS_FILE, LANDLORD_EMAIL, PASSPORT_DIR
from core.contract_docs import generate_contract, generate_contract_pdf, generate_consent
from core.landlord import landlord_brand, landlord_domain
from core.logger import get_logger
from core.passports import load_passport_map, apply_passport_watermark

logger = get_logger(__name__)

def get_landlord_phone():
    """Телефон арендодателя для блока подписи — берётся из раздела «Контакты» в админке (тот же файл, что и /api/contacts)."""
    if os.path.exists(CONTACTS_FILE):
        try:
            with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            phone = saved.get("phone", "").strip()
            if phone:
                return phone
        except Exception as e:
            logger.warning("Не удалось прочитать телефон из контактов: %s", e)
    return "не указан"

def _sig_hash(*parts) -> str:
    """Короткий детерминированный хэш для блока электронной подписи."""
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:24]

def _doc_id_for(booking, doc_type):
    """Идентификатор документа — вычисляется один раз и используется и в шапке страниц, и в блоке подписи."""
    booking_ref = str(booking.get("username") or booking.get("id", ""))
    return _sig_hash(booking_ref, doc_type, booking.get("check_in", ""), booking.get("check_out", ""))

def _signature_block(booking, doc_type, doc_id):
    """
    Блок электронной подписи (ПЭП) в рамке с логотипом «Городская Пауза» —
    одинаковый по структуре для любого документа (договор, согласие на ПД).
    doc_id передаётся снаружи, чтобы совпадать с тем, что показан в шапке
    каждой страницы документа.
    """
    landlord_phone = get_landlord_phone()
    # Хэш арендодателя одинаковый для всех документов, пока не меняется телефон в контактах.
    landlord_sign_hash = _sig_hash(LANDLORD_EMAIL, landlord_phone, landlord_brand())

    booking_ref = str(booking.get("username") or booking.get("id", ""))
    guest_hash = _sig_hash(booking_ref, doc_type, booking.get("guest_phone", ""), booking.get("signed_at", ""))
    return (
        "\n\n[[SIGNATURE_BOX_START]]\n"
        "Документ подписан с использованием почты и номера телефона "
        "Арендодателя и Арендатора в качестве простой электронной подписи "
        "(ПЭП) в соответствии со ст. 4 ФЗ №63 «Об электронной подписи»\n\n"
        f"Идентификатор документа: {doc_id}\n\n"
        "Подпись Арендодателя:\n"
        f"{landlord_sign_hash}\n"
        f"{landlord_brand()}\n"
        f"Email: {LANDLORD_EMAIL}\n"
        f"Телефон: {landlord_phone}\n\n"
        "Подпись Арендатора:\n"
        f"{guest_hash}\n"
        f"{booking.get('guest_name', '')}\n"
        f"Паспорт: {booking.get('passport', '')}\n"
        f"Email: {booking.get('guest_email', '')}\n"
        f"Телефон: {booking.get('guest_phone', '')}\n\n"
        f"Дата подписания документа: {booking.get('signed_at', '')}\n"
        "[[SIGNATURE_BOX_END]]\n"
    )

EDO_AGREEMENT_TEXT = """СОГЛАШЕНИЕ ОБ ЭЛЕКТРОННОМ ДОКУМЕНТООБОРОТЕ

Настоящее Соглашение включено в состав электронного документа (в том
числе отдельным файлом в формате PDF) и считается оформленным в
письменной форме; им выражается согласие сторон на применение простой
электронной подписи в смысле Федерального закона от 06.04.2011 №63-ФЗ
«Об электронной подписи».

Стороны придали письменную форму настоящему Документу путём составления
одного электронного документа, подписав его электронной подписью.
Стороны согласны, что электронная форма настоящего Документа имеет
такую же юридическую силу, как документ, составленный и подписанный в
бумажном виде или на ином материальном носителе. В целях определения
актуальной (действующей) редакции Документа в случае его обсуждения
Сторонами каждая новая редакция Документа обозначается новым
(уникальным) идентификатором. Актуальной (действующей) редакцией
Документа является редакция, утверждённая Сторонами посредством
подтверждения подписания по персональной ссылке, направленной на
электронную почту Арендатора в системе бронирования {DOMAIN},
и отправки данной редакции на его электронную почту.

Электронный документ считается подписанным аналогом собственноручной
подписи, если он соответствует совокупности следующих требований:

 - Электронный документ подписан с использованием системы бронирования
   {DOMAIN} путём перехода Арендатора по персональной ссылке,
   направленной на указанный им адрес электронной почты, и подтверждения
   подписания на соответствующей странице;
 - В текст электронного документа включены электронная почта, номер
   телефона и паспортные (или иные идентифицирующие) данные Арендатора
   и Арендодателя;
 - В текст электронного документа включён идентификатор электронного
   документа, сгенерированный системой {DOMAIN}.
"""

def _passport_photos_with_grid(booking_ref):
    """
    Загружает прикреплённые фото паспорта гостя (main/reg1) и накладывает
    защитный водяной знак — повторяющуюся диагональную надпись
    "Запрещено копировать и использовать отдельно от данного документа" —
    для вставки в подписанный договор (сами оригиналы в PASSPORT_DIR
    остаются без изменений).
    """
    pm = load_passport_map()
    entry = pm.get(booking_ref)
    if not isinstance(entry, dict):
        return []

    images = []
    for slot in ("main", "reg1"):
        filename = entry.get(slot)
        if not filename:
            continue
        filepath = os.path.join(PASSPORT_DIR, filename)
        if not os.path.exists(filepath):
            continue
        try:
            images.append(apply_passport_watermark(Image.open(filepath)))
        except Exception as e:
            logger.warning(f"не удалось наложить водяной знак на фото паспорта {filename}: {e}")
    return images

def generate_signed_contract_pdf(booking):
    """
    Итоговый подписанный документ: договор (с приложениями и актом) +
    соглашение об электронном документообороте + фото паспорта гостя
    (с водяным знаком) + блок ПЭП — вызывается только после подписания.
    """
    booking_ref = str(booking.get("username") or booking.get("id", ""))
    doc_id = _doc_id_for(booking, "contract")
    main_text = generate_contract(booking) + "\n\n" + EDO_AGREEMENT_TEXT.replace("{DOMAIN}", landlord_domain())
    photos = _passport_photos_with_grid(booking_ref)
    signature_text = _signature_block(booking, "contract", doc_id)
    try:
        return generate_contract_pdf(
            main_text, booking_ref + "_podpisan",
            extra_blocks=photos + [signature_text],
            header_text=f"{landlord_brand()} {doc_id}",
        )
    except Exception as e:
        # Страховка: если из-за фото PDF не собрался, гость всё равно получает
        # договор (без страницы с фото), а ошибка остаётся в журнале сервера.
        logger.error(f"PDF договора {booking_ref} с фото паспорта не собрался: {e}. Собираю без фото.", exc_info=True)
        return generate_contract_pdf(
            main_text, booking_ref + "_podpisan",
            extra_blocks=[signature_text],
            header_text=f"{landlord_brand()} {doc_id}",
        )

def generate_signed_consent_pdf(booking):
    """Согласие на обработку ПД + блок ПЭП — тот же принцип, что и с договором."""
    booking_ref = str(booking.get("username") or booking.get("id", ""))
    doc_id = _doc_id_for(booking, "consent")
    text = generate_consent(booking) + _signature_block(booking, "consent", doc_id)
    return generate_contract_pdf(
        text, booking_ref + "_soglasie_pd",
        header_text=f"{landlord_brand()} {doc_id}",
        flat_numbering=True,
    )
