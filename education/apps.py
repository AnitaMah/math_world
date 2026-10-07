from django.apps import AppConfig


class EducationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'education'

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        from .game import on_login
        user_logged_in.connect(on_login, dispatch_uid="education_merge_anonymous_player")
