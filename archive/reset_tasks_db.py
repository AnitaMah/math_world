import os
from archive.task_queue import create_task_table

if os.path.exists("../tasks.db"):
    os.remove("../tasks.db")
    print("🗑 tasks.db видалено.")

create_task_table()
print("✅ Нова база створена.")
