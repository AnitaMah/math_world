import os
import django

# 🔧 Ініціалізація Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "math_world.settings")
django.setup()

from education.models import Item
from llm_worker import generate_theory_practice_task


def add_all_items_to_queue():
    items = Item.objects.all()
    for item in items:
        # Передаємо 2 аргументи, бо так вимагає task
        generate_theory_practice_task.delay(item.id, item.content)

        print(f"📨 Додано в чергу Item ID={item.id}: {item.content[:50]}...")


if __name__ == "__main__":
    add_all_items_to_queue()
    print("✅ Усі задачі успішно додані до черги!")
