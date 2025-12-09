from django.core.management.base import BaseCommand
from education.models import Item, TheoryPractice
from utils.llm_client import send_llm_prompt
from utils.geometry import is_geometry_topic, build_geometry_prompt, save_image_diagram
from utils.image_generator import generate_image_from_prompt


def generate_theory_and_practice(item: Item) -> tuple[str, str]:
    """
    Генерує теорію і практику для одного Item.
    """
    prompt = (
        f"Ти створюєш навчальний контент з математики. Створи коротке пояснення до теми:\n"
        f"\"{item.content}\"\n\n"
        f"Після теорії додай практичну задачу. Наприклад:\n"
        f"Теорія: ...\nПрактика: ...\n"
        f"Пиши українською мовою. Без HTML або форматування, тільки текст."
    )

    full_text = send_llm_prompt(prompt)
    theory, practice = "", ""

    if "Практика:" in full_text:
        parts = full_text.split("Практика:", 1)
        theory = parts[0].replace("Теорія:", "").strip()
        practice = parts[1].strip()
    else:
        theory = full_text.strip()

    return theory, practice


class Command(BaseCommand):
    help = "Генерує теорію, практику та (опціонально) зображення для Item-ів"

    def handle(self, *args, **options):
        items = Item.objects.all()
        total, generated = 0, 0

        for item in items:
            total += 1
            if TheoryPractice.objects.filter(item=item).exists():
                self.stdout.write(f"🔹 Пропущено (вже є): {item.id}")
                continue

            theory, practice = generate_theory_and_practice(item)

            tp = TheoryPractice.objects.create(
                item=item,
                theory=theory,
                practice=practice
            )
            self.stdout.write(f"✅ Створено TheoryPractice для Item {item.id}")

            # Генерація зображення (якщо геометрія)
            if is_geometry_topic(item.content):
                prompt = build_geometry_prompt(item.content)
                image = generate_image_from_prompt(prompt)
                if image:
                    path = save_image_diagram(image, item.id)
                    tp.image_path = path
                    tp.save()
                    self.stdout.write(f"🖼 Збережено зображення: {path}")
                    generated += 1
                else:
                    self.stdout.write(f"⚠️ Не вдалося згенерувати зображення для Item {item.id}")

        self.stdout.write(self.style.SUCCESS(f"🎉 Усього: {total}, згенеровано нових: {generated}"))
