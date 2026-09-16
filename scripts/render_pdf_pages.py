"""
Step 12 of the refactor plan: render PDF pages to PNG images so they can
be OCR'd (Step 13). Wraps `pdftoppm` rather than a Python PDF library,
because the textbook PDFs in this project have a broken/custom text
layer -- see the refactor plan, Section 1.3 -- so we never try to read
text out of the PDF directly. We only ever want pixels.

Usage:
    python scripts/render_pdf_pages.py <pdf_path> <first_page> <last_page> [--out-dir DIR] [--dpi N]

Example (single page, matching the manual test already done in this
project's refactor conversation):
    python scripts/render_pdf_pages.py 5-klas-matematika-merzljak-2018-1-46.pdf 5 5

Example (a whole section, e.g. §1 = pages 5-15):
    python scripts/render_pdf_pages.py 5-klas-matematika-merzljak-2018-1-46.pdf 5 15 --out-dir review/section_1

Requires the `pdftoppm` command-line tool (part of poppler-utils). On
Windows via WSL, or a poppler install for Windows, this needs to be on
PATH; check with `pdftoppm -v`.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_DPI = 300


def render_pages(pdf_path: Path, first_page: int, last_page: int, out_dir: Path, dpi: int = DEFAULT_DPI) -> list[Path]:
    if shutil.which("pdftoppm") is None:
        raise RuntimeError(
            "pdftoppm not found on PATH. Install poppler-utils "
            "(e.g. 'apt install poppler-utils', or a Windows poppler build) "
            "and make sure it's on PATH."
        )

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / "page"

    subprocess.run(
        [
            "pdftoppm",
            "-f", str(first_page),
            "-l", str(last_page),
            "-r", str(dpi),
            "-png",
            str(pdf_path),
            str(prefix),
        ],
        check=True,
    )

    rendered = sorted(out_dir.glob("page-*.png"))
    return rendered


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf_path", type=Path)
    parser.add_argument("first_page", type=int)
    parser.add_argument("last_page", type=int)
    parser.add_argument("--out-dir", type=Path, default=Path("review/pages"))
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    args = parser.parse_args()

    try:
        rendered = render_pages(args.pdf_path, args.first_page, args.last_page, args.out_dir, args.dpi)
    except (RuntimeError, FileNotFoundError) as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    print(f"✅ Rendered {len(rendered)} page(s) to {args.out_dir}/")
    for p in rendered:
        print(f"   {p}")


if __name__ == "__main__":
    main()
