"""Фронтенд (docs/frontend/PLAN.md): прапорці інтерфейсу в контексті шаблонів."""
from django.conf import settings
from django.template import engines
from django.contrib.auth.models import User
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from education.context import ui_flags


class UiFlagsContextProcessorTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/")

    def test_returns_new_ui_key(self):
        self.assertIn("NEW_UI", ui_flags(self.request))

    @override_settings(NEW_UI=True)
    def test_new_ui_on(self):
        self.assertIs(ui_flags(self.request)["NEW_UI"], True)

    @override_settings(NEW_UI=False)
    def test_new_ui_off(self):
        self.assertIs(ui_flags(self.request)["NEW_UI"], False)

    def test_new_ui_is_bool_in_settings(self):
        # NEW_UI=0 у .env має давати False, а не непорожній рядок "0"
        self.assertIsInstance(settings.NEW_UI, bool)

    def test_registered_and_visible_in_templates(self):
        template = engines["django"].from_string("{% if NEW_UI %}new{% else %}old{% endif %}")
        with self.settings(NEW_UI=True):
            self.assertEqual(template.render({}, self.request), "new")
        with self.settings(NEW_UI=False):
            self.assertEqual(template.render({}, self.request), "old")


class UiTokensPageTests(SimpleTestCase):
    """`/ui/tokens/` (фаза 1): вітрина токенів, лише при DEBUG."""

    @override_settings(DEBUG=True)
    def test_available_in_debug(self):
        response = self.client.get("/ui/tokens/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tokens.css")
        self.assertContains(response, "isl-5")
        # мінімум контрасту — з крапкою, бо його читає JS (українська локаль дала б «4,5»)
        self.assertContains(response, 'data-min="4.5"')

    @override_settings(DEBUG=False)
    def test_hidden_without_debug(self):
        self.assertEqual(self.client.get("/ui/tokens/").status_code, 404)


class TokensCssTests(SimpleTestCase):
    """tokens.css — єдине джерело кольорів (docs/frontend/PLAN.md, фаза 1)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from pathlib import Path
        static = Path(__file__).resolve().parent / "static" / "education" / "css"
        cls.static = static
        cls.tokens = (static / "tokens.css").read_text(encoding="utf-8")

    def test_every_token_shown_on_page_is_defined(self):
        from education.views_ui import CONTRAST_PAIRS, TOKEN_GROUPS
        names = {n for _, group in TOKEN_GROUPS for n, _ in group}
        names |= {n for fg, bg, _ in CONTRAST_PAIRS for n in (fg, bg)}
        missing = sorted(n for n in names if f"{n}:" not in self.tokens)
        self.assertEqual(missing, [])

    def test_five_island_pairs_and_classes(self):
        for n in range(1, 6):
            self.assertIn(f"--isl-{n}-acc:", self.tokens)
            self.assertIn(f"--isl-{n}-land:", self.tokens)
            self.assertIn(f".isl-{n} {{ --acc: var(--isl-{n}-acc); --land: var(--isl-{n}-land); }}", self.tokens)

    def test_new_ui_css_has_no_raw_colors(self):
        """Нові CSS-файли беруть кольори лише з токенів. Старі (map_ui.css, play.css) — до фаз 14/18."""
        import re
        legacy = {"tokens.css", "map_ui.css", "play.css"}
        for css in self.static.glob("*.css"):
            if css.name in legacy:
                continue
            raw = re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", css.read_text(encoding="utf-8"))
            self.assertEqual(raw, [], f"{css.name}: колір поза tokens.css")


class BaseTemplateTests(TestCase):
    """base.html і /ui/kit/ (фаза 2)."""

    @override_settings(DEBUG=True)
    def test_kit_available_in_debug(self):
        response = self.client.get("/ui/kit/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "education/base.html")

    @override_settings(DEBUG=False)
    def test_kit_hidden_without_debug(self):
        self.assertEqual(self.client.get("/ui/kit/").status_code, 404)

    @override_settings(DEBUG=True)
    def test_base_skeleton(self):
        html = self.client.get("/ui/kit/").content.decode()
        self.assertIn('<html lang="uk">', html)
        self.assertIn("viewport-fit=cover", html)
        self.assertIn('<title>UI-кіт · Математичний світ</title>', html)
        # skip link — перший елемент body, веде на <main id="main">
        body = html.split("<body", 1)[1]
        self.assertLess(body.index('class="skip-link"'), body.index("<svg"))
        self.assertIn('href="#main"', body)
        self.assertIn('<main id="main"', body)
        self.assertIn("csrfmiddlewaretoken", body)
        # порядок CSS: шрифти → токени → основа → стилі сторінки
        order = [html.index(f) for f in ("fonts.css", "tokens.css", "base.css", "components.css", "ui-dev.css")]
        self.assertEqual(order, sorted(order))

    def test_no_google_fonts_in_new_templates(self):
        from pathlib import Path
        tpl = Path(__file__).resolve().parent / "templates" / "education"
        for name in ("base.html", "ui_kit.html", "ui_tokens.html"):
            self.assertNotIn("fonts.googleapis.com", (tpl / name).read_text(encoding="utf-8"), name)

    def test_every_font_face_file_exists(self):
        import re
        from pathlib import Path
        static = Path(__file__).resolve().parent / "static" / "education"
        css = (static / "css" / "fonts.css").read_text(encoding="utf-8")
        urls = re.findall(r"url\('\.\./fonts/([^']+)'\)", css)
        self.assertEqual(len(urls), 12)  # Unbounded 2 ваги + Nunito 4 ваги, × cyrillic/latin
        missing = [u for u in urls if not (static / "fonts" / u).exists()]
        self.assertEqual(missing, [])


class IconTagTests(TestCase):
    """{% icon %} і спрайт _icons.html (фаза 3)."""

    def render(self, src, ctx=None):
        return engines["django"].from_string("{% load ui %}" + src).render(ctx or {})

    def test_decorative_icon(self):
        html = self.render('{% icon "star" size=18 %}')
        self.assertIn('<use href="#i-star"/>', html)
        self.assertIn('width="18" height="18"', html)
        self.assertIn('aria-hidden="true"', html)
        self.assertIn('class="icon icon--star"', html)

    def test_label_adds_title_and_role(self):
        html = self.render('{% icon "lock" label="Урок закрито" %}')
        self.assertIn('role="img"', html)
        self.assertIn("<title>Урок закрито</title>", html)
        self.assertNotIn("aria-hidden", html)

    def test_extra_class_and_default_size(self):
        html = self.render('{% icon "bolt" class="icon--points" %}')
        self.assertIn('class="icon icon--bolt icon--points"', html)
        self.assertIn('width="20"', html)

    def test_label_from_data_is_escaped(self):
        # назва уроку з БД у підписі не має ламати розмітку
        html = self.render('{% icon "star" label=title %}', {"title": '<b>"x"'})
        self.assertIn("&lt;b&gt;&quot;x&quot;", html)
        self.assertNotIn("<b>", html)

    def test_unknown_icon_fails_loudly(self):
        from django.template import TemplateSyntaxError
        with self.assertRaises(TemplateSyntaxError):
            self.render('{% icon "unicorn" %}')

    def test_sprite_has_exactly_the_known_icons(self):
        import re
        from pathlib import Path
        from education.templatetags.ui import ICONS
        sprite = (Path(__file__).resolve().parent / "templates" / "education" / "_icons.html").read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'<symbol id="i-([a-z-]+)"', sprite)), set(ICONS))

    @override_settings(DEBUG=True)
    def test_kit_shows_every_icon(self):
        from education.templatetags.ui import ICONS
        html = self.client.get("/ui/kit/").content.decode()
        for name in ICONS:
            self.assertIn(f'href="#i-{name}"', html)


class ComponentIncludeTests(SimpleTestCase):
    """_stars.html і _progress.html (фаза 4)."""

    def render(self, src, ctx=None):
        return engines["django"].from_string(src).render(ctx or {})

    def test_stars_two_of_three(self):
        html = self.render('{% include "education/_stars.html" with count=2 size=20 %}')
        self.assertEqual(html.count("star--on"), 2)
        self.assertEqual(html.count("star--off"), 1)
        self.assertIn('aria-label="2 з 3 зірок"', html)
        self.assertIn('width="20"', html)

    def test_stars_defaults_and_outline(self):
        html = self.render('{% include "education/_stars.html" with outline=True %}')
        self.assertEqual(html.count("star--off"), 3)
        self.assertIn("stars--outline", html)
        self.assertIn('width="14"', html)
        self.assertIn('aria-label="0 з 3 зірок"', html)

    def test_stars_from_variable(self):
        html = self.render('{% include "education/_stars.html" with count=lesson.stars %}', {"lesson": {"stars": 3}})
        self.assertEqual(html.count("star--on"), 3)

    def test_progress_percent_and_aria(self):
        html = self.render('{% include "education/_progress.html" with value=6 max=17 label="Розв’язано 6 з 17" size="md" %}')
        self.assertIn("--p: 35%", html)  # 6/17 = 35.3 %
        self.assertIn('role="progressbar"', html)
        self.assertIn('aria-valuenow="6"', html)
        self.assertIn('aria-valuemax="17"', html)
        self.assertIn("progress--md", html)

    def test_progress_empty_lesson(self):
        html = self.render('{% include "education/_progress.html" with value=0 max=0 %}')
        self.assertIn("--p: 0%", html)


class TopbarAndNavTests(TestCase):
    """Верхня панель, нижня навігація, заглушки «Прогрес»/«Профіль» (фаза 5)."""

    @classmethod
    def setUpTestData(cls):
        from education.models import Grade, Subject, Textbook
        math = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})[0]
        g5 = Grade.objects.create(subject=math, number=5, name_uk="5 клас")
        Grade.objects.create(subject=math, number=6, name_uk="6 клас")
        Textbook.objects.create(subject=math, grade=g5, profile_code="math_merzlyak_5", title="Математика. 5 клас",
                                author="Мерзляк А. Г., Полонський В. Б., Якір М. С.", pdf_sha256="x" * 64)

    def test_guest_sees_login_with_next(self):
        html = self.client.get("/progress/").content.decode()
        self.assertIn('class="topbar"', html)
        self.assertIn("Увійти", html)
        self.assertIn("/accounts/login/?next=/progress/", html)
        self.assertNotIn("Вийти", html)

    def test_user_sees_name_and_logout_form(self):
        self.client.force_login(User.objects.create_user("anita", password="pw-12345678"))
        html = self.client.get("/progress/").content.decode()
        self.assertIn("anita", html)
        self.assertIn('action="/accounts/logout/"', html)
        self.assertNotIn(">Увійти<", html)

    def test_grade_tabs_with_short_author(self):
        html = self.client.get("/progress/").content.decode()
        self.assertIn("5 клас · Мерзляк", html)
        self.assertIn(">6 клас<", html)  # підручника 6 класу в БД ще немає — без автора

    def test_active_grade_tab(self):
        from django.template import Context, Template
        request = RequestFactory().get("/grades/5/")
        request.user = User()
        html = Template("{% load ui %}{% topbar %}").render(Context({"request": request, "current_grade": 5}))
        self.assertIn('aria-current="page">5 клас · Мерзляк', html)
        self.assertIn("5 клас<svg", html.replace("\n", ""))  # кнопка «5 клас ▾» на телефоні

    def test_player_chips_are_filled_by_js(self):
        html = self.client.get("/progress/").content.decode()
        for key in ("stars", "points", "streak", "streak_word"):
            self.assertIn(f'data-me="{key}"', html)
        self.assertIn("education/js/me.js", html)
        self.assertIn('title="Серія днів"', html)

    def test_bottom_nav_marks_active_tab(self):
        html = self.client.get("/profile/").content.decode()
        nav = html.split('class="bottom-nav"', 1)[1]
        self.assertIn('href="/profile/" aria-current="page"', nav)
        self.assertNotIn('href="/progress/" aria-current="page"', nav)

    def test_stub_pages(self):
        self.assertContains(self.client.get("/progress/"), "Скоро тут буде твій прогрес")
        guest = self.client.get("/profile/")
        self.assertContains(guest, "Зареєструватися")
        self.client.force_login(User.objects.create_user("olia", password="pw-12345678"))
        self.assertContains(self.client.get("/profile/"), "olia")


class MockContractTests(SimpleTestCase):
    """Моки фронтенду = контракт із бекендом (фаза 6): tools/frontend/check_mocks.py."""

    def test_mocks_match_contract(self):
        import importlib.util
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / "tools" / "frontend" / "check_mocks.py"
        spec = importlib.util.spec_from_file_location("check_mocks", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.check_all(), [])

    def test_checker_catches_broken_lesson(self):
        import importlib.util
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / "tools" / "frontend" / "check_mocks.py"
        spec = importlib.util.spec_from_file_location("check_mocks", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        broken = {"grade": 5, "subject": "math", "textbook": None, "current": None, "sections": [
            {"id": 1, "number": 1, "title": "Р", "paragraphs": [{"id": 1, "number": 1, "title": "§", "items": [
                {"id": 1, "number": 1, "title": "У", "state": "done", "stars": 4, "solved": 0, "total": 0,
                 "tasks": {"auto": 0, "ai": 0}, "blocks": ["magic"], "map": {"x": None, "y": None}}]}]}]}
        errors = " | ".join(module.check_grade_map(broken, "test"))
        self.assertIn("stars поза 0–3", errors)
        self.assertIn("має бути `soon`", errors)
        self.assertIn("невідомі blocks", errors)


class UiApiPageTests(TestCase):
    @override_settings(DEBUG=True)
    def test_available_in_debug(self):
        response = self.client.get("/ui/api/")
        self.assertContains(response, "education/js/ui-api.js")

    @override_settings(DEBUG=False)
    def test_hidden_without_debug(self):
        self.assertEqual(self.client.get("/ui/api/").status_code, 404)


class GradeMapPageTests(TestCase):
    """`/grades/<n>/` — сторінка мапи (фаза 8)."""

    @classmethod
    def setUpTestData(cls):
        from education.models import Grade, Subject
        math = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})[0]
        Grade.objects.create(subject=math, number=5, name_uk="5 клас")

    def test_page_renders_map_shell(self):
        response = self.client.get("/grades/5/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('data-grade="5"', html)
        self.assertIn("education/js/map.js", html)
        self.assertIn("education/css/map.css", html)
        self.assertIn("<title>Мапа 5 класу · Математичний світ</title>", html)
        for state in ("mapLoading", "mapError", "mapEmpty", "lessonPanel", "mapNodes", "tpl-lesson-panel", "tpl-island-row"):
            self.assertIn(f'id="{state}"', html)
        # панель підписується на події мапи раніше, ніж мапа їх надсилає
        self.assertLess(html.index("js/lesson-panel.js"), html.index("js/map.js"))

    def test_grade_tab_active_and_links_to_maps(self):
        html = self.client.get("/grades/5/").content.decode()
        self.assertIn('href="/grades/5/" aria-current="page"', html)

    def test_unknown_grade_404(self):
        self.assertEqual(self.client.get("/grades/99/").status_code, 404)

    def test_old_sections_url_still_works(self):
        # старі сторінки живуть до фази 18; /grades/<id>/sections/ не конфліктує з /grades/<n>/
        from django.urls import resolve
        self.assertEqual(resolve("/grades/3/sections/").url_name, "section_list")
        self.assertEqual(resolve("/grades/5/").url_name, "grade_map_page")


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

    @override_settings(NEW_UI=False)
    def test_old_list_without_new_ui(self):
        html = self.client.get("/").content.decode()
        self.assertNotIn("Обери свій світ", html)
        self.assertIn("Оберіть клас", html)

    def test_uk_plural_filter(self):
        from education.templatetags.ui import uk_plural
        forms = "острів,острови,островів"
        self.assertEqual([uk_plural(n, forms) for n in (1, 2, 5, 11, 21, 22, 0)],
                         ["острів", "острови", "островів", "островів", "острів", "острови", "островів"])


class LessonPageTests(TestCase):
    """`/items/<id>/` у новому UI — теорія й вправи уроку (фаза 13)."""

    @classmethod
    def setUpTestData(cls):
        from education.models import (Answer, ContentBlock, Exercise, Grade, Item, Paragraph, Section,
                                      SubExercise, Subject, Textbook)
        math = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})[0]
        g5 = Grade.objects.create(subject=math, number=5, name_uk="5 клас")
        tb = Textbook.objects.create(subject=math, grade=g5, profile_code="m5", title="М5", pdf_sha256="b" * 64)
        s1 = Section.objects.create(grade=g5, number=1, name_uk="Розділ I. Натуральні числа")
        Paragraph.objects.create(section=s1, number=1, name_uk="§ 1. Натуральні числа")
        p2 = Paragraph.objects.create(section=s1, number=2, name_uk="§ 2. Додавання і віднімання")
        cls.item = Item.objects.create(paragraph=p2, number=7, content="7. Додавання натуральних чисел")
        ContentBlock.objects.create(item=cls.item, block_type="theory", order=1, text="Сума не змінюється.")
        block = ContentBlock.objects.create(item=cls.item, block_type="exercise", order=2)
        ex = Exercise.objects.create(textbook=tb, block=block, number=153, condition="Обчисли:", difficulty="high")
        sub = SubExercise.objects.create(exercise=ex, number="1", order=1, text="25 + 17")
        Answer.objects.create(exercise=ex, subexercise=sub, kind="book", text="42")

    def test_new_lesson_page(self):
        html = self.client.get(f"/items/{self.item.id}/").content.decode()
        self.assertIn("education/css/lesson.css", html)
        self.assertIn('class="page-lesson isl-2"', html)                # §2 → другий колір острова
        self.assertIn("Додавання натуральних чисел</h1>", html)          # без «7.» на початку
        self.assertIn(f'href="/grades/5/#lesson-{self.item.id}"', html)  # крихти й «На мапу»
        self.assertIn("Теорія", html)
        self.assertIn("Сума не змінюється.", html)
        self.assertIn("Вправи", html)
        self.assertIn('lex__diff--high">Високий<', html)
        self.assertIn("25 + 17", html)

    def test_answers_only_for_staff(self):
        html = self.client.get(f"/items/{self.item.id}/").content.decode()
        self.assertNotIn("Відповідь (бачить лише вчитель)", html)
        self.assertNotIn(">1) 42", html)
        staff = User.objects.create_user("teacher", password="pw-12345678", is_staff=True)
        self.client.force_login(staff)
        html = self.client.get(f"/items/{self.item.id}/").content.decode()
        self.assertIn("Відповідь (бачить лише вчитель)", html)
        self.assertIn("1) 42", html)

    @override_settings(NEW_UI=False)
    def test_old_page_without_new_ui(self):
        html = self.client.get(f"/items/{self.item.id}/").content.decode()
        self.assertNotIn("lesson.css", html)
        self.assertIn("map_ui.css", html)

    def test_block_filters(self):
        from education.templatetags.ui import block_icon, block_name, difficulty_name
        self.assertEqual(block_name("self_check"), "Перевір себе")       # без «(❓)» з моделі
        self.assertEqual(block_icon("wise_owl"), "owl")
        self.assertEqual(difficulty_name("olympiad"), "Олімпіадний")
        self.assertEqual(difficulty_name("unknown"), "")


class ReflowFilterTests(SimpleTestCase):
    def test_joins_broken_lines(self):
        from education.templatetags.ui import reflow
        out = reflow("Якщо ви доторкнетеся\nдо аркуша.\nТочки по-\nзначають <b>\n1. Перше")
        self.assertEqual(out, "<p>Якщо ви доторкнетеся до аркуша.</p><p>Точки позначають &lt;b&gt;</p><p>1. Перше</p>")
