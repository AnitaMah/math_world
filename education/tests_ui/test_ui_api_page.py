from django.test import TestCase, override_settings


class UiApiPageTests(TestCase):
    @override_settings(DEBUG=True)
    def test_available_in_debug(self):
        response = self.client.get("/ui/api/")
        self.assertContains(response, "education/js/ui-api.js")

    @override_settings(DEBUG=False)
    def test_hidden_without_debug(self):
        self.assertEqual(self.client.get("/ui/api/").status_code, 404)
