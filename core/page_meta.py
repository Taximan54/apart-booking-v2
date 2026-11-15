"""Название и описание сайта в <head> главной страницы: подставляются на сервере из настроек (для роботов без JavaScript)."""
import html
import re

from core.logger import get_logger

logger = get_logger(__name__)

# Подпись к названию, как в заголовке вкладки на странице (см. applySiteSettings в index.html)
TITLE_SUFFIX = "Апартаменты посуточно"


def _meta(name_attr: str, key: str, value: str) -> re.Pattern:
    return re.compile(r'<meta\s+' + name_attr + r'="' + re.escape(key) + r'"\s+content="[^"]*"\s*>')


def render_index_html(page: str, property_id: int = 1, path: str = "/") -> str:
    """
    Подставляет в <title>, og:* и description значения из настроек сайта выбранного объекта.
    При любой ошибке (нет настроек, страница изменилась) возвращает страницу без изменений.
    """
    try:
        from core.data_store import get_site_settings_dict
        from core.landlord import site_url

        settings = get_site_settings_dict(property_id)
        name = (settings.get("site_name") or "").strip()
        if not name:
            return page
        subtitle = (settings.get("hero_subtitle") or "").strip()
        title = html.escape(f"{name} — {TITLE_SUFFIX}", quote=True)
        base = site_url()
        url = html.escape(base + ("" if path in ("", "/") else path), quote=True)
        image = html.escape(base + "/static/og-image.jpg", quote=True)

        result = re.sub(r"<title>.*?</title>", lambda m: f"<title>{title}</title>", page, count=1, flags=re.S)
        result = _meta("property", "og:title", "").sub(lambda m: f'<meta property="og:title" content="{title}">', result, count=1)
        result = _meta("property", "og:url", "").sub(lambda m: f'<meta property="og:url" content="{url}">', result, count=1)
        result = _meta("property", "og:image", "").sub(lambda m: f'<meta property="og:image" content="{image}">', result, count=1)
        if subtitle:
            desc = html.escape(subtitle, quote=True)
            result = _meta("property", "og:description", "").sub(lambda m: f'<meta property="og:description" content="{desc}">', result, count=1)
            result = _meta("name", "description", "").sub(lambda m: f'<meta name="description" content="{desc}">', result, count=1)
        return result
    except Exception as e:
        logger.warning("Не удалось подставить название сайта в заголовок страницы: %s", e)
        return page
