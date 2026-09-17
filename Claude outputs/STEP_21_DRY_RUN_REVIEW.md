# Step 21 — manual review of `import_curriculum --dry-run` output

Reviewed the full `--dry-run` output for `review/section_1_text/combined.txt`
(§1 of the grade-5 Merzlyak book) by hand, line by line, against the real
OCR source text. Goal: catch anything a classifier got wrong before Step 22
starts writing `ContentBlock` rows for real.

## What was checked

All 9 markers in the source were found and produced blocks — nothing was
missed at the block level:

| Marker | Lines | Block type |
|---|---|---|
| `Розв'язуємо усно` | 44, 197 | `oral_exercise` (2 blocks) |
| `Вправи` | 57, 213 | `exercise` (2 blocks) |
| `Вправи для повторення` | 89, 307 | `review_exercise` (2 blocks) |
| `Задача від Мудрої Сови` | 115, 347 | `wise_owl` (2 blocks) |
| `Коли зроблено уроки` | 353 | `history_aside` (1 block) |

`wise_owl`'s stop-at-first-blank-line rule and `history_aside`'s ~140-line
capture (ending correctly at "3. Відрізок. Довжина відрізка") both matched
the real text exactly, as already covered by the Step 18/19 tests.

## Bug found and fixed: a wild OCR misread could swallow several real items

`find_exercise_blocks`'s "increasing number" guard (added in Step 16 to stop
page-header bleed-through like `2. Цифри...` from being mistaken for a new
item) had a blind spot: it only checked that a number was *greater* than the
highest seen so far, with no ceiling. In the second `Вправи` block, item 32
is OCR'd as `82."` (an `8`/`3` misread, not the usual low-number bleed).
Because 82 is huge, it became the new high-water mark — and every real item
after it (33, 34, 35, 36) has a smaller number, so none of them could ever
exceed 82 again. All five items (32-36) silently collapsed into a single
row labelled `82`.

Fixed by capping how far a number is allowed to jump before it's trusted
(`MAX_ITEM_NUMBER_JUMP = 5`, `content_classifier.py`): a jump that large is
now treated the same as the old low-number bleed case (folded into the
current item's text, watermark left alone), so the next real, small number
can resync as its own item. Applied to both `find_exercise_blocks` and
`find_oral_exercise_blocks` (they share the same guard).

Result for that block: item count went from 15 to 18. Items 33-36 now each
get their own row again; item 32's text is preserved (folded into item 31's
text, not dropped), since a single corrupted number can't safely be
recovered as its own item without guessing at the OCR error itself.

Verified against the real source and covered by two new tests
(`test_exercise_block_recovers_real_items_after_a_wild_number_misread`,
`test_exercise_block_wild_misread_text_is_preserved_not_dropped`) using a
verbatim excerpt of lines 213, 293-305. Full suite: 39/39 passing.

## Known, accepted limitation: one duplicate-number merge remains

In the second `oral_exercise` block, item 5 is OCR'd as `6.` (so items 5
and 6 both read `6.`). Since the *second* `6.` doesn't exceed the
already-updated watermark (also 6), it's folded into item 5's text rather
than starting its own item — a genuine duplicate number is indistinguishable
from noise with this heuristic, unlike the wild-jump case above. This merges
2 real items into 1 (6 real items -> 5 previews in that block). Left as-is:
fixing it would need guessing which of two identical numbers is the "real"
one, which risks new false positives elsewhere for a single item's split.
The text itself is not lost, only its row-per-item split.

## Everything else: working as designed

- Page-header bleed-through (e.g. `2. Цифри...`, `10 9 1. Натуральні
  числа`) is correctly folded into the preceding item/block's text rather
  than becoming a bogus new item, in every other occurrence.
- `review_exercise` blocks intentionally capture their whole raw span as
  one blob (no per-item split) -- confirmed this is what's wanted for both
  occurrences, including the header-bleed noise inside them, which is
  harmless there since nothing depends on that block being item-split.
- Truncation to 200 characters in the CLI's printed preview (`import_curriculum
  --dry-run`) sometimes cuts a preview off mid-sentence with "…" — this is
  cosmetic (the underlying `text` field is untruncated) and only affects
  what's shown on screen, not what would be written to `ContentBlock`.

## Recommendation for Step 22

Both classifiers' output for §1 now matches the real book, with the one
documented duplicate-number limitation above (2 items merged into 1 in a
single spot). Reasonable to proceed to Step 22 (writing real `ContentBlock`
rows) for §1 on this basis, flagging that one spot for a manual fix-up in
the admin afterward if it matters.
