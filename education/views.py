# education/views.py

from django.shortcuts import render, get_object_or_404
from education.models import Grade, Section, Paragraph, Item, TheoryPractice


# -------------------------------------------------------
# 1. Список класів
# -------------------------------------------------------

def grade_list(request):
    grades = Grade.objects.all().order_by("number")
    return render(request, "education/grade_list.html", {"grades": grades})


# -------------------------------------------------------
# 2. Список розділів конкретного класу
# -------------------------------------------------------

def section_list(request, grade_id):
    grade = get_object_or_404(Grade, id=grade_id)
    sections = Section.objects.filter(grade=grade).order_by("number")
    return render(request, "education/section_list.html", {
        "grade": grade,
        "sections": sections
    })


# -------------------------------------------------------
# 3. Список параграфів конкретного розділу
# -------------------------------------------------------

def paragraph_list(request, section_id):
    section = get_object_or_404(Section, id=section_id)
    paragraphs = Paragraph.objects.filter(section=section).order_by("number")
    return render(request, "education/paragraph_list.html", {
        "section": section,
        "paragraphs": paragraphs
    })


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

    return render(request, "education/item_detail.html", {
        "item": item,
        "tp": tp
    })
