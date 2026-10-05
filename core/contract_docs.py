"""Договор и согласие: шаблон, суммы/даты прописью, разметка, генерация PDF."""
import io
import os
import re
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas as _PDFCanvas
from reportlab.platypus import (
    SimpleDocTemplate,
    PageBreak,
    Image as RLImage,
    Spacer,
    KeepTogether,
    Paragraph,
    Table,
    TableStyle,
)
from xml.sax.saxutils import escape as xml_escape

from core.constants import DATA_DIR, CONTRACT_FILE, CONTRACT_STATIC, CONTRACTS_DIR, DEFAULT_LANDLORD
from core.data_store import get_default_deposit
from core.runtime import now_nsk
from core.landlord import landlord_address, landlord_brand, landlord_domain, get_landlord_email
from core.logger import get_logger

logger = get_logger(__name__)


# =====================================================
# CONTRACT
# =====================================================

def load_contract_template():
    if os.path.exists(CONTRACT_FILE):
        with open(CONTRACT_FILE, "r", encoding="utf-8") as f:
            return f.read()
    if os.path.exists(CONTRACT_STATIC):
        with open(CONTRACT_STATIC, "r", encoding="utf-8") as f:
            return f.read()
    return ""

# =====================================================
# СУММА ПРОПИСЬЮ И ДАТА СЛОВАМИ (для договора)
# =====================================================

_NUM_ONES_M = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_NUM_ONES_F = ["", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_NUM_TEENS  = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать",
               "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
_NUM_TENS   = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят",
               "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
_NUM_HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот",
                 "шестьсот", "семьсот", "восемьсот", "девятьсот"]

def _three_digit_words(n, feminine=False):
    """Прописывает число от 0 до 999 (для составления тысяч/рублей)."""
    words = []
    h, rest = divmod(n, 100)
    if h:
        words.append(_NUM_HUNDREDS[h])
    if 10 <= rest < 20:
        words.append(_NUM_TEENS[rest - 10])
    else:
        t, o = divmod(rest, 10)
        if t:
            words.append(_NUM_TENS[t])
        if o:
            words.append((_NUM_ONES_F if feminine else _NUM_ONES_M)[o])
    return words

def _plural_ru(n, forms):
    """forms = (для 1, для 2-4, для 5-20/0) — стандартное русское склонение по числительному."""
    n = abs(int(n)) % 100
    if 11 <= n <= 14:
        return forms[2]
    n10 = n % 10
    if n10 == 1:
        return forms[0]
    if 2 <= n10 <= 4:
        return forms[1]
    return forms[2]

def _rub_in_words(amount):
    """
    Переводит целую сумму в рублях в пропись с заглавной буквы:
    6745 → "Шесть тысяч семьсот сорок пять рублей". Копейки не
    поддерживаются — в проекте суммы аренды всегда целые.
    """
    n = int(round(amount))
    parts = []
    thousands, rub = divmod(n, 1000)
    if thousands:
        parts.extend(_three_digit_words(thousands, feminine=True))
        parts.append(_plural_ru(thousands, ("тысяча", "тысячи", "тысяч")))
    if rub or not thousands:
        rw = _three_digit_words(rub, feminine=False)
        if rw:
            parts.extend(rw)
        elif not thousands:
            parts.append("ноль")
    parts.append(_plural_ru(n, ("рубль", "рубля", "рублей")))
    text = " ".join(parts)
    return text[0].upper() + text[1:] if text else "Ноль рублей"

def _sum_with_words(amount):
    """"6745" → "6745 (Шесть тысяч семьсот сорок пять рублей)" — для подстановки в договор."""
    return f"{int(round(amount))} ({_rub_in_words(amount)})"

_MONTHS_RU_GENITIVE = ["января", "февраля", "марта", "апреля", "мая", "июня",
                       "июля", "августа", "сентября", "октября", "ноября", "декабря"]

def _date_ru_words(dt):
    """datetime(2026,7,22) → "22 июля 2026" (без "г." — суффикс уже есть в тексте шаблона)."""
    return f"{dt.day} {_MONTHS_RU_GENITIVE[dt.month - 1]} {dt.year}"

def fill_contract(template, data):
    for key, value in data.items():
        placeholder = "{{" + key + "}}"
        if placeholder in template:
            # Подставленное значение оборачиваем спец-маркерами (не **, а
            # непечатаемые символы) — при рендере в PDF это автоматически
            # станет жирным текстом. Отдельные от ** маркеры нужны, чтобы не
            # ломаться, когда пользователь вручную выделяет жирным целую
            # строку, ВНУТРИ которой уже есть подставленный плейсхолдер —
            # см. _render_inline_bold().
            template = template.replace(placeholder, f"{_AUTO_BOLD_OPEN}{value}{_AUTO_BOLD_CLOSE}")
    return template

def _contract_placeholders(booking):
    """Собирает словарь плейсхолдеров для подстановки в шаблон договора/согласия по данным брони."""
    today        = _date_ru_words(now_nsk())
    checkin_fmt  = datetime.strptime(booking["check_in"],  "%Y-%m-%d").strftime("%d.%m.%Y")
    checkout_fmt = datetime.strptime(booking["check_out"], "%Y-%m-%d").strftime("%d.%m.%Y")
    nights       = booking.get("nights") or booking.get("guests", 1)
    total        = booking.get("total_price", 0)
    discount_pct = booking.get("discount_percent", 0) or 0
    # total_price уже учитывает скидку по промокоду — для "цены за ночь" в договоре
    # восстанавливаем исходную (до скидки) сумму, чтобы тариф совпадал с тем, что гость видел при выборе дат
    pre_discount_total = round(total / (1 - discount_pct / 100)) if discount_pct else total
    per_night    = round(pre_discount_total / nights) if nights else pre_discount_total
    deposit      = booking.get("deposit") or get_default_deposit()

    return {
        "ДАТА_ДОГОВОРА":  today,
        "АРЕНДОДАТЕЛЬ":   landlord_brand(),
        "ФИО":            booking.get("guest_name", ""),
        "ПАСПОРТ":        booking.get("passport", "____________"),
        "АДРЕС":          landlord_address(),
        "НОЧЕЙ":          str(nights),
        "ДАТА_ЗАЕЗДА":    checkin_fmt,
        "ДАТА_ВЫЕЗДА":    checkout_fmt,
        "ГОСТЕЙ":         str(booking.get("guests_count", booking.get("guests", 2))),
        "ЦЕНА_В_СУТКИ":   _sum_with_words(per_night),
        "ИТОГО":          _sum_with_words(total),
        "ДЕПОЗИТ":        _sum_with_words(deposit),
        "EMAIL":          get_landlord_email(),
        "САЙТ":           landlord_domain(),
        "НОМЕР_БРОНИ":    str(booking.get("username") or booking.get("id", "")),
        # Также поддерживаем латинские плейсхолдеры
        "DATA_DOGOVORA":  today,
        "FIO":            booking.get("guest_name", ""),
        "PASPORT":        booking.get("passport", "____________"),
        "ADRES":          ("g. Novosibirsk, ul. Dachnaya, d. 5, kv. 286, 22 etazh" if landlord_address() == DEFAULT_LANDLORD["address"] else landlord_address()),
        "NOCHEY":         str(nights),
        "DATA_ZAEZDA":    checkin_fmt,
        "DATA_VYEZDA":    checkout_fmt,
        "GOSTEY":         str(booking.get("guests_count", 2)),
        "CENA_SUTKI":     _sum_with_words(per_night),
        "SUMMA":          _sum_with_words(total),
        "DEPOZIT":        _sum_with_words(deposit),
        "NOMER_BRONI":    str(booking.get("username") or booking.get("id", "")),
    }

def generate_contract(booking):
    """Генерирует текст договора из шаблона и данных брони."""
    template = load_contract_template()
    if not template:
        return "Shablon dogovora ne nayden."
    return fill_contract(template, _contract_placeholders(booking))

def save_contract(booking_ref, contract_text):
    """Сохраняет договор в файл (.txt — для архива в админке)."""
    path = os.path.join(CONTRACTS_DIR, booking_ref + ".txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(contract_text)
    return path

_CYRILLIC_FONT_NAME = None

def _register_cyrillic_font():
    """
    Регистрирует шрифт с поддержкой кириллицы для reportlab — обычное И
    жирное начертание, и связывает их в одно "семейство" через
    registerFontFamily(). Это отдельный обязательный шаг: без него тег
    <b>...</b> внутри Paragraph молча игнорируется и жирный текст в PDF
    не появляется, даже если сам обычный шрифт зарегистрирован нормально.
    """
    global _CYRILLIC_FONT_NAME
    if _CYRILLIC_FONT_NAME:
        return _CYRILLIC_FONT_NAME
    candidates = [
        ("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("Liberation", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ("Noto", "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
                 "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
        ("Arial", "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
                  "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf"),
    ]
    for name, path, bold_path in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                bold_name = name + "-Bold"
                if os.path.exists(bold_path):
                    pdfmetrics.registerFont(TTFont(bold_name, bold_path))
                else:
                    # Жирного файла нет — регистрируем обычный повторно под
                    # именем "-Bold", чтобы <b> хотя бы не ломал рендер
                    # (сам текст не потеряется, просто не будет визуально жирным)
                    pdfmetrics.registerFont(TTFont(bold_name, path))
                pdfmetrics.registerFontFamily(name, normal=name, bold=bold_name, italic=name, boldItalic=bold_name)
                _CYRILLIC_FONT_NAME = name
                return name
            except Exception:
                continue
    logger.warning("не найден TTF-шрифт с кириллицей (нужен пакет fonts-dejavu-core) — "
          "PDF-договор может отобразиться некорректно")
    _CYRILLIC_FONT_NAME = "Helvetica"
    return _CYRILLIC_FONT_NAME

_CYRILLIC_FONT_PATH_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
]

def _get_cyrillic_ttf_path():
    """Путь к TTF-файлу с кириллицей для наложения текста на изображения через PIL (не через reportlab)."""
    for path in _CYRILLIC_FONT_PATH_CANDIDATES:
        if os.path.exists(path):
            return path
    return None

# =====================================================
# РАЗМЕТКА ТЕКСТА ДОГОВОРА: жирные плейсхолдеры и заголовки разделов
# =====================================================
# В тексте шаблона поддерживается инлайн-разметка **жирный текст** (как в
# Markdown) — её вставляет кнопка "Жирный" в редакторе админки, а также
# fill_contract() автоматически оборачивает ею подставленные значения
# плейсхолдеров. Заголовки разделов ("1. Предмет Договора", "3.1. Права и
# обязанности Арендодателя:", "Приложение N 1") определяются автоматически
# по структуре строки — их не нужно размечать вручную.

_HEADING_MAIN_RE     = re.compile(r"^\d+\.\s+\S")            # "1. Предмет Договора"
_HEADING_APPENDIX_RE = re.compile(r"^Приложение\b", re.IGNORECASE)
_HEADING_SUB_RE       = re.compile(r"^\d+\.\d+\.\s+.*:\s*$")  # "3.1. Права и обязанности Арендодателя:"

# Маркеры автоматического жирного текста для подставленных плейсхолдеров
# (см. fill_contract). Символы из приватной юникод-зоны — гарантированно не
# встретятся в обычном тексте договора и не конфликтуют с ручной разметкой **.
_AUTO_BOLD_OPEN  = "\ue000"
_AUTO_BOLD_CLOSE = "\ue001"
_AUTO_BOLD_RE = re.compile(_AUTO_BOLD_OPEN + r"(.*?)" + _AUTO_BOLD_CLOSE)

# Маркеры выравнивания строки целиком — вставляются кнопками "По центру" /
# "Вправо" в редакторе админки. В отличие от **жирного**, это выравнивание
# ВСЕЙ строки (абзаца), а не части текста внутри неё.
_ALIGN_CENTER_RE = re.compile(r"^\[\[CENTER\]\](.*)\[\[/CENTER\]\]$")
_ALIGN_RIGHT_RE  = re.compile(r"^\[\[RIGHT\]\](.*)\[\[/RIGHT\]\]$")

def _strip_alignment_marker(line):
    """Возвращает (текст_без_маркера, 'center'|'right'|None)."""
    m = _ALIGN_CENTER_RE.match(line)
    if m:
        return m.group(1), "center"
    m = _ALIGN_RIGHT_RE.match(line)
    if m:
        return m.group(1), "right"
    return line, None

def _is_heading_line(line, in_appendix=False):
    """
    Заголовок раздела — если это "Приложение N ...", подзаголовок вида
    "3.1. ...:", или (только ВНЕ приложений) "N. Текст". Внутри приложений
    single-level нумерация используется для обычных списков (перечень
    имущества и т.п.), поэтому там она заголовком не считается — иначе
    каждый пункт списка ("1. Кухонный гарнитур", "2. Телевизор"...)
    ошибочно стал бы крупным жирным заголовком.
    """
    if _HEADING_APPENDIX_RE.match(line):
        return True
    if _HEADING_SUB_RE.match(line):
        return True
    if not in_appendix and _HEADING_MAIN_RE.match(line):
        return True
    return False

def _render_inline_bold(line):
    """
    Экранирует текст строки для reportlab и раскрывает жирную разметку:
    - автоматическую (маркеры _AUTO_BOLD_OPEN/CLOSE вокруг значений
      плейсхолдеров, вставленные fill_contract) — обрабатывается ПЕРВЫМ
      проходом как самодостаточные, всегда корректно закрытые фрагменты;
    - ручную (маркеры **текст**, вставленные кнопкой "Жирный" в админке) —
      обрабатывается ВТОРЫМ проходом как переключатель (открыл/закрыл).
    Два прохода с разными маркерами нужны, чтобы не ломаться, когда
    пользователь вручную выделяет жирным целую строку, внутри которой уже
    есть подставленный плейсхолдер (иначе два вида разметки со ОДНИМ и тем
    же маркером ** налагались бы друг на друга и текст переставал быть
    жирным именно там, где выделен плейсхолдер).
    """
    # Проход 1: вырезаем авто-жирные фрагменты, экранируем их содержимое и
    # заменяем на короткие служебные токены, чтобы они не мешали разбору **
    auto_spans = []
    def _stash_auto(m):
        auto_spans.append(f"<b>{xml_escape(m.group(1))}</b>")
        return f"\ue002{len(auto_spans) - 1}\ue003"
    line = _AUTO_BOLD_RE.sub(_stash_auto, line)

    # Проход 2: ручные маркеры ** — простое переключение жирности
    parts = line.split("**")
    out = []
    for i, part in enumerate(parts):
        escaped = xml_escape(part)
        out.append(f"<b>{escaped}</b>" if i % 2 == 1 else escaped)
    result = "".join(out)

    # Возвращаем на место авто-жирные фрагменты (уже готовый <b>...</b>)
    for i, span in enumerate(auto_spans):
        result = result.replace(f"\ue002{i}\ue003", span)
    return result

def contract_text_to_html(text, flat_numbering=False):
    """
    Конвертирует размеченный текст договора/согласия (маркеры [[CENTER]],
    [[RIGHT]], **жирный**, авто-жирные плейсхолдеры) в готовый HTML для
    показа гостю на странице подписания. Использует те же _is_heading_line
    / _strip_alignment_marker / _render_inline_bold, что и PDF-рендер —
    один источник правды для разметки, чтобы гостю на сайте и в PDF
    договор выглядел одинаково. Блок электронной подписи
    ([[SIGNATURE_BOX_START/END]]) не показывается — он появляется только
    в уже подписанном документе.
    flat_numbering=True — для документов без настоящих разделов (согласие
    на ПД и т.п.), где "1.", "2.", "3." это просто обычные пронумерованные
    пункты, а не заголовки — иначе они ошибочно стали бы жирными крупными
    заголовками (как список имущества в приложении к договору).
    """
    in_appendix = flat_numbering
    in_box = False
    parts = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if line == "[[SIGNATURE_BOX_START]]":
            in_box = True
            continue
        if line == "[[SIGNATURE_BOX_END]]":
            in_box = False
            continue
        if in_box:
            continue
        if not line:
            parts.append('<div class="doc-gap"></div>')
            continue
        line, align = _strip_alignment_marker(line)
        if _HEADING_APPENDIX_RE.match(line):
            in_appendix = True
        is_heading = _is_heading_line(line, in_appendix)
        classes = []
        if is_heading:
            classes.append("doc-heading")
        if align == "center":
            classes.append("doc-center")
        elif align == "right":
            classes.append("doc-right")
        cls = f' class="{" ".join(classes)}"' if classes else ""
        parts.append(f"<p{cls}>{_render_inline_bold(line)}</p>")
    return "\n".join(parts)

def _make_numbered_canvas(header_text, font_name):
    """
    Canvas с шапкой на каждой странице: "header_text · N / M" (как у ОкиДоки).
    Общее число страниц (M) известно только после полной вёрстки, поэтому
    используется двухпроходная схема: сначала копим состояния всех страниц,
    затем при save() дорисовываем шапку с уже известным общим количеством.
    """
    class NumberedCanvas(_PDFCanvas):
        def __init__(self, *args, **kwargs):
            _PDFCanvas.__init__(self, *args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self._draw_header(total)
                _PDFCanvas.showPage(self)
            _PDFCanvas.save(self)

        def _draw_header(self, total):
            self.saveState()
            try:
                self.setFont(font_name, 8.5)
            except Exception:
                self.setFont("Helvetica", 8.5)
            self.setFillColor(colors.HexColor("#9a8148"))
            text = f"{header_text}. {self._pageNumber} / {total}"
            self.drawRightString(A4[0] - 20 * mm, 12 * mm, text)
            self.restoreState()

    return NumberedCanvas

def generate_contract_pdf(contract_text, booking_ref, extra_blocks=None, header_text=None, output_dir=None, flat_numbering=False):
    """
    Рендерит текст в PDF и сохраняет в архив.
    extra_blocks — необязательный список элементов, которые добавляются
    ПОСЛЕ основного текста: либо строка (текст), либо PIL.Image
    (вставляется как картинка, отмасштабированная по ширине страницы) —
    используется для фото паспорта в подписанном договоре.
    header_text — если задан, на каждой странице сверху справа печатается
    "header_text · N / M" (как у ОкиДоки) — используется для подписанных
    документов, где header_text это "Городская Пауза · <идентификатор>".
    Строки между маркерами [[SIGNATURE_BOX_START]]/[[SIGNATURE_BOX_END]]
    оформляются отдельной рамкой с золотой обводкой и логотипом сверху.
    Внутри обычного текста маркеры **текст** дают жирное начертание, а
    заголовки разделов ("1. ...", "3.1. ...:", "Приложение N 1") автоматически
    выводятся крупным жирным шрифтом.
    flat_numbering=True — для документов без настоящих разделов (согласие
    на ПД и т.п.), где "1.", "2.", "3." — обычные пронумерованные пункты,
    а не заголовки; отключает автоопределение заголовков по номеру с самого
    начала документа (как для списков внутри приложений к договору).
    output_dir — если задан, PDF сохраняется туда вместо CONTRACTS_DIR
    (используется для предпросмотра, чтобы не засорять архив договоров).
    """
    font_name = _register_cyrillic_font()
    target_dir = output_dir or CONTRACTS_DIR
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, booking_ref + ".pdf")
    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"Договор аренды {booking_ref}",
    )
    style = ParagraphStyle(
        "contract", fontName=font_name, fontSize=10.5, leading=15, spaceAfter=4,
    )
    style_center = ParagraphStyle("contract_center", parent=style, alignment=TA_CENTER)
    style_right  = ParagraphStyle("contract_right",  parent=style, alignment=TA_RIGHT)
    heading_style = ParagraphStyle(
        "contract_heading", fontName=font_name, fontSize=13, leading=17,
        spaceBefore=10, spaceAfter=6,
    )
    heading_style_center = ParagraphStyle("contract_heading_center", parent=heading_style, alignment=TA_CENTER)
    heading_style_right  = ParagraphStyle("contract_heading_right",  parent=heading_style, alignment=TA_RIGHT)
    box_style = ParagraphStyle(
        "sigbox", fontName=font_name, fontSize=9.5, leading=14, spaceAfter=3,
        textColor=colors.HexColor("#3a3226"),
    )
    logo_style = ParagraphStyle(
        "logo", fontName=font_name, fontSize=15, leading=18,
        textColor=colors.HexColor("#9a8148"), alignment=1,  # центр
    )
    max_img_width = A4[0] - 40 * mm
    max_img_height = A4[1] - 36 * mm - 60  # высота кадра минус запас на отступы и интервал
    max_box_width = A4[0] - 44 * mm  # чуть уже полей, чтобы была видна рамка

    def _add_text_block(text, story, break_before_appendix=False):
        in_box = False
        box_lines = []
        in_appendix = flat_numbering
        for raw_line in text.split("\n"):
            line = raw_line.strip()
            if line == "[[SIGNATURE_BOX_START]]":
                in_box = True
                box_lines = []
                continue
            if line == "[[SIGNATURE_BOX_END]]":
                in_box = False
                box_flow = [Paragraph("Г О Р О Д С К А Я   П А У З А", logo_style), Spacer(1, 10)]
                for bl in box_lines:
                    if not bl:
                        box_flow.append(Spacer(1, 6))
                    else:
                        box_flow.append(Paragraph(_render_inline_bold(bl), box_style))
                tbl = Table([[box_flow]], colWidths=[max_box_width])
                tbl.setStyle(TableStyle([
                    ("BOX", (0, 0), (-1, -1), 1.1, colors.HexColor("#C9A84C")),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FCFAF3")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 16),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 16),
                    ("TOPPADDING", (0, 0), (-1, -1), 14),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
                ]))
                story.append(KeepTogether([tbl]))
                continue
            if in_box:
                box_lines.append(line)
                continue
            if not line:
                story.append(Spacer(1, 8))
                continue
            line, align = _strip_alignment_marker(line)
            if break_before_appendix and line.startswith("Приложение N 1"):
                story.append(PageBreak())
            if _HEADING_APPENDIX_RE.match(line):
                in_appendix = True
            is_heading = _is_heading_line(line, in_appendix)
            if is_heading:
                chosen_style = {"center": heading_style_center, "right": heading_style_right}.get(align, heading_style)
            else:
                chosen_style = {"center": style_center, "right": style_right}.get(align, style)
            story.append(Paragraph(_render_inline_bold(line), chosen_style))

    story = []
    _add_text_block(contract_text, story, break_before_appendix=True)

    i = 0
    blocks = extra_blocks or []
    while i < len(blocks):
        block = blocks[i]
        if isinstance(block, str):
            # Текстовый блок (например, блок подписи) — всегда с новой страницы
            story.append(PageBreak())
            _add_text_block(block, story)
            i += 1
        else:
            # Группа идущих подряд фото — держим вместе на одной странице
            img_group = []
            while i < len(blocks) and not isinstance(blocks[i], str):
                img = blocks[i]
                iw, ih = img.size
                # Масштаб: по ширине страницы, но не выше самой страницы —
                # иначе очень вытянутое фото (например, 9:16) не помещается
                # в кадр и PDF не создаётся вовсе.
                scale = min(max_img_width / iw, max_img_height / ih)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=88)
                buf.seek(0)
                img_group.append(RLImage(buf, width=iw * scale, height=ih * scale))
                img_group.append(Spacer(1, 12))
                i += 1
            story.append(PageBreak())
            story.append(KeepTogether(img_group))

    if header_text:
        doc.build(story, canvasmaker=_make_numbered_canvas(header_text, font_name))
    else:
        doc.build(story)
    return path

# =====================================================
# СОГЛАСИЕ НА ОБРАБОТКУ ПЕРСОНАЛЬНЫХ ДАННЫХ
# =====================================================

CONSENT_FILE   = f"{DATA_DIR}/consent_template.txt"
CONSENT_STATIC = "static/consent_template.txt"

def load_consent_template():
    if os.path.exists(CONSENT_FILE):
        with open(CONSENT_FILE, "r", encoding="utf-8") as f:
            return f.read()
    if os.path.exists(CONSENT_STATIC):
        with open(CONSENT_STATIC, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def generate_consent(booking):
    """Генерирует текст согласия на обработку ПД по тому же принципу, что и generate_contract()."""
    today = _date_ru_words(now_nsk())
    template = load_consent_template()
    if not template:
        return "Shablon soglasiya ne nayden."
    return fill_contract(template, {
        "ДАТА_ДОГОВОРА": today,
        "ФИО":           booking.get("guest_name", ""),
        "ПАСПОРТ":       booking.get("passport", "не указано"),
        "EMAIL":         booking.get("guest_email", ""),
        "НОМЕР_БРОНИ":   str(booking.get("username") or booking.get("id", "")),
    })
