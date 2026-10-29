from django.apps import AppConfig


class GameConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'game'

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        from .services import on_login
        user_logged_in.connect(on_login, dispatch_uid="education_merge_anonymous_player")
