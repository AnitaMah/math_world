"""Vision-LLM корекція (фаза 15): дорогий, але точний прохід лише для проблемних зон.

Ідея: Tesseract читає все безкоштовно, валідація (фаза 14) показує, де він помилився.
Тільки ці вправи ми вирізаємо з картинки сторінки і відправляємо в vision-модель разом
з OCR-текстом як підказкою. Відповідь — строгий JSON, і ми **не довіряємо їй сліпо**:

1. невалідний JSON / не та схема → не застосовуємо;
2. відповідь у 2+ рази довша за OCR → модель, мабуть, «дописала» → відкидаємо;
3. CER між OCR і LLM > 50 % → надто різні тексти, автоматично не застосовуємо (лише у звіт);
4. номери підпунктів не збіглися з OCR → текст застосовуємо, але лишаємо ``needs_review``.

Обидві версії зберігаються: ``data['ocr_text']``, ``data['vision_text']``, ``data['text_source']``.

Інфраструктура перенесена зі старого ``scripts/gemini_client.py``: кеш на диску
(sha вирізки + версія промпту + модель), денний бюджет запитів, ретрай з backoff на 429/503.
Модуль не імпортує Django, а ``google-genai`` імпортується лише при створенні Gemini-клієнта.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np

from .bench import cer
from .datatypes import BBox, Node, SourceRef

PROMPT_VERSION = "v1"
DEFAULT_DAILY_BUDGET = 200
MAX_LENGTH_RATIO = 2.0
MAX_AUTO_CER = 0.5
MIN_LENGTH_BASE = 20          # для дуже коротких OCR-текстів порівнюємо з 20 символами
LOW_CONF = 60.0
CROP_PAD = 14
TOKENS_PER_TILE = 258         # Gemini: картинка ≤ 384 px — 258 токенів, більші ріжуться на плитки 768×768

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["text", "subitems", "confidence"],
    "additionalProperties": False,
    "properties": {
        "text": {"type": "string"},
        "subitems": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["n", "text"],
                "additionalProperties": False,
                "properties": {"n": {"type": "string"}, "text": {"type": "string"}},
            },
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}

PROMPT_V1 = """Ти — уважний коректор шкільного підручника з математики (українська мова).
На картинці — одна вправа зі сторінки. Перепиши її текст ДОСЛІВНО, нічого не розв'язуй,
нічого не додавай і не пропускай. Номер вправи і позначки складності (° • * ′) не пиши.

Правила запису математики:
- множення — «·», ділення — «:», мінус — «−», плюс — «+», дорівнює — «=»;
- звичайний дріб — «a/b» (наприклад «3/4»), мішане число — «ціле пробіл дріб» («2 1/3»);
- десятковий дріб — з комою («3,5»); степінь — «^» («10^3»);
- латинські позначення точок і відрізків (AB, MN) лишай латиницею.

Підпункти «1)», «2)», «а)» винеси в "subitems" (n — номер без дужки, text — текст підпункту);
у "text" лиши лише умову без підпунктів. Якщо підпунктів немає — "subitems": [].
"confidence" — наскільки ти впевнений, що все прочитано правильно (0..1).

Ось що прочитав звичайний OCR (може містити помилки, використовуй лише як підказку):
<<<
{ocr}
>>>

Відповідай ЛИШЕ JSON-об'єктом {{"text": ..., "subitems": [{{"n": ..., "text": ...}}], "confidence": ...}}."""

PROMPTS = {"v1": PROMPT_V1}


# --------------------------------------------------------------------------- клієнт


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
    return any(code in message for code in ("429", "503", "UNAVAILABLE", "RESOURCE_EXHAUSTED"))


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
        result = self.inner.transcribe(image_png, prompt, schema)
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


# --------------------------------------------------------------------------- вибір зон


@dataclass
class VisionTarget:
    exercise: Node
    reasons: list[str]

    @property
    def source(self) -> SourceRef | None:
        return self.exercise.source


def _written_subitems(ex: Node) -> list[Node]:
    return [c for c in ex.children if c.kind == "subexercise"]


def exercise_ocr_text(ex: Node) -> str:
    """Те, що OCR прочитав для вправи: умова + підпункти «N) текст»."""
    condition = ex.data.get("condition") or (ex.text.splitlines()[0] if ex.text else "")
    parts = [condition]
    parts += [f"{s.number}) {s.text}" for s in _written_subitems(ex)]
    if ex.data.get("condition_tail"):
        parts.append(ex.data["condition_tail"])
    return "\n".join(p for p in parts if p)


def select_targets(root: Node, layouts: Iterable[Any] = (), conf_threshold: float = LOW_CONF) -> list[VisionTarget]:
    """Вправи, які варто показати моделі, з причинами:
    needs_review, дріб на картинці (has_fractions), зламаний вираз, рядок з низьким conf."""
    low_conf_keys = {(lay.pdf_page, ln.line_id) for lay in layouts for ln in lay.body_lines
                     if ln.words and ln.conf < conf_threshold}
    targets = []
    for ex in root.find("exercise"):
        reasons = []
        if ex.data.get("has_fractions"):
            reasons.append("fraction_zone")
        if any(s.data.get("expr_status") == "malformed" for s in ex.walk()):
            reasons.append("expr_malformed")
        if ex.needs_review or any(s.needs_review for s in ex.walk() if s is not ex):
            reasons.append("needs_review")
        if low_conf_keys and any(tuple(k) in low_conf_keys for k in ex.data.get("line_keys", [])):
            reasons.append("low_conf")
        if reasons and ex.source and ex.source.bbox:
            targets.append(VisionTarget(ex, reasons))
    # Спершу найцінніші: дроби і зламані вирази, потім решта (за сторінкою).
    priority = {"fraction_zone": 0, "expr_malformed": 1, "needs_review": 2, "low_conf": 3}
    targets.sort(key=lambda t: (min(priority[r] for r in t.reasons), t.source.pdf_page))
    return targets


def crop_png(image: np.ndarray, box: BBox, pad: int = CROP_PAD) -> bytes:
    h, w = image.shape[:2]
    crop = image[max(0, box.y0 - pad):min(h, box.y1 + pad), max(0, box.x0 - pad):min(w, box.x1 + pad)]
    if crop.size == 0:
        raise VisionError(f"Порожня вирізка для {box}")
    ok, buf = cv2.imencode(".png", crop)
    if not ok:
        raise VisionError("Не вдалося закодувати PNG")
    return buf.tobytes()


def estimate_tokens(width: int, height: int) -> int:
    if width <= 384 and height <= 384:
        return TOKENS_PER_TILE
    return TOKENS_PER_TILE * math.ceil(width / 768) * math.ceil(height / 768)


# --------------------------------------------------------------------------- перевірка і застосування


def validate_response(response: Any, schema: Mapping[str, Any] = RESPONSE_SCHEMA) -> str | None:
    """None — відповідь коректна; інакше текст помилки."""
    import jsonschema

    try:
        jsonschema.validate(response, schema)
    except jsonschema.ValidationError as exc:
        return exc.message
    return None


def _canon_apostrophes(text: str) -> str:
    """Модель повертає типографський апостроф («від’ємник»); у проєкті він один (як після normalize)."""
    from .normalize import APOSTROPHES, CANON_APOSTROPHE
    return "".join(CANON_APOSTROPHE if ch in APOSTROPHES else ch for ch in text)


def vision_full_text(response: Mapping[str, Any]) -> str:
    lines = [response.get("text", "")] + [f"{s['n']}) {s['text']}" for s in response.get("subitems", [])]
    return "\n".join(line for line in lines if line)


@dataclass
class Decision:
    status: str               # applied | applied_review | rejected_length | rejected_cer | invalid
    reason: str = ""
    cer: float | None = None


def judge(ocr_text: str, response: Any, ocr_labels: Sequence[str]) -> Decision:
    """Захист від галюцинацій (кроки 0656–0659)."""
    error = validate_response(response)
    if error:
        return Decision("invalid", f"схема: {error}")
    llm_text = vision_full_text(response)
    if len(llm_text) > MAX_LENGTH_RATIO * max(len(ocr_text), MIN_LENGTH_BASE):
        return Decision("rejected_length", f"{len(llm_text)} символів проти {len(ocr_text)} в OCR")
    distance = cer(ocr_text, llm_text)
    if distance > MAX_AUTO_CER:
        return Decision("rejected_cer", f"CER {distance:.0%}", distance)
    llm_labels = [s["n"].strip().rstrip(")") for s in response["subitems"]]
    if list(ocr_labels) != llm_labels:
        return Decision("applied_review", f"підпункти OCR {list(ocr_labels)} ≠ LLM {llm_labels}", distance)
    return Decision("applied", "", distance)


def apply_response(ex: Node, response: Mapping[str, Any], decision: Decision,
                   natural_numbers: bool = True) -> None:
    """Записує результат у вправу. Обидві версії тексту лишаються в data."""
    from .math_text import analyze_expression

    ocr_text = exercise_ocr_text(ex)
    ex.data["ocr_text"] = ocr_text
    ex.data["vision_status"] = decision.status
    if decision.reason:
        ex.data["vision_reason"] = decision.reason
    if decision.cer is not None:
        ex.data["vision_cer"] = round(decision.cer, 3)
    if decision.status in ("invalid",):
        ex.data["text_source"] = "ocr"
        return
    ex.data["vision_text"] = vision_full_text(response)
    ex.data["vision_confidence"] = response.get("confidence")
    if not decision.status.startswith("applied"):
        ex.data["text_source"] = "ocr"          # лише у звіт, людина вирішить
        ex.needs_review = True
        return

    ex.data["text_source"] = "vision"
    ex.data["condition"] = _canon_apostrophes(response["text"].strip())
    subs = {s.number: s for s in _written_subitems(ex)}
    compute = ex.data.get("task_verb") == "compute"
    for item in response["subitems"]:
        label = item["n"].strip().rstrip(")")
        sub = subs.get(label)
        if sub is None:
            continue
        sub.data["ocr_text"] = sub.text
        sub.text = _canon_apostrophes(item["text"].strip())
        sub.data["text_source"] = "vision"
        if compute:
            result = analyze_expression(sub.text, natural_numbers=natural_numbers)
            sub.data.update(expr=result.expression, expr_status=result.status)
            sub.data.pop("expr_issues", None)
            sub.data.pop("answer", None)
            if result.issues:
                sub.data["expr_issues"] = result.issues
            if result.answer is not None:
                sub.data.update(answer=result.answer, answer_source="computed")
            sub.needs_review = result.status in ("suspect", "malformed")
        else:
            sub.needs_review = False
    if decision.status == "applied":
        ex.needs_review = any(s.needs_review for s in _written_subitems(ex))
    else:
        ex.needs_review = True


# --------------------------------------------------------------------------- прогін


@dataclass
class VisionStats:
    candidates: int = 0
    selected: int = 0
    sent: int = 0
    cached: int = 0
    estimated_tokens: int = 0
    budget_stopped: bool = False
    errors: int = 0
    by_status: dict[str, int] = field(default_factory=dict)
    planned: list[dict[str, Any]] = field(default_factory=list)


def run_vision(root: Node, page_images: Mapping[int, Path | np.ndarray], client: VisionClient | None,
               layouts: Iterable[Any] = (), limit: int | None = None, dry_run: bool = False,
               prompt_version: str = PROMPT_VERSION, natural_numbers: bool = True) -> VisionStats:
    """Відправляє вибрані зони в модель і застосовує відповіді з перевірками.

    dry_run — нічого не відправляє, лише показує список зон і оцінку токенів.
    Бюджет вичерпано посеред прогону → зупиняємось, решта вправ лишається як була.
    """
    from .preprocess import load_image

    template = PROMPTS[prompt_version]
    targets = select_targets(root, layouts)
    stats = VisionStats(candidates=len(targets))
    if limit is not None:
        targets = targets[:limit]
    stats.selected = len(targets)
    images: dict[int, np.ndarray] = {}
    for target in targets:
        src = target.source
        if src.pdf_page not in images:
            img = page_images.get(src.pdf_page)
            if img is None:
                continue
            images[src.pdf_page] = img if isinstance(img, np.ndarray) else load_image(img)
        png = crop_png(images[src.pdf_page], src.bbox)
        stats.estimated_tokens += estimate_tokens(src.bbox.width + 2 * CROP_PAD, src.bbox.height + 2 * CROP_PAD)
        ocr_text = exercise_ocr_text(target.exercise)
        stats.planned.append({"exercise": target.exercise.number, "page": src.pdf_page,
                              "reasons": target.reasons, "bytes": len(png)})
        if dry_run or client is None:
            continue
        try:
            response = client.transcribe(png, template.format(ocr=ocr_text), RESPONSE_SCHEMA)
        except VisionBudgetExceeded:
            stats.budget_stopped = True
            break
        except Exception as exc:  # noqa: BLE001 — одна зона з помилкою не валить прогін
            stats.errors += 1
            target.exercise.data["vision_status"] = "error"
            target.exercise.data["vision_reason"] = str(exc)[:200]
            continue
        if getattr(client, "last_from_cache", False):
            stats.cached += 1
        else:
            stats.sent += 1
        labels = [s.number for s in _written_subitems(target.exercise)]
        decision = judge(ocr_text, response, labels)
        apply_response(target.exercise, response, decision, natural_numbers)
        stats.by_status[decision.status] = stats.by_status.get(decision.status, 0) + 1
    return stats


def vision_env(env_file: str | Path = ".env") -> dict[str, str]:
    """Налаштування для Gemini: файл .env, поверх нього справжні змінні середовища.

    `manage.py` сам .env у os.environ не кладе, тому без цього ключ з .env «не задано»."""
    from .config import read_env_file
    return {**read_env_file(env_file), **os.environ}


def make_client(cache_dir: Path, daily_budget: int = DEFAULT_DAILY_BUDGET,
                environ: Mapping[str, str] | None = None) -> CachedClient:
    env = vision_env() if environ is None else dict(environ)
    inner = GeminiVisionClient(api_key=env.get("GEMINI_API_KEY"), model=env.get("GEMINI_MODEL"))
    return CachedClient(inner, Path(cache_dir) / "vision", DailyBudget(Path(cache_dir) / "vision_budget.json", daily_budget))


# --------------------------------------------------------------------------- CLI


def main(argv: Sequence[str] | None = None) -> int:
    """python -m education.pdf_pipeline.vision --tree pipeline_out/m5_tree.json --pdf <pdf> --limit 3 [--dry-run]"""
    from .config import PipelineConfig, read_env_file
    from .images import get_page_images

    parser = argparse.ArgumentParser(description="Vision-LLM корекція проблемних вправ дерева")
    parser.add_argument("--tree", required=True, type=Path)
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--out", type=Path, help="куди записати оновлене дерево (за замовчуванням <tree>_vision.json)")
    parser.add_argument("--limit", type=int, default=3, help="скільки зон відправити (за замовчуванням 3)")
    parser.add_argument("--dry-run", action="store_true", help="нічого не відправляти, показати план і токени")
    parser.add_argument("--budget", type=int, default=DEFAULT_DAILY_BUDGET)
    parser.add_argument("--fractions", action="store_true", help="дробові відповіді нормальні (6 клас)")
    args = parser.parse_args(argv)

    env = {**read_env_file(), **os.environ}
    cfg = PipelineConfig.from_env(env)
    root = Node.from_dict(json.loads(args.tree.read_text(encoding="utf-8")))
    pages = sorted({t.source.pdf_page for t in select_targets(root)})
    page_images = {p.pdf_page: p.path for p in get_page_images(args.pdf, pages, cfg)} if pages else {}
    client = None if args.dry_run else make_client(cfg.cache_dir, args.budget, env)
    stats = run_vision(root, page_images, client, limit=args.limit, dry_run=args.dry_run,
                       natural_numbers=not args.fractions)

    for item in stats.planned:
        print(f"  №{item['exercise']:>5}  стор. {item['page']:>3}  {','.join(item['reasons']):<30} {item['bytes'] // 1024} КБ")
    print(f"Кандидатів: {stats.candidates}, вибрано: {stats.selected}, ~{stats.estimated_tokens} токенів картинок")
    if args.dry_run:
        return 0
    print(f"Відправлено: {stats.sent}, з кешу: {stats.cached}, помилок: {stats.errors}, "
          f"бюджет зупинив: {stats.budget_stopped}, статуси: {stats.by_status}")
    if client is not None:
        print(f"Використано сьогодні: {client.budget.used}/{client.budget.limit}")
    out = args.out or args.tree.with_name(args.tree.stem + "_vision.json")
    out.write_text(json.dumps(root.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Дерево: {out}")
    for ex in root.find("exercise"):
        if "vision_status" in ex.data:
            print(f"\n№{ex.number} [{ex.data['vision_status']}] {ex.data.get('vision_reason', '')}")
            print("  OCR:   ", ex.data.get("ocr_text", "").replace("\n", " | ")[:300])
            print("  Vision:", ex.data.get("vision_text", "").replace("\n", " | ")[:300])
    return 0


if __name__ == "__main__":
    sys.exit(main())
