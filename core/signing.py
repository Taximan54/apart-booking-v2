"""Подписание договора (ПЭП) и письма гостю/владельцу о брони и документах."""
import hashlib
import json
import os
from PIL import Image
from datetime import datetime

from config import BASE_URL
from core.constants import (
    CONTACTS_FILE,
    LANDLORD_EMAIL,
    PASSPORT_DIR,
    CHECKIN_FILE,
    DEFAULT_CHECKIN_MEMO,
    CHECKOUT_FILE,
    DEFAULT_CHECKOUT_CHECKLIST,
    REVIEW_FILE,
    DEFAULT_REVIEW_TEMPLATE,
    MAIL_ADMIN,
)
from core.contract_docs import (
    generate_contract,
    generate_contract_pdf,
    generate_consent,
    save_contract,
)
from core.mailer import send_email
from core.passports import load_passport_map, apply_passport_watermark
from core.landlord import landlord_brand, landlord_domain, get_landlord_email, site_url
from core.logger import get_logger

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

def email_contract_signed(booking):
    """Письмо гостю с подписанным договором + согласием на ПД (оба с блоком ПЭП) — после подписания по ссылке."""
    booking_ref = str(booking.get("username") or booking.get("id", ""))
    guest_email = booking.get("guest_email", "")
    if not guest_email:
        return

    contract_pdf = generate_signed_contract_pdf(booking)
    consent_pdf  = generate_signed_consent_pdf(booking)

    html = (
        "<div style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;"
        "background:#0A0A0A;color:#F0E6C8;padding:40px'>"
        "<div style='text-align:center;margin-bottom:32px'>"
        "<div style='font-size:28px;letter-spacing:4px;color:#C9A84C'>" + landlord_brand().upper() + "</div></div>"
        "<div style='background:#141414;border:1px solid rgba(201,168,76,0.3);padding:32px;margin-bottom:24px'>"
        "<div style='font-size:16px;color:#C9A84C;margin-bottom:12px'>✅ Договор подписан</div>"
        f"<div style='font-size:13px;color:#A89060;margin-bottom:16px'>Бронь {booking_ref}</div>"
        "<div style='font-size:12px;color:#A89060;line-height:1.7'>"
        f"Договор подписан {booking.get('signed_at','')} — это простая электронная "
        "подпись (ПЭП) в соответствии с 63-ФЗ. Подписанный экземпляр договора "
        "(вместе с соглашением об электронном документообороте) и согласие на "
        "обработку персональных данных приложены к этому письму.</div></div>"
        "<div style='text-align:center;font-size:11px;color:#5A4A30'>" + get_landlord_email() + " | " + landlord_domain() + "</div></div>"
    )
    send_email(
        guest_email, f"Договор подписан — {booking_ref}", html,
        attachments=[
            {"filename": f"dogovor_{booking_ref}_podpisan.pdf", "filepath": contract_pdf},
            {"filename": f"soglasie_pd_{booking_ref}.pdf", "filepath": consent_pdf},
        ]
    )

    # Дублируем это же письмо на почту Городской Паузы (из Контактов) — для архива
    landlord_email = LANDLORD_EMAIL
    if os.path.exists(CONTACTS_FILE):
        try:
            with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
                saved_contacts = json.load(f)
            landlord_email = (saved_contacts.get("email") or "").strip() or LANDLORD_EMAIL
        except Exception as e:
            logger.warning("Не удалось прочитать email хозяина из контактов: %s", e)
    if landlord_email and landlord_email != guest_email:
        try:
            send_email(
                landlord_email, f"[Копия] Договор подписан — {booking_ref}", html,
                attachments=[
                    {"filename": f"dogovor_{booking_ref}_podpisan.pdf", "filepath": contract_pdf},
                    {"filename": f"soglasie_pd_{booking_ref}.pdf", "filepath": consent_pdf},
                ]
            )
        except Exception as e:
            logger.error(f"Copy to landlord email failed: {e}", exc_info=True)

def email_manual_contract(booking, target_email):
    """
    Письмо с договором для броней с внешних площадок (Авито и т.п.) или
    для ручной/повторной отправки договора администратором.
    В отличие от email_booking_confirmed — без текста про предоплату/остаток,
    так как условия оплаты на внешних площадках отличаются.
    """
    booking_ref  = str(booking.get("username") or booking.get("id", ""))
    check_in_fmt  = datetime.strptime(booking["check_in"],  "%Y-%m-%d").strftime("%d.%m.%Y")
    check_out_fmt = datetime.strptime(booking["check_out"], "%Y-%m-%d").strftime("%d.%m.%Y")
    contract_text = generate_contract(booking)
    contract_filename = f"dogovor_{booking_ref}.pdf"

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0A0A0A;color:#F0E6C8;padding:40px">
      <div style="text-align:center;margin-bottom:32px">
        <div style="font-size:28px;letter-spacing:4px;color:#C9A84C">{landlord_brand().upper()}</div>
      </div>
      <div style="background:#141414;border:1px solid #1E1E1E;padding:32px;margin-bottom:24px">
        <div style="font-size:16px;color:#C9A84C;margin-bottom:16px">Договор аренды апартаментов</div>
        <div style="font-size:13px;color:#A89060;margin-bottom:24px">Бронь {booking_ref}</div>
        <table style="width:100%;border-collapse:collapse">
          <tr><td style="padding:8px 0;color:#5A4A30;font-size:12px">Заезд</td>
              <td style="color:#F0E6C8;font-size:12px">{check_in_fmt} с 15:00</td></tr>
          <tr><td style="padding:8px 0;color:#5A4A30;font-size:12px">Выезд</td>
              <td style="color:#F0E6C8;font-size:12px">{check_out_fmt} до 12:00</td></tr>
        </table>
      </div>
      <div style="background:#141414;border:1px solid #1E1E1E;padding:24px;margin-bottom:24px">
        <div style="font-size:12px;color:#A89060;line-height:1.7">
          Договор для ознакомления и подписания приложен к этому письму отдельным
          файлом ({contract_filename}). Пожалуйста, ознакомьтесь с условиями перед заездом.
        </div>
      </div>
      <div style="text-align:center;font-size:11px;color:#5A4A30">{get_landlord_email()} &nbsp;|&nbsp; {landlord_domain()}</div>
    </div>
    """
    save_contract(booking_ref, contract_text)
    pdf_path = generate_contract_pdf(contract_text, booking_ref)
    send_email(
        target_email,
        f"Договор аренды — {booking_ref}",
        html,
        attachments=[{"filename": contract_filename, "filepath": pdf_path}]
    )

def email_complete_data_request(booking):
    """
    Письмо гостю по ручной брони (Авито и т.п.) — ссылка на страницу, где он
    донабирает недостающие паспортные данные (если админ их не указал),
    обязательно прикрепляет фото паспорта и подписывает договор. После
    подписания гостю отдельным письмом уходит уже готовый подписанный PDF
    (см. email_contract_signed).
    """
    booking_ref = str(booking.get("username") or booking.get("id", ""))
    guest_email = booking.get("guest_email", "")
    if not guest_email:
        return
    check_in_fmt  = datetime.strptime(booking["check_in"],  "%Y-%m-%d").strftime("%d.%m.%Y")
    check_out_fmt = datetime.strptime(booking["check_out"], "%Y-%m-%d").strftime("%d.%m.%Y")
    sign_token = booking.get("sign_token", "")
    complete_link = f"{BASE_URL}/complete/{sign_token}" if sign_token else ""

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0A0A0A;color:#F0E6C8;padding:40px">
      <div style="text-align:center;margin-bottom:32px">
        <div style="font-size:28px;letter-spacing:4px;color:#C9A84C">{landlord_brand().upper()}</div>
      </div>
      <div style="background:#141414;border:1px solid #1E1E1E;padding:32px;margin-bottom:24px">
        <div style="font-size:16px;color:#C9A84C;margin-bottom:16px">Бронирование подтверждено</div>
        <div style="font-size:13px;color:#A89060;margin-bottom:24px">Бронь {booking_ref}</div>
        <table style="width:100%;border-collapse:collapse">
          <tr><td style="padding:8px 0;color:#5A4A30;font-size:12px">Заезд</td>
              <td style="color:#F0E6C8;font-size:12px">{check_in_fmt} с 15:00</td></tr>
          <tr><td style="padding:8px 0;color:#5A4A30;font-size:12px">Выезд</td>
              <td style="color:#F0E6C8;font-size:12px">{check_out_fmt} до 12:00</td></tr>
        </table>
      </div>
      <div style="background:#141414;border:1px solid rgba(201,168,76,0.3);padding:24px;margin-bottom:24px">
        <div style="font-size:12px;color:#A89060;line-height:1.7">
          Для оформления договора аренды, пожалуйста, перейдите по ссылке ниже —
          там нужно будет прикрепить фото паспорта (и указать паспортные данные,
          если этого ещё не сделали) и подписать договор. Это займёт пару минут.
        </div>
        <div style="text-align:center;margin-top:20px">
          <a href="{complete_link}" style="display:inline-block;background:#C9A84C;color:#0A0A0A;
             text-decoration:none;padding:12px 28px;font-size:12px;letter-spacing:0.05em;font-weight:bold">
            Заполнить данные и подписать договор</a>
        </div>
      </div>
      <div style="text-align:center;font-size:11px;color:#5A4A30">{get_landlord_email()} &nbsp;|&nbsp; {landlord_domain()}</div>
    </div>
    """
    send_email(guest_email, f"Бронирование подтверждено — {booking_ref}", html)

def load_checkin_memo(door_code=""):
    """Загружает памятку гостю, подставляет код замка и телефон хозяина из раздела «Контакты»."""
    if os.path.exists(CHECKIN_FILE):
        with open(CHECKIN_FILE, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = DEFAULT_CHECKIN_MEMO
    return (text
            .replace("{{КОД_ЗАМКА}}", str(door_code))
            .replace("{{ТЕЛЕФОН_ХОЗЯИНА}}", get_landlord_phone()))

def load_checkout_checklist():
    """Загружает чек-лист выезда."""
    if os.path.exists(CHECKOUT_FILE):
        with open(CHECKOUT_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return DEFAULT_CHECKOUT_CHECKLIST

def load_review_template(promo_code="", discount_percent=10):
    """Загружает шаблон письма с просьбой об отзыве."""
    if os.path.exists(REVIEW_FILE):
        with open(REVIEW_FILE, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = DEFAULT_REVIEW_TEMPLATE
    return text.replace("{{ПРОМОКОД}}", promo_code).replace("{{ПРОЦЕНТ_СКИДКИ}}", str(discount_percent))

def email_checkin_memo(guest_name, guest_email, booking_ref, check_in, door_code):
    """Письмо гостю — полная оплата получена, памятка с кодом замка."""
    memo_text = load_checkin_memo(door_code)
    html = (
        "<div style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;"
        "background:#0A0A0A;color:#F0E6C8;padding:40px'>"
        "<div style='text-align:center;margin-bottom:32px'>"
        "<div style='font-size:28px;letter-spacing:4px;color:#C9A84C'>"
        "\u0413\u041e\u0420\u041e\u0414\u0421\u041a\u0410\u042f \u041f\u0410\u0423\u0417\u0410</div>"
        "</div>"
        "<div style='background:#141414;border:1px solid #1E1E1E;padding:32px;margin-bottom:24px'>"
        "<div style='font-size:13px;color:#C9A84C;margin-bottom:16px'>"
        "\u041f\u0410\u041c\u042f\u0422\u041a\u0410 \u0413\u041e\u0421\u0422\u042e</div>"
        "<div style='font-size:13px;color:#F0E6C8;margin-bottom:8px'>"
        "\u0414\u043e\u0431\u0440\u043e \u043f\u043e\u0436\u0430\u043b\u043e\u0432\u0430\u0442\u044c, " + guest_name + "!</div>"
        "<div style='font-size:12px;color:#A89060;margin-bottom:24px'>"
        "\u0411\u0440\u043e\u043d\u044c: " + booking_ref + " | \u0417\u0430\u0435\u0437\u0434: " + check_in + "</div>"
        "<pre style='font-size:12px;color:#F0E6C8;line-height:1.8;white-space:pre-wrap;"
        "font-family:Arial,sans-serif;background:#0A0A0A;padding:20px;border:1px solid #1E1E1E'>"
        + memo_text + "</pre>"
        "</div>"
        "<div style='text-align:center;font-size:10px;color:#5A4A30;margin-top:24px'>"
        "" + landlord_domain() + " \u2014 " + get_landlord_email() + "</div>"
        "</div>"
    )
    send_email(guest_email,
               "\u041f\u0430\u043c\u044f\u0442\u043a\u0430 \u0433\u043e\u0441\u0442\u044e \u2014 " + booking_ref,
               html)

def email_checkout_checklist(guest_name, guest_email, booking_ref, check_out):
    """Письмо гостю — чек-лист перед выездом."""
    checklist_text = load_checkout_checklist()
    html = (
        "<div style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;"
        "background:#0A0A0A;color:#F0E6C8;padding:40px'>"
        "<div style='text-align:center;margin-bottom:32px'>"
        "<div style='font-size:28px;letter-spacing:4px;color:#C9A84C'>"
        "\u0413\u041e\u0420\u041e\u0414\u0421\u041a\u0410\u042f \u041f\u0410\u0423\u0417\u0410</div>"
        "</div>"
        "<div style='background:#141414;border:1px solid #1E1E1E;padding:32px;margin-bottom:24px'>"
        "<div style='font-size:13px;color:#C9A84C;margin-bottom:16px'>"
        "\u0427\u0415\u041a-\u041b\u0418\u0421\u0422 \u041f\u0415\u0420\u0415\u0414 \u0412\u042b\u0415\u0417\u0414\u041e\u041c</div>"
        "<div style='font-size:13px;color:#F0E6C8;margin-bottom:8px'>"
        "\u0423\u0432\u0430\u0436\u0430\u0435\u043c\u044b\u0439 " + guest_name + "!</div>"
        "<div style='font-size:12px;color:#A89060;margin-bottom:24px'>"
        "\u0411\u0440\u043e\u043d\u044c: " + booking_ref + " | \u0412\u044b\u0435\u0437\u0434: " + check_out + " \u0434\u043e 12:00</div>"
        "<pre style='font-size:12px;color:#F0E6C8;line-height:1.8;white-space:pre-wrap;"
        "font-family:Arial,sans-serif;background:#0A0A0A;padding:20px;border:1px solid #1E1E1E'>"
        + checklist_text + "</pre>"
        "</div>"
        "<div style='text-align:center;font-size:10px;color:#5A4A30;margin-top:24px'>"
        "" + landlord_domain() + " \u2014 " + get_landlord_email() + "</div>"
        "</div>"
    )
    send_email(guest_email,
               "\u0427\u0435\u043a-\u043b\u0438\u0441\u0442 \u043f\u0435\u0440\u0435\u0434 \u0432\u044b\u0435\u0437\u0434\u043e\u043c \u2014 " + booking_ref,
               html)

def email_review_request(guest_name, guest_email, booking_ref, promo_code, discount_percent):
    """Письмо гостю — просьба об отзыве + промокод на следующий заезд."""
    review_text = load_review_template(promo_code, discount_percent)
    html = (
        "<div style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;"
        "background:#0A0A0A;color:#F0E6C8;padding:40px'>"
        "<div style='text-align:center;margin-bottom:32px'>"
        "<div style='font-size:28px;letter-spacing:4px;color:#C9A84C'>"
        "\u0413\u041e\u0420\u041e\u0414\u0421\u041a\u0410\u042f \u041f\u0410\u0423\u0417\u0410</div>"
        "</div>"
        "<div style='background:#141414;border:1px solid #1E1E1E;padding:32px;margin-bottom:24px'>"
        "<div style='font-size:13px;color:#C9A84C;margin-bottom:16px'>"
        "\u0421\u041f\u0410\u0421\u0418\u0411\u041e \u0417\u0410 \u0412\u0418\u0417\u0418\u0422!</div>"
        "<pre style='font-size:13px;color:#F0E6C8;line-height:1.8;white-space:pre-wrap;"
        "font-family:Arial,sans-serif'>" + review_text + "</pre>"
        "<div style='margin-top:24px;padding:16px;background:rgba(201,168,76,.06);"
        "border:1px solid rgba(201,168,76,.3);text-align:center'>"
        "<div style='font-size:10px;color:#5A4A30;margin-bottom:8px'>\u0412\u0410\u0428 \u041f\u0420\u041e\u041c\u041e\u041a\u041e\u0414</div>"
        "<div style='font-size:24px;color:#C9A84C;letter-spacing:4px'>" + promo_code + "</div>"
        "<div style='font-size:11px;color:#A89060;margin-top:8px'>"
        "\u0421\u043a\u0438\u0434\u043a\u0430 " + str(discount_percent) + "% \u043d\u0430 \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0435\u0435 \u0431\u0440\u043e\u043d\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435</div>"
        "</div>"
        "</div>"
        "<div style='text-align:center;margin-top:24px'>"
        "<a href='" + site_url() + "' style='color:#C9A84C;font-size:13px;"
        "letter-spacing:2px'>" + landlord_domain().upper() + "</a>"
        "</div>"
        "</div>"
    )
    send_email(guest_email,
               "\u0421\u043f\u0430\u0441\u0438\u0431\u043e \u0437\u0430 \u0432\u0438\u0437\u0438\u0442 \u2014 \u043f\u043e\u0434\u0430\u0440\u043e\u043a \u0434\u043b\u044f \u0432\u0430\u0441",
               html)

def email_owner_checkout_reminder(to_email, checkouts_today, properties_map):
    """Письмо владельцу — сводка выездов сегодня, для планирования уборки."""
    cards_html = ""
    for b in checkouts_today:
        prop_name = properties_map.get(b.get("property_id", 1), "Квартира")
        guest = b.get("guest_name") or "Гость"
        phone = b.get("guest_phone") or "—"
        ref = b.get("username") or str(b.get("id", ""))
        cards_html += (
            "<div style='border-left:3px solid #C9A84C;padding:14px 18px;margin-bottom:12px;background:#141414'>"
            "<div style='font-size:15px;color:#F0E6C8;font-weight:600;margin-bottom:6px'>" + prop_name + "</div>"
            "<div style='font-size:13px;color:#A89060'>" + guest + " &nbsp;·&nbsp; " + phone + "</div>"
            "<div style='font-size:11px;color:#5A4A30;margin-top:6px'>Бронь " + ref + " &nbsp;·&nbsp; выезд до 12:00</div>"
            "</div>"
        )
    html = (
        "<div style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;"
        "background:#0A0A0A;color:#F0E6C8;padding:40px'>"
        "<div style='text-align:center;margin-bottom:32px'>"
        "<div style='font-size:24px;letter-spacing:2px;color:#C9A84C'>🧹 Выезды сегодня (" + str(len(checkouts_today)) + ")</div>"
        "</div>"
        + cards_html +
        "<div style='text-align:center;margin-top:24px;font-size:11px;color:#5A4A30'>"
        "Не забудьте запланировать уборку / горничную по каждому адресу</div>"
        "</div>"
    )
    send_email(to_email, f"Выезды сегодня ({len(checkouts_today)})", html)

def email_booking_created(booking_id, guest_name, guest_email, check_in, check_out, nights, total, prepay):
    """Письмо гостю — бронь создана, ожидаем оплату."""
    html = (
        "<div style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;"
        "background:#0A0A0A;color:#F0E6C8;padding:40px'>"
        "<div style='text-align:center;margin-bottom:32px'>"
        "<div style='font-size:28px;letter-spacing:4px;color:#C9A84C'>"
        "\u0413\u041e\u0420\u041e\u0414\u0421\u041a\u0410\u042f \u041f\u0410\u0423\u0417\u0410</div>"
        "<div style='font-size:11px;color:#5A4A30;margin-top:6px'>"
        "\u0410\u043f\u0430\u0440\u0442\u0430\u043c\u0435\u043d\u0442\u044b \u043f\u043e\u0441\u0443\u0442\u043e\u0447\u043d\u043e</div>"
        "</div>"
        "<div style='background:#141414;border:1px solid #1E1E1E;padding:32px;margin-bottom:24px'>"
        "<div style='font-size:13px;color:#C9A84C;margin-bottom:8px'>"
        "\u0411\u0420\u041e\u041d\u042c \u0421\u041e\u0417\u0414\u0410\u041d\u0410</div>"
        "<div style='font-size:32px;color:#C9A84C;letter-spacing:3px;margin-bottom:24px'>"
        + booking_id + "</div>"
        "<table style='width:100%;border-collapse:collapse'>"
        "<tr><td style='padding:8px 0;color:#5A4A30;font-size:12px'>"
        "\u0413\u043e\u0441\u0442\u044c</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + guest_name + "</td></tr>"
        "<tr><td style='padding:8px 0;color:#5A4A30;font-size:12px'>"
        "\u0417\u0430\u0435\u0437\u0434</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + check_in + "</td></tr>"
        "<tr><td style='padding:8px 0;color:#5A4A30;font-size:12px'>"
        "\u0412\u044b\u0435\u0437\u0434</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + check_out + "</td></tr>"
        "<tr><td style='padding:8px 0;color:#5A4A30;font-size:12px'>"
        "\u041d\u043e\u0447\u0435\u0439</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + str(nights) + "</td></tr>"
        "<tr style='border-top:1px solid #1E1E1E'>"
        "<td style='padding:12px 0;color:#A89060;font-size:13px'>"
        "\u0421\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c</td>"
        "<td style='padding:12px 0;color:#C9A84C;font-size:20px'>"
        + str(total) + " \u20bd</td></tr>"
        "<tr><td style='padding:4px 0;color:#5A4A30;font-size:12px'>"
        "\u041f\u0440\u0435\u0434\u043e\u043f\u043b\u0430\u0442\u0430 20%</td>"
        "<td style='color:#C9A84C;font-size:13px'>" + str(prepay) + " \u20bd</td></tr>"
        "</table></div>"
        "<div style='background:#141414;border:1px solid #1E1E1E;padding:24px;margin-bottom:24px'>"
        "<div style='font-size:11px;color:#C9A84C;margin-bottom:12px'>"
        "\u0427\u0422\u041e \u0414\u0410\u041b\u042c\u0428\u0415</div>"
        "<div style='font-size:12px;color:#A89060;line-height:1.8'>"
        "1. \u041e\u043f\u043b\u0430\u0442\u0438\u0442\u0435 \u043f\u0440\u0435\u0434\u043e\u043f\u043b\u0430\u0442\u0443 20% \u043f\u043e \u0441\u0441\u044b\u043b\u043a\u0435 \u0422-\u0411\u0430\u043d\u043a<br>"
        "2. \u041d\u0430\u0436\u043c\u0438\u0442\u0435 \u00ab\u042f \u043e\u043f\u043b\u0430\u0442\u0438\u043b\u00bb \u043d\u0430 \u0441\u0430\u0439\u0442\u0435<br>"
        "3. \u0410\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438\u0442 \u0438 \u043e\u0442\u043f\u0440\u0430\u0432\u0438\u0442 \u0434\u043e\u0433\u043e\u0432\u043e\u0440 + \u043a\u043e\u0434 \u0437\u0430\u043c\u043a\u0430<br>"
        "4. \u0417\u0430\u0435\u0437\u0434 \u0441 15:00, \u0432\u044b\u0435\u0437\u0434 \u0434\u043e 12:00"
        "</div></div>"
        "<div style='text-align:center;font-size:11px;color:#5A4A30'>"
        "" + get_landlord_email() + " | " + landlord_domain() + "</div></div>"
    )
    send_email(guest_email,
               "\u0411\u0440\u043e\u043d\u044c " + booking_id + " \u2014 " + landlord_brand(),
               html)

def email_booking_confirmed(booking, door_code=None):
    """Письмо гостю — предоплата подтверждена, ссылка на подписание договора + инструкция по остатку."""
    guest_email  = booking.get("guest_email", "")
    guest_name   = booking.get("guest_name", "")
    booking_ref  = str(booking.get("username") or booking.get("id", ""))
    check_in     = booking.get("check_in", "")
    check_out    = booking.get("check_out", "")
    total_price  = booking.get("total_price", 0)
    prepay       = round(total_price * 0.2)
    remainder    = total_price - prepay
    sign_token   = booking.get("sign_token", "")
    sign_link    = f"{BASE_URL}/sign/{sign_token}" if sign_token else ""

    # PDF гостю пока не отправляем — только текст сохраняем в архив для админки.
    # Готовый (подписанный) PDF гость получит одним письмом после подписания
    # по ссылке — см. email_contract_signed().
    contract_text = generate_contract(booking)
    save_contract(booking_ref, contract_text)

    html = (
        "<div style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;"
        "background:#0A0A0A;color:#F0E6C8;padding:40px'>"
        "<div style='text-align:center;margin-bottom:32px'>"
        "<div style='font-size:28px;letter-spacing:4px;color:#C9A84C'>"
        "\u0413\u041e\u0420\u041e\u0414\u0421\u041a\u0410\u042f \u041f\u0410\u0423\u0417\u0410</div>"
        "</div>"
        "<div style='background:#141414;border:1px solid #1E1E1E;padding:32px;margin-bottom:24px'>"
        "<div style='font-size:16px;color:#C9A84C;margin-bottom:16px'>"
        "\u2705 \u041f\u0440\u0435\u0434\u043e\u043f\u043b\u0430\u0442\u0430 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0430!</div>"
        "<div style='font-size:13px;color:#A89060;margin-bottom:24px'>"
        "\u0411\u0440\u043e\u043d\u044c " + booking_ref + "</div>"
        "<table style='width:100%;border-collapse:collapse'>"
        "<tr><td style='padding:8px 0;color:#5A4A30;font-size:12px'>"
        "\u0417\u0430\u0435\u0437\u0434</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + check_in + " \u0441 15:00</td></tr>"
        "<tr><td style='padding:8px 0;color:#5A4A30;font-size:12px'>"
        "\u0412\u044b\u0435\u0437\u0434</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + check_out + " \u0434\u043e 12:00</td></tr>"
        "<tr><td style='padding:8px 0;color:#5A4A30;font-size:12px'>"
        "\u0410\u0434\u0440\u0435\u0441</td>"
        "<td style='color:#F0E6C8;font-size:12px'>"
        "\u0443\u043b. \u0414\u0430\u0447\u043d\u0430\u044f, \u0434. 5, \u043a\u0432. 286, 22 \u044d\u0442\u0430\u0436</td></tr>"
        "</table></div>"
        "<div style='background:#141414;border:1px solid rgba(201,168,76,0.3);padding:24px;margin-bottom:24px'>"
        "<div style='font-size:13px;color:#C9A84C;margin-bottom:16px'>"
        "\u0414\u041e\u041f\u041e\u041b\u041d\u0418\u0422\u0415\u041b\u042c\u041d\u0410\u042f \u041e\u041f\u041b\u0410\u0422\u0410</div>"
        "<div style='font-size:12px;color:#A89060;line-height:1.9'>"
        "\u0414\u043b\u044f \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0438\u044f \u0431\u0440\u043e\u043d\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u044f \u043d\u0435\u043e\u0431\u0445\u043e\u0434\u0438\u043c\u043e:<br>"
        "\u2022 \u041e\u0441\u0442\u0430\u0442\u043e\u043a \u0441\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u0438: <b style='color:#F0E6C8'>" + str(remainder) + " \u20bd</b><br>"
        "\u2022 \u0414\u0435\u043f\u043e\u0437\u0438\u0442: <b style='color:#F0E6C8'>6\u202f000 \u20bd</b> (\u0432\u043e\u0437\u0432\u0440\u0430\u0449\u0430\u0435\u0442\u0441\u044f \u043f\u0440\u0438 \u0432\u044b\u0435\u0437\u0434\u0435)<br>"
        "\u041e\u043f\u043b\u0430\u0442\u0430 \u043d\u0430\u043b\u0438\u0447\u043d\u044b\u043c\u0438 \u0438\u043b\u0438 \u043f\u0435\u0440\u0435\u0432\u043e\u0434\u043e\u043c \u043f\u043e \u0440\u0435\u043a\u0432\u0438\u0437\u0438\u0442\u0430\u043c, \u043f\u0440\u0435\u0434\u043e\u0441\u0442\u0430\u0432\u043b\u0435\u043d\u043d\u044b\u043c \u043f\u0440\u0438 \u0437\u0430\u0441\u0435\u043b\u0435\u043d\u0438\u0438.<br>"
        "\u041f\u043e\u0441\u043b\u0435 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u044f \u043e\u043f\u043b\u0430\u0442\u044b \u043c\u044b \u043e\u0442\u043f\u0440\u0430\u0432\u0438\u043c \u0432\u0430\u043c \u043f\u0430\u043c\u044f\u0442\u043a\u0443 \u0441 \u043a\u043e\u0434\u043e\u043c \u043e\u0442 \u0437\u0430\u043c\u043a\u0430."
        "</div></div>"
        "<div style='background:#141414;border:1px solid #1E1E1E;padding:24px;margin-bottom:24px'>"
        "<div style='font-size:11px;color:#C9A84C;margin-bottom:12px'>"
        "\u0414\u041e\u0413\u041e\u0412\u041e\u0420 \u0410\u0420\u0415\u041d\u0414\u042b</div>"
        "<div style='font-size:12px;color:#A89060;line-height:1.7'>"
        "\u041f\u0440\u043e\u0441\u044c\u0431\u0430 \u043e\u0437\u043d\u0430\u043a\u043e\u043c\u0438\u0442\u044c\u0441\u044f \u0441 \u0442\u0435\u043a\u0441\u0442\u043e\u043c \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430 \u0438 \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u0442\u044c \u0435\u0433\u043e \u043f\u043e \u0441\u0441\u044b\u043b\u043a\u0435 \u043d\u0438\u0436\u0435 \u2014 \u044d\u0442\u043e \u0437\u0430\u0439\u043c\u0451\u0442 \u043c\u0435\u043d\u044c\u0448\u0435 \u043c\u0438\u043d\u0443\u0442\u044b. \u041f\u043e\u0441\u043b\u0435 \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u0438\u044f \u0433\u043e\u0442\u043e\u0432\u044b\u0439 \u0434\u043e\u0433\u043e\u0432\u043e\u0440 \u0438 \u0441\u043e\u0433\u043b\u0430\u0441\u0438\u0435 \u043d\u0430 \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0443 \u043f\u0435\u0440\u0441\u043e\u043d\u0430\u043b\u044c\u043d\u044b\u0445 \u0434\u0430\u043d\u043d\u044b\u0445 \u043f\u0440\u0438\u0434\u0443\u0442 \u0432\u0430\u043c \u043d\u0430 \u044d\u0442\u0443 \u0436\u0435 \u043f\u043e\u0447\u0442\u0443.</div>"
        + (
            "<div style='text-align:center;margin-top:20px'>"
            f"<a href='{sign_link}' style='display:inline-block;background:#C9A84C;color:#0A0A0A;"
            "text-decoration:none;padding:12px 28px;font-size:12px;letter-spacing:0.05em;font-weight:bold'>"
            "\u041e\u0437\u043d\u0430\u043a\u043e\u043c\u0438\u0442\u044c\u0441\u044f \u0438 \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u0442\u044c \u0434\u043e\u0433\u043e\u0432\u043e\u0440</a></div>"
            if sign_link else ""
        ) +
        "</div>"
        "<div style='text-align:center;font-size:11px;color:#5A4A30'>"
        "" + get_landlord_email() + " | " + landlord_domain() + "</div></div>"
    )
    send_email(guest_email,
               "\u0411\u0440\u043e\u043d\u044c \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0430 \u2014 " + booking_ref,
               html)


def email_admin_new_booking(booking_id, guest_name, guest_phone, guest_email,
                             check_in, check_out, nights, total,
                             promo_code="", discount_percent=0):
    """Письмо админу — новая бронь ожидает подтверждения."""
    promo_row = ""
    if promo_code:
        promo_row = (
            "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px'>"
            "\u041f\u0440\u043e\u043c\u043e\u043a\u043e\u0434</td>"
            "<td style='color:#C9A84C;font-size:12px'>" + promo_code +
            " (\u2212" + str(discount_percent) + "%)</td></tr>"
        )
    html = (
        "<div style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;"
        "background:#0A0A0A;color:#F0E6C8;padding:40px'>"
        "<div style='font-size:18px;color:#C9A84C;margin-bottom:8px'>"
        "\u041d\u043e\u0432\u0430\u044f \u0431\u0440\u043e\u043d\u044c \u0441 \u0441\u0430\u0439\u0442\u0430</div>"
        "<div style='font-size:13px;color:#5A4A30;margin-bottom:24px'>"
        "\u041e\u0436\u0438\u0434\u0430\u0435\u0442 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0438\u044f \u043e\u043f\u043b\u0430\u0442\u044b</div>"
        "<div style='background:#141414;border:1px solid #1E1E1E;padding:24px;margin-bottom:16px'>"
        "<table style='width:100%;border-collapse:collapse'>"
        "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px;width:140px'>"
        "\u0411\u0440\u043e\u043d\u044c</td>"
        "<td style='color:#C9A84C;font-size:13px'>" + booking_id + "</td></tr>"
        "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px'>"
        "\u0413\u043e\u0441\u0442\u044c</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + guest_name + "</td></tr>"
        "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px'>"
        "\u0422\u0435\u043b\u0435\u0444\u043e\u043d</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + guest_phone + "</td></tr>"
        "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px'>Email</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + guest_email + "</td></tr>"
        "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px'>"
        "\u0417\u0430\u0435\u0437\u0434</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + check_in + "</td></tr>"
        "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px'>"
        "\u0412\u044b\u0435\u0437\u0434</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + check_out + "</td></tr>"
        + promo_row +
        "<tr style='border-top:1px solid #1E1E1E'>"
        "<td style='padding:10px 0;color:#A89060;font-size:13px'>"
        "\u0421\u0443\u043c\u043c\u0430</td>"
        "<td style='color:#C9A84C;font-size:18px'>" + str(total) + " \u20bd</td></tr>"
        "</table></div>"
        "<div style='padding:16px;background:rgba(201,168,76,0.05);border:1px solid rgba(201,168,76,0.2);font-size:12px;color:#A89060'>"
        "\u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438\u0442\u0435 \u043e\u043f\u043b\u0430\u0442\u0443 \u0432 \u0430\u0434\u043c\u0438\u043d\u043a\u0435: "
        "<a href='" + site_url() + "/static/admin.html' style='color:#C9A84C'>"
        "" + landlord_domain() + "/static/admin.html</a>"
        "</div></div>"
    )
    send_email(MAIL_ADMIN,
               "\u041d\u043e\u0432\u0430\u044f \u0431\u0440\u043e\u043d\u044c " + booking_id + " \u2014 \u0416\u0434\u0451\u0442 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0438\u044f",
               html)
