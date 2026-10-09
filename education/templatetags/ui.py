"""Template tags нового UI (docs/frontend/PLAN.md).

``{% load ui %}`` → ``{% icon "star" size=18 %}``, ``{% icon "lock" label="Закрито" %}``,
``{% icon "bolt" class="icon--points" %}``.
"""
import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe
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
_FIG_REF = re.compile(
    r"рис(?:\.|ун\w*)\s*(\d+)((?:\s*(?:,|і|та|й|–|—|-)\s*\d+(?![\d.,]*\s*(?:см|мм|дм|км|м)\b))*)",
    re.IGNORECASE)


def paragraphs(text):
    """Склеює рядки, розірвані при парсингу PDF, в абзаци (фаза 13).

    Новий абзац — якщо попередній рядок закінчується розділовим знаком
    кінця речення або наступний починається з маркера списку / номера.
    Перенос слова «по-\nзначають» склеюється.
    """
    if not text:
        return []
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
            cur[-1] = cur[-1][:-1] + line
        else:
            cur.append(line)
    if cur:
        paras.append(" ".join(cur))
    return [_strip_stray_captions(p) for p in paras]


_LOWER = "а-яіїєґ'’"


def _strip_stray_captions(p):
    """Підпис «Рис. 3», що OCR вклеїв посеред речення: «геометрич- Рис. 3 них» → «геометричних».

    Справжні згадки пишуться з малої («рис. 3»), тож прибираємо лише «Рис. N» між словами.
    """
    p = re.sub(rf"(\w)-\s+Рис\.\s*\d+\s+(?=[{_LOWER}])", r"\1", p)
    return re.sub(rf"(?<=[\w,])\s+Рис\.\s*\d+(?=\s+[{_LOWER}])", "", p)


def figure_refs(paragraph):
    """Номери рисунків, згаданих в абзаці: «рис. 3», «рисунку 6», «рис. 3 і 4», «рис. 3–5»."""
    out = []
    for m in _FIG_REF.finditer(paragraph):
        nums = [int(m.group(1))] + [int(n) for n in re.findall(r"\d+", m.group(2) or "")]
        tail = m.group(2) or ""
        if len(nums) == 2 and re.search(r"[–—-]", tail) and 0 < nums[1] - nums[0] <= 10:
            nums = list(range(nums[0], nums[1] + 1))
        out += [str(n) for n in nums if str(n) not in out]
    return out


def figure_html(fig):
    return (f'<figure class="lfigure"><img src="{escape(fig.image.url)}" alt="{escape(str(fig))}" '
            f'loading="lazy"><figcaption>{escape(str(fig))}</figcaption></figure>')


def text_with_figures(text, figmap=None, used=None):
    """Абзаци `<p>` + рисунки одразу після абзацу, де їх уперше згадано.

    figmap: {"3": Figure}; used: спільна множина вже вставлених номерів (на весь урок).
    Незгадані рисунки не показуються (здебільшого це фото-ілюстрації).
    """
    figmap = figmap or {}
    used = used if used is not None else set()
    html = []
    for p in paragraphs(text):
        html.append(f"<p>{escape(p)}</p>")
        for n in figure_refs(p):
            fig = figmap.get(n)
            if fig is not None and n not in used:
                used.add(n)
                html.append(figure_html(fig))
    return mark_safe("".join(html))


@register.filter
def reflow(text):
    """Лише абзаци, без рисунків."""
    return text_with_figures(text)


# --------------------------------------------------------------------------- вхід і реєстрація (фаза 15)

AUTH_HINTS = {   # дружніші за стандартні help_text Django
    "username": "Літери, цифри та символи @ . + - _ — до 150 знаків.",
    "password2": "Введи той самий пароль ще раз.",
}


@register.inclusion_tag("registration/_field.html")
def auth_field(field, hints=True):
    """Поле форми входу/реєстрації: label над полем, підказка, помилки з aria-describedby.

    Віджет рендерить Django (`as_widget`) — тож лишаються autocomplete, maxlength, required і
    пароль не повертається у value. Вимоги до пароля (HTML-список валідаторів) — у <details>.
    """
    fid = field.id_for_label or f"id_{field.html_name}"
    help_html = str(field.help_text or "")
    rules = help_html if hints and help_html.lstrip().startswith("<ul") else ""
    hint = (AUTH_HINTS.get(field.name) or ("" if rules else help_html)) if hints and not field.errors else ""
    described = [f"{fid}-err"] if field.errors else []
    if hint:
        described.append(f"{fid}-hint")
    attrs = {"class": "field__input"}
    if described:
        attrs["aria-describedby"] = " ".join(described)
    if field.errors:
        attrs["aria-invalid"] = "true"
    return {"field": field, "fid": fid, "widget": field.as_widget(attrs=attrs),
            "hint": hint, "rules": mark_safe(rules) if rules else ""}
