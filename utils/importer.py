from education.models import Grade, Section, Paragraph, Item
from archive.task_queue import add_all_items_to_queue, create_task_table
from utils.curriculum_loader import read_curriculum
from utils.helpers import roman_to_int

def import_curriculum_to_db(filepath="data/5_class_ukr.txt", grade_number=5, grade_name="Математика 5 клас"):
    create_task_table()
    text = read_curriculum(filepath)
    lines = text.strip().split('\n')

    current_grade = Grade.objects.create(number=grade_number, name_uk=grade_name)
    current_section = current_paragraph = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith("Розділ"):
            roman, name = line.split(". ", 1)
            num = roman_to_int(roman.replace("Розділ ", ""))
            current_section = Section.objects.create(grade=current_grade, number=num, name_uk=name)
            continue

        if line.startswith("§"):
            _, rest = line.split("§", 1)
            num, name = rest.strip().split(". ", 1)
            current_paragraph = Paragraph.objects.create(section=current_section, number=int(num), name_uk=name)
            continue

        if line[0].isdigit() and ". " in line:
            num, content = line.split(". ", 1)
            Item.objects.create(paragraph=current_paragraph, number=int(num), content=content)
    print("📘 Навчальна програма імпортована до бази даних.")

    # ✅ Ось цей виклик:
    add_all_items_to_queue()
