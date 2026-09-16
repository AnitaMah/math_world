"""
Step 20 (early/dry-run form): CLI to run a content classifier over raw
OCR'd text and print what it would create -- nothing is written to the
database. Currently supports only "review_exercise" (Step 15); more
block types get added here as Steps 16-19 land.

Usage:
    python scripts/classify_content.py review\\section_1_text\\combined.txt --block-type review_exercise
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running this script directly (python scripts/classify_content.py)
# without having the project installed as a package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from education.parsing.content_classifier import find_exercise_blocks, find_review_exercise_blocks


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("text_file", type=Path)
    parser.add_argument("--block-type", default="review_exercise", choices=["review_exercise", "exercise"])
    args = parser.parse_args()

    if not args.text_file.exists():
        print(f"❌ File not found: {args.text_file}", file=sys.stderr)
        sys.exit(1)

    raw_text = args.text_file.read_text(encoding="utf-8")

    if args.block_type == "review_exercise":
        blocks = find_review_exercise_blocks(raw_text)
        print(f"Found {len(blocks)} '{args.block_type}' block(s) (DRY RUN -- nothing written):\n")
        for n, block in enumerate(blocks, start=1):
            print(f"--- Block {n} (lines {block.start_line}-{block.end_line}) ---")
            print(block.text)
            print()

    elif args.block_type == "exercise":
        blocks = find_exercise_blocks(raw_text)
        print(f"Found {len(blocks)} '{args.block_type}' block(s) (DRY RUN -- nothing written):\n")
        for n, block in enumerate(blocks, start=1):
            print(f"--- Block {n} (lines {block.start_line}-{block.end_line}, {len(block.items)} item(s)) ---")
            for item in block.items:
                tag = f" [{item.difficulty}]" if item.difficulty else ""
                print(f"  {item.number}{tag}: {item.text}")
            print()


if __name__ == "__main__":
    main()
