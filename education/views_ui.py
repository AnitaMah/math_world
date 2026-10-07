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
