from django.test import TestCase


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
        static = Path(__file__).resolve().parents[1] / "static" / "education"
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
        path = Path(__file__).resolve().parents[1] / "static" / "education" / "img" / "apple-touch-icon.png"
        self.assertTrue(path.exists())
