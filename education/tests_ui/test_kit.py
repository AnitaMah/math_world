from django.test import TestCase, override_settings


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
        tpl = Path(__file__).resolve().parents[1] / "templates" / "education"
        for name in ("base.html", "ui_kit.html", "ui_tokens.html"):
            self.assertNotIn("fonts.googleapis.com", (tpl / name).read_text(encoding="utf-8"), name)

    def test_every_font_face_file_exists(self):
        import re
        from pathlib import Path
        static = Path(__file__).resolve().parents[1] / "static" / "education"
        css = (static / "css" / "fonts.css").read_text(encoding="utf-8")
        urls = re.findall(r"url\('\.\./fonts/([^']+)'\)", css)
        self.assertEqual(len(urls), 12)  # Unbounded 2 ваги + Nunito 4 ваги, × cyrillic/latin
        missing = [u for u in urls if not (static / "fonts" / u).exists()]
        self.assertEqual(missing, [])
