"""Хранение и обработка фото паспортов гостей."""
import io
import json
import os
from PIL import Image

from core.constants import PASSPORT_MAP_FILE


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
