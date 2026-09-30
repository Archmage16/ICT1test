"""Validation shared by public account forms; no contact-ownership claims."""
import re
import unicodedata

import phonenumbers
from django.core.exceptions import ValidationError

NAME_ERROR = "Используйте только буквы, пробелы, дефис или апостроф между частями имени."
PHONE_ERROR = "Введите корректный телефон: +7 701 123 45 67 или номер другой страны с кодом +."
EMAIL_ERROR = "Введите корректную почту, например student@example.com."
EMAIL_DUPLICATE = "Эта почта уже используется другим аккаунтом. Укажите другую или войдите в свой аккаунт."
NAME_HELP = "Буквы любого языка; допустимы пробел, дефис и апостроф. Без цифр."
PHONE_HELP = "Необязательно. Казахстан: +7 701 123 45 67 или 8 701 123 45 67. Другие страны: с кодом +."
EMAIL_HELP = "Например student@example.com. Проверяется формат, а не принадлежность адреса."


def clean_person_name(value):
    value = unicodedata.normalize("NFC", value.strip())
    value = value.replace("\u2019", "'").replace("\u02bc", "'").replace("\u2010", "-").replace("\u2011", "-")
    # Collapse ordinary spaces only, not tabs/newlines or invisible controls.
    value = re.sub(" +", " ", value)
    if not value:
        return ""
    previous_letter = False
    for character in value:
        category = unicodedata.category(character)
        if category.startswith("L"):
            previous_letter = True
        elif category.startswith("M") and previous_letter:
            continue
        elif character in " -'" and previous_letter:
            previous_letter = False
        else:
            raise ValidationError(NAME_ERROR, code="invalid_name")
    if not previous_letter:
        raise ValidationError(NAME_ERROR, code="invalid_name")
    return value


def clean_phone_number(value):
    value = value.strip()
    if not value:
        return ""
    # Do not let the parser silently ignore text, extensions or extra + signs.
    if not re.fullmatch(r"\+?[0-9 ()-]+", value):
        raise ValidationError(PHONE_ERROR, code="invalid_phone")
    try:
        number = phonenumbers.parse(value, "KZ")
    except phonenumbers.NumberParseException:
        raise ValidationError(PHONE_ERROR, code="invalid_phone") from None
    if not phonenumbers.is_valid_number(number):
        raise ValidationError(PHONE_ERROR, code="invalid_phone")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
