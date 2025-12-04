# llm_worker.py

import os
import sqlite3

import django

# 🔹 ПЕРШЕ: Ініціалізуємо Django ще ДО ІМПОРТІВ моделей!
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "math_world.settings")
django.setup()

# 🔹 Тепер можна імпортувати моделі та Celery
from celery import Celery
from django.conf import settings

from education.models import Item, TheoryPractice
from utils.geometry import (
    build_geometry_prompt,
    is_geometry_topic,
    save_svg_diagram,
)
from utils.llm_client import send_llm_prompt

# 🔹 Створюємо Celery app
app = Celery("llm_worker", broker="redis://localhost:6379/0")

@app.task
def generate_theory_practice_task(item_id, item_name):
    print(f"🛠 Генерація для: {item_name} (ID: {item_id})")

    try:
        item = Item.objects.get(id=item_id)

        theory = send_llm_prompt(f"Поясни коротко: {item.content}")
        practice = send_llm_prompt(f"Дай просту практичну задачу до теми: {item.content}")

        geometry_diagram = None
        if is_geometry_topic(item.content):
            svg_prompt = build_geometry_prompt(item.content)
            svg_markup = send_llm_prompt(svg_prompt)
            geometry_diagram = save_svg_diagram(svg_markup, item.id)
            if geometry_diagram:
                print(f"🖼 Збережено геометричний ескіз: {geometry_diagram}")
            else:
                print("ℹ️ Модель не повернула SVG, ескіз не збережено")

        tp, _ = TheoryPractice.objects.get_or_create(item=item)
        tp.theory = theory
        tp.practice = practice
        if geometry_diagram and not tp.image_path:
            tp.image_path = geometry_diagram
        tp.save()

        if geometry_diagram and not item.image_path:
            item.image_path = geometry_diagram
            item.save(update_fields=["image_path"])

        with sqlite3.connect("tasks.db") as conn:
            conn.execute("UPDATE task_queue SET status='done' WHERE item_id=?", (item_id,))

        print("✅ Успішно!")

    except Exception as e:
        print("❌ Помилка:", e)
        with sqlite3.connect("tasks.db") as conn:
            conn.execute("UPDATE task_queue SET status='error' WHERE item_id=?", (item_id,))
