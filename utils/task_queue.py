import sqlite3
from education.models import Item

def create_task_table():
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            item_name TEXT,
            status TEXT
        )
    """)
    conn.commit()
    conn.close()
    print("🆕 Таблиця task_queue створена (якщо ще не існувала).")

def add_task(item_id, item_name):
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO task_queue (item_id, item_name, status)
        VALUES (?, ?, ?)
    """, (item_id, item_name, "pending"))
    conn.commit()
    conn.close()

def add_all_items_to_queue():
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()

    for item in Item.objects.all():
        cursor.execute("""
            INSERT INTO task_queue (item_id, item_name, status)
            VALUES (?, ?, ?)
        """, (item.id, item.content, "pending"))

    conn.commit()
    conn.close()
    print("✅ Усі Item додані в чергу (task_queue)")
