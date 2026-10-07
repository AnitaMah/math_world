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
