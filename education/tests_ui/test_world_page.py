from django.test import TestCase


class WorldPageTests(TestCase):
    """`/` — «Світ» (фаза 12)."""

    @classmethod
    def setUpTestData(cls):
        from education.models import Grade, Item, Paragraph, Section, Subject, Textbook
        math = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})[0]
        g5 = Grade.objects.create(subject=math, number=5, name_uk="5 клас")
        g6 = Grade.objects.create(subject=math, number=6, name_uk="6 клас")
        Textbook.objects.create(subject=math, grade=g5, profile_code="m5", title="М5", author="Мерзляк А. Г.",
                                year=2018, pdf_sha256="a" * 64)
        s1 = Section.objects.create(grade=g5, number=1, name_uk="Розділ I. Натуральні числа")
        Section.objects.create(grade=g5, number=2, name_uk="Розділ II. Дроби")
        p1 = Paragraph.objects.create(section=s1, number=1, name_uk="§ 1. Натуральні числа")
        for n in range(1, 4):
            Item.objects.create(paragraph=p1, number=n, content=f"Урок {n}")
        s6 = Section.objects.create(grade=g6, number=1, name_uk="Розділ 1. Подільність")
        Paragraph.objects.create(section=s6, number=1, name_uk="§ 1. Дільники")

    def test_world_cards(self):
        html = self.client.get("/").content.decode()
        self.assertIn("Обери свій світ", html)
        self.assertIn('href="/grades/5/"', html)
        self.assertIn("Мерзляк, 2018 · 2 острови · 3 уроки", html)
        self.assertIn("1 острів · 1 параграф", html)          # 6 клас: урок = §, без підручника в БД
        self.assertIn("7–9 клас", html)
        self.assertIn("education/js/world.js", html)
        self.assertIn("Українська мова · скоро", html)


    def test_uk_plural_filter(self):
        from education.templatetags.ui import uk_plural
        forms = "острів,острови,островів"
        self.assertEqual([uk_plural(n, forms) for n in (1, 2, 5, 11, 21, 22, 0)],
                         ["острів", "острови", "островів", "островів", "острів", "острови", "островів"])
