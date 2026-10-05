"""Суммы и даты прописью, разметка договора, проверки телефона и паспорта."""
import datetime

import pytest

from core.contract_docs import _date_ru_words, _rub_in_words, contract_text_to_html
from core.validators import _passport_digits_ok, _phone_digits_ok


@pytest.mark.parametrize("amount,words", [
    (0, "Ноль рублей"),
    (1, "Один рубль"),
    (2, "Два рубля"),
    (5, "Пять рублей"),
    (11, "Одиннадцать рублей"),
    (21, "Двадцать один рубль"),
    (100, "Сто рублей"),
    (1500, "Одна тысяча пятьсот рублей"),
    (2000, "Две тысячи рублей"),
    (6745, "Шесть тысяч семьсот сорок пять рублей"),
    (12000, "Двенадцать тысяч рублей"),
    (21001, "Двадцать одна тысяча один рубль"),
    (999999, "Девятьсот девяносто девять тысяч девятьсот девяносто девять рублей"),
])
def test_rub_in_words(amount, words):
    assert _rub_in_words(amount) == words


def test_date_in_words():
    assert _date_ru_words(datetime.date(2026, 7, 22)) == "22 июля 2026"
    assert _date_ru_words(datetime.date(2026, 3, 1)) == "1 марта 2026"


def test_contract_markup_bold_center_heading():
    assert contract_text_to_html("**жирный** текст") == "<p><b>жирный</b> текст</p>"
    assert contract_text_to_html("[[CENTER]]по центру[[/CENTER]]") == '<p class="doc-center">по центру</p>'
    html = contract_text_to_html("1. Предмет договора\n1.1. Пункт")
    assert '<p class="doc-heading">1. Предмет договора</p>' in html
    assert "<p>1.1. Пункт</p>" in html


def test_phone_and_passport_validation():
    assert _phone_digits_ok("+7 (999) 123-45-67")
    assert not _phone_digits_ok("12345")
    assert _passport_digits_ok("1234 567890")
    assert not _passport_digits_ok("123")
