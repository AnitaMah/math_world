"""Тести для education.pdf_pipeline.content.normalize."""
import unittest

from education.pdf_pipeline.datatypes import BBox, Line, Word
from education.pdf_pipeline.content.normalize import (
    LATIN_TO_CYR, Context, Normalizer, join_hyphenation, normalize_lines, rule_latin_lookalike_word,
    rule_mixed_script, word_script,
)


def make_line(text: str, y: int = 0) -> Line:
    words = [Word(t, BBox(i * 60, y, i * 60 + 50, y + 20), 90.0) for i, t in enumerate(text.split())]
    return Line(words=words, page_index=1)


def norm(text: str, **kwargs) -> str:
    lines, _ = normalize_lines([make_line(text)], **kwargs)
    return lines[0].text if lines else ""


class LatinToCyrillicTableTests(unittest.TestCase):
    def test_every_pair_maps_to_cyrillic(self):
        for lat, cyr in LATIN_TO_CYR.items():
            with self.subTest(lat=lat):
                self.assertEqual(word_script(lat), "lat")
                self.assertEqual(word_script(cyr), "cyr")

    def test_word_script(self):
        self.assertEqual(word_script("Вправи"), "cyr")
        self.assertEqual(word_script("Bправи"), "mixed")
        self.assertEqual(word_script("AB"), "lat")
        self.assertEqual(word_script("2000"), "other")


class MixedScriptTests(unittest.TestCase):
    def test_fixes_mixed_words(self):
        ctx = Context(None, None)
        self.assertEqual(rule_mixed_script("Bправи", ctx), "Вправи")
        self.assertEqual(rule_mixed_script("нaтуральний", ctx), "натуральний")

    def test_unknown_latin_letter_left_alone(self):
        self.assertIsNone(rule_mixed_script("нqтуральний", Context(None, None)))


class LookalikeWordTests(unittest.TestCase):
    def test_real_ocr_examples(self):
        self.assertEqual(norm("Записати Bech натуральний ряд"), "Записати весь натуральний ряд")
        # Після «9.» починається речення (так і в книзі: «9.• На уроці»), тому велика літера.
        self.assertEqual(norm("9. Ha уроці фізкультури"), "9. На уроці фізкультури")
        self.assertEqual(norm("Чи кожне число B ряду"), "Чи кожне число в ряду")

    def test_start_of_sentence_keeps_capital(self):
        self.assertEqual(norm("числа. Ha уроці"), "числа. На уроці")

    def test_variable_after_bukvoyu_is_kept(self):
        self.assertEqual(norm("позначили буквою a."), "позначили буквою a.")

    def test_math_variables_kept(self):
        self.assertEqual(norm("x + 5 = 12"), "x + 5 = 12")
        self.assertEqual(norm("2 · a"), "2 · a")

    def test_geometry_kept(self):
        self.assertEqual(norm("відрізок AB дорівнює"), "відрізок AB дорівнює")

    def test_roman_numerals_kept(self):
        self.assertEqual(norm("Розділ II. Дробові числа"), "Розділ II. Дробові числа")
        self.assertIsNone(rule_latin_lookalike_word("IV", Context("Розділ", None)))

    def test_conjunction_a_between_words(self):
        self.assertEqual(norm("варення, a на обід"), "варення, а на обід")


class OtherRulesTests(unittest.TestCase):
    def test_apostrophe(self):
        self.assertEqual(norm("Розв’язуємо усно"), "Розв'язуємо усно")
        self.assertEqual(norm("з`їв"), "з'їв")

    def test_known_word(self):
        self.assertEqual(norm("більше 3a 3,"), "більше за 3,")

    def test_dash_between_words(self):
        self.assertEqual(norm("а Олена -- двадцятою"), "а Олена — двадцятою")

    def test_minus_between_numbers(self):
        self.assertEqual(norm("2000 — 546;"), "2000 − 546;")

    def test_hyphen_between_numbers_is_flagged_not_changed(self):
        lines, stats = normalize_lines([make_line("98 - 34;")])
        word = lines[0].words[1]
        self.assertEqual(word.text, "-")
        self.assertEqual(word.flags, ("suspect_operator",))
        self.assertEqual(stats["suspect_operator"], 1)

    def test_raw_text_and_bbox_preserved(self):
        line = make_line("Ha уроці")
        new = normalize_lines([line])[0][0]
        self.assertEqual(new.words[0].raw_text, "Ha")
        self.assertEqual(new.words[0].bbox, line.words[0].bbox)
        self.assertEqual(line.words[0].text, "Ha")          # оригінал не змінено
        self.assertIsNone(new.words[1].raw_text)           # незмінене слово — без raw_text

    def test_disable_rule(self):
        self.assertEqual(norm("Ha уроці", disabled=["latin_lookalike_word"]), "Ha уроці")

    def test_stats(self):
        _, stats = normalize_lines([make_line("Ha уроці -- далі 2000 — 546")])
        self.assertEqual(stats["latin_lookalike_word"], 1)
        self.assertEqual(stats["word_dash"], 1)
        self.assertEqual(stats["minus_between_numbers"], 1)


class HyphenationTests(unittest.TestCase):
    def test_join(self):
        lines = [make_line("три наступних натураль-", 0), make_line("них числа.", 25)]
        self.assertEqual(join_hyphenation(lines), 1)
        self.assertEqual(lines[0].text, "три наступних натуральних")
        self.assertEqual(lines[1].text, "числа.")
        self.assertEqual(lines[0].words[-1].raw_text, "натураль-|них")

    def test_join_with_punctuation(self):
        lines = [make_line("за Переяслав-", 0), make_line("ської, Київської", 25)]
        join_hyphenation(lines)
        self.assertEqual(lines[0].text, "за Переяславської,")

    def test_real_hyphen_kept(self):
        lines = [make_line("візьми будь-", 0), make_line("який предмет", 25)]
        join_hyphenation(lines)
        self.assertEqual(lines[0].text, "візьми будь-який")

    def test_capital_or_number_not_joined(self):
        lines = [make_line("слово-", 0), make_line("Київ", 25), make_line("2000 -", 50), make_line("546", 75)]
        self.assertEqual(join_hyphenation(lines), 0)

    def test_line_becomes_empty_and_is_dropped(self):
        lines, _ = normalize_lines([make_line("кож-", 0), make_line("ному", 25), make_line("стовпчику", 50)])
        self.assertEqual([ln.text for ln in lines], ["кожному", "стовпчику"])


class EnvFileTests(unittest.TestCase):
    def test_read_env_file(self):
        import tempfile
        from pathlib import Path
        from education.pdf_pipeline.config import PipelineConfig, read_env_file
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text("# коментар\nTESSERACT_CMD='C:\\\\Program Files\\\\t.exe'\n\nTESSDATA_PREFIX_BEST=C:/tessdata_best\nBAD LINE\n",
                           encoding="utf-8")
            values = read_env_file(env)
            self.assertEqual(values["TESSERACT_CMD"], "C:\\\\Program Files\\\\t.exe")
            self.assertEqual(values["TESSDATA_PREFIX_BEST"], "C:/tessdata_best")
            self.assertEqual(read_env_file(Path(tmp) / "nope"), {})


if __name__ == "__main__":
    unittest.main()
