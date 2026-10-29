from django.test import TestCase


class RealApiTests(TestCase):
    """Перехід на реальний API (фаза 17)."""

    def test_debug_flag_for_mocks(self):
        with self.settings(DEBUG=True):
            self.assertIn('<html lang="uk" data-debug="1">', self.client.get("/progress/").content.decode())
        with self.settings(DEBUG=False):
            self.assertIn('<html lang="uk">', self.client.get("/progress/").content.decode())
