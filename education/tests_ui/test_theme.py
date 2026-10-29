from django.test import TestCase


class ThemeNoFlashScriptTests(TestCase):
    """Інлайн-скрипт у <head> (фаза 20, FE-0636): виставляє data-theme до першого малювання."""

    def test_every_page_has_the_inline_init(self):
        html = self.client.get("/").content.decode()
        self.assertIn("localStorage.getItem(\"mw_theme\")", html)
        self.assertIn('document.documentElement.dataset.theme = t', html)
        # до будь-якого <link rel="stylesheet">, щоб застосувалось раніше CSS
        self.assertLess(html.index("mw_theme"), html.index('rel="stylesheet"'))
