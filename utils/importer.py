from education.models import Grade, Section, Paragraph, Item
from utils.curriculum_loader import read_curriculum
from utils.helpers import roman_to_int

def import_curriculum_to_db(file_path: str, grade_number: int):
    data = read_curriculum(file_path)

    grade, _ = Grade.objects.get_or_create(number=grade_number)

    for section_title, paragraphs in data.items():
        section = Section.objects.create(title=section_title, grade=grade)

        for paragraph_num, (paragraph_title, items) in enumerate(paragraphs.items(), start=1):
            paragraph = Paragraph.objects.create(
                title=paragraph_title,
                number=paragraph_num,
                section=section
            )

            for item_number, item_text in enumerate(items, start=1):
                Item.objects.create(
                    paragraph=paragraph,
                    number=item_number,
                    content=item_text.strip()
                )

    print("✅ Успішно імпортовано навчальну програму до бази даних")
