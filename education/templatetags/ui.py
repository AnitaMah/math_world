"""Template tags нового UI (docs/frontend/PLAN.md).

``{% load ui %}`` → ``{% icon "star" size=18 %}``, ``{% icon "lock" label="Закрито" %}``,
``{% icon "bolt" class="icon--points" %}``.
"""
from django import template
from django.utils.html import format_html

register = template.Library()

# Усі символи спрайту templates/education/_icons.html (тест звіряє список зі спрайтом)
ICONS = frozenset({
    "star", "bolt", "flame", "play", "boat", "logo",
    "lock", "map", "chart", "user", "check", "sparkle", "close",
    "chevron-down", "chevron-left", "chevron-right", "book",
})


@register.simple_tag
def icon(name, size=20, label="", **attrs):
    """Іконка зі спрайту. Без ``label`` — декоративна (``aria-hidden``); з ``label`` —
    ``role="img"`` + ``<title>`` (для іконок без тексту поруч, напр. замок на вузлі)."""
    if name not in ICONS:
        raise template.TemplateSyntaxError(f"icon: невідома іконка {name!r}; є: {', '.join(sorted(ICONS))}")
    size = int(size)
    css = "icon icon--" + name + (" " + attrs["class"] if attrs.get("class") else "")
    if label:
        return format_html(
            '<svg class="{}" width="{}" height="{}" role="img" aria-label="{}" focusable="false">'
            '<title>{}</title><use href="#i-{}"/></svg>',
            css, size, size, label, label, name,
        )
    return format_html(
        '<svg class="{}" width="{}" height="{}" aria-hidden="true" focusable="false"><use href="#i-{}"/></svg>',
        css, size, size, name,
    )
