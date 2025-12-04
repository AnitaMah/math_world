from __future__ import annotations

from pathlib import Path
from typing import Iterable

from django.conf import settings

# Базові слова для виявлення геометричного контексту (укр/нім)
GEOMETRY_KEYWORDS: Iterable[str] = (
    "геометр",
    "кут",
    "пряма",
    "промінь",
    "відрізок",
    "трикут",
    "прямокут",
    "квадрат",
    "коло",
    "радіус",
    "діаметр",
    "окружн",
    "многокут",
    "площа",
    "периметр",
    "trapez",
    "winkel",
    "kreis",
    "dreieck",
    "rechteck",
    "linie",
)


def is_geometry_topic(text: str | None) -> bool:
    """Перевіряє, чи є задача геометричною за ключовими словами."""

    if not text:
        return False
    lowered = text.lower()
    return any(keyword in lowered for keyword in GEOMETRY_KEYWORDS)


def build_geometry_prompt(task_text: str) -> str:
    """Створює prompt для Ollama (bakllava), щоб повернути мінімалістичний SVG."""

    return (
        "Ти допомагаєш учням візуалізувати геометричні задачі. "
        "Побудуй простий SVG (width=512, height=320) з базових фігур: line, circle, rect, "
        "polygon, polyline та текстові підписи для ключових точок. Без зображень чи base64. "
        "Поверни ЛИШЕ SVG без пояснень. "
        f"Контекст задачі: {task_text}"
    )


def save_svg_diagram(svg_markup: str, item_id: int) -> str | None:
    """Зберігає SVG у media/generated та повертає шлях відносно MEDIA_ROOT."""

    if "<svg" not in svg_markup.lower():
        return None

    target_dir = Path(settings.MEDIA_ROOT) / "generated"
    target_dir.mkdir(parents=True, exist_ok=True)

    path = target_dir / f"item_{item_id}.svg"
    path.write_text(svg_markup, encoding="utf-8")
    return str(path.relative_to(settings.MEDIA_ROOT))
