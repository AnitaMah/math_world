# importer/management/commands/import_pdf_to_txt.py

from django.core.management.base import BaseCommand
from pdf2image import convert_from_path
from PIL import Image
import pytesseract
import os

# --- 🔧 Налаштування ---
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
POPPLER_PATH = r"C:\Program Files\poppler-24\Library\bin"
LANG = "ukr+eng"  # українська + англійська
MEDIA_DIR = "media/ocr_output"

class Command(BaseCommand):
    help = "📄 Розпізнає текст з PDF та зберігає .txt та .png файли з формулами, рисунками та спец. символами"

    def add_arguments(self, parser):
        parser.add_argument(
            "--grade", type=int, required=True, help="Клас, наприклад: 5"
        )

    def handle(self, *args, **options):
        grade_number = options["grade"]
        pdf_path = f"static/{grade_number}_klas_matematika.pdf"

        # Налаштування середовища
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        os.makedirs(MEDIA_DIR, exist_ok=True)

        self.stdout.write(f"📖 Обробка PDF: {pdf_path}")

        # 📸 Крок 1: Конвертація PDF у зображення
        try:
            images = convert_from_path(pdf_path, dpi=300, poppler_path=POPPLER_PATH)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Помилка конвертації PDF: {e}"))
            return

        # 🧠 Крок 2: OCR та збереження тексту/зображень
        for i, img in enumerate(images):
            page_num = i + 1
            image_path = os.path.join(MEDIA_DIR, f"page_{page_num:03}.png")
            txt_path = os.path.join(MEDIA_DIR, f"page_{page_num:03}.txt")

            # Збереження зображення сторінки (всі формули, рисунки зберігаються)
            img.save(image_path, "PNG")

            # OCR: розпізнавання тексту (у т.ч. спец. символів)
            text = pytesseract.image_to_string(img, lang=LANG)

            # Збереження тексту у файл
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)

            self.stdout.write(f"✅ Сторінка {page_num} — текст та рисунок збережено")

        self.stdout.write(self.style.SUCCESS("🎉 Успішно збережено всі сторінки PDF!"))
