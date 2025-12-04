from utils.llm_client import send_llm_prompt

def generate_theory(topic: str, grade: int) -> str:
    prompt = (
        f"Ти — вчитель математики для {grade} класу. "
        f"Створи коротке пояснення теорії на тему: «{topic}». "
        f"Можеш використовувати приклади. Пиши для дітей зрозуміло та стисло."
    )
    return send_llm_prompt(prompt)

def generate_practice(topic: str, grade: int) -> str:
    prompt = (
        f"Ти — вчитель математики для {grade} класу. "
        f"Створи 3-5 практичних завдань на тему: «{topic}». "
        f"Почни з простого, потім ускладни. Наприкінці додай коротку відповідь."
    )
    return send_llm_prompt(prompt)
