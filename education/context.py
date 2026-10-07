"""Context processors для шаблонів фронтенду (docs/frontend/PLAN.md, фаза 0.4)."""
from django.conf import settings


def ui_flags(request):
    """Прапорці інтерфейсу, доступні в усіх шаблонах: ``{% if NEW_UI %}…{% endif %}``."""
    return {"NEW_UI": getattr(settings, "NEW_UI", False)}
