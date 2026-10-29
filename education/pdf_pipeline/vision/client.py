"""Клієнт vision-LLM: ретраї з backoff, денний бюджет запитів, кеш на диску (фаза 15).

Винесено з ``vision.py`` (BE-S12). Інфраструктура перенесена зі старого
``scripts/gemini_client.py``: кеш на диску (sha вирізки + версія промпту + модель),
денний бюджет запитів, ретрай з backoff на 429/503. ``google-genai`` імпортується
лише при створенні Gemini-клієнта.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

DEFAULT_DAILY_BUDGET = 200


class VisionError(RuntimeError):
    pass


class VisionBudgetExceeded(VisionError):
    pass


class VisionClient(Protocol):
    model: str

    def transcribe(self, image_png: bytes, prompt: str, schema: Mapping[str, Any]) -> dict[str, Any]:
        """Картинка + промпт → розібраний JSON (dict). Помилки мережі — винятки."""


def _retryable(exc: Exception) -> bool:
    message = str(exc)
    return any(code in message for code in ("429", "503", "UNAVAILABLE", "RESOURCE_EXHAUSTED",
                                            "getaddrinfo", "Server disconnected", "timed out"))


def call_with_backoff(fn: Callable[[], Any], retries: int = 3, base_delay: float = 5.0,
                      sleep: Callable[[float], None] = time.sleep) -> Any:
    """429/503 → чекаємо 5, 10, 20 с і пробуємо знову; інші помилки — одразу назовні."""
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — SDK кидає власні типи
            if attempt == retries or not _retryable(exc):
                raise
            sleep(base_delay * 2 ** attempt)
    raise AssertionError("unreachable")


class DailyBudget:
    """Лічильник запитів за день у JSON-файлі. Новий день — лічильник з нуля."""

    def __init__(self, path: Path, limit: int = DEFAULT_DAILY_BUDGET, today: Callable[[], str] | None = None):
        self.path = Path(path)
        self.limit = limit
        self.today = today or (lambda: time.strftime("%Y-%m-%d"))

    def _state(self) -> dict[str, Any]:
        state: dict[str, Any] = {}
        if self.path.exists():
            try:
                state = json.loads(self.path.read_text(encoding="utf-8"))
            except ValueError:
                state = {}
        return state if state.get("date") == self.today() else {"date": self.today(), "count": 0}

    @property
    def used(self) -> int:
        return int(self._state()["count"])

    def spend(self) -> None:
        state = self._state()
        if state["count"] >= self.limit:
            raise VisionBudgetExceeded(f"Денний бюджет vision-запитів ({self.limit}) вичерпано ({state['date']})")
        state["count"] += 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state), encoding="utf-8")

    def refund(self) -> None:
        """Невдалий запит бюджет не витрачає: повертаємо витрачену одиницю."""
        state = self._state()
        if state["count"] > 0:
            state["count"] -= 1
            self.path.write_text(json.dumps(state), encoding="utf-8")


def cache_key(image_png: bytes, prompt: str, model: str, schema: Mapping[str, Any]) -> str:
    """sha вирізки + повний промпт (в ньому версія і OCR-підказка) + модель + схема."""
    h = hashlib.sha256()
    for part in (hashlib.sha256(image_png).hexdigest(), prompt, model, json.dumps(schema, sort_keys=True)):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


class CachedClient:
    """Обгортка над будь-яким клієнтом: кеш на диску + денний бюджет.

    Кешована відповідь бюджет не витрачає — повторний прогін безкоштовний.
    """

    def __init__(self, inner: VisionClient, cache_dir: Path, budget: DailyBudget):
        self.inner = inner
        self.model = inner.model
        self.cache_dir = Path(cache_dir)
        self.budget = budget
        self.last_from_cache = False

    def transcribe(self, image_png: bytes, prompt: str, schema: Mapping[str, Any]) -> dict[str, Any]:
        path = self.cache_dir / f"{cache_key(image_png, prompt, self.model, schema)}.json"
        if path.exists():
            self.last_from_cache = True
            return json.loads(path.read_text(encoding="utf-8"))
        self.last_from_cache = False
        self.budget.spend()
        try:
            result = self.inner.transcribe(image_png, prompt, schema)
        except Exception:
            self.budget.refund()
            raise
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        return result


class GeminiVisionClient:
    """Gemini через ``google-genai``. Модель — лише з ``GEMINI_MODEL`` (без хардкоду)."""

    def __init__(self, api_key: str | None = None, model: str | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = model or os.environ.get("GEMINI_MODEL") or ""
        if not self.api_key:
            raise VisionError("GEMINI_API_KEY не задано (.env або змінна середовища)")
        if not self.model:
            raise VisionError("GEMINI_MODEL не задано — подивись доступні: python scripts/list_gemini_models.py")
        from google import genai  # лінивий імпорт: модуль працює і без пакета

        self._client = genai.Client(api_key=self.api_key)
        self._sleep = sleep

    def transcribe(self, image_png: bytes, prompt: str, schema: Mapping[str, Any]) -> dict[str, Any]:
        from google.genai import types

        def call() -> Any:
            return self._client.models.generate_content(
                model=self.model,
                contents=[types.Part.from_bytes(data=image_png, mime_type="image/png"), prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", temperature=0,
                    # інструментів у нас немає — вимикаємо AFC, щоб SDK не сипав попередженнями
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )

        response = call_with_backoff(call, sleep=self._sleep)
        try:
            return json.loads(response.text)
        except (TypeError, ValueError) as exc:
            raise VisionError(f"Модель повернула не JSON: {str(response.text)[:200]!r}") from exc


class FakeVisionClient:
    """Для тестів: відповіді за порядком або функцією; рахує виклики, може кидати помилки."""

    model = "fake-vision"

    def __init__(self, responses: Sequence[Any] | Callable[[bytes, str], Any] = ()):
        self.responses = responses
        self.calls: list[tuple[bytes, str]] = []

    def transcribe(self, image_png: bytes, prompt: str, schema: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append((image_png, prompt))
        if callable(self.responses):
            result = self.responses(image_png, prompt)
        else:
            result = self.responses[(len(self.calls) - 1) % len(self.responses)]
        if isinstance(result, Exception):
            raise result
        return result


def vision_env(env_file: str | Path = ".env") -> dict[str, str]:
    """Налаштування для Gemini: файл .env, поверх нього справжні змінні середовища.

    `manage.py` сам .env у os.environ не кладе, тому без цього ключ з .env «не задано»."""
    from ..config import read_env_file
    return {**read_env_file(env_file), **os.environ}


def make_client(cache_dir: Path, daily_budget: int = DEFAULT_DAILY_BUDGET,
                environ: Mapping[str, str] | None = None) -> CachedClient:
    env = vision_env() if environ is None else dict(environ)
    inner = GeminiVisionClient(api_key=env.get("GEMINI_API_KEY"), model=env.get("GEMINI_MODEL"))
    return CachedClient(inner, Path(cache_dir) / "vision", DailyBudget(Path(cache_dir) / "vision_budget.json", daily_budget))
