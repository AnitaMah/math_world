from diffusers import StableDiffusionPipeline
from PIL import Image
import torch


# 🖼️ Обираємо пристрій
device = "cuda" if torch.cuda.is_available() else "cpu"

# ✅ Безпечне завантаження моделі з підтримкою fallback на float32
try:
    pipe = StableDiffusionPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype=torch.float16,
        variant="fp16"
    ).to(device)
except Exception as e:
    print(f"⚠️ FP16 не підтримується, спроба fallback на float32: {e}")
    pipe = StableDiffusionPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype=torch.float32
    ).to(device)


def generate_image_from_prompt(prompt: str, height=512, width=512) -> Image.Image | None:
    """
    Генерує зображення з текстового prompt за допомогою SDXL.
    :param prompt: Текстовий опис зображення.
    :param height: Висота зображення (512 за замовчуванням).
    :param width: Ширина зображення (512 за замовчуванням).
    :return: Об'єкт PIL.Image або None, якщо генерація не вдалася.
    """
    try:
        result = pipe(prompt=prompt, height=height, width=width).images[0]
        return result
    except Exception as e:
        print(f"❌ Помилка генерації зображення: {e}")
        return None
