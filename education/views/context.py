"""Context processors для шаблонів (docs/frontend/PLAN.md)."""
from django.conf import settings


def ui_debug(request):
    """``UI_DEBUG`` = settings.DEBUG: base.html ставить ``<html data-debug="1">``, і лише тоді
    js/api.js дозволяє моки (``?mock=1``). Прапорець ``NEW_UI`` прибрано у фазі 18."""
    return {"UI_DEBUG": settings.DEBUG}
