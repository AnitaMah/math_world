"""Реєстр профілів підручників: get_profile("math_merzlyak_5")."""
from .base import DIFFICULTY_LEVELS, BlockMarker, TextbookProfile, TocEntry, load_toc
from .merzlyak_5 import PROFILE as MERZLYAK_5
from .tarasenkova_6 import PROFILE as TARASENKOVA_6

PROFILES: dict[str, TextbookProfile] = {p.code: p for p in (MERZLYAK_5, TARASENKOVA_6)}

# Усі типи блоків, які зустрічаються в профілях, + ті, що визначає сам парсер.
BLOCK_TYPES = frozenset({"theory", "self_check"} | {m.block_type for p in PROFILES.values() for m in p.block_markers})


def get_profile(code: str) -> TextbookProfile:
    try:
        return PROFILES[code]
    except KeyError:
        raise KeyError(f"Невідомий профіль {code!r}; є: {sorted(PROFILES)}") from None


__all__ = ["BLOCK_TYPES", "DIFFICULTY_LEVELS", "PROFILES", "BlockMarker", "TextbookProfile",
           "TocEntry", "get_profile", "load_toc"]
