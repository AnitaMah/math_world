import requests
import base64
import os

LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"
DEFAULT_MODEL = "mamaylm-gemma-3-12b-it-v1.0-i1"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 600

# LLM_BACKEND=lmstudio (default, requires LM Studio running locally on
# LM_STUDIO_URL) or LLM_BACKEND=gemini (cloud, free tier -- see
# scripts/gemini_client.py, Step 27 of the refactor plan). Every existing
# caller of send_llm_prompt() keeps working unchanged either way.
LLM_BACKEND = os.environ.get("LLM_BACKEND", "lmstudio")


def send_llm_prompt(prompt: str, image_path: str = None, model: str = DEFAULT_MODEL,
                    temperature: float = DEFAULT_TEMPERATURE, max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
    """
    Надсилає prompt до LLM. Бекенд обирається змінною середовища
    LLM_BACKEND: "lmstudio" (за замовчуванням, локальна LM Studio) або
    "gemini" (хмарний, безкоштовний рівень -- scripts/gemini_client.py).

    :param prompt: Текстовий запит
    :param image_path: (необов’язково) шлях до зображення, якщо потрібен multimodal input
    :param model: Назва моделі (ігнорується для gemini-бекенду -- див. GEMINI_MODEL у .env)
    :param temperature: Креативність моделі (ігнорується для gemini-бекенду)
    :param max_tokens: Максимальна довжина відповіді (ігнорується для gemini-бекенду)
    :return: Текст відповіді або повідомлення про помилку
    """
    if LLM_BACKEND == "gemini":
        return _send_gemini_prompt(prompt, image_path)

    messages = [{"role": "user", "content": prompt}]

    # Додаємо зображення (якщо потрібно і файл існує)
    if image_path:
        if not os.path.exists(image_path):
            return f"⚠️ Зображення не знайдено: {image_path}"

        try:
            with open(image_path, "rb") as img_file:
                encoded_image = base64.b64encode(img_file.read()).decode("utf-8")
                messages[0]["images"] = [encoded_image]
        except Exception as e:
            return f"❌ Помилка при зчитуванні зображення: {e}"

    # Підготовка даних до запиту
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False
    }

    try:
        response = requests.post(LM_STUDIO_URL, json=payload)
        response.raise_for_status()

        # Дістаємо першу відповідь моделі
        reply = response.json()["choices"][0]["message"]["content"].strip()
        return reply

    except requests.exceptions.ConnectionError:
        return "🚫 Помилка з'єднання: Переконайся, що LM Studio запущений локально."

    except requests.exceptions.HTTPError as e:
        return f"❌ HTTP-помилка: {e.response.status_code} - {e.response.text}"

    except KeyError:
        return "❌ Помилка: Модель не повернула очікувану структуру відповіді."

    except Exception as e:
        return f"❌ Невідома помилка: {e}"


def _send_gemini_prompt(prompt: str, image_path: str = None) -> str:
    """
    Gemini-бекенд для send_llm_prompt(). Використовує кешуючий клієнт із
    scripts/gemini_client.py (Step 27), тому повторний виклик з тим самим
    prompt/зображенням не витрачає денну квоту повторно.
    """
    try:
        from scripts.gemini_client import GeminiClient, GeminiBudgetExceeded
    except ImportError as e:
        return f"❌ Не вдалося завантажити Gemini-клієнт: {e}"

    try:
        client = GeminiClient()
        if image_path:
            if not os.path.exists(image_path):
                return f"⚠️ Зображення не знайдено: {image_path}"
            return client.generate_from_image(image_path, prompt)
        return client.generate_text(prompt)
    except GeminiBudgetExceeded as e:
        return f"🚫 {e}"
    except Exception as e:
        return f"❌ Помилка Gemini: {e}"
