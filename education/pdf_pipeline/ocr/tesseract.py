"""OCR через Tesseract (pytesseract): слова з координатами і впевненістю."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytesseract

from ..config import PipelineConfig
from ..datatypes import BBox, Word
from .base import ImageInput, OcrParams

WORD_LEVEL = 5   # у виводі image_to_data: 1 сторінка, 2 блок, 3 абзац, 4 рядок, 5 слово


class TesseractNotAvailable(RuntimeError):
    """Tesseract не знайдено — з підказкою, що налаштувати."""


class TesseractEngine:
    """Обгортка над Tesseract. Налаштування (шлях, моделі) береться з PipelineConfig."""

    def __init__(self, cfg: PipelineConfig, timeout: float = 120):
        self.cfg = cfg
        self.timeout = timeout
        if cfg.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = cfg.tesseract_cmd
        try:
            self.version = str(pytesseract.get_tesseract_version())
        except (pytesseract.TesseractNotFoundError, OSError) as exc:
            raise TesseractNotAvailable(
                "Tesseract не знайдено. Вкажи шлях у .env: "
                "TESSERACT_CMD=C:/Program Files/Tesseract-OCR/tesseract.exe"
            ) from exc

    @property
    def name(self) -> str:
        # Модель (best/fast) теж впливає на результат — додаємо папку моделей у назву.
        models = self.cfg.tessdata_dir.name if self.cfg.tessdata_dir else "default"
        return f"tesseract-{self.version}-{models}"

    def build_config(self, params: OcrParams) -> str:
        """Рядок параметрів командного рядка Tesseract."""
        parts = [f"--oem {params.oem}", f"--psm {params.psm}", "-c preserve_interword_spaces=1"]
        if self.cfg.tessdata_dir:
            parts.append(f'--tessdata-dir "{self.cfg.tessdata_dir.as_posix()}"')
        parts += [f"-c {key}={value}" for key, value in params.extra]
        return " ".join(parts)

    def recognize(self, image: ImageInput, params: OcrParams) -> list[Word]:
        """Розпізнає картинку; координати — у пікселях саме цієї картинки."""
        if isinstance(image, Path):
            image = str(image)
        data = pytesseract.image_to_data(
            image,
            lang=params.lang,
            config=self.build_config(params),
            output_type=pytesseract.Output.DICT,
            timeout=self.timeout,
        )
        return parse_tesseract_data(data)


def parse_tesseract_data(data: dict[str, list]) -> list[Word]:
    """Перетворює словник з image_to_data на список Word (лише рівень «слово», без порожніх)."""
    words: list[Word] = []
    for i, level in enumerate(data["level"]):
        if int(level) != WORD_LEVEL:
            continue
        text = str(data["text"][i]).strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:          # -1 = не слово (порожня область)
            continue
        left, top = int(data["left"][i]), int(data["top"][i])
        words.append(Word(
            text=text,
            bbox=BBox(left, top, left + int(data["width"][i]), top + int(data["height"][i])),
            conf=conf,
            block_no=int(data["block_num"][i]),
            par_no=int(data["par_num"][i]),
            line_no=int(data["line_num"][i]),
            word_no=int(data["word_num"][i]),
        ))
    return words
