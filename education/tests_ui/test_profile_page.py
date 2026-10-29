from django.contrib.auth.models import User
from django.test import TestCase


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
