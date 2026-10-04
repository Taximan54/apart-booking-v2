"""Хранение и обработка фото паспортов гостей."""
import io
import json
import os
from PIL import Image, ImageDraw, ImageFont

from core.constants import PASSPORT_MAP_FILE
from core.contract_docs import _get_cyrillic_ttf_path


# =====================================================
# API — PASSPORT PHOTO (защищённое хранение)
# =====================================================
# ВАЖНО: PASSPORT_DIR НЕ должна раздаваться nginx напрямую как статика
# (в отличие от /data/photos/) — доступ к фото паспорта только через
# защищённый эндпоинт с проверкой Bearer-токена админа.

def compress_passport_image(file_bytes: bytes) -> bytes:
    """
    Сжимает фото паспорта до разумного размера для хранения:
    - уменьшает до максимум 1600px по длинной стороне (достаточно, чтобы
      прочитать текст и разглядеть фото, но не хранить лишние мегабайты)
    - конвертирует в JPEG с качеством 82% (даже с телефона в 12+ Мп
      итоговый файл обычно 100-300КБ вместо нескольких мегабайт)
    """
    img = Image.open(io.BytesIO(file_bytes))
    img = img.convert("RGB")  # на случай PNG с альфа-каналом или HEIC
    img.thumbnail((1600, 1600), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=82, optimize=True)
    return out.getvalue()

def load_passport_map():
    if os.path.exists(PASSPORT_MAP_FILE):
        with open(PASSPORT_MAP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_passport_map(data):
    with open(PASSPORT_MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


PASSPORT_WATERMARK_TEXT = "ЗАПРЕЩЕНО КОПИРОВАТЬ И ИСПОЛЬЗОВАТЬ ОТДЕЛЬНО ОТ ДАННОГО ДОКУМЕНТА  •  "

def apply_passport_watermark(img):
    """
    Накладывает защитную сетку — повторяющуюся диагональную надпись
    «Запрещено копировать и использовать отдельно от данного документа» —
    на фото паспорта. Принимает PIL.Image, возвращает новый RGB-Image
    (оригинал на диске не меняется). Используется и для PDF договора,
    и для просмотра фото в админке/архиве.
    """
    img = img.convert("RGB")
    w, h = img.size
    ttf_path = _get_cyrillic_ttf_path()

    # Диагональная плашка с повторяющимся текстом рисуется на отдельном,
    # заведомо большом холсте, затем поворачивается на 30° и накладывается
    # поверх фото — так надпись покрывает всё изображение по диагонали.
    diag = int((w ** 2 + h ** 2) ** 0.5) + 40
    tile = Image.new("RGBA", (diag, 60), (0, 0, 0, 0))
    tdraw = ImageDraw.Draw(tile)
    font = None
    if ttf_path:
        try:
            font = ImageFont.truetype(ttf_path, 16)
        except Exception:
            font = None
    if font is None:
        font = ImageFont.load_default()
    repeat = int(max(3, diag // max(1, tdraw.textlength(PASSPORT_WATERMARK_TEXT, font=font) or 1) + 2))
    tdraw.text((0, 18), PASSPORT_WATERMARK_TEXT * repeat, font=font, fill=(201, 168, 76, 130))

    overlay = Image.new("RGBA", (diag, diag), (0, 0, 0, 0))
    step_y = 70
    for y in range(0, diag, step_y):
        row = tile.copy()
        overlay.paste(row, (0, y), row)
    overlay = overlay.rotate(30, expand=False)

    # Обрезаем повёрнутый водяной знак по размеру фото и накладываем по центру
    ox = (overlay.width - w) // 2
    oy = (overlay.height - h) // 2
    overlay_cropped = overlay.crop((ox, oy, ox + w, oy + h))
    return Image.alpha_composite(img.convert("RGBA"), overlay_cropped).convert("RGB")
