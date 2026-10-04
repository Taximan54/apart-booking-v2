"""Проверки введённых данных (телефон, паспорт)."""
import re


def _phone_digits_ok(phone: str) -> bool:
    """Ровно 10 цифр после кода +7 (итого 11 цифр, начиная с 7)."""
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("7"):
        digits = digits[1:]
    elif digits.startswith("8"):
        digits = digits[1:]
    return len(digits) == 10

def _passport_digits_ok(passport: str) -> bool:
    """Ровно 4 цифры серии + 6 цифр номера = 10 цифр."""
    digits = re.sub(r"\D", "", passport or "")
    return len(digits) == 10
