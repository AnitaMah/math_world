"""Тести профілів підручників — на реальних рядках з обох книжок."""
import re
import unittest

from education.pdf_pipeline.profiles import BLOCK_TYPES, DIFFICULTY_LEVELS, PROFILES, get_profile
from education.pdf_pipeline.profiles.base import (
    BlockMarker, TextbookProfile, normalize_marker_text, roman_to_int, section_number,
)

M5 = get_profile("math_merzlyak_5")
T6 = get_profile("math_tarasenkova_6")


def block(profile, text):
    found = profile.match_block_marker(text)
    return found[0].block_type if found else None


class RegistryTests(unittest.TestCase):
    def test_get_profile(self):
        self.assertIs(get_profile("math_merzlyak_5"), M5)
        with self.assertRaises(KeyError):
            get_profile("nope")

    def test_all_regexes_compiled_and_levels_valid(self):
        for profile in PROFILES.values():
            with self.subTest(profile=profile.code):
                for pattern in (profile.section_re, profile.paragraph_re, profile.exercise_re):
                    self.assertIsInstance(pattern, re.Pattern)
                self.assertTrue(set(profile.difficulty_marks.values()) <= set(DIFFICULTY_LEVELS))

    def test_block_types_include_parser_types(self):
        self.assertTrue({"theory", "self_check", "exercise", "wise_owl", "rule"} <= BLOCK_TYPES)

    def test_bad_profile_rejected(self):
        with self.assertRaises(ValueError):
            TextbookProfile(code="x", subject_code="m", grade=1, author="", year=0, title="", pdf_name="",
                            lesson_level="item", section_re=re.compile(""), paragraph_re=re.compile(""),
                            item_re=None, exercise_re=re.compile(""), block_markers=(),
                            difficulty_marks={"*": "super-hard"}, default_difficulty=None)


class HelpersTests(unittest.TestCase):
    def test_normalize_marker_text(self):
        self.assertEqual(normalize_marker_text("РОЗВ’ЯЖІТЬ  ЗАДАЧІ:"), "розв'яжіть задачі")
        self.assertEqual(normalize_marker_text("Bправи"), "вправи")
        self.assertEqual(normalize_marker_text("З а д а ч а . Знайдіть"), "задача знайдіть")
        self.assertEqual(normalize_marker_text("1) 6 і 24"), "1 6 і 24")    # одиночні токени не склеюємо

    def test_roman(self):
        self.assertEqual([roman_to_int(r) for r in ("I", "II", "IV", "IX", "XIV")], [1, 2, 4, 9, 14])
        for bad in ("IIII", "IIV", "ABC", ""):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                roman_to_int(bad)
        self.assertEqual(section_number("3"), 3)
        self.assertEqual(section_number("II"), 2)

    def test_marker_prefix_mode(self):
        m = BlockMarker("worked_example", ("Задача",), whole_line=False)
        self.assertGreaterEqual(m.score("Задача. Знайдіть усі дільники"), 85)
        self.assertLess(m.score("Знайдіть усі дільники"), 85)


class MerzlyakMarkerTests(unittest.TestCase):
    def test_markers(self):
        cases = {
            "Розв'язуємо усно": "oral_exercise",
            "Розв’язуємо усно": "oral_exercise",
            "Розвязуємо усно": "oral_exercise",           # OCR загубив апостроф
            "Вправи": "exercise",
            "Bправи": "exercise",                          # латинська B
            "Вправи для повторення": "review_exercise",     # довша фраза перемагає «Вправи»
            "Задача від Мудрої Сови": "wise_owl",
            "Задача від Мудрої Сови ох": "wise_owl",       # сміття від іконки
            "Коли зроблено уроки": "history_aside",
            "Завдання № 1 «Перевірте себе» в тестовій формі": "self_test",
            "Завдання № 3 «Перевірте себе» в тестовій формі": "self_test",
            "Головне в параграфі 1": "summary",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(block(M5, text), expected)

    def test_not_markers(self):
        for text in ["Скільки вправ ти зробив?", "8. Скільки чисел стоїть у натуральному ряду",
                     "Ці вправи допоможуть", "Задача"]:
            with self.subTest(text=text):
                self.assertIsNone(block(M5, text))

    def test_exercise_start_and_difficulty(self):
        self.assertEqual(M5.parse_exercise_start('8." Скільки чисел'), (8, "sufficient", "Скільки чисел"))
        self.assertEqual(M5.parse_exercise_start("8.• Скільки"), (8, "sufficient", "Скільки"))
        self.assertEqual(M5.parse_exercise_start("11.•• Деяке"), (11, "high", "Деяке"))
        self.assertEqual(M5.parse_exercise_start("3.° Запишіть"), (3, "medium", "Запишіть"))
        self.assertEqual(M5.parse_exercise_start("25.* Доведіть"), (25, "olympiad", "Доведіть"))
        self.assertEqual(M5.parse_exercise_start("12. Обчисліть:"), (12, None, "Обчисліть:"))
        self.assertIsNone(M5.parse_exercise_start("Вправи"))
        self.assertIsNone(M5.parse_exercise_start("1) 238 + 435;"))

    def test_item_and_paragraph_regex(self):
        self.assertTrue(M5.item_re.match("2. Цифри. Десятковий запис натуральних чисел"))
        self.assertTrue(M5.paragraph_re.match("§ 1. Натуральні числа"))
        m = M5.section_re.match("Розділ I. Натуральні числа і дії з ними")
        self.assertEqual(m.group("num"), "I")


class TarasenkovaMarkerTests(unittest.TestCase):
    def test_markers(self):
        cases = {
            "РОЗВ’ЯЖІТЬ ЗАДАЧІ": "exercise",
            "ЗАСТОСУЙТЕ НА ПРАКТИЦІ": "applied_exercise",
            "ЗАДАЧІ НА ПОВТОРЕННЯ": "review_exercise",
            "ПРИГАДАЙТЕ ГОЛОВНЕ": "self_check",
            "Запам'ятайте!": "rule",
            "Зверніть увагу:": "note",
            "Дізнайтеся більше": "extra_reading",
            "Задача. Знайдіть усі дільники числа: 1) 7; 2) 12; 3) 25.": "worked_example",
            "З а д а ч а . Знайдіть усі непарні числа": "worked_example",   # надруковано врозрядку
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(block(T6, text), expected)

    def test_exercise_difficulty(self):
        self.assertEqual(T6.parse_exercise_start("35′. Назвіть: 1) три"), (35, "preparatory", "Назвіть: 1) три"))
        self.assertEqual(T6.parse_exercise_start("35'. Назвіть"), (35, "preparatory", "Назвіть"))
        self.assertEqual(T6.parse_exercise_start("40°. Із чисел"), (40, "medium", "Із чисел"))
        self.assertEqual(T6.parse_exercise_start("63. Перемалюйте"), (63, "sufficient", "Перемалюйте"))
        self.assertEqual(T6.parse_exercise_start("72*. Запишіть"), (72, "high", "Запишіть"))

    def test_paragraph_heading_uppercase(self):
        m = T6.paragraph_re.match("§ 2. ОЗНАКИ ПОДІЛЬНОСТІ НА 2, 10, 5")
        self.assertEqual(m.group("num"), "2")
        self.assertIsNone(T6.item_re)


if __name__ == "__main__":
    unittest.main()
