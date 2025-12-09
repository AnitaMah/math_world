import json
from django.core.management.base import BaseCommand
from education.models import Section, Paragraph

class Command(BaseCommand):
    help = "Генерує education/static/education/map_data_uk.json з моделей"

    def handle(self, *args, **options):
        nodes = []
        links = []

        # Розділи
        for section in Section.objects.all():
            if section.map_x is not None and section.map_y is not None:
                nodes.append({
                    "id": f"s{section.id}",
                    "name": section.name,
                    "x": section.map_x,
                    "y": section.map_y,
                    "color": "#81c784",
                    "url": f"/education/section/{section.id}/"
                })

        # Параграфи
        for paragraph in Paragraph.objects.all():
            if paragraph.map_x is not None and paragraph.map_y is not None:
                nodes.append({
                    "id": f"p{paragraph.id}",
                    "name": paragraph.name,
                    "x": paragraph.map_x,
                    "y": paragraph.map_y,
                    "color": "#ffd54f",
                    "url": f"/education/paragraph/{paragraph.id}/"
                })
                if paragraph.section_id:
                    links.append({
                        "from": f"s{paragraph.section_id}",
                        "to": f"p{paragraph.id}"
                    })

        # Зберігаємо JSON
        map_data = {"nodes": nodes, "links": links}
        with open("education/static/education/map_data_uk.json", "w", encoding="utf-8") as f:
            json.dump(map_data, f, ensure_ascii=False, indent=2)

        self.stdout.write(self.style.SUCCESS("✅ Файл map_data_uk.json згенеровано з бази даних."))