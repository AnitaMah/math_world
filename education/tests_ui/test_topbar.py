from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase


class TopbarAndNavTests(TestCase):
    """Верхня панель, нижня навігація (фаза 5)."""

    @classmethod
    def setUpTestData(cls):
        from education.models import Grade, Subject, Textbook
        math = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})[0]
        g5 = Grade.objects.create(subject=math, number=5, name_uk="5 клас")
        Grade.objects.create(subject=math, number=6, name_uk="6 клас")
        Textbook.objects.create(subject=math, grade=g5, profile_code="math_merzlyak_5", title="Математика. 5 клас",
                                author="Мерзляк А. Г., Полонський В. Б., Якір М. С.", pdf_sha256="x" * 64)

    def test_guest_sees_login_with_next(self):
        html = self.client.get("/progress/").content.decode()
        self.assertIn('class="topbar"', html)
        self.assertIn("Увійти", html)
        self.assertIn("/accounts/login/?next=/progress/", html)
        self.assertNotIn("Вийти", html)

    def test_user_sees_name_and_logout_form(self):
        self.client.force_login(User.objects.create_user("anita", password="pw-12345678"))
        html = self.client.get("/progress/").content.decode()
        self.assertIn("anita", html)
        self.assertIn('action="/accounts/logout/"', html)
        self.assertNotIn(">Увійти<", html)

    def test_grade_tabs_with_short_author(self):
        html = self.client.get("/progress/").content.decode()
        self.assertIn("5 клас · Мерзляк", html)
        self.assertIn(">6 клас<", html)  # підручника 6 класу в БД ще немає — без автора

    def test_active_grade_tab(self):
        from django.template import Context, Template
        request = RequestFactory().get("/grades/5/")
        request.user = User()
        html = Template("{% load ui %}{% topbar %}").render(Context({"request": request, "current_grade": 5}))
        self.assertIn('aria-current="page">5 клас · Мерзляк', html)
        self.assertIn("5 клас<svg", html.replace("\n", ""))  # кнопка «5 клас ▾» на телефоні

    def test_player_chips_are_filled_by_js(self):
        html = self.client.get("/progress/").content.decode()
        for key in ("stars", "points", "streak", "streak_word"):
            self.assertIn(f'data-me="{key}"', html)
        self.assertIn("education/js/me.js", html)
        self.assertIn('title="Серія днів"', html)

    def test_bottom_nav_marks_active_tab(self):
        html = self.client.get("/profile/").content.decode()
        nav = html.split('class="bottom-nav"', 1)[1]
        self.assertIn('href="/profile/" aria-current="page"', nav)
        self.assertNotIn('href="/progress/" aria-current="page"', nav)

    def test_profile_account_actions(self):
        guest = self.client.get("/profile/")
        self.assertContains(guest, "Зареєструватися")
        self.client.force_login(User.objects.create_user("olia", password="pw-12345678"))
        self.assertContains(self.client.get("/profile/"), "olia")
