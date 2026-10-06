"""Картинка для перевірки розмітки очима: кольорові рамки поверх сторінки.

    python -m education.pdf_pipeline.layout_debug 5-klas-matematika-merzljak-2018-1-46.pdf --pages 5-8

Кольори: синій — колонтитул, зелений — текст, блакитний — номер сторінки внизу,
фіолетовий — текстова рамка, червоний — рисунок, помаранчевий — клітинки сіток
(з номером підпункту; червоний номер = відновлений за позицією).
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np

from .config import PipelineConfig
from .datatypes import BBox
from .layout import PageLayout, analyze_document
from .preprocess import load_image, save_image

# BGR
BLUE, GREEN, CYAN, PURPLE, RED, ORANGE = (200, 80, 0), (0, 160, 0), (200, 200, 0), (160, 0, 160), (0, 0, 220), (0, 140, 255)


def _rect(img: np.ndarray, box: BBox, color: tuple[int, int, int], thickness: int = 1) -> None:
    cv2.rectangle(img, (box.x0, box.y0), (box.x1, box.y1), color, thickness)


def draw_layout(image: np.ndarray, layout: PageLayout) -> np.ndarray:
    """Повертає копію сторінки з намальованою розміткою."""
    out = image.copy() if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    for ln in layout.header_lines:
        _rect(out, ln.bbox, BLUE, 2)
    for ln in layout.footer_lines:
        _rect(out, ln.bbox, CYAN, 2)
    for ln in layout.body_lines:
        _rect(out, ln.bbox, PURPLE if ln.zone == "boxed" else GREEN)
    for region in layout.regions:
        _rect(out, region.bbox, RED if region.kind == "figure" else PURPLE, 3)
    for grid in layout.grids():
        for cell in grid.cells:
            if cell.bbox is None:
                continue
            _rect(out, cell.bbox, ORANGE, 2)
            color = RED if cell.ocr_fixed else ORANGE
            cv2.putText(out, cell.label, (cell.bbox.x0 - 22, cell.bbox.y1), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    if layout.book_page is not None:
        cv2.putText(out, f"book page {layout.book_page}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, CYAN, 2)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    from .images import get_page_images, parse_page_range
    from .ocr import ocr_page
    from .ocr.tesseract import TesseractEngine
    from .preprocess import preprocess_page

    parser = argparse.ArgumentParser(description="Намалювати розмітку сторінок для перевірки")
    parser.add_argument("pdf")
    parser.add_argument("--pages", required=True, help='напр. "5-8,12"')
    parser.add_argument("--out", type=Path, default=Path("pipeline_out/layout_debug"))
    args = parser.parse_args(argv)

    cfg = PipelineConfig.from_env()
    engine = TesseractEngine(cfg)
    pages = get_page_images(args.pdf, parse_page_range(args.pages), cfg)
    results = [ocr_page(preprocess_page(p), engine) for p in pages]
    layouts, headers = analyze_document(results)
    for page, layout in zip(pages, layouts):
        path = args.out / f"{Path(args.pdf).stem}_p{page.pdf_page:03d}.png"
        save_image(path, draw_layout(load_image(page.path), layout))
        print(f"{path}  (стор. книги {layout.book_page}, сіток: {len(layout.grids())}, рамок: {len(layout.regions)})")
    print("Колонтитули:", [h.to_dict() for h in headers])
    return 0


if __name__ == "__main__":
    sys.exit(main())
