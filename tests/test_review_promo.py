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
# Решения админа и рассылка после выезда (один проход планировщика)
# ---------------------------------------------------------------------------

def test_review_decisions_storage(env, monkeypatch, tmp_path):
    rp, _ = env
    monkeypatch.setattr(rp, "REVIEW_DECISIONS_FILE", str(tmp_path / "review_decisions.json"))
    assert rp.load_review_decisions() == {}
    rp.set_review_decision("GP-ABC123", "promo")
    rp.set_review_decision("GP-BAD999", "skip")
    rp.set_review_decision("GP-ABC123", "nopromo")                                        # решение можно заменить
    assert rp.load_review_decisions() == {"GP-ABC123": "nopromo", "GP-BAD999": "skip"}
    with pytest.raises(ValueError):
        rp.set_review_decision("GP-ABC123", "что-то другое")
    open(rp.REVIEW_DECISIONS_FILE, "w", encoding="utf-8").write("{не json")
    assert rp.load_review_decisions() == {}                                               # битый файл — как будто решений нет


def test_review_decision_api(env, monkeypatch, tmp_path):
    import inspect
    from core.auth import require_admin
    from routers import pricing as r
    rp, _ = env
    monkeypatch.setattr(rp, "REVIEW_DECISIONS_FILE", str(tmp_path / "review_decisions.json"))
    for func in (r.get_review_decisions, r.set_booking_review_decision):
        default = inspect.signature(func).parameters["_"].default
        assert getattr(default, "dependency", None) is require_admin, f"{func.__name__} без проверки админа"
    monkeypatch.setattr(r, "exists_by_ref", lambda ref: ref == "GP-ABC123")
    assert run(r.get_review_decisions(True)) == {}
    assert run(r.set_booking_review_decision("GP-ABC123", r.ReviewDecision(decision="promo"), True)) == {"ok": True}
    assert run(r.get_review_decisions(True)) == {"GP-ABC123": "promo"}
    with pytest.raises(HTTPException) as e:
        run(r.set_booking_review_decision("GP-ABC123", r.ReviewDecision(decision="всем"), True))
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        run(r.set_booking_review_decision("GP-NONE00", r.ReviewDecision(decision="promo"), True))
    assert e.value.status_code == 404


def _run_review_pass(monkeypatch, rp, tmp_path, bookings, decisions):
    """Один проход цикла рассылок в 14:05 (12.10.2026): возвращает (отправленные письма, помеченные брони).
    bookings — брони из базы, decisions — {номер брони: решение админа}."""
    import threading
    from datetime import datetime

    import core.scheduler as sched

    class StopLoop(Exception):
        pass

    async def stop_sleep(_):
        raise StopLoop()
    monkeypatch.setattr(rp, "REVIEW_DECISIONS_FILE", str(tmp_path / "review_decisions.json"))
    for ref, decision in decisions.items():
        rp.set_review_decision(ref, decision)
    by_ref = {b["username"]: b for b in bookings}
    sent, marked = [], []
    monkeypatch.setattr(sched, "now_nsk", lambda: datetime(2026, 10, 12, 14, 5))
    monkeypatch.setattr(sched, "get_site_settings_dict", lambda *a, **k: {})
    monkeypatch.setattr(sched, "list_properties", lambda: [{"id": 1, "name": "Квартира", "active": True}])
    monkeypatch.setattr(sched, "get_bookings_checkout_today", lambda pid: [])
    monkeypatch.setattr(sched, "get_bookings_checkout_yesterday", lambda pid: [])
    monkeypatch.setattr(sched, "get_by_ref_or_id", lambda ref: by_ref.get(str(ref)))
    monkeypatch.setattr(sched, "get_last_owner_notify_date", lambda: "2026-10-12")
    monkeypatch.setattr(sched, "get_last_backup_date", lambda: "2026-10-12")
    monkeypatch.setattr(sched, "email_review_request", lambda *a: sent.append(a))
    monkeypatch.setattr(sched, "mark_review_sent", lambda i, u: marked.append((i, u)))
    monkeypatch.setattr(sched.asyncio, "sleep", stop_sleep)
    monkeypatch.setattr(threading.Thread, "start", lambda self: self.run())
    with pytest.raises(StopLoop):
        run(sched.send_notifications())
    return sent, marked


def _booking(num, ref, name, email="x@example.com", **extra):
    data = {"id": num, "username": ref, "guest_name": name, "guest_email": email, "status": "confirmed", "check_out": "2026-10-11", "review_sent": 0}
    data.update(extra)
    return data


def test_scheduler_sends_only_chosen_bookings(env, monkeypatch, tmp_path):
    rp, files = env
    rp.save_review_settings(25, "")
    approved = _booking(7, "GP-ABC123", "Анна", "anna@example.com")
    undecided = _booking(8, "GP-NODEC88", "Без решения")
    skipped = _booking(9, "GP-SKIP999", "Не отправлять")
    done = _booking(10, "GP-DONE100", "Уже получил", review_sent=1)
    no_email = _booking(11, "GP-NOMAIL11", "Без почты", email="")
    not_yet = _booking(12, "GP-LATER12", "Ещё живёт", check_out="2026-10-13")
    cancelled = _booking(13, "GP-CANC013", "Отмена", status="cancelled")
    decisions = {"GP-ABC123": "promo", "GP-SKIP999": "skip", "GP-DONE100": "promo", "GP-NOMAIL11": "promo",
                 "GP-LATER12": "promo", "GP-CANC013": "promo", "GP-NONE000": "promo"}   # последняя — брони уже нет
    sent, marked = _run_review_pass(monkeypatch, rp, tmp_path,
                                    [approved, undecided, skipped, done, no_email, not_yet, cancelled], decisions)
    assert sent == [("Анна", "anna@example.com", "GP-ABC123", "RETURNC123", 25)]
    assert marked == [(7, "GP-ABC123")]
    assert json.load(open(files["PROMO_FILE"], encoding="utf-8")) == {"RETURNC123": 25}     # промокод создан с выбранной скидкой


def test_scheduler_without_promo_choice_sends_letter_without_code(env, monkeypatch, tmp_path):
    rp, files = env
    rp.save_review_settings(25, "")                                                       # скидка в настройках есть, но админ выбрал «без промокода»
    booking = _booking(7, "GP-ABC123", "Анна", "anna@example.com")
    sent, marked = _run_review_pass(monkeypatch, rp, tmp_path, [booking], {"GP-ABC123": "nopromo"})
    assert sent == [("Анна", "anna@example.com", "GP-ABC123", "", 0)] and marked == [(7, "GP-ABC123")]
    assert not os.path.exists(files["PROMO_FILE"]), "при выборе «без промокода» промокод не создаётся"


def test_scheduler_zero_discount_sends_letter_without_code(env, monkeypatch, tmp_path):
    rp, files = env
    rp.save_review_settings(0, "")
    booking = _booking(7, "GP-ABC123", "Анна", "anna@example.com")
    sent, marked = _run_review_pass(monkeypatch, rp, tmp_path, [booking], {"GP-ABC123": "promo"})
    assert sent == [("Анна", "anna@example.com", "GP-ABC123", "", 0)] and marked == [(7, "GP-ABC123")]
    assert not os.path.exists(files["PROMO_FILE"]), "при скидке 0% промокод не создаётся"


def test_scheduler_without_any_decision_sends_nothing(env, monkeypatch, tmp_path):
    rp, _ = env
    booking = _booking(7, "GP-ABC123", "Анна", "anna@example.com")
    sent, marked = _run_review_pass(monkeypatch, rp, tmp_path, [booking], {})
    assert sent == [] and marked == []


# ---------------------------------------------------------------------------
# Письмо с промокодом любому человеку («Промокоды → Отправить промокод человеку»)
# ---------------------------------------------------------------------------

def _send_env(env, monkeypatch):
    from routers import pricing as r
    rp, files = env
    sent = []
    monkeypatch.setattr(r, "send_email", lambda to, subject, html, attachments=None, text_body=None: sent.append((to, subject, html, text_body)))
    return r, rp, files, sent


def test_send_promo_to_guest_creates_new_personal_code(env, monkeypatch):
    import inspect
    from core.auth import require_admin
    from core.models import ReviewPromoSend
    r, rp, files, sent = _send_env(env, monkeypatch)
    default = inspect.signature(r.send_promo_to_guest).parameters["_"].default
    assert getattr(default, "dependency", None) is require_admin, "отправка промокода без проверки админа"
    res = run(r.send_promo_to_guest(ReviewPromoSend(email=" guest@example.com ", name="Мария", percent=15), True))
    assert res["to"] == "guest@example.com" and res["percent"] == 15 and res["created"] is True
    assert res["code"].startswith("GUEST") and len(res["code"]) == 10
    assert json.load(open(files["PROMO_FILE"], encoding="utf-8"))[res["code"]] == 15      # код сохранён и будет работать на сайте
    to, subject, html, text = sent[0]
    assert to == "guest@example.com" and "Мария" in text and res["code"] in text and "15%" in text


def test_send_promo_to_guest_existing_code_is_not_changed(env, monkeypatch):
    from core.models import ReviewPromoSend
    r, rp, files, sent = _send_env(env, monkeypatch)
    json.dump({"SUMMER": 20, "ZERO": 0}, open(files["PROMO_FILE"], "w", encoding="utf-8"))
    res = run(r.send_promo_to_guest(ReviewPromoSend(email="a@example.com", code=" summer "), True))
    assert res["code"] == "SUMMER" and res["percent"] == 20 and res["created"] is False
    assert json.load(open(files["PROMO_FILE"], encoding="utf-8")) == {"SUMMER": 20, "ZERO": 0}
    assert "SUMMER" in sent[0][3] and "20%" in sent[0][3]
    for bad in ("NOPE", "ZERO"):                                                          # нет такого кода / у кода нет скидки
        with pytest.raises(HTTPException) as e:
            run(r.send_promo_to_guest(ReviewPromoSend(email="a@example.com", code=bad), True))
        assert e.value.status_code == 400
    assert len(sent) == 1


def test_send_promo_to_guest_validation_sends_nothing(env, monkeypatch):
    from core.models import ReviewPromoSend
    r, rp, files, sent = _send_env(env, monkeypatch)
    for bad in (ReviewPromoSend(email="без-собаки"), ReviewPromoSend(email="a b@c.d"), ReviewPromoSend(email="a@example.com", percent=0),
                ReviewPromoSend(email="a@example.com", percent=95), ReviewPromoSend(email="a@example.com", subject="x" * 151)):
        with pytest.raises(HTTPException) as e:
            run(r.send_promo_to_guest(bad, True))
        assert e.value.status_code == 400
    assert sent == [] and not os.path.exists(files["PROMO_FILE"]), "при ошибке в данных ничего не отправляется и промокод не создаётся"


def test_send_promo_to_guest_failed_send_removes_new_code(env, monkeypatch):
    from core.models import ReviewPromoSend
    r, rp, files, sent = _send_env(env, monkeypatch)
    json.dump({"SUMMER": 20}, open(files["PROMO_FILE"], "w", encoding="utf-8"))

    def broken(*a, **k):
        raise RuntimeError("smtp down")
    monkeypatch.setattr(r, "send_email", broken)
    with pytest.raises(HTTPException) as e:
        run(r.send_promo_to_guest(ReviewPromoSend(email="a@example.com", percent=10), True))
    assert e.value.status_code == 502
    assert json.load(open(files["PROMO_FILE"], encoding="utf-8")) == {"SUMMER": 20}       # новый код не остался, прежние на месте


def test_send_promo_to_guest_custom_subject_and_text(env, monkeypatch):
    from core.models import ReviewPromoSend
    r, rp, files, sent = _send_env(env, monkeypatch)
    res = run(r.send_promo_to_guest(ReviewPromoSend(email="a@example.com", name="Иван", percent=12, subject="Скидка для {{ИМЯ}}",
                                                    text="Привет, {{ИМЯ}}! Ваш код {{ПРОМОКОД}} даёт {{ПРОЦЕНТ_СКИДКИ}}%."), True))
    _, subject, _, text = sent[0]
    assert subject == "Скидка для Иван"
    assert text.startswith(f"Привет, Иван! Ваш код {res['code']} даёт 12%.")
    assert "Спасибо за визит" not in text                                                 # стандартный текст не подмешивается


def test_personal_promo_codes_are_unique_and_readable(env):
    rp, files = env
    codes = {rp.issue_personal_promo_code(10) for _ in range(30)}
    assert len(codes) == 30 and all(c.startswith("GUEST") and not set(c[5:]) & set("01OIl") for c in codes)
    assert set(json.load(open(files["PROMO_FILE"], encoding="utf-8"))) == codes
