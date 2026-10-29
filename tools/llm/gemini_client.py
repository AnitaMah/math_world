"""
Step 27 of the refactor plan: a thin, quota-conscious wrapper around the
Gemini API.

Why this exists instead of calling google-genai directly everywhere:
  - Every response is cached to disk, keyed by a hash of the request, so
    re-running any script never re-spends quota on input it already saw.
  - A running daily request counter enforces a hard budget so a bug or a
    retry loop can't silently blow through the free tier.
  - A single retry-with-backoff on 429 (rate limited), then it gives up
    loudly rather than hammering the API.

This module deliberately does NOT hardcode a model name at import time --
Google's free-tier model lineup and quotas have moved more than once in
2026 (2.0 -> 2.5 -> 3.x Flash), and third-party docs/blogs can lag or lead
what's actually live on a given key. Run `scripts/list_gemini_models.py`
to see the real, current model names your key can call before picking
one via GEMINI_MODEL (env var) or the `model` argument; check
https://aistudio.google.com/rate-limit for whichever currently has the
most generous free daily quota.

Setup:
    pip install google-genai python-dotenv
    export GEMINI_API_KEY=...        # from https://aistudio.google.com/apikey
    export GEMINI_MODEL=gemini-3.6-flash   # gemini-2.5-flash and gemini-3.8-flash both
                                            # returned errors telling us to use this one
                                            # (Sept 2026) -- Google's own API error message
                                            # is more reliable here than any doc/blog guess.

Quick test:
    python scripts/gemini_client.py "Say hello in Ukrainian in five words."
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv  # type: ignore

    # Loads .env from the current working directory (project root, when
    # run via `python manage.py shell` or `python scripts/...`) into
    # os.environ, if it isn't loaded there already. Safe to call more than
    # once; does nothing if python-dotenv isn't installed yet, since
    # GEMINI_API_KEY can still be set as a real environment variable.
    load_dotenv()
except ImportError:
    pass
from typing import Optional

CACHE_DIR = Path("review/gemini_cache")
BUDGET_FILE = Path("review/gemini_request_count.json")
DEFAULT_DAILY_BUDGET = 200  # conservative; well under any free-tier RPD seen in 2026


class GeminiBudgetExceeded(RuntimeError):
    pass


class GeminiClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        daily_budget: int = DEFAULT_DAILY_BUDGET,
        cache_dir: Path = CACHE_DIR,
        budget_file: Path = BUDGET_FILE,
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "GEMINI_API_KEY not set. Get a free key at "
                "https://aistudio.google.com/apikey and `export GEMINI_API_KEY=...`"
            )
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
        self.daily_budget = daily_budget
        self.cache_dir = cache_dir
        self.budget_file = budget_file
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.budget_file.parent.mkdir(parents=True, exist_ok=True)

        # Imported lazily so this file can be read/tested without the
        # dependency installed yet.
        from google import genai  # type: ignore

        self._client = genai.Client(api_key=self.api_key)

    # ---- quota bookkeeping -------------------------------------------------

    def _today_key(self) -> str:
        return time.strftime("%Y-%m-%d")

    def _load_budget_state(self) -> dict:
        if self.budget_file.exists():
            state = json.loads(self.budget_file.read_text(encoding="utf-8"))
        else:
            state = {}
        today = self._today_key()
        if state.get("date") != today:
            state = {"date": today, "count": 0}
        return state

    def _save_budget_state(self, state: dict) -> None:
        self.budget_file.write_text(json.dumps(state), encoding="utf-8")

    def _check_and_increment_budget(self) -> None:
        state = self._load_budget_state()
        if state["count"] >= self.daily_budget:
            raise GeminiBudgetExceeded(
                f"Daily Gemini request budget ({self.daily_budget}) already used "
                f"today ({state['date']}). Raise daily_budget explicitly if you "
                "really mean to send more, but check your actual free-tier quota "
                "first at https://aistudio.google.com/rate-limit."
            )
        state["count"] += 1
        self._save_budget_state(state)

    # ---- caching -------------------------------------------------------------

    def _cache_key(self, *parts: str) -> str:
        h = hashlib.sha256()
        for p in parts:
            h.update(p.encode("utf-8"))
            h.update(b"\x00")
        return h.hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    # ---- public API ------------------------------------------------------

    def generate_text(self, prompt: str, prompt_version: str = "v1") -> str:
        """Text-only call (cheap). Used for theory drafts / map layout."""
        key = self._cache_key("text", self.model, prompt_version, prompt)
        cached = self._read_cache(key)
        if cached is not None:
            return cached["text"]

        self._check_and_increment_budget()
        response = self._call_with_backoff(
            lambda: self._client.models.generate_content(model=self.model, contents=prompt)
        )
        text = response.text
        self._write_cache(key, {"text": text})
        return text

    def generate_from_image(self, image_path: Path, prompt: str, prompt_version: str = "v1") -> str:
        """Image+text call (expensive). Used only for flagged math regions."""
        image_bytes = Path(image_path).read_bytes()
        key = self._cache_key("image", self.model, prompt_version, prompt, hashlib.sha256(image_bytes).hexdigest())
        cached = self._read_cache(key)
        if cached is not None:
            return cached["text"]

        self._check_and_increment_budget()
        from google.genai import types  # type: ignore

        response = self._call_with_backoff(
            lambda: self._client.models.generate_content(
                model=self.model,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                    prompt,
                ],
            )
        )
        text = response.text
        self._write_cache(key, {"text": text})
        return text

    # ---- internals -------------------------------------------------------

    def _read_cache(self, key: str):
        path = self._cache_path(key)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def _write_cache(self, key: str, value: dict) -> None:
        self._cache_path(key).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def _call_with_backoff(self, fn, max_retries: int = 2):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - surfacing SDK errors as-is after retries
            message = str(e)
            # 429 = rate limited (our own request pace); 503 = the model
            # is temporarily overloaded on Google's side. Both are worth
            # a short wait-and-retry rather than failing the whole call.
            if ("429" in message or "503" in message or "UNAVAILABLE" in message) and max_retries > 0:
                time.sleep(20)
                return self._call_with_backoff(fn, max_retries=max_retries - 1)
            raise


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/gemini_client.py \"<prompt text>\"", file=sys.stderr)
        sys.exit(1)
    prompt = sys.argv[1]
    client = GeminiClient()
    print(client.generate_text(prompt, prompt_version="cli-test"))


if __name__ == "__main__":
    main()
