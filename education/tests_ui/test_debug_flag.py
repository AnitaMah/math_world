from django.template import engines
from django.test import RequestFactory, SimpleTestCase

from education.views.context import ui_debug


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
