"""
Повний pipeline:
- Конвертація PDF → зображення
- OCR
- Витяг тексту задач
- Генерація теорії через LLM
- Збереження в базу
"""

import os
from education.models import Item, TheoryPractice
from utils.llm_client import send_llm_prompt
from pdf2image import convert_from_path
from PIL import Image
import pytesseract

# --- Налаштування ---
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
POPPLER_PATH = r"C:\Program Files\poppler-24\Library\bin"
MEDIA_IMAGE_DIR = "media/ocr_pages"
LANG = "ukr"
GRADE = 5
PDF_PATH = f"static/{GRADE}_klas_matematika.pdf"

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
os.makedirs(MEDIA_IMAGE_DIR, exist_ok=True)


def ocr_pdf(pdf_path):
    images = convert_from_path(pdf_path, dpi=300, poppler_path=POPPLER_PATH)
    pages = []
    for i, img in enumerate(images):
        image_path = os.path.join(MEDIA_IMAGE_DIR, f"page_{i+1:03}.png")
        img.save(image_path, "PNG")
        text = pytesseract.image_to_string(img, lang=LANG)
        pages.append((i + 1, text))
    return pages


def extract_context(page_text, item_text, radius=3):
    lines = page_text.splitlines()
    for i, line in enumerate(lines):
        if item_text.lower()[:10] in line.lower():
            start = max(i - radius, 0)
            end = min(i + radius + 1, len(lines))
            return "\n".join(lines[start:end])
    return ""


def generate_theory(item_text, grade, context_text):
    prompt = (
        f"Ти — вчитель математики для {grade} класу. "
        f"Створи коротке пояснення теорії на тему: «{item_text}». "
        f"Врахуй контекст з підручника:\n{context_text}"
    )
    return send_llm_prompt(prompt)


def run_pipeline():
    print(f"🔍 Обробляємо PDF: {PDF_PATH}")
    pages = ocr_pdf(PDF_PATH)

    items = Item.objects.all()
    for item in items:
        item_text = item.content.strip()
        found = False
        for page_num, page_text in pages:
            if item_text[:10].lower() in page_text.lower():
                context = extract_context(page_text, item_text)
                theory = generate_theory(item_text, GRADE, context)
                TheoryPractice.objects.update_or_create(
                    item=item,
                    defaults={"theory": theory}
                )
                print(f"✅ Теорію згенеровано для Item {item.id} (сторінка {page_num})")
                found = True
                break
        if not found:
            print(f"⚠️ Не знайдено теорії для Item {item.id}: {item_text[:50]}")


if __name__ == "__main__":
    run_pipeline()
