"""API: шаблон договора, памятка/чек-лист и архив договоров."""
import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, FileResponse
from pydantic import BaseModel

from core.auth import require_admin
from core.constants import (
    CONTRACT_FILE,
    CONTRACT_STATIC,
    CHECKIN_FILE,
    DEFAULT_CHECKIN_MEMO,
    CHECKOUT_FILE,
    DEFAULT_CHECKOUT_CHECKLIST,
    REVIEW_FILE,
    DEFAULT_REVIEW_TEMPLATE,
    CONTRACTS_DIR,
    CONTRACT_PREVIEW_DIR,
)
from core.contract_docs import (
    generate_contract,
    fill_contract,
    _contract_placeholders,
    generate_contract_pdf,
)
from core.data_store import get_default_deposit
from core.bookings_repo import get_by_ref_alt
from core.db import booking_ref_alt, find_booking_row, get_db
from core.models import ContractTemplate, CheckinMemo
from core.passports import load_passport_map
from core.runtime import now_nsk

router = APIRouter()


# =====================================================
# API — CONTRACT TEMPLATE
# =====================================================

@router.get("/api/contract-template")
async def get_contract_template():
    if os.path.exists(CONTRACT_FILE):
        with open(CONTRACT_FILE, "r", encoding="utf-8") as f:
            return PlainTextResponse(f.read())
    if os.path.exists(CONTRACT_STATIC):
        with open(CONTRACT_STATIC, "r", encoding="utf-8") as f:
            return PlainTextResponse(f.read())
    return PlainTextResponse("")

@router.post("/api/contract-template")
async def set_contract_template(c: ContractTemplate, _: bool = Depends(require_admin)):
    with open(CONTRACT_FILE, "w", encoding="utf-8") as f:
        f.write(c.text)
    return {"ok": True}

@router.get("/api/checkin-memo")
async def get_checkin_memo():
    if os.path.exists(CHECKIN_FILE):
        with open(CHECKIN_FILE, "r", encoding="utf-8") as f:
            return PlainTextResponse(f.read())
    return PlainTextResponse(DEFAULT_CHECKIN_MEMO)

@router.post("/api/checkin-memo")
async def set_checkin_memo(c: CheckinMemo, _: bool = Depends(require_admin)):
    with open(CHECKIN_FILE, "w", encoding="utf-8") as f:
        f.write(c.text)
    return {"ok": True}

@router.get("/api/checkout-checklist")
async def get_checkout_checklist():
    if os.path.exists(CHECKOUT_FILE):
        with open(CHECKOUT_FILE, "r", encoding="utf-8") as f:
            return PlainTextResponse(f.read())
    return PlainTextResponse(DEFAULT_CHECKOUT_CHECKLIST)

@router.post("/api/checkout-checklist")
async def set_checkout_checklist(c: CheckinMemo, _: bool = Depends(require_admin)):
    with open(CHECKOUT_FILE, "w", encoding="utf-8") as f:
        f.write(c.text)
    return {"ok": True}

@router.get("/api/review-template")
async def get_review_template():
    if os.path.exists(REVIEW_FILE):
        with open(REVIEW_FILE, "r", encoding="utf-8") as f:
            return PlainTextResponse(f.read())
    return PlainTextResponse(DEFAULT_REVIEW_TEMPLATE)

@router.post("/api/review-template")
async def set_review_template(c: CheckinMemo, _: bool = Depends(require_admin)):
    with open(REVIEW_FILE, "w", encoding="utf-8") as f:
        f.write(c.text)
    return {"ok": True}

# =====================================================
# API — CONTRACTS
# =====================================================

@router.get("/api/contracts")
async def list_contracts(_: bool = Depends(require_admin)):
    """
    Список всех броней с сохранёнными документами. Собирается по всем
    типам файлов в CONTRACTS_DIR (черновик .txt, подписанный договор
    _podpisan.pdf, согласие на ПД _soglasie_pd.pdf), а не только по .txt —
    иначе подписанные документы для броней без .txt-черновика (например,
    старых) не попадали бы в архив. Также отмечает наличие фото паспорта.
    """
    os.makedirs(CONTRACTS_DIR, exist_ok=True)
    all_files = os.listdir(CONTRACTS_DIR)

    def base_ref(fname):
        for suffix in ("_podpisan.pdf", "_soglasie_pd.pdf", ".txt"):
            if fname.endswith(suffix):
                return fname[: -len(suffix)]
        return None

    refs_seen = {}
    for f in all_files:
        ref = base_ref(f)
        if ref is None:
            continue
        # нормализуем ГП- к GP- как основному ключу
        norm_ref = ref.replace("\u0413\u041f-", "GP-")
        refs_seen.setdefault(norm_ref, {"txt": False, "contract_pdf": False, "consent_pdf": False, "mtime": 0})
        if f.endswith(".txt"):
            refs_seen[norm_ref]["txt"] = True
        elif f.endswith("_podpisan.pdf"):
            refs_seen[norm_ref]["contract_pdf"] = True
        elif f.endswith("_soglasie_pd.pdf"):
            refs_seen[norm_ref]["consent_pdf"] = True
        stat = os.stat(os.path.join(CONTRACTS_DIR, f))
        refs_seen[norm_ref]["mtime"] = max(refs_seen[norm_ref]["mtime"], stat.st_mtime)

    pm = load_passport_map()
    conn = get_db()
    result = []
    for ref, flags in refs_seen.items():
        ref_alt = booking_ref_alt(ref)
        row = find_booking_row(conn, ref, "guest_name, guest_email, check_in, check_out, total_price, status")
        pm_key = ref if ref in pm else (ref_alt if ref_alt in pm else ref)
        pm_entry = pm.get(pm_key)
        passport_slots = [s for s in ("main", "reg1") if isinstance(pm_entry, dict) and pm_entry.get(s)]
        entry = {
            "ref": ref,
            "passport_ref": pm_key,
            "has_draft": flags["txt"],
            "has_contract_pdf": flags["contract_pdf"],
            "has_consent_pdf": flags["consent_pdf"],
            "has_passport_photo": bool(passport_slots),
            "passport_photo_slots": passport_slots,
            "created": datetime.fromtimestamp(flags["mtime"], tz=now_nsk().tzinfo).strftime("%d.%m.%Y %H:%M"),
        }
        if row:
            entry.update({
                "guest_name":  row["guest_name"] or "—",
                "guest_email": row["guest_email"] or "—",
                "check_in":    row["check_in"] or "—",
                "check_out":   row["check_out"] or "—",
                "total_price": row["total_price"] or 0,
                "status":      row["status"] or "—",
            })
        result.append(entry)
    conn.close()
    result.sort(key=lambda e: e["created"], reverse=True)
    return result

@router.get("/api/contracts/{booking_ref}")
async def get_contract(booking_ref: str, _: bool = Depends(require_admin)):
    """Получить сохранённый договор."""
    path = os.path.join(CONTRACTS_DIR, booking_ref + ".txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return PlainTextResponse(f.read())
    # Генерируем на лету — ищем по обоим вариантам префикса
    booking = get_by_ref_alt(booking_ref)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return PlainTextResponse(generate_contract(booking))

@router.get("/api/admin/contract-pdf/{booking_ref}/{doc_type}")
async def get_signed_contract_pdf(booking_ref: str, doc_type: str, _: bool = Depends(require_admin)):
    """
    Отдаёт подписанный PDF из архива: doc_type = 'contract' (договор +
    приложения + фото паспорта с водяным знаком) или 'consent' (согласие
    на обработку ПД). Файлы создаются в момент подписания гостем —
    до этого момента отдаёт 404.
    """
    suffix = {"contract": "_podpisan.pdf", "consent": "_soglasie_pd.pdf"}.get(doc_type)
    if not suffix:
        raise HTTPException(status_code=400, detail="Неверный doc_type — ожидается 'contract' или 'consent'")
    for candidate in (booking_ref, booking_ref_alt(booking_ref)):
        path = os.path.join(CONTRACTS_DIR, candidate + suffix)
        if os.path.exists(path):
            filename = ("dogovor_podpisan_" if doc_type == "contract" else "soglasie_pd_") + booking_ref + ".pdf"
            return FileResponse(path, media_type="application/pdf", filename=filename)
    raise HTTPException(status_code=404, detail="Подписанный документ не найден — договор ещё не подписан")

class ContractPreviewRequest(BaseModel):
    text: str

@router.post("/api/admin/contract-preview")
async def contract_preview(body: ContractPreviewRequest, _: bool = Depends(require_admin)):
    """
    Генерирует PDF-предпросмотр ТЕКУЩЕГО текста в редакторе шаблона (даже
    ещё не сохранённого) с фиктивными тестовыми данными вместо реальной
    брони — чтобы сразу видеть, как договор будет выглядеть у гостя.
    Сохраняется во временную папку (не в архив договоров), перезаписывается
    при каждом вызове.
    """
    dummy_booking = {
        "check_in":       (now_nsk() + timedelta(days=2)).strftime("%Y-%m-%d"),
        "check_out":      (now_nsk() + timedelta(days=7)).strftime("%Y-%m-%d"),
        "nights":         5,
        "guest_name":     "Иванов Иван Иванович",
        "passport":       "0000 000000",
        "guests_count":   2,
        "total_price":    33725,
        "discount_percent": 0,
        "deposit":        get_default_deposit(),
        "username":       "PREVIEW",
    }
    filled_text = fill_contract(body.text, _contract_placeholders(dummy_booking))
    path = generate_contract_pdf(filled_text, "preview", output_dir=CONTRACT_PREVIEW_DIR)
    return FileResponse(path, media_type="application/pdf", filename="dogovor_predprosmotr.pdf")
