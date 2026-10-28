"""Фронтенд (docs/frontend/PLAN.md): сторінки нового інтерфейсу, шаблонні теги, моки, CSS."""
from django.contrib.auth.models import User
from django.template import engines
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from education.context import ui_debug


class UiDebugContextProcessorTests(SimpleTestCase):
    """`UI_DEBUG` — замість прапорця NEW_UI (прибрано у фазі 18)."""

    def test_follows_debug(self):
        request = RequestFactory().get("/")
        with self.settings(DEBUG=True):
            self.assertIs(ui_debug(request)["UI_DEBUG"], True)
            self.assertEqual(engines["django"].from_string("{% if UI_DEBUG %}d{% endif %}").render({}, request), "d")
        with self.settings(DEBUG=False):
            self.assertIs(ui_debug(request)["UI_DEBUG"], False)

    def test_new_ui_flag_is_gone(self):
        from django.conf import settings
        self.assertFalse(hasattr(settings, "NEW_UI"))


class UiTokensPageTests(TestCase):
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
        """Усі CSS-файли беруть кольори лише з токенів (старі map_ui.css і play.css видалено у фазі 18)."""
        import re
        legacy = {"tokens.css"}
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
        self.assertIn('<html lang="uk"', html)
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
    """Верхня панель, нижня навігація (фаза 5)."""

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

    def test_profile_account_actions(self):
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


    def test_uk_plural_filter(self):
        from education.templatetags.ui import uk_plural
        forms = "острів,острови,островів"
        self.assertEqual([uk_plural(n, forms) for n in (1, 2, 5, 11, 21, 22, 0)],
                         ["острів", "острови", "островів", "островів", "острів", "острови", "островів"])


class ProgressPageTests(TestCase):
    """`/progress/` — зірки по параграфах і бали за тиждень (фаза 20, беклог FE-0630)."""

    @classmethod
    def setUpTestData(cls):
        from education.models import Grade, Subject, Textbook
        math = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})[0]
        g5 = Grade.objects.create(subject=math, number=5, name_uk="5 клас")
        Textbook.objects.create(subject=math, grade=g5, profile_code="m5", title="М5",
                                author="Мерзляк А. Г.", year=2018, pdf_sha256="e" * 64)
        Grade.objects.create(subject=math, number=6, name_uk="6 клас")

    def test_renders_grade_cards_and_chart(self):
        html = self.client.get("/progress/").content.decode()
        self.assertIn('data-grade="5"', html)
        self.assertIn('data-grade="6"', html)
        self.assertIn("Мерзляк, 2018", html)
        self.assertIn('data-me="history"', html)
        self.assertIn('id="tpl-progress-row"', html)
        self.assertIn("education/js/progress.js", html)

    def test_api_me_has_week_history(self):
        data = self.client.get("/api/me/").json()
        self.assertEqual(len(data["history"]), 7)
        self.assertEqual({tuple(sorted(d)) for d in data["history"]}, {("date", "points")})
        self.assertEqual(sum(d["points"] for d in data["history"]), 0)


class ProfilePageTests(TestCase):
    """`/profile/` — ім’я, серія днів, вхід/вихід (фаза 20, беклог FE-0631)."""

    def test_guest_sees_login_and_signup(self):
        html = self.client.get("/profile/").content.decode()
        self.assertIn('data-me="streak"', html)
        self.assertIn('data-me="streak_word"', html)
        self.assertIn("education/js/me.js", html)
        self.assertIn("Гість", html)
        self.assertIn('href="/accounts/login/?next=/profile/"', html)
        self.assertIn("Зареєструватися", html)
        self.assertNotIn("Вийти", html)

    def test_authenticated_user_sees_name_and_logout(self):
        self.client.force_login(User.objects.create_user("olia", password="pw-12345678"))
        html = self.client.get("/profile/").content.decode()
        self.assertIn("olia", html)
        self.assertIn('action="/accounts/logout/"', html)
        self.assertNotIn("Увійти", html)
        self.assertNotIn("Зареєструватися", html)

    def test_theme_picker(self):
        """Беклог FE-0636: перемикач теми — ті самі три варіанти, що знає js/theme.js."""
        html = self.client.get("/profile/").content.decode()
        for value in ("dark", "light", "system"):
            self.assertIn(f'data-theme-pick="{value}"', html)
        self.assertIn('id="themePicker"', html)
        self.assertIn("education/js/profile-settings.js", html)

    def test_sound_toggle(self):
        """Беклог FE-0637: вимикач звуку правильної/неправильної відповіді."""
        html = self.client.get("/profile/").content.decode()
        self.assertIn('id="profileSoundToggle"', html)
        self.assertIn("data-sound-label", html)
        self.assertIn("education/js/profile-settings.js", html)


class ThemeNoFlashScriptTests(TestCase):
    """Інлайн-скрипт у <head> (фаза 20, FE-0636): виставляє data-theme до першого малювання."""

    def test_every_page_has_the_inline_init(self):
        html = self.client.get("/").content.decode()
        self.assertIn("localStorage.getItem(\"mw_theme\")", html)
        self.assertIn('document.documentElement.dataset.theme = t', html)
        # до будь-якого <link rel="stylesheet">, щоб застосувалось раніше CSS
        self.assertLess(html.index("mw_theme"), html.index('rel="stylesheet"'))


class ServiceWorkerTests(TestCase):
    """`/sw.js` (фаза 20, беклог FE-0638): офлайн-кеш каркасу й завдань уроку."""

    def test_served_at_root_for_full_scope(self):
        """Поза /static/ — інакше область дії service worker обмежилась би самим /static/."""
        resp = self.client.get("/sw.js")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/javascript")

    def test_never_caches_answer_checks(self):
        body = self.client.get("/sw.js").content.decode()
        self.assertIn('request.method !== "GET"', body)   # POST (перевірка відповіді) не чіпаємо

    def test_registration_script_on_every_page(self):
        html = self.client.get("/").content.decode()
        self.assertIn("education/js/sw-register.js", html)


class ManifestTests(TestCase):
    """PWA-маніфест — «Додати на головний екран» (фаза 20, беклог FE-0639)."""

    def test_linked_on_every_page(self):
        html = self.client.get("/").content.decode()
        self.assertIn('rel="manifest" href="/static/education/manifest.webmanifest"', html)
        self.assertIn('rel="apple-touch-icon" href="/static/education/img/apple-touch-icon.png"', html)

    def test_manifest_is_valid_and_icons_exist(self):
        import json
        from pathlib import Path
        static = Path(__file__).resolve().parent / "static" / "education"
        data = json.loads((static / "manifest.webmanifest").read_text(encoding="utf-8"))
        for key in ("name", "short_name", "start_url", "scope", "display", "background_color",
                    "theme_color", "icons"):
            self.assertIn(key, data)
        self.assertGreaterEqual(len(data["icons"]), 2)
        purposes = set()
        for icon in data["icons"]:
            path = static / icon["src"].removeprefix("/static/education/")
            self.assertTrue(path.exists(), f"{icon['src']} не існує")
            purposes.add(icon.get("purpose", "any"))
        self.assertIn("maskable", purposes)   # хоч одна іконка для Android, не лише "any"

    def test_apple_touch_icon_exists(self):
        from pathlib import Path
        path = Path(__file__).resolve().parent / "static" / "education" / "img" / "apple-touch-icon.png"
        self.assertTrue(path.exists())


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
        self.assertIn('diff--high">Високий<', html)
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


    def test_block_filters(self):
        from education.templatetags.ui import block_icon, block_name, difficulty_name
        self.assertEqual(block_name("self_check"), "Перевір себе")       # без «(❓)» з моделі
        self.assertEqual(block_icon("wise_owl"), "owl")
        self.assertEqual(difficulty_name("olympiad"), "Олімпіадний")
        self.assertEqual(difficulty_name("unknown"), "")

    def test_german_cookie_falls_back_to_ukrainian_when_translation_missing(self):
        """FE-0642: *_de порожнє для цього уроку (0 з 75 параграфів перекладено) — запасний варіант uk."""
        self.client.cookies["mw_lang"] = "de"
        html = self.client.get(f"/items/{self.item.id}/").content.decode()
        self.assertIn("Додавання натуральних чисел</h1>", html)

    def test_german_cookie_uses_translation_when_present(self):
        self.item.content_de = "7. Addition natürlicher Zahlen"
        self.item.save()
        self.client.cookies["mw_lang"] = "de"
        html = self.client.get(f"/items/{self.item.id}/").content.decode()
        self.assertIn("Addition natürlicher Zahlen</h1>", html)

    def test_no_cookie_stays_ukrainian_even_with_translation_present(self):
        self.item.content_de = "7. Addition natürlicher Zahlen"
        self.item.save()
        html = self.client.get(f"/items/{self.item.id}/").content.decode()
        self.assertIn("Додавання натуральних чисел</h1>", html)


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


class PlayPageTests(TestCase):
    """`/play/item|paragraph/<id>/` у новому UI — екран гри (фаза 14). Бекенд гри не змінюємо."""

    @classmethod
    def setUpTestData(cls):
        from education.models import (Answer, ContentBlock, Exercise, Grade, Item, Paragraph, Section,
                                      SubExercise, Subject, Textbook)
        math = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})[0]
        g5 = Grade.objects.create(subject=math, number=5, name_uk="5 клас")
        tb = Textbook.objects.create(subject=math, grade=g5, profile_code="m5", title="М5", pdf_sha256="c" * 64)
        s1 = Section.objects.create(grade=g5, number=1, name_uk="Розділ I")
        p1 = Paragraph.objects.create(section=s1, number=1, name_uk="§ 1. Натуральні числа")
        cls.p2 = Paragraph.objects.create(section=s1, number=2, name_uk="§ 2. Шкали")   # без пунктів → § як урок
        cls.i1 = Item.objects.create(paragraph=p1, number=1, content="1. Ряд натуральних чисел")
        cls.i2 = Item.objects.create(paragraph=p1, number=2, content="2. Цифри")        # без вправ

        def playable(**where):
            block = ContentBlock.objects.create(block_type="exercise", order=1, **where)
            ex = Exercise.objects.create(textbook=tb, block=block, number=10, condition="Обчисли:")
            sub = SubExercise.objects.create(exercise=ex, number="1", order=1, text="2 + 2")
            Answer.objects.create(exercise=ex, subexercise=sub, kind="book", text="4")

        playable(item=cls.i1)
        playable(paragraph=cls.p2)

    def test_new_play_page(self):
        html = self.client.get(f"/play/item/{self.i1.id}/").content.decode()
        self.assertIn("education/css/play.css", html)
        self.assertIn("education/js/play.js", html)
        self.assertIn('class="page-play isl-1"', html)
        self.assertNotIn('class="topbar', html)                       # повноекранна: без верхньої панелі
        self.assertNotIn('class="bottom-nav', html)
        self.assertIn(f'data-map="/grades/5/#lesson-{self.i1.id}"', html)
        self.assertIn('aria-label="Вийти з уроку"', html)
        self.assertIn("Урок 1 · Ряд натуральних чисел", html)
        self.assertIn(f'data-api="/api/play/items/{self.i1.id}/"', html)
        self.assertIn('id="soundToggle"', html)                           # беклог FE-0637
        self.assertIn('id="offlineBanner"', html)                         # беклог FE-0638
        # наступний урок з завданнями — § 2 (пункт 2 без вправ пропускаємо)
        self.assertIn(f'data-next="/play/paragraph/{self.p2.id}/"', html)

    def test_paragraph_lesson(self):
        html = self.client.get(f"/play/paragraph/{self.p2.id}/").content.decode()
        self.assertIn('class="page-play isl-2"', html)
        self.assertIn("§2 · Шкали", html)
        self.assertIn(f'data-map="/grades/5/#lesson-p{self.p2.id}"', html)
        self.assertIn('data-next=""', html)                            # останній урок класу


    def test_no_raw_colors_in_play_css(self):
        import re
        from pathlib import Path
        css = (Path(__file__).parent / "static/education/css/play.css").read_text(encoding="utf-8")
        self.assertFalse(re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", css))


class AuthPagesTests(TestCase):
    """Вхід і реєстрація в новому дизайні (фаза 15)."""

    def test_login_page(self):
        html = self.client.get("/accounts/login/?next=/grades/5/").content.decode()
        self.assertIn("education/css/auth.css", html)
        self.assertIn('class="page-auth"', html)
        self.assertNotIn('class="topbar', html)
        self.assertNotIn('class="bottom-nav', html)
        self.assertIn('<label class="field__label" for="id_username">', html)
        self.assertIn('autocomplete="current-password"', html)              # віджет Django збережено
        self.assertIn('name="next" value="/grades/5/"', html)
        self.assertIn('href="/accounts/signup/?next=/grades/5/"', html)      # next не губиться

    def test_failed_login_shows_error(self):
        User.objects.create_user("olia", password="pw-12345-long")
        html = self.client.post("/accounts/login/", {"username": "olia", "password": "wrong"}).content.decode()
        self.assertIn('class="auth__error" role="alert"', html)
        self.assertIn("введіть правильні", html)

    def test_login_goes_to_next(self):
        User.objects.create_user("olia", password="pw-12345-long")
        resp = self.client.post("/accounts/login/", {"username": "olia", "password": "pw-12345-long", "next": "/grades/5/"})
        self.assertRedirects(resp, "/grades/5/", fetch_redirect_response=False)

    def test_signup_field_errors_and_rules(self):
        html = self.client.get("/accounts/signup/").content.decode()
        self.assertIn("<summary>Вимоги до пароля</summary>", html)
        self.assertIn("Літери, цифри та символи", html)
        html = self.client.post("/accounts/signup/", {"username": "", "password1": "a", "password2": "b"}).content.decode()
        self.assertIn('aria-invalid="true"', html)
        self.assertIn('class="field__error" id="id_username-err"', html)
        self.assertIn('aria-describedby="id_username-err"', html)
        self.assertNotIn('id="id_username-hint"', html)                  # підказку замінює помилка

    def test_signup_keeps_guest_and_goes_home(self):
        from education.models import Player
        session = self.client.session
        session.save()
        guest = Player.objects.create(session_key=session.session_key, points=5)
        session["player_id"] = guest.pk          # так гравця-гостя запам’ятовує game.get_player
        session.save()
        resp = self.client.post("/accounts/signup/", {"username": "petryk", "password1": "Very-long-pass-77",
                                                      "password2": "Very-long-pass-77"})
        self.assertRedirects(resp, "/", fetch_redirect_response=False)
        self.assertEqual(Player.objects.get(user__username="petryk").points, 5)

    def test_signup_next_only_local(self):
        data = {"username": "ivas", "password1": "Very-long-pass-77", "password2": "Very-long-pass-77"}
        resp = self.client.post("/accounts/signup/", {**data, "next": "https://evil.example/"})
        self.assertRedirects(resp, "/", fetch_redirect_response=False)
        self.client.logout()
        resp = self.client.post("/accounts/signup/?next=/grades/5/", {**data, "username": "ivas2"})
        self.assertRedirects(resp, "/grades/5/", fetch_redirect_response=False)


class PolishTests(TestCase):
    """Доступність і дрібниці (фаза 16)."""

    @classmethod
    def setUpTestData(cls):
        from education.models import Grade, Subject
        math = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})[0]
        Grade.objects.create(subject=math, number=5, name_uk="5 клас")

    def test_favicon_and_og(self):
        html = self.client.get("/").content.decode()
        self.assertIn('rel="icon" href="/static/education/img/favicon.svg"', html)
        self.assertIn('property="og:title"', html)
        self.assertIn('name="description"', html)

    def test_chips_have_text_labels(self):
        html = self.client.get("/").content.decode()
        for label in ("Зірки: ", "Бали: ", "Серія: "):
            self.assertIn(f'<span class="visually-hidden">{label}</span>', html)

    def test_map_text_alternative(self):
        html = self.client.get("/grades/5/").content.decode()
        self.assertIn('id="lessonList" aria-label="Усі уроки списком"', html)
        self.assertIn('aria-describedby="nodesHelp"', html)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
    def test_404_page(self):
        resp = self.client.get("/nema-takoi-storinky/")
        self.assertEqual(resp.status_code, 404)
        html = resp.content.decode()
        self.assertIn("Тут лише море", html)
        self.assertIn('href="/"', html)
        self.assertIn('lang="uk"', html)

    def test_500_is_static(self):
        from pathlib import Path
        html = (Path(__file__).parent / "templates/500.html").read_text(encoding="utf-8")
        self.assertNotIn("{%", html)
        self.assertNotIn("{{", html)
        self.assertIn('lang="uk"', html)
        self.assertIn('href="/"', html)


class RealApiTests(TestCase):
    """Перехід на реальний API (фаза 17)."""

    def test_debug_flag_for_mocks(self):
        with self.settings(DEBUG=True):
            self.assertIn('<html lang="uk" data-debug="1">', self.client.get("/progress/").content.decode())
        with self.settings(DEBUG=False):
            self.assertIn('<html lang="uk">', self.client.get("/progress/").content.decode())


class ParagraphPageAndRedirectTests(TestCase):
    """Фаза 18: сторінка § замість старого списку пунктів; старі адреси — 301 на мапу."""

    @classmethod
    def setUpTestData(cls):
        from education.models import (ContentBlock, Exercise, Grade, Item, Paragraph, Section, SubExercise,
                                      Answer, Subject, Textbook)
        math = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})[0]
        cls.g5 = Grade.objects.create(subject=math, number=5, name_uk="5 клас")
        tb = Textbook.objects.create(subject=math, grade=cls.g5, profile_code="m5", title="М5", pdf_sha256="d" * 64)
        cls.s1 = Section.objects.create(grade=cls.g5, number=1, name_uk="Розділ I")
        cls.p1 = Paragraph.objects.create(section=cls.s1, number=1, name_uk="§ 1. Натуральні числа")
        cls.p2 = Paragraph.objects.create(section=cls.s1, number=2, name_uk="§ 2. Шкали")      # § як урок
        cls.i1 = Item.objects.create(paragraph=cls.p1, number=1, content="1. Ряд натуральних чисел")
        ContentBlock.objects.create(paragraph=cls.p1, block_type="summary", order=1, text="Головне: числа 1, 2, 3.")
        block = ContentBlock.objects.create(paragraph=cls.p2, block_type="exercise", order=1)
        ex = Exercise.objects.create(textbook=tb, block=block, number=50, condition="Обчисли:")
        sub = SubExercise.objects.create(exercise=ex, number="1", order=1, text="2 + 3")
        Answer.objects.create(exercise=ex, subexercise=sub, kind="book", text="5")
        Exercise.objects.create(textbook=tb, block=block, number=51, condition="Сумнівна умова", needs_review=True)

    def test_paragraph_overview_with_items(self):
        html = self.client.get(f"/paragraphs/{self.p1.id}/").content.decode()
        self.assertIn("Натуральні числа</h1>", html)
        self.assertIn("Уроки параграфа", html)
        self.assertIn(f'href="/items/{self.i1.id}/"', html)
        self.assertIn("Головне в параграфі", html)                       # блок рівня §
        self.assertIn("Головне: числа 1, 2, 3.", html)
        self.assertNotIn("Почати урок", html)                           # огляд, а не урок
        self.assertIn(f'href="/grades/5/#lesson-{self.i1.id}"', html)

    def test_paragraph_as_lesson(self):
        html = self.client.get(f"/paragraphs/{self.p2.id}/").content.decode()
        self.assertIn(f'href="/play/paragraph/{self.p2.id}/"', html)
        self.assertIn("Почати урок", html)
        self.assertIn(f'href="/grades/5/#lesson-p{self.p2.id}"', html)
        self.assertIn("2 + 3", html)
        self.assertNotIn("Сумнівна умова", html)                         # needs_review — лише персоналу
        staff = User.objects.create_user("t", password="pw-12345678", is_staff=True)
        self.client.force_login(staff)
        self.assertIn("Сумнівна умова", self.client.get(f"/paragraphs/{self.p2.id}/").content.decode())

    def test_item_crumbs_link_to_paragraph(self):
        html = self.client.get(f"/items/{self.i1.id}/").content.decode()
        self.assertIn(f'href="/paragraphs/{self.p1.id}/">§1 Натуральні числа</a>', html)

    def test_old_urls_redirect_permanently(self):
        cases = {
            "/grades/": "/",
            f"/grades/{self.g5.id}/sections/": "/grades/5/",
            f"/sections/{self.s1.id}/paragraphs/": f"/grades/5/#lesson-{self.i1.id}",
            f"/paragraphs/{self.p2.id}/items/": f"/paragraphs/{self.p2.id}/",
        }
        for old, new in cases.items():
            with self.subTest(old=old):
                resp = self.client.get(old)
                self.assertEqual(resp.status_code, 301)
                self.assertEqual(resp["Location"], new)
        self.assertEqual(self.client.get("/grades/999999/sections/").status_code, 404)

    def test_old_templates_and_static_are_gone(self):
        from pathlib import Path
        root = Path(__file__).parent
        for rel in ["templates/education/item_list.html", "templates/education/item_detail.html",
                    "templates/education/grade_list.html", "templates/education/_map_partial.html",
                    "templates/education/play_v2.html", "templates/education/_lesson_blocks_v2.html",
                    "static/education/map.js", "static/education/map_data_uk.json",
                    "static/education/css/map_ui.css", "static/education/css/play-v2.css", "static/education/js/play-v2.js"]:
            self.assertFalse((root / rel).exists(), rel)
