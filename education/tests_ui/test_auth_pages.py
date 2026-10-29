from django.contrib.auth.models import User
from django.test import TestCase


class AuthPagesTests(TestCase):
    """Вхід і реєстрація в новому дизайні (фаза 15)."""

    def test_login_page(self):
        html = self.client.get("/accounts/login/?next=/grades/5/").content.decode()
        self.assertIn("education/css/auth.css", html)
        self.assertIn('class="page-auth"', html)
        self.assertNotIn('class="topbar', html)
        self.assertNotIn('class="bottom-nav', html)
        self.assertIn('<label class="field__label" for="id_username">', html)
        self.assertIn('autocomplete="current-password"', html)              # віджет Django збережено
        self.assertIn('name="next" value="/grades/5/"', html)
        self.assertIn('href="/accounts/signup/?next=/grades/5/"', html)      # next не губиться

    def test_failed_login_shows_error(self):
        User.objects.create_user("olia", password="pw-12345-long")
        html = self.client.post("/accounts/login/", {"username": "olia", "password": "wrong"}).content.decode()
        self.assertIn('class="auth__error" role="alert"', html)
        self.assertIn("введіть правильні", html)

    def test_login_goes_to_next(self):
        User.objects.create_user("olia", password="pw-12345-long")
        resp = self.client.post("/accounts/login/", {"username": "olia", "password": "pw-12345-long", "next": "/grades/5/"})
        self.assertRedirects(resp, "/grades/5/", fetch_redirect_response=False)

    def test_signup_field_errors_and_rules(self):
        html = self.client.get("/accounts/signup/").content.decode()
        self.assertIn("<summary>Вимоги до пароля</summary>", html)
        self.assertIn("Літери, цифри та символи", html)
        html = self.client.post("/accounts/signup/", {"username": "", "password1": "a", "password2": "b"}).content.decode()
        self.assertIn('aria-invalid="true"', html)
        self.assertIn('class="field__error" id="id_username-err"', html)
        self.assertIn('aria-describedby="id_username-err"', html)
        self.assertNotIn('id="id_username-hint"', html)                  # підказку замінює помилка

    def test_signup_keeps_guest_and_goes_home(self):
        from education.models import Player
        session = self.client.session
        session.save()
        guest = Player.objects.create(session_key=session.session_key, points=5)
        session["player_id"] = guest.pk          # так гравця-гостя запам’ятовує game.get_player
        session.save()
        resp = self.client.post("/accounts/signup/", {"username": "petryk", "password1": "Very-long-pass-77",
                                                      "password2": "Very-long-pass-77"})
        self.assertRedirects(resp, "/", fetch_redirect_response=False)
        self.assertEqual(Player.objects.get(user__username="petryk").points, 5)

    def test_signup_next_only_local(self):
        data = {"username": "ivas", "password1": "Very-long-pass-77", "password2": "Very-long-pass-77"}
        resp = self.client.post("/accounts/signup/", {**data, "next": "https://evil.example/"})
        self.assertRedirects(resp, "/", fetch_redirect_response=False)
        self.client.logout()
        resp = self.client.post("/accounts/signup/?next=/grades/5/", {**data, "username": "ivas2"})
        self.assertRedirects(resp, "/grades/5/", fetch_redirect_response=False)
