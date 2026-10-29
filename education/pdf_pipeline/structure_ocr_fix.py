"""Відновлення номерів вправ, зіпсованих OCR: типові помилки (цифри-двійники, зайва
цифра, значок складності прочитано як «7», цифра прочитана як схожа літера) і спроба
отримати з «сирого» тексту очікуваний номер однією такою правкою.

Винесено зі ``structure.py`` (BE-S11): це самостійний, суто текстовий шар — не залежить
від дерева розбору чи стану автомата, лише від рядка і очікуваного числа.
"""
from __future__ import annotations

import re

# Номер вправи, де цифру OCR прочитав як літеру: «о. Біля школи» (5.), «З. Назвіть» (3.).
# Тут крапка обов'язкова — інакше «о Біля…» посеред тексту теж стало б вправою.
_DIGIT_LOOKALIKES = {"о": "05", "О": "05", "o": "05", "O": "05", "б": "6", "З": "3", "з": "3",
                     "В": "8", "S": "5", "s": "5", "l": "1", "I": "1", "|": "1", "т": "7"}
# Початок вправи без крапки або зі зламаним значком: «82 Скільки», «4 Яке число», «4, Назвіть», «67" Точка»
_LOOSE_EXERCISE_RE = re.compile(r"^(?P<num>\d{1,4})(?P<junk>[,.\"”'°•·*]{0,3})\s+(?P<rest>[А-ЯІЇЄҐA-Z].*)$")
_LETTER_NUMBER_RE = re.compile(
    r"^(?P<num>[\d" + "".join(re.escape(c) for c in _DIGIT_LOOKALIKES) + r"]{1,4})"
    r"(?P<junk>[,.\"”'°•·*]{1,3})\s+(?P<rest>[А-ЯІЇЄҐA-Z].*)$")
# Цифри, які OCR плутає між собою у цьому шрифті
_CONFUSABLE_DIGITS = {"3": "8", "8": "3", "5": "6", "6": "5", "1": "7", "7": "1", "0": "8"}
# Сміття перед номером: розділові знаки та окремі 1–2-літерні «слова» (fy, &). Літери не мають бути частиною
# довшого слова, інакше «на рисунку 138.» читалося б як сміття + номер 138.
_LEADING_JUNK_RE = re.compile(r"^(?:[^\w\s§]|(?<![^\W\d_])[^\W\d_]{1,2}(?![^\W\d_])\.?|\s){1,8}?(?=\d)")
_MARK_SEVEN_RE = re.compile(r"^(?P<junk>[^\d]{0,8}?)(?P<num>\d{2,4})7(?=\s*[.,])")


def letter_number_candidates(raw: str) -> set[int]:
    """«о» → {0, 5}, «1о» → {10, 15}: усі числа, які могли бути на місці літер-двійників."""
    options = [""]
    for ch in raw:
        digits = ch if ch.isdigit() else _DIGIT_LOOKALIKES.get(ch, "")
        options = [o + d for o in options for d in digits]
    return {int(o) for o in options if o}


def number_fixable(raw: str, expected: int) -> bool:
    """Чи можна отримати ``expected`` з ``raw`` однією типовою помилкою OCR.

    «88» → 83 (3↔8), «168» → 163, «382» → 32 (зайва цифра — це був значок •),
    «82» → 8 (значок прочитано як цифру).
    """
    target = str(expected)
    if raw == target:
        return True
    if len(raw) > len(target):       # значок прочитано цифрою І цифру сплутано: «7717» → 171, «766» → 166
        for i in range(len(raw)):
            rest = raw[:i] + raw[i + 1:]
            if len(rest) == len(target) and sum(a != b for a, b in zip(rest, target)) == 1 \
                    and all(a == b or _CONFUSABLE_DIGITS.get(a) == b for a, b in zip(rest, target)):
                return True
    for i in range(len(raw)):
        if raw[:i] + raw[i + 1:] == target:                                   # зайва цифра
            return True
        swapped = _CONFUSABLE_DIGITS.get(raw[i])
        if swapped and raw[:i] + swapped + raw[i + 1:] == target:            # сплутана цифра
            return True
    return False


def _mark_as_seven(text: str) -> str:
    """«5707. Складіть» → «570. Складіть»: ′ (штрих складності) прочитано як цифра 7."""
    return _MARK_SEVEN_RE.sub(lambda m: m.group("junk") + m.group("num"), text, count=1)
