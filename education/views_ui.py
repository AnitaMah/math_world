"""Сторінки нового інтерфейсу (docs/frontend/PLAN.md). Тонкі view: лише рендер шаблонів.

Службові сторінки `/ui/…` доступні тільки при DEBUG — це «вітрина» для розробки.
"""
from django.conf import settings
from django.http import Http404
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
    from .templatetags.ui import ICONS
    sec_chips = [(1, "I", "Натуральні числа"), (2, "I", "Додавання і віднімання"), (3, "I", "Множення і ділення"),
                 (4, "II", "Звичайні дроби"), (5, "II", "Десяткові дроби")]
    return render(request, "education/ui_kit.html", {"icons": sorted(ICONS), "sec_chips": sec_chips})


def progress_page(request):
    """`/progress/` — заглушка вкладки «Прогрес» (рішення 2026-10-08; повний екран — беклог)."""
    return render(request, "education/stub_page.html", {
        "stub_icon": "chart",
        "stub_title": "Прогрес",
        "stub_text": "Скоро тут буде твій прогрес: зірки за кожен острів і бали за тиждень.",
    })


def profile_page(request):
    """`/profile/` — заглушка вкладки «Профіль»: ім’я і вхід/вихід уже працюють."""
    return render(request, "education/stub_page.html", {
        "stub_icon": "user",
        "stub_title": "Профіль",
        "stub_text": "Скоро тут будуть налаштування і нагороди за серію днів.",
        "show_account": True,
    })


def ui_api(request):
    """`/ui/api/` — відповіді API-клієнта й normalizeMap() (реальний бекенд або ?mock=1)."""
    _debug_only()
    return render(request, "education/ui_api.html")


def grade_map_page(request, number):
    """`/grades/<n>/` — мапа-архіпелаг класу (фаза 8). Дані малює js/map.js з /api/grades/<n>/map/."""
    from django.shortcuts import get_object_or_404
    from .models import Grade
    grade = get_object_or_404(Grade, number=number, subject__code="math")
    return render(request, "education/map.html", {"grade": grade, "current_grade": grade.number})


def _grade_cards():
    """Картки класів для екрана «Світ»: дані з БД (кількість островів і уроків, автор)."""
    from .models import Grade, Item, Paragraph
    from .templatetags.ui import _short_author
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
    """`/` — «Світ»: вибір класу (фаза 12). Старий список класів — при NEW_UI=0."""
    if not getattr(settings, "NEW_UI", False):
        from .views import grade_list
        return grade_list(request)
    cards = _grade_cards()
    fog_from = (max(c["number"] for c in cards) + 1) if cards else 5
    return render(request, "education/world.html", {"cards": cards, "fog_from": fog_from, "show_fog": fog_from <= 9})


def lesson_page(request, item):
    """`/items/<id>/` у новому UI (фаза 13): теорія й вправи уроку кольором острова.

    Викликається з views.item_detail, коли NEW_UI увімкнено. Відповіді й позначки «перевірити» —
    лише для персоналу (is_staff): діти бачать умови, а не відповіді.
    """
    from .models import Paragraph
    from .services import playable_counts
    from .views import _blocks_context, _item_title

    paragraph = item.paragraph
    section = paragraph.section
    grade = section.grade
    order = list(Paragraph.objects.filter(section__grade=grade)
                 .order_by("section__number", "number").values_list("id", flat=True))
    isl = (order.index(paragraph.id) % 5) + 1 if paragraph.id in order else 1

    stars = 0
    from .game import get_player
    player = get_player(request, create=False)
    if player is not None:
        prog = player.progress.filter(item=item).first()
        stars = prog.stars if prog else 0

    playable = playable_counts([item]).get(item.id, 0)
    import re
    return render(request, "education/lesson.html", {
        "item": item,
        "title": re.sub(r"^\s*\d+\.\s*", "", _item_title(item, "uk")),
        "paragraph": paragraph,
        "paragraph_title": re.sub(r"^§\s*\d+\.\s*", "", paragraph.name_uk),
        "section": section,
        "grade": grade,
        "current_grade": grade.number,
        "isl": isl,
        "stars": stars,
        "playable": playable,
        "blocks": _blocks_context(item),
        "staff": request.user.is_staff,
    })
