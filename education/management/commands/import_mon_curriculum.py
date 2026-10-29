"""Створює розділи/параграфи МОН-програми для одного класу (без підручника).

    python manage.py import_mon_curriculum --grade 5
    python manage.py import_mon_curriculum --grade 6

Замінює import_mon_grade5 / import_mon_grade6 (byte-for-byte той самий вміст і логіка
-- об'єднано тим самим способом, що й demo_mon_grade*_section* -> demo_mon_seed: Django
не підтримує команди в підпапках management/commands/, тож два майже ідентичні файли
лише роздували папку; сам зміст програми -- education/management/mon_content/grade5.py,
grade6.py (CURRICULUM).

Джерело: офіційна навчальна програма «Математика» для 5-9 класів (модельна програма
Мерзляк А.Г. та ін.), затверджена МОН 12.07.2021 № 795, адаптована до Типової освітньої
програми в редакції наказу МОН від 09.08.2024 № 1120. Прочитано напряму з PDF (дзеркало
https://osvita.ua, бо mon.gov.ua блокує автоматизоване завантаження) -- розділи, параграфи
й години звірені з першоджерелом.
"""
import hashlib

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from education.management.mon_content import grade5, grade6
from education.models import Grade, Paragraph, Section, Subject, Textbook

CURRICULUM = {5: grade5.CURRICULUM, 6: grade6.CURRICULUM}
SEED = {5: b"mon-ua-math-grade5-2024-verified-v2", 6: b"mon-ua-math-grade6-2024-verified"}


class Command(BaseCommand):
    help = ("Створює розділи/параграфи класу за офіційною навчальною програмою МОН "
           "(Мерзляк та ін.), звіреною напряму з первинним документом.")

    def add_arguments(self, parser):
        parser.add_argument("--grade", type=int, required=True, choices=sorted(CURRICULUM))

    @transaction.atomic
    def handle(self, *args, **options):
        g = options["grade"]
        sections_data = CURRICULUM[g]
        subject, _ = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})
        grade, _ = Grade.objects.get_or_create(subject=subject, number=g, defaults={"name_uk": f"{g} клас"})

        if g == 5:
            # Прибираємо попередню нечірену чернетку (неправильні розділи/години) -- замінена цим імпортом.
            Textbook.objects.filter(profile_code="mon_grade5_draft").delete()

        sha = hashlib.sha256(SEED[g]).hexdigest()
        textbook, _ = Textbook.objects.get_or_create(
            pdf_sha256=sha,
            defaults=dict(
                subject=subject, grade=grade, profile_code=f"mon_grade{g}",
                title=f"Навчальна програма «Математика», {g} клас (МОН України)",
                author="МОН України, модельна програма Мерзляк А.Г. та ін.", year=2024,
            ),
        )
        # Повний переімпорт під цим Textbook -- без цього старі параграфи з попередніх
        # (невіряних) чернеток лишилися б осиротілими, якщо кількість параграфів змінилась.
        Section.objects.filter(textbook=textbook).delete()

        for s_idx, section_data in enumerate(sections_data, start=1):
            section = Section.objects.create(
                grade=grade, textbook=textbook, number=s_idx, name_uk=section_data["name"]
            )
            for p_idx, name in enumerate(section_data["paragraphs"], start=1):
                Paragraph.objects.create(section=section, number=p_idx, name_uk=name)

        self.stdout.write(self.style.SUCCESS(
            f"Створено {len(sections_data)} розділи, "
            f"{sum(len(s['paragraphs']) for s in sections_data)} параграфів ({g} клас, звірено з МОН)."
        ))
