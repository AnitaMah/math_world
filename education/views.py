# education/views.py
from urllib.parse import urlencode

from django.conf import settings
from django.shortcuts import get_object_or_404, render

from education.models import Grade, Item, Paragraph, Section, TheoryPractice
from utils.geometry import is_geometry_topic

LANG_LABELS = {"uk": "Українська", "de": "Deutsch"}

UI_COPY = {
    "uk": {
        "title": "MINT Game — Математичний світ для дітей",
        "lead": (
            "Інтерактивна мандрівка для учнів різних класів: починаємо зі змісту, "
            "щоб діти бачили, куди рухатися далі."
        ),
        "toc_title": "Зміст (UI)",
        "toc_lead": "UI починається зі змісту: оберіть клас, щоб побачити теми і параграфи.",
        "sections_label": "теми / розділи",
        "cta": {
            "title": "Готові почати?",
            "body": "Перейдіть до списку класів, щоб обрати конкретний розділ і параграф.",
            "button": "Переглянути класи",
        },
        "cta_note": "UI (інтерфейс користувача) починається зі змісту: оберіть клас, розділ і параграф.",
        "language_label": "Мова",
    },
    "de": {
        "title": "MINT Game – Mathematische Welt für Kinder",
        "lead": (
            "Eine spielerische Reise durch Mathethemen. Zuerst sehen Kinder den Inhalt, "
            "dann öffnen sich passende Übungen und Aufgaben."
        ),
        "toc_title": "Inhaltsverzeichnis (UI)",
        "toc_lead": "Das UI beginnt mit dem Inhaltsverzeichnis: Wähle eine Klasse, um Themen und Abschnitte zu sehen.",
        "sections_label": "Themen / Abschnitte",
        "cta": {
            "title": "Bereit zu starten?",
            "body": "Gehe zur Klassenübersicht, um einen Abschnitt und Paragraph auszuwählen.",
            "button": "Klassen ansehen",
        },
        "cta_note": "Das UI beginnt mit dem Inhaltsverzeichnis: Wähle Klasse, Abschnitt und Paragraph.",
        "language_label": "Sprache",
    },
}

LIST_COPY = {
    "uk": {
        "grade_title": "Список класів",
        "grade_lead": "Оберіть клас, щоб перейти до змісту тем і параграфів.",
        "sections": "Розділи",
        "paragraphs": "Параграфи",
        "items": "Пункти",
        "open": "Відкрити",
        "back": "Назад",
    },
    "de": {
        "grade_title": "Klassenübersicht",
        "grade_lead": "Wähle eine Klasse, um Themen und Paragraphen zu öffnen.",
        "sections": "Abschnitte",
        "paragraphs": "Paragraphen",
        "items": "Punkte",
        "open": "Öffnen",
        "back": "Zurück",
    },
}


def _get_lang(request):
    lang = request.GET.get("lang", "uk")
    return "de" if lang == "de" else "uk"


# -------------------------------------------------------
# 1. Список класів
# -------------------------------------------------------

def mint_overview(request):
    lang = _get_lang(request)


    content = UI_COPY[lang]
    grades = (
        Grade.objects.order_by("number")
        .prefetch_related(
            "section_set__paragraph_set__item_set",
        )
    )

    grade_cards = []
    for grade in grades:
        grade_name = grade.name_de if lang == "de" and grade.name_de else grade.name_uk
        grade_name = grade_name or f"{grade.number}"
        theme = (
            grade.theme_de
            if lang == "de" and grade.theme_de
            else grade.theme_uk
        ) or grade_name

        sections = []
        for section in grade.section_set.all().order_by("number"):
            section_title = (
                section.name_de
                if lang == "de" and section.name_de
                else section.name_uk
            )
            paragraphs = []
            for paragraph in section.paragraph_set.all().order_by("number"):
                paragraph_title = (
                    paragraph.name_de
                    if lang == "de" and paragraph.name_de
                    else paragraph.name_uk
                )

                paragraph_items = []
                for item in paragraph.item_set.all().order_by("number"):
                    item_text = (
                        item.content_de
                        if lang == "de" and item.content_de
                        else item.content
                    )
                    if not item_text:
                        continue

                    lines = [line.strip().lstrip("• ") for line in item_text.splitlines() if line.strip()]
                    if not lines:
                        continue

                    paragraph_items.append(
                        {
                            "number": item.number,
                            "title": lines[0],
                            "details": lines[1:],
                        }
                    )

                paragraphs.append(
                    {
                        "number": paragraph.number,
                        "title": paragraph_title,
                        "items": paragraph_items,
                    }
                )
                grade_cards.append(
                    {
                        "grade": grade_name,
                        "theme": theme,
                        "sections": sections,
                    }
                )

            sections.append({"title": section_title, "paragraphs": paragraphs})

        grade_cards.append({
            "grade": grade_name,
            "theme": theme,
            "sections": sections,
        })

    other_lang = "uk" if lang == "de" else "de"
    toggle_query = urlencode({"lang": other_lang})
    lang_labels = {"uk": "Українська", "de": "Deutsch"}

    return render(
        request,
        "education/mint_overview.html",
        {
            "lang": lang,
            "content": content,
            "grades": grade_cards,
            "toggle_query": toggle_query,
            "other_lang": other_lang,
            "current_lang_label": LANG_LABELS[lang],
            "other_lang_label": LANG_LABELS[other_lang],
        },
    )




def grade_list(request):
    lang = _get_lang(request)
    content = LIST_COPY[lang]
    grades = (
        Grade.objects.all()
        .order_by("number")
        .prefetch_related("section_set__paragraph_set__item_set")
    )

    grade_cards = []
    for grade in grades:
        grade_name = grade.name_de if lang == "de" and grade.name_de else grade.name_uk
        theme = grade.theme_de if lang == "de" and grade.theme_de else grade.theme_uk
        sections = grade.section_set.all()
        grade_cards.append(
            {
                "id": grade.id,
                "grade": grade_name,
                "theme": theme or grade_name,
                "sections_count": sections.count(),
            }
        )

    other_lang = "uk" if lang == "de" else "de"
    toggle_query = urlencode({"lang": other_lang})

    return render(
        request,
        "education/grade_list.html",
        {
            "lang": lang,
            "grades": grade_cards,
            "content": content,
            "toggle_query": toggle_query,
            "current_lang_label": LANG_LABELS[lang],
            "other_lang_label": LANG_LABELS[other_lang],
        },
    )


# -------------------------------------------------------
# 2. Список розділів конкретного класу
# -------------------------------------------------------

def section_list(request, grade_id):
    grade = get_object_or_404(Grade, id=grade_id)
    sections = (
        Section.objects.filter(grade=grade)
        .order_by("number")
        .prefetch_related("paragraph_set__item_set")
    )

    lang = _get_lang(request)
    grade_name = grade.name_de if lang == "de" and grade.name_de else grade.name_uk
    content = LIST_COPY[lang]

    section_cards = []
    for section in sections:
        title = section.name_de if lang == "de" and section.name_de else section.name_uk
        section_cards.append(
            {
                "id": section.id,
                "title": title,
                "paragraphs_count": section.paragraph_set.count(),
            }
        )

    other_lang = "uk" if lang == "de" else "de"
    toggle_query = urlencode({"lang": other_lang})

    return render(
        request,
        "education/section_list.html",
        {
            "lang": lang,
            "grade": grade_name,
            "content": content,
            "sections": section_cards,
            "toggle_query": toggle_query,
            "current_lang_label": LANG_LABELS[lang],
            "other_lang_label": LANG_LABELS[other_lang],
            "grade_id": grade.id,
        },
    )


# -------------------------------------------------------
# 3. Список параграфів конкретного розділу
# -------------------------------------------------------

def paragraph_list(request, section_id):
    section = get_object_or_404(Section, id=section_id)
    paragraphs = Paragraph.objects.filter(section=section).order_by("number")
    paragraphs = (
        Paragraph.objects.filter(section=section)
        .order_by("number")
        .prefetch_related("item_set")
    )

    lang = _get_lang(request)
    section_title = section.name_de if lang == "de" and section.name_de else section.name_uk
    content = LIST_COPY[lang]

    paragraph_cards = []
    for paragraph in paragraphs:
        title = paragraph.name_de if lang == "de" and paragraph.name_de else paragraph.name_uk
        paragraph_cards.append(
            {
                "id": paragraph.id,
                "title": title,
                "items_count": paragraph.item_set.count(),
                "number": paragraph.number,
            }
        )

    other_lang = "uk" if lang == "de" else "de"
    toggle_query = urlencode({"lang": other_lang})

    return render(
        request,
        "education/paragraph_list.html",
        {
            "lang": lang,
            "section": section_title,
            "content": content,
            "paragraphs": paragraph_cards,
            "toggle_query": toggle_query,
            "current_lang_label": LANG_LABELS[lang],
            "other_lang_label": LANG_LABELS[other_lang],
            "section_id": section.id,
            "grade_id": section.grade.id,
        },
    )


# -------------------------------------------------------
# 4. Список пунктів конкретного параграфу
# -------------------------------------------------------

def item_list(request, paragraph_id):
    paragraph = get_object_or_404(Paragraph, id=paragraph_id)
    items = Item.objects.filter(paragraph=paragraph).order_by("number")
    return render(request, "education/item_list.html", {
        "paragraph": paragraph,
        "items": items
    })


# -------------------------------------------------------
# 5. Перегляд конкретного пункту + теорія + практика
# -------------------------------------------------------

def item_detail(request, item_id):
    item = get_object_or_404(Item, id=item_id)
    tp = TheoryPractice.objects.filter(item=item).first()

    is_geometry = is_geometry_topic(item.content)
    return render(
        request,
        "education/item_detail.html",
        {
            "item": item,
            "tp": tp,
            "is_geometry": is_geometry,
            "media_url": settings.MEDIA_URL,
        },
    )