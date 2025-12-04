# llm_worker.py

import os
import django

# 🔹 ПЕРШЕ: Ініціалізуємо Django ще ДО ІМПОРТІВ моделей!
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "math_world.settings")
django.setup()

# 🔹 Тепер можна імпортувати моделі та Celery
from celery import Celery
from education.models import Item, TheoryPractice
from utils.llm_client import send_llm_prompt
import sqlite3

# 🔹 Створюємо Celery app
app = Celery("llm_worker", broker="redis://localhost:6379/0")

@app.task
def generate_theory_practice_task(item_id, item_name):
    print(f"🛠 Генерація для: {item_name} (ID: {item_id})")

    try:
        item = Item.objects.get(id=item_id)

        theory = send_llm_prompt(f"Поясни коротко: {item.content}")
        practice = send_llm_prompt(f"Дай просту практичну задачу до теми: {item.content}")

        tp, _ = TheoryPractice.objects.get_or_create(item=item)
        tp.theory = theory
        tp.practice = practice
        tp.save()

        with sqlite3.connect("../tasks.db") as conn:
            conn.execute("UPDATE task_queue SET status='done' WHERE item_id=?", (item_id,))

        print("✅ Успішно!")

    except Exception as e:
        print("❌ Помилка:", e)
        with sqlite3.connect("../tasks.db") as conn:
            conn.execute("UPDATE task_queue SET status='error' WHERE item_id=?", (item_id,))
