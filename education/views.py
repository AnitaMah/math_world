from django.shortcuts import render, get_object_or_404
from django.http import Http404
from pathlib import Path
import json

from .models import Grade, Section, Paragraph, Item, TheoryPractice


# -------------------------
#   🔧 СЕРВІСНА ФУНКЦІЯ
# -------------------------

def load_map_data():
    """Завантажує JSON з мапою."""
    json_path = Path("education/static/education/map_data_uk.json")
    if json_path.exists():
        with json_path.open(encoding="utf-8") as f:
            return json.load(f)
    return {"nodes": [], "links": []}


# -------------------------
#   📘 СПИСОК КЛАСІВ
# -------------------------

def grade_list(request):
    grades = Grade.objects.all()

    context = {
        "content": {
            "grade_title": "Класи",
            "grade_lead": "Оберіть клас для перегляду тем"
        },
        "grades": grades,
        "lang": request.GET.get("lang", "uk"),
        "current_lang_label": "Українська",
        "other_lang_label": "Deutsch",
        "toggle_query": "lang=de",

        # МАПА
        "map_data": load_map_data(),
        "map_image": "education/img/5_class_map.png",
        "show_links": True
    }

    return render(request, "education/grade_list.html", context)


# -------------------------
#   📚 СПИСОК РОЗДІЛІВ
# -------------------------

def section_list(request, grade_id):
    grade = get_object_or_404(Grade, pk=grade_id)
    sections = Section.objects.filter(grade=grade)

    context = {
        "grade": grade.name,
        "sections": sections,
        "section_id": grade_id,     # для кнопки "Назад"
        "content": {
            "sections": "Розділи",
            "back": "Назад"
        },
        "lang": request.GET.get("lang", "uk"),
        "current_lang_label": "Українська",
        "other_lang_label": "Deutsch",
        "toggle_query": "lang=de",

        # МАПА
        "map_data": load_map_data(),
        "map_image": "education/img/5_class_map.png",
        "show_links": True
    }

    return render(request, "education/section_list.html", context)


# -------------------------
#   📄 СПИСОК ПАРАГРАФІВ
# -------------------------

def paragraph_list(request, section_id):
    section = get_object_or_404(Section, pk=section_id)
    paragraphs = Paragraph.objects.filter(section=section)

    context = {
        "section": section.name,
        "paragraphs": paragraphs,
        "section_id": section_id,
        "content": {
            "paragraphs": "Параграфи",
            "back": "Назад"
        },
        "lang": request.GET.get("lang", "uk"),
        "current_lang_label": "Українська",
        "other_lang_label": "Deutsch",
        "toggle_query": "lang=de",

        # МАПА
        "map_data": load_map_data(),
        "map_image": "education/img/5_class_map.png",
        "show_links": True
    }

    return render(request, "education/paragraph_list.html", context)


# -------------------------
#   📝 СПИСОК ЗАВДАНЬ
# -------------------------

def item_list(request, paragraph_id):
    paragraph = get_object_or_404(Paragraph, pk=paragraph_id)
    items = Item.objects.filter(paragraph=paragraph)

    context = {
        "paragraph": paragraph.name,
        "items": items,
        "section_id": paragraph.section.id,
        "content": {
            "items": "Завдання",
            "back": "Назад"
        },
        "lang": request.GET.get("lang", "uk"),
        "current_lang_label": "Українська",
        "other_lang_label": "Deutsch",
        "toggle_query": "lang=de",

        # МАПА
        "map_data": load_map_data(),
        "map_image": "education/img/5_class_map.png",
        "show_links": True
    }

    return render(request, "education/item_list.html", context)


# -------------------------
#   📘 ДЕТАЛІ ЗАВДАННЯ
# -------------------------

def item_detail(request, paragraph_id, item_id):
    paragraph = get_object_or_404(Paragraph, pk=paragraph_id)
    item = get_object_or_404(Item, pk=item_id, paragraph=paragraph)

    try:
        tp = TheoryPractice.objects.get(item=item)
    except TheoryPractice.DoesNotExist:
        tp = None

    context = {
        "paragraph": paragraph.name,
        "content": {
            "items": "Деталі завдання",
            "back": "Назад"
        },
        "items": [item],
        "tp": tp,
        "section_id": paragraph.section.id,
        "lang": request.GET.get("lang", "uk"),
        "current_lang_label": "Українська",
        "other_lang_label": "Deutsch",
        "toggle_query": "lang=de",

        # МАПА
        "map_data": load_map_data(),
        "map_image": "education/img/5_class_map.png",
        "show_links": True
    }

    return render(request, "education/item_detail.html", context)
