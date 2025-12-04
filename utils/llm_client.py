import requests
import base64
import os

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "bakllava"


def send_llm_prompt(prompt: str, image_path: str = None, model: str = DEFAULT_MODEL, max_tokens: int = 600) -> str:
    """
    Відправляє текстовий або мультимедійний prompt до локальної LLM (через Ollama)

    :param prompt: Текстовий prompt для LLM
    :param image_path: Шлях до зображення, якщо потрібно
    :param model: Назва моделі Ollama (за замовчуванням bakllava)
    :param max_tokens: Максимальна довжина відповіді
    :return: Відповідь моделі або повідомлення про помилку
    """

    data = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }

    # Додаємо зображення, якщо вказано
    if image_path:
        if not os.path.exists(image_path):
            return f"⚠️ Зображення не знайдено: {image_path}"

        try:
            with open(image_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode("utf-8")
                data["images"] = [img_data]
        except Exception as e:
            return f"❌ Помилка при читанні зображення: {e}"

    try:
        response = requests.post(OLLAMA_URL, json=data)
        response.raise_for_status()
        return response.json().get("response", "").strip()

    except requests.exceptions.ConnectionError:
        return "🚫 Не вдалося підключитися до Ollama. Перевір, чи запущено: `ollama run bakllava`"

    except requests.exceptions.HTTPError as e:
        return f"❌ HTTP-помилка: {e}"

    except Exception as e:
        return f"❌ Невідома помилка: {e}"
