"""Фронтенд (docs/frontend/PLAN.md): прапорці інтерфейсу в контексті шаблонів."""
from django.conf import settings
from django.template import engines
from django.test import RequestFactory, SimpleTestCase, override_settings

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


class BaseTemplateTests(SimpleTestCase):
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
        order = [html.index(f) for f in ("fonts.css", "tokens.css", "base.css", "ui-dev.css")]
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
