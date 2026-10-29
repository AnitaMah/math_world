"""Сторінки нового інтерфейсу (docs/frontend/PLAN.md). Тонкі view: лише рендер шаблонів.

Службові сторінки `/ui/…` доступні тільки при DEBUG — це «вітрина» для розробки.
"""
from django.conf import settings
from django.contrib.staticfiles.finders import find as find_static
from django.http import Http404, HttpResponse
from django.shortcuts import render

TOKEN_GROUPS = [
    ("Фон і поверхні", [
        ("--bg", "фон сторінки"), ("--bg-sea-1", "океан, центр"), ("--bg-sea-2", "океан, край"),
        ("--surface", "верхня панель, нижня навігація"), ("--surface-2", "панель уроку, картки на мапі"),
        ("--card", "картка в панелі"), ("--card-2", "чіпи верхньої панелі"), ("--card-3", "теги блоків"),
    ]),
    ("Лінії", [
        ("--line", "розділювачі"), ("--line-2", "рамки чіпів, трек прогресу"),
        ("--line-3", "рамки карток на мапі"), ("--line-strong", "пунктир, «Увійти»"),
    ]),
    ("Текст", [
        ("--text", "основний"), ("--text-2", "вторинний"), ("--muted", "приглушений"),
        ("--muted-2", "підписи, лічильники"), ("--ink", "текст на акценті"),
    ]),
    ("Ігрові", [
        ("--star", "зірка"), ("--star-off", "порожня зірка"), ("--points", "бали"), ("--streak", "серія"),
        ("--ok", "пройдено / правильно"), ("--ok-bg", ""), ("--bad", "неправильно"), ("--bad-bg", ""),
        ("--info", "відкрито"), ("--info-bg", ""), ("--neutral-bg", "закрито, у хмарах"),
    ]),
    ("Мапа", [
        ("--rim", "берег"), ("--rim-stroke", "обвідка берега"), ("--shallow", "мілина"),
        ("--wave", "хвилі"), ("--speck", "цятки"), ("--fog", "хмари"), ("--fog-stroke", "обвідка хмар"),
        ("--route", "стежка"), ("--boat-route", "маршрут човна"),
    ]),
    ("Вузли", [
        ("--node-open-bg", "відкритий"), ("--node-locked-bg", "закритий"), ("--node-locked-fg", ""),
        ("--node-locked-border", ""), ("--node-soon-bg", "у хмарах"), ("--node-soon-fg", ""),
        ("--node-soon-border", ""),
    ]),
]

# Пари «текст на фоні», для яких сторінка рахує контраст (WCAG: текст ≥ 4.5, графіка ≥ 3)
CONTRAST_PAIRS = [
    ("--text", "--bg", 4.5), ("--text-2", "--surface-2", 4.5), ("--muted", "--surface-2", 4.5),
    ("--muted-2", "--surface-2", 4.5), ("--muted-2", "--card", 4.5), ("--muted-2", "--surface", 4.5),
    ("--ink", "--isl-1-acc", 4.5), ("--ink", "--isl-2-acc", 4.5), ("--ink", "--isl-3-acc", 4.5),
    ("--ink", "--isl-4-acc", 4.5), ("--ink", "--isl-5-acc", 4.5),
    ("--ok", "--ok-bg", 4.5), ("--bad", "--bad-bg", 4.5), ("--info", "--info-bg", 4.5),
    ("--muted", "--neutral-bg", 4.5), ("--node-soon-fg", "--node-soon-bg", 4.5),
    ("--node-locked-fg", "--node-locked-bg", 3.0),
]

FONT_SCALE = [32, 26, 22, 20, 17, 15, 14, 13, 12]


def _debug_only():
    if not settings.DEBUG:
        raise Http404


def ui_tokens(request):
    """`/ui/tokens/` — усі токени з tokens.css плашками, острови, вузли, шрифти, контраст."""
    _debug_only()
    return render(request, "education/ui_tokens.html", {
        "groups": TOKEN_GROUPS,
        "pairs": CONTRAST_PAIRS,
        "islands": range(1, 6),
        "font_scale": FONT_SCALE,
    })


def ui_kit(request):
    """`/ui/kit/` — вітрина базових стилів і компонентів нового UI (росте з кожною фазою)."""
    _debug_only()
    from ..templatetags.ui import ICONS
    sec_chips = [(1, "I", "Натуральні числа"), (2, "I", "Додавання і віднімання"), (3, "I", "Множення і ділення"),
                 (4, "II", "Звичайні дроби"), (5, "II", "Десяткові дроби")]
    return render(request, "education/ui_kit.html", {"icons": sorted(ICONS), "sec_chips": sec_chips})


def progress_page(request):
    """`/progress/` — вкладка «Прогрес» (фаза 20, беклог FE-0630): бали за тиждень, зірки по параграфах.

    Каркас карток класів рендерить сервер (дані з БД, як на «Світі»); зірки по параграфах і графік
    балів — `js/progress.js` і `js/me.js` з `/api/grades/<n>/map/` і `/api/me/` (або моків).
    """
    return render(request, "education/progress.html", {"cards": _grade_cards()})


def profile_page(request):
    """`/profile/` — вкладка «Профіль» (фаза 20, беклог FE-0631): ім’я, серія днів, вхід/вихід.

    Серію заповнює `js/me.js` з `/api/me/` (той самий `[data-me]`, що й у верхній панелі).
    """
    return render(request, "education/profile.html")


def ui_api(request):
    """`/ui/api/` — відповіді API-клієнта й normalizeMap() (реальний бекенд або ?mock=1)."""
    _debug_only()
    return render(request, "education/ui_api.html")


def service_worker(request):
    """`/sw.js` — поза `/static/`, щоб область дії (scope) покривала весь сайт: мапу, урок, гру
    (фаза 20, беклог FE-0638). Віддає файл з education/static/education/js/sw.js як є."""
    path = find_static("education/js/sw.js")
    if not path:
        raise Http404
    with open(path, encoding="utf-8") as f:
        return HttpResponse(f.read(), content_type="application/javascript")


def grade_map_page(request, number):
    """`/grades/<n>/` — мапа-архіпелаг класу (фаза 8). Дані малює js/map.js з /api/grades/<n>/map/."""
    from django.shortcuts import get_object_or_404
    from ..models import Grade
    grade = get_object_or_404(Grade, number=number, subject__code="math")
    return render(request, "education/map.html", {"grade": grade, "current_grade": grade.number})


def _grade_cards():
    """Картки класів для екрана «Світ»: дані з БД (кількість островів і уроків, автор)."""
    from ..models import Grade, Item, Paragraph
    from ..templatetags.ui import _short_author
    cards = []
    for g in Grade.objects.filter(subject__code="math").order_by("number").prefetch_related("textbooks"):
        tb = next((t for t in g.textbooks.all()), None)
        sections = g.section_set.count()
        items = Item.objects.filter(paragraph__section__grade=g).count()
        paragraphs = Paragraph.objects.filter(section__grade=g).count()
        cards.append({
            "number": g.number,
            "author": _short_author(tb) if tb else "",
            "year": tb.year if tb else None,
            "sections": sections,
            "lessons": items or paragraphs,       # урок = пункт (Мерзляк) або § (Тарасенкова)
            "lesson_is_paragraph": not items,
        })
    return cards


def world_page(request):
    """`/` — «Світ»: вибір класу (фаза 12)."""
    cards = _grade_cards()
    fog_from = (max(c["number"] for c in cards) + 1) if cards else 5
    return render(request, "education/world.html", {"cards": cards, "fog_from": fog_from, "show_fog": fog_from <= 9})


def _place_figures(blocks):
    """Рисунки блоків — у тексті, одразу після абзацу, де їх уперше згадано (рис. 3, рисунку 6…).

    Пул рисунків спільний на урок: рисунок із блоку «Теорія» може бути згаданий у «Коли зроблено
    уроки». Незгадані рисунки не показуються. Результат — b["html"] для кожного блоку.
    """
    from ..templatetags.ui import text_with_figures
    figmap = {}
    for b in blocks:
        for f in b["figures"]:
            if f.image and f.number and f.number not in figmap:
                figmap[f.number] = f
    used = set()
    for b in blocks:
        b["html"] = text_with_figures(b["obj"].text, figmap, used)
    return used


def lesson_page(request, item):
    """`/items/<id>/` — теорія й вправи уроку кольором острова (фаза 13)."""
    return _lesson_render(request, "item", item)


def paragraph_page(request, paragraph_id):
    """`/paragraphs/<id>/` — сторінка § (фаза 18, замість старого `item_list`).

    § без пунктів (Тарасенкова) — це сам урок: теорія, вправи, «Почати урок». § з пунктами (Мерзляк) —
    блоки рівня § («Головне в параграфі», «Перевірте себе») і список його уроків.
    """
    from django.shortcuts import get_object_or_404
    from ..models import Paragraph
    paragraph = get_object_or_404(Paragraph.objects.select_related("section__grade"), pk=paragraph_id)
    return _lesson_render(request, "paragraph", paragraph)


def _strip_title(text, paragraph=False):
    import re
    return re.sub(r"^§\s*\d+\.\s*" if paragraph else r"^\s*\d+\.\s*", "", text or "")


def _lesson_render(request, kind, lesson):
    """Спільний рендер `lesson.html` для пункту й параграфа.

    Відповіді, позначки «перевірити» і вправи з `needs_review` — лише для персоналу (is_staff):
    діти бачать умови, а не відповіді, і не бачать сумнівного (як і в грі).
    """
    from django.urls import reverse

    from game.services import get_player

    from ..services import playable_counts
    from . import _blocks_context, _item_title, get_lang

    lang = get_lang(request)
    paragraph = lesson.paragraph if kind == "item" else lesson
    section = paragraph.section
    grade = section.grade
    staff = request.user.is_staff
    items = list(paragraph.item_set.order_by("number")) if kind == "paragraph" else []
    is_lesson = kind == "item" or not items          # § з пунктами — не урок, а огляд

    player = get_player(request, create=False)
    progress = {}
    if player is not None:
        from django.db.models import Q
        for p in player.progress.filter(Q(item__paragraph=paragraph) | Q(paragraph=paragraph)):
            progress[("item", p.item_id) if p.item_id else ("paragraph", p.paragraph_id)] = p.stars

    blocks = _blocks_context(lesson)
    if not staff:
        for b in blocks:
            b["exercises"] = [e for e in b["exercises"] if not e["obj"].needs_review]
    _place_figures(blocks)

    if kind == "item":
        title = _strip_title(_item_title(lesson, lang))
        label = f"Урок {lesson.number}"
        play_url = reverse("play_item", args=[lesson.pk])
        anchor = f"lesson-{lesson.pk}"
    else:
        title = _strip_title(paragraph.get_name(lang), paragraph=True)
        label = f"§{paragraph.number}"
        play_url = reverse("play_paragraph", args=[lesson.pk]) if is_lesson else ""
        anchor = f"lesson-p{lesson.pk}" if is_lesson else (f"lesson-{items[0].pk}" if items else "")
    map_url = reverse("grade_map_page", args=[grade.number]) + (f"#{anchor}" if anchor else "")

    item_counts = playable_counts(items)
    return render(request, "education/lesson.html", {
        "kind": kind, "lesson": lesson, "is_lesson": is_lesson,
        "title": title, "label": label,
        "paragraph": paragraph, "paragraph_title": _strip_title(paragraph.get_name(lang), paragraph=True),
        "section": section, "grade": grade, "current_grade": grade.number,
        "isl": _island_of(paragraph),
        "stars": progress.get((kind, lesson.pk), 0),
        "playable": playable_counts([lesson]).get(lesson.pk, 0) if is_lesson else 0,
        "play_url": play_url, "map_url": map_url,
        "blocks": blocks, "staff": staff,
        "items": [{"obj": i, "title": _strip_title(_item_title(i, lang)), "url": reverse("item_detail", args=[i.pk]),
                   "stars": progress.get(("item", i.pk), 0), "playable": item_counts.get(i.pk, 0)} for i in items],
    })


# --------------------------------------------------------------------------- гра (фаза 14)

def _island_of(paragraph):
    """Колір острова параграфа: isl-1..5 за його порядком у класі (як на мапі)."""
    from ..models import Paragraph
    order = list(Paragraph.objects.filter(section__grade=paragraph.section.grade)
                 .order_by("section__number", "number").values_list("id", flat=True))
    return (order.index(paragraph.id) % 5) + 1 if paragraph.id in order else 1


def _grade_lessons(grade):
    """Уроки класу в порядку мапи: пункти параграфа, або сам § (kind="paragraph"), якщо пунктів немає."""
    from django.db.models import Prefetch
    from ..models import Item, Paragraph
    pars = (Paragraph.objects.filter(section__grade=grade).order_by("section__number", "number")
            .prefetch_related(Prefetch("item_set", queryset=Item.objects.order_by("number"))))
    lessons = []
    for p in pars:
        items = list(p.item_set.all())
        lessons += [("item", i) for i in items] if items else [("paragraph", p)]
    return lessons


def _lesson_ref(kind, obj):
    return f"lesson-{'p' if kind == 'paragraph' else ''}{obj.pk}"


def _next_lesson_url(grade, kind, lesson):
    """Наступний урок класу, у якому є ігрові завдання (кнопка «Наступний урок» на фіналі)."""
    from django.urls import reverse
    from ..services import playable_counts
    lessons = _grade_lessons(grade)
    keys = [(k, o.pk) for k, o in lessons]
    if (kind, lesson.pk) not in keys:
        return ""
    rest = lessons[keys.index((kind, lesson.pk)) + 1:]
    counts = {"item": playable_counts([o for k, o in rest if k == "item"]),
              "paragraph": playable_counts([o for k, o in rest if k == "paragraph"])}
    for k, o in rest:
        if counts[k].get(o.pk):
            return reverse("play_item" if k == "item" else "play_paragraph", args=[o.pk])
    return ""


def play_page(request, kind, lesson):
    """`/play/item|paragraph/<id>/` у новому UI (фаза 14): повноекранна гра кольором острова.

    Завдання, перевірку й прогрес фронтенд бере з /api/play/… (бекенд не змінюємо).
    Вихід ✕ і «На мапу» ведуть на мапу класу з цим уроком (#lesson-<id>).
    """
    import re
    from django.urls import reverse
    from . import _item_title, get_lang

    lang = get_lang(request)
    paragraph = lesson.paragraph if kind == "item" else lesson
    grade = paragraph.section.grade
    if kind == "item":
        title = re.sub(r"^\s*\d+\.\s*", "", _item_title(lesson, lang))
        label = f"Урок {lesson.number} · {title}"
        api_url = reverse("api_play_item", args=[lesson.pk])
        theory_url = reverse("item_detail", args=[lesson.pk])
    else:
        title = re.sub(r"^§\s*\d+\.\s*", "", paragraph.get_name(lang))
        label = f"§{paragraph.number} · {title}"
        api_url = reverse("api_play_paragraph", args=[lesson.pk])
        theory_url = reverse("paragraph_page", args=[lesson.pk])
    map_url = reverse("grade_map_page", args=[grade.number]) + "#" + _lesson_ref(kind, lesson)
    return render(request, "education/play.html", {
        "title": title, "label": label, "kind": kind, "lesson": lesson,
        "isl": _island_of(paragraph), "grade": grade, "current_grade": grade.number,
        "api_url": api_url, "map_url": map_url, "theory_url": theory_url,
        "next_url": _next_lesson_url(grade, kind, lesson),
    })
