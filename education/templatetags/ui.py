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
    "chat", "pencil", "repeat", "owl", "scroll",
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


def _short_author(textbook):
    """«Мерзляк А. Г., Полонський В. Б., …» → «Мерзляк» (перше прізвище)."""
    author = (getattr(textbook, "author", "") or "").strip()
    return author.split(",")[0].split()[0] if author else ""


@register.inclusion_tag("education/_topbar.html", takes_context=True)
def topbar(context):
    """Верхня панель: класи предмета (вкладки), чіпи гравця (заповнює js/me.js), вхід/ім’я.

    Поточний клас — змінна контексту ``current_grade`` (номер), її задає view сторінки мапи.
    """
    from education.models import Grade

    request = context.get("request")
    current = context.get("current_grade")
    grades = []
    for g in (Grade.objects.filter(subject__code="math").order_by("number")
              .prefetch_related("textbooks")):
        author = next((_short_author(t) for t in g.textbooks.all() if t.author), "")
        grades.append({
            "number": g.number,
            "label": f"{g.number} клас" + (f" · {author}" if author else ""),
            "active": current is not None and int(current) == g.number,
        })
    user = getattr(request, "user", None)
    return {
        "grades": grades,
        "current_grade": current,
        "user": user,
        "request": request,
        "csrf_token": context.get("csrf_token"),
        "next_path": request.get_full_path() if request else "/",
    }


@register.filter
def uk_plural(n, forms):
    """``{{ n|uk_plural:"острів,острови,островів" }}`` → форма слова для n (без самого числа)."""
    one, few, many = [f.strip() for f in str(forms).split(",")]
    try:
        n = abs(int(n))
    except (TypeError, ValueError):
        return many
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


# Блоки уроку (фаза 13): людські назви без службових значків з моделі («Самоперевірка (❓)») + іконка
BLOCKS = {
    "theory": ("Теорія", "book"),
    "self_check": ("Перевір себе", "check"),
    "oral_exercise": ("Розв’язуємо усно", "chat"),
    "exercise": ("Вправи", "pencil"),
    "review_exercise": ("Повторення", "repeat"),
    "wise_owl": ("Задача від Мудрої Сови", "owl"),
    "history_aside": ("Коли зроблено уроки", "scroll"),
    "self_test": ("Перевірте себе", "check"),
    "summary": ("Головне в параграфі", "book"),
}
DIFFICULTY = {
    "preparatory": "Підготовчий", "medium": "Середній", "sufficient": "Достатній",
    "high": "Високий", "olympiad": "Олімпіадний",
}


@register.filter
def block_name(block_type):
    return BLOCKS.get(block_type, (str(block_type), "book"))[0]


@register.filter
def block_icon(block_type):
    return BLOCKS.get(block_type, ("", "book"))[1]


@register.filter
def difficulty_name(code):
    """Назва складності без значків («Високий»); невідома чи порожня → ''."""
    return DIFFICULTY.get(code or "", "")


_PARA_END = (".", "!", "?", ":", ";", "»")


@register.filter
def reflow(text):
    """Склеює рядки, розірвані при парсингу PDF, в абзаци (фаза 13).

    Новий абзац — якщо попередній рядок закінчується розділовим знаком
    кінця речення або наступний починається з маркера списку / номера.
    """
    from django.utils.html import escape
    from django.utils.safestring import mark_safe
    import re
    if not text:
        return ""
    paras, cur = [], []
    for raw in str(text).splitlines():
        line = raw.strip()
        if not line:
            if cur:
                paras.append(" ".join(cur)); cur = []
            continue
        starts_new = bool(re.match(r"^([-–—•»]|\d+[.)]\s)", line))
        if cur and (starts_new or cur[-1].endswith(_PARA_END)):
            paras.append(" ".join(cur)); cur = []
        if cur and cur[-1].endswith("-") and line[:1].islower():
            cur[-1] = cur[-1][:-1] + line   # перенос слова
        else:
            cur.append(line)
    if cur:
        paras.append(" ".join(cur))
    return mark_safe("".join(f"<p>{escape(p)}</p>" for p in paras))
