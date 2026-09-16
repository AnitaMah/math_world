from pathlib import Path
import json

from django.conf import settings
from django.shortcuts import render, get_object_or_404

from .models import Grade, Section, Paragraph, Item, TheoryPractice


# -------------------------
#   🔧 СЕРВІСНА ФУНКЦІЯ
# -------------------------

def load_map_data():
    """
    Завантажує JSON з мапою, якщо файл існує. Мапа -- візуальний бонус
    поверх звичайних списків нижче, тому відсутність файлу чи картинки
    не повинна ламати сторінку (шаблон рендерить її як необов'язковий
    оверлей).
    """
    json_path = Path(__file__).resolve().parent / "static" / "education" / "map_data_uk.json"
    if json_path.exists():
        with json_path.open(encoding="utf-8") as f:
            return json.load(f)
    return {"nodes": [], "links": []}


def _lang(request):
    return "de" if request.GET.get("lang") == "de" else "uk"


def _base_context(request, **extra):
    lang = _lang(request)
    context = {
        "lang": lang,
        "current_lang_label": "Українська" if lang == "uk" else "Deutsch",
        "other_lang_label": "Deutsch" if lang == "uk" else "Українська",
        "toggle_query": f"lang={'de' if lang == 'uk' else 'uk'}",
        "map_data": load_map_data(),
        "show_links": True,
    }
    context.update(extra)
    return context


# -------------------------
#   📘 СПИСОК КЛАСІВ
# -------------------------

def grade_list(request):
    lang = _lang(request)
    grades = list(Grade.objects.select_related("subject").order_by("number"))

    context = _base_context(
        request,
        content={
            "grade_title": "Класи",
            "grade_lead": "Оберіть клас для перегляду тем",
        },
        grades=[
            {
                "id": g.id,
                "number": g.number,
                "name": g.get_name(lang),
                "subject": g.subject.name_de if lang == "de" and g.subject.name_de else g.subject.name_uk,
            }
            for g in grades
        ],
    )
    return render(request, "education/grade_list.html", context)


# -------------------------
#   📚 СПИСОК РОЗДІЛІВ
# -------------------------

def section_list(request, grade_id):
    lang = _lang(request)
    grade = get_object_or_404(Grade, pk=grade_id)
    sections = Section.objects.filter(grade=grade).order_by("number")

    context = _base_context(
        request,
        grade=grade.get_name(lang),
        grade_id=grade.id,
        sections=[
            {"id": s.id, "number": s.number, "name": s.get_name(lang)} for s in sections
        ],
        content={"sections": "Розділи", "back": "Назад"},
    )
    return render(request, "education/section_list.html", context)


# -------------------------
#   📄 СПИСОК ПАРАГРАФІВ
# -------------------------

def paragraph_list(request, section_id):
    lang = _lang(request)
    section = get_object_or_404(Section, pk=section_id)
    paragraphs = Paragraph.objects.filter(section=section).order_by("number")

    context = _base_context(
        request,
        section=section.get_name(lang),
        section_id=section.id,
        grade_id=section.grade_id,
        paragraphs=[
            {"id": p.id, "number": p.number, "name": p.get_name(lang)} for p in paragraphs
        ],
        content={"paragraphs": "Параграфи", "back": "Назад"},
    )
    return render(request, "education/paragraph_list.html", context)


# -------------------------
#   📝 СПИСОК ЗАВДАНЬ
# -------------------------

def item_list(request, paragraph_id):
    lang = _lang(request)
    paragraph = get_object_or_404(Paragraph, pk=paragraph_id)
    items = Item.objects.filter(paragraph=paragraph).order_by("number")

    context = _base_context(
        request,
        paragraph=paragraph.get_name(lang),
        paragraph_id=paragraph.id,
        section_id=paragraph.section_id,
        grade_id=paragraph.section.grade_id,
        items=[
            {"id": i.id, "number": i.number, "details": i.details_list(lang)}
            for i in items
        ],
        content={"items": "Завдання", "back": "Назад"},
    )
    return render(request, "education/item_list.html", context)


# -------------------------
#   📘 ДЕТАЛІ ЗАВДАННЯ
# -------------------------

def item_detail(request, item_id):
    lang = _lang(request)
    item = get_object_or_404(Item, pk=item_id)
    paragraph = item.paragraph

    try:
        tp = TheoryPractice.objects.get(item=item)
    except TheoryPractice.DoesNotExist:
        tp = None

    blocks_by_type = {}
    for block in item.content_blocks.all():
        blocks_by_type.setdefault(block.block_type, []).append(block)

    context = _base_context(
        request,
        paragraph=paragraph.get_name(lang),
        paragraph_id=paragraph.id,
        section_id=paragraph.section_id,
        grade_id=paragraph.section.grade_id,
        item={
            "id": item.id,
            "number": item.number,
            "details": item.details_list(lang),
        },
        tp=tp,
        blocks_by_type=blocks_by_type,
        media_url=settings.MEDIA_URL,
        content={"items": "Деталі завдання", "back": "Назад"},
    )
    return render(request, "education/item_detail.html", context)
