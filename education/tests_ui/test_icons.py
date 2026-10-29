from django.template import engines
from django.test import TestCase, override_settings


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
        sprite = (Path(__file__).resolve().parents[1] / "templates" / "education" / "partials" / "icons.html").read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'<symbol id="i-([a-z-]+)"', sprite)), set(ICONS))

    @override_settings(DEBUG=True)
    def test_kit_shows_every_icon(self):
        from education.templatetags.ui import ICONS
        html = self.client.get("/ui/kit/").content.decode()
        for name in ICONS:
            self.assertIn(f'href="#i-{name}"', html)
