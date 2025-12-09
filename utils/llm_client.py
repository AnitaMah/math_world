import requests
import base64
import os

LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"
DEFAULT_MODEL = "mamaylm-gemma-3-12b-it-v1.0-i1"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 600


def send_llm_prompt(prompt: str, image_path: str = None, model: str = DEFAULT_MODEL,
                    temperature: float = DEFAULT_TEMPERATURE, max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
    """
    Надсилає prompt до локальної LLM через LM Studio API. Підтримує як текстові, так і мультимодальні моделі.

    :param prompt: Текстовий запит
    :param image_path: (необов’язково) шлях до зображення, якщо потрібен multimodal input
    :param model: Назва моделі, яку використовує LM Studio
    :param temperature: Креативність моделі
    :param max_tokens: Максимальна довжина відповіді
    :return: Текст відповіді або повідомлення про помилку
    """

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
