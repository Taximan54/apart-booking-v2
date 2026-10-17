"""Письмо гостю после выезда: размер скидки, тема и текст из админки, обычное личное письмо."""
import asyncio
import json
import os

import pytest
from fastapi import HTTPException


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def env(tmp_path, monkeypatch):
    import core.review_promo as rp
    import routers.pricing as pricing
    files = {"REVIEW_PROMO_FILE": str(tmp_path / "review_promo.json"), "REVIEW_FILE": str(tmp_path / "review_template.txt"),
             "PROMO_FILE": str(tmp_path / "promo_codes.json")}
    for module in (rp, pricing):
        for name, path in files.items():
            if hasattr(module, name):
                monkeypatch.setattr(module, name, path)
    return rp, files


def test_defaults_and_save_limits(env):
    rp, _ = env
    from core.constants import DEFAULT_REVIEW_SUBJECT
    assert rp.get_review_settings() == {"percent": 10, "subject": DEFAULT_REVIEW_SUBJECT}
    assert rp.save_review_settings(25, "  Спасибо, {{ИМЯ}}!  ") == {"percent": 25, "subject": "Спасибо, {{ИМЯ}}!"}
    assert rp.get_review_settings()["percent"] == 25
    assert rp.save_review_settings(0, "")["subject"] == DEFAULT_REVIEW_SUBJECT           # пустая тема — по умолчанию
    for bad in (-1, 91, 1000):
        with pytest.raises(ValueError):
            rp.save_review_settings(bad, "x")
    with pytest.raises(ValueError):
        rp.save_review_settings(10, "x" * 151)


def test_broken_settings_file_gives_defaults(env):
    rp, files = env
    open(files["REVIEW_PROMO_FILE"], "w", encoding="utf-8").write("{не json")
    assert rp.get_review_settings()["percent"] == 10
    open(files["REVIEW_PROMO_FILE"], "w", encoding="utf-8").write(json.dumps({"percent": "много", "subject": ""}))
    assert rp.get_review_settings()["percent"] == 10
    open(files["REVIEW_PROMO_FILE"], "w", encoding="utf-8").write(json.dumps({"percent": 500}))
    assert rp.get_review_settings()["percent"] == 90                                      # лишнее обрезается до максимума


def test_issue_promo_code_keeps_other_codes(env):
    rp, files = env
    json.dump({"SUMMER": 15}, open(files["PROMO_FILE"], "w", encoding="utf-8"))
    code = rp.issue_promo_code("GP-ABC123", 20)
    assert code == "RETURNC123"
    saved = json.load(open(files["PROMO_FILE"], encoding="utf-8"))
    assert saved == {"SUMMER": 15, "RETURNC123": 20}
    assert rp.issue_promo_code("GP-ABC123", 30) and json.load(open(files["PROMO_FILE"], encoding="utf-8"))["RETURNC123"] == 30


def test_build_email_fills_placeholders_and_is_a_plain_letter(env):
    rp, _ = env
    subject, html, text = rp.build_review_email("Анна", "RETURN1234", 15)
    assert subject == "Спасибо за визит, Анна"
    assert "Здравствуйте, Анна!" in text and "RETURN1234" in text and "15%" in text
    assert "{{" not in text and "{{" not in html and "{{" not in subject
    assert "citypause.ru" in text                                                         # {{САЙТ}} подставлен
    for marketing in ("#0A0A0A", "letter-spacing", "background:#"):
        assert marketing not in html, f"в письме не должно быть рекламного оформления: {marketing}"
    assert "<table" not in html.lower() and "<img" not in html.lower()
    assert text.rstrip().endswith("citypause.ru") or "citypause.ru" in text.split("--")[-1]


def test_build_email_zero_percent_has_no_promo(env):
    rp, _ = env
    subject, html, text = rp.build_review_email("Анна", "", 0)
    assert "RETURN" not in text and "%" not in text and "промокод" not in text.lower()
    assert "{{" not in text and "Здравствуйте, Анна!" in text and "Бронируйте напрямую" in text
    assert "\n\n\n" not in text                                                           # пустые строки не накапливаются


def test_custom_template_without_placeholder_gets_promo_line(env):
    rp, files = env
    open(files["REVIEW_FILE"], "w", encoding="utf-8").write("Спасибо за визит!\n\nОставьте отзыв.")
    _, html, text = rp.build_review_email("Иван", "RETURN9999", 12)
    assert "Ваш промокод: RETURN9999 (скидка 12% на следующее бронирование)." in text
    # шаблон с меткой промокода: отдельная строка не дублируется
    open(files["REVIEW_FILE"], "w", encoding="utf-8").write("Код: {{ПРОМОКОД}}")
    _, _, text2 = rp.build_review_email("Иван", "RETURN9999", 12)
    assert text2.count("RETURN9999") == 1


def test_html_is_escaped_and_missing_name_is_handled(env):
    rp, files = env
    open(files["REVIEW_FILE"], "w", encoding="utf-8").write("<script>alert(1)</script> {{ИМЯ}} & {{ПРОМОКОД}}")
    subject, html, text = rp.build_review_email("", "RETURN1111", 10, subject="Тема {{ИМЯ}}")
    assert "<script>" not in html and "&lt;script&gt;" in html and "&amp;" in html
    assert subject == "Тема гость" and "гость" in text


def test_email_review_request_sends_plain_and_html(env, monkeypatch):
    import core.emails as emails
    sent = []
    monkeypatch.setattr(emails, "send_email", lambda to, subject, html, attachments=None, text_body=None: sent.append((to, subject, html, text_body)))
    emails.email_review_request("Анна", "anna@example.com", "GP-ABC123", "RETURNC123", 10)
    to, subject, html, text = sent[0]
    assert to == "anna@example.com" and subject == "Спасибо за визит, Анна" and "RETURNC123" in html and "RETURNC123" in text


def test_mailer_puts_plain_text_before_html(monkeypatch):
    import core.mailer as mailer
    captured = {}

    class FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, *a):
            pass

        def sendmail(self, sender, to, message):
            captured["raw"] = message
    monkeypatch.setattr(mailer, "MAIL_PASSWORD", "x")
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTP)
    mailer.send_email("a@b.c", "Тема", "<p>html</p>", text_body="plain text")
    raw = captured["raw"]
    assert raw.index("text/plain") < raw.index("text/html")
    captured.clear()
    mailer.send_email("a@b.c", "Тема", "<p>html</p>")                                     # старое поведение: только html
    assert "text/plain" not in captured["raw"] and "text/html" in captured["raw"]


def test_admin_api(env, monkeypatch):
    import inspect
    from core.auth import require_admin
    from core.models import ReviewPromoTest, ReviewPromoUpdate
    from routers import pricing as r
    for func in (r.get_review_promo, r.set_review_promo, r.send_review_promo_test):
        default = inspect.signature(func).parameters["_"].default
        assert getattr(default, "dependency", None) is require_admin, f"{func.__name__} без проверки админа"
    state = run(r.get_review_promo(True))
    assert state["percent"] == 10 and "{{ИМЯ}}" in state["text"] and state["default_text"] == state["text"]
    for bad in (ReviewPromoUpdate(percent=95, subject="", text="x"), ReviewPromoUpdate(percent=10, subject="", text="   "),
                ReviewPromoUpdate(percent=-5, subject="", text="x")):
        with pytest.raises(HTTPException) as e:
            run(r.set_review_promo(bad, True))
        assert e.value.status_code == 400
    saved = run(r.set_review_promo(ReviewPromoUpdate(percent=30, subject="Привет, {{ИМЯ}}", text="Код {{ПРОМОКОД}} на {{ПРОЦЕНТ_СКИДКИ}}%"), True))
    assert saved["percent"] == 30 and run(r.get_review_promo(True))["text"] == "Код {{ПРОМОКОД}} на {{ПРОЦЕНТ_СКИДКИ}}%"
    sent = []
    monkeypatch.setattr(r, "send_email", lambda to, subject, html, attachments=None, text_body=None: sent.append((to, subject, text_body)))
    monkeypatch.setattr(r, "get_landlord_email", lambda: "owner@example.com")
    assert run(r.send_review_promo_test(ReviewPromoTest(), True))["to"] == "owner@example.com"
    run(r.send_review_promo_test(ReviewPromoTest(email=" me@example.com "), True))
    assert [s[0] for s in sent] == ["owner@example.com", "me@example.com"]
    assert sent[0][1] == "Привет, Иван" and "RETURNTEST" in sent[0][2] and "30%" in sent[0][2]
    for bad in ("без-собаки", "a b@c.d"):
        with pytest.raises(HTTPException):
            run(r.send_review_promo_test(ReviewPromoTest(email=bad), True))
    run(r.set_review_promo(ReviewPromoUpdate(percent=0, subject="", text="Спасибо!\n\nКод {{ПРОМОКОД}}"), True))
    run(r.send_review_promo_test(ReviewPromoTest(), True))
    assert "RETURNTEST" not in sent[-1][2], "при скидке 0% в пробном письме нет промокода"


def test_discounts_page_passes_property():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "discounts.html")
    text = open(path, encoding="utf-8").read()
    assert "PROPERTY_SLUG" in text and "/api/discounts` + (PROPERTY_SLUG" in text
    assert 'href="index.html"' not in text


# ---------------------------------------------------------------------------
# Рассылка после выезда (один проход планировщика)
# ---------------------------------------------------------------------------

def _run_review_pass(monkeypatch, bookings):
    """Один проход цикла рассылок в 14:05: возвращает (отправленные письма, помеченные брони)."""
    import threading
    from datetime import datetime

    import core.scheduler as sched

    class StopLoop(Exception):
        pass

    async def stop_sleep(_):
        raise StopLoop()
    sent, marked = [], []
    monkeypatch.setattr(sched, "now_nsk", lambda: datetime(2026, 10, 12, 14, 5))
    monkeypatch.setattr(sched, "get_site_settings_dict", lambda *a, **k: {})
    monkeypatch.setattr(sched, "list_properties", lambda: [{"id": 1, "name": "Квартира", "active": True}])
    monkeypatch.setattr(sched, "get_bookings_checkout_today", lambda pid: [])
    monkeypatch.setattr(sched, "get_bookings_checkout_yesterday", lambda pid: list(bookings))
    monkeypatch.setattr(sched, "get_last_owner_notify_date", lambda: "2026-10-12")
    monkeypatch.setattr(sched, "get_last_backup_date", lambda: "2026-10-12")
    monkeypatch.setattr(sched, "email_review_request", lambda *a: sent.append(a))
    monkeypatch.setattr(sched, "mark_review_sent", lambda i, u: marked.append((i, u)))
    monkeypatch.setattr(sched.asyncio, "sleep", stop_sleep)
    monkeypatch.setattr(threading.Thread, "start", lambda self: self.run())
    with pytest.raises(StopLoop):
        run(sched.send_notifications())
    return sent, marked


def test_scheduler_uses_chosen_discount(env, monkeypatch):
    rp, files = env
    rp.save_review_settings(25, "")
    booking = {"id": 7, "username": "GP-ABC123", "guest_name": "Анна", "guest_email": "anna@example.com"}
    done = {"id": 8, "username": "GP-DONE888", "guest_name": "Пётр", "guest_email": "p@example.com", "review_sent": 1}
    no_email = {"id": 9, "username": "GP-NOMAIL9", "guest_name": "Без почты", "guest_email": ""}
    sent, marked = _run_review_pass(monkeypatch, [booking, done, no_email])
    assert sent == [("Анна", "anna@example.com", "GP-ABC123", "RETURNC123", 25)]
    assert marked == [(7, "GP-ABC123")]
    assert json.load(open(files["PROMO_FILE"], encoding="utf-8")) == {"RETURNC123": 25}     # промокод создан с выбранной скидкой


def test_scheduler_zero_discount_sends_letter_without_code(env, monkeypatch):
    rp, files = env
    rp.save_review_settings(0, "")
    booking = {"id": 7, "username": "GP-ABC123", "guest_name": "Анна", "guest_email": "anna@example.com"}
    sent, marked = _run_review_pass(monkeypatch, [booking])
    assert sent == [("Анна", "anna@example.com", "GP-ABC123", "", 0)] and marked == [(7, "GP-ABC123")]
    assert not os.path.exists(files["PROMO_FILE"]), "при скидке 0% промокод не создаётся"
