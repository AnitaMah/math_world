from __future__ import annotations

from pathlib import Path
from typing import Iterable
from django.conf import settings

GEOMETRY_KEYWORDS: Iterable[str] = (
    "геометр", "кут", "пряма", "промінь", "відрізок", "трикут",
    "прямокут", "квадрат", "коло", "радіус", "діаметр", "окружн",
    "многокут", "площа", "периметр", "trapez", "winkel", "kreis",
    "dreieck", "rechteck", "linie",
)


def is_geometry_topic(text: str | None) -> bool:
    """Чи задача має геометричний характер (укр/нім)."""
    if not text:
        return False
    lowered = text.lower()
    return any(keyword in lowered for keyword in GEOMETRY_KEYWORDS)


def build_geometry_prompt(task_text: str) -> str:
    """
    Prompt для SDXL або іншої text-to-image моделі (наприклад HuggingFace Diffusers).
    """
    return (
        "Minimalistic vector-style geometry diagram, clean white background, "
        "black thin lines, schematic illustration. "
        f"Topic: {task_text}. Educational math image."
    )


def save_image_diagram(image, item_id: int) -> str:
    """
    Зберігає PIL Image у media/generated/item_{id}.png
    """
    target_dir = Path(settings.MEDIA_ROOT) / "generated"
    target_dir.mkdir(parents=True, exist_ok=True)

    file_path = target_dir / f"item_{item_id}.png"
    image.save(file_path)
    return str(file_path.relative_to(settings.MEDIA_ROOT))


def save_svg_diagram(svg_markup: str | None, item_id: int) -> str | None:
    """
    Зберігає текстову SVG-розмітку (повернуту LLM) у
    media/generated/item_{id}.svg. Раніше `llm_worker.py` імпортував цю
    функцію, якої не існувало (був лише `save_image_diagram`, який очікує
    PIL Image, а не текст) -- це викликало ImportError одразу при старті
    Celery worker'а. Якщо модель не повернула схожого на SVG тексту,
    нічого не зберігаємо і повертаємо None (виклик у llm_worker.py вже
    очікує на такий випадок).
    """
    if not svg_markup or "<svg" not in svg_markup.lower():
        return None

    target_dir = Path(settings.MEDIA_ROOT) / "generated"
    target_dir.mkdir(parents=True, exist_ok=True)

    file_path = target_dir / f"item_{item_id}.svg"
    file_path.write_text(svg_markup, encoding="utf-8")
    return str(file_path.relative_to(settings.MEDIA_ROOT))
