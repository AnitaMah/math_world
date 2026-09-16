"""
Step 13 of the refactor plan: run Tesseract OCR (Ukrainian language pack)
over PNG pages already rendered by scripts/render_pdf_pages.py (Step 12),
writing one .txt file per page.

Why Tesseract and not pdftotext/pypdf: this project's PDFs have a broken
embedded font-encoding table (confirmed in Section 1.3 of the refactor
plan -- Cyrillic gets swapped for Latin look-alikes on direct text
extraction). Rendering to an image and OCR'ing it side-steps that
entirely, since we never touch the PDF's own (corrupted) text layer.

Requires:
    - Tesseract OCR installed, with the Ukrainian language pack
      (tesseract-ocr-ukr). Check with: tesseract --list-langs
      (should include "ukr" in the list).

Usage:
    python scripts/ocr_pages.py <pages_dir> [--out-dir DIR] [--psm N]

Example (OCR everything render_pdf_pages.py just produced):
    python scripts/ocr_pages.py review/section_1 --out-dir review/section_1_text
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_PSM = 6  # "assume a single uniform block of text" -- matches a
                  # textbook page's layout better than Tesseract's default.

# Windows installers put tesseract.exe here by default. Checked directly
# as a fallback so this script works even when the PATH environment
# variable hasn't picked up a fresh install yet (a common Windows
# annoyance -- new terminals, and sometimes a full reboot, are needed
# before PATH changes are visible everywhere).
WINDOWS_FALLBACK_PATHS = [
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
]


def find_tesseract() -> str:
    on_path = shutil.which("tesseract")
    if on_path:
        return on_path
    for candidate in WINDOWS_FALLBACK_PATHS:
        if candidate.exists():
            return str(candidate)
    raise RuntimeError(
        "tesseract not found on PATH or in the usual Windows install "
        "locations. Install Tesseract OCR with the Ukrainian language "
        "pack (tesseract-ocr-ukr) -- see "
        "https://github.com/UB-Mannheim/tesseract/wiki"
    )


def ocr_pages(pages_dir: Path, out_dir: Path, psm: int = DEFAULT_PSM) -> list[Path]:
    tesseract_bin = find_tesseract()

    if not pages_dir.exists():
        raise FileNotFoundError(f"Pages directory not found: {pages_dir}")

    png_files = sorted(pages_dir.glob("*.png"))
    if not png_files:
        raise FileNotFoundError(f"No .png files found in {pages_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    for png_path in png_files:
        out_base = out_dir / png_path.stem  # tesseract appends .txt itself
        subprocess.run(
            [
                tesseract_bin,
                str(png_path),
                str(out_base),
                "-l", "ukr",
                "--psm", str(psm),
            ],
            check=True,
        )
        written.append(out_base.with_suffix(".txt"))

    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pages_dir", type=Path)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--psm", type=int, default=DEFAULT_PSM)
    args = parser.parse_args()

    out_dir = args.out_dir or (args.pages_dir.parent / f"{args.pages_dir.name}_text")

    try:
        written = ocr_pages(args.pages_dir, out_dir, args.psm)
    except (RuntimeError, FileNotFoundError) as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    print(f"✅ OCR'd {len(written)} page(s) to {out_dir}/")
    for p in written:
        print(f"   {p}")


if __name__ == "__main__":
    main()
