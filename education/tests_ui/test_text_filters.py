from django.test import SimpleTestCase


class ReflowFilterTests(SimpleTestCase):
    def test_joins_broken_lines(self):
        from education.templatetags.ui import reflow
        out = reflow("Якщо ви доторкнетеся\nдо аркуша.\nТочки по-\nзначають <b>\n1. Перше")
        self.assertEqual(out, "<p>Якщо ви доторкнетеся до аркуша.</p><p>Точки позначають &lt;b&gt;</p><p>1. Перше</p>")


class FigurePlacementTests(SimpleTestCase):
    def test_refs(self):
        from education.templatetags.ui import figure_refs
        self.assertEqual(figure_refs("лінійки (рис. 5). На рисунку 6 і 7"), ["5", "6", "7"])
        self.assertEqual(figure_refs("(рис. 3–5)"), ["3", "4", "5"])
        self.assertEqual(figure_refs("(рис. 7, б)"), ["7"])
        self.assertEqual(figure_refs("рисунок 10, 4 см"), ["10"])

    def test_figure_after_first_mention_only(self):
        from types import SimpleNamespace as NS
        from education.templatetags.ui import text_with_figures
        fig = type("F", (), {"number": "3", "image": NS(url="/m/f3.png"), "__str__": lambda s: "Рис. 3"})()
        used = set()
        html = text_with_figures("Точка (рис. 3).\nЩе раз рис. 3.\nА рис. 9 немає.", {"3": fig}, used)
        self.assertEqual(html.count("<figure"), 1)
        self.assertTrue(html.startswith("<p>Точка (рис. 3).</p><figure"))
        self.assertEqual(used, {"3"})
        self.assertNotIn("f3.png", text_with_figures("Знову рис. 3.", {"3": fig}, used))

    def test_stray_caption_removed(self):
        from education.templatetags.ui import paragraphs
        self.assertEqual(paragraphs("Точка і відрізок — приклади геометрич- Рис. 3 них фігур."),
                         ["Точка і відрізок — приклади геометричних фігур."])
        self.assertEqual(paragraphs("лінія Рис. 4 яку"), ["лінія яку"])
        self.assertEqual(paragraphs("Дивись (рис. 4)."), ["Дивись (рис. 4)."])
