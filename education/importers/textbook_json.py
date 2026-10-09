"""Імпорт ``textbook.json`` (контракт фази 16) у БД — ідемпотентно.

    TextbookImporter(data, dry_run=False, reset=False, base_dir=Path(".")).run() -> ImportResult

Принципи:
- **Повторний імпорт того самого JSON нічого не змінює** (усе ``unchanged``): кожен запис
  шукається за стабільним ключем, поля порівнюються, і ``save()`` викликається лише якщо щось
  справді змінилось.
- **Стабільні ключі**, а не позиція в списку — щоб знайдена OCR-ом «загублена» вправа не зсунула
  всі наступні (і ручні правки не «переїхали» на сусідню вправу):
  блок — (урок, тип, k-та поява цього типу в уроці); вправа — (блок, номер, k-та поява номера);
  підпункт — (вправа, номер, k-та поява); відповідь — (вправа, підпункт, вид).
- **Ручні правки (``text_source="manual"``) не перезаписуються і не видаляються.**
- **Структура зі змісту (Section/Paragraph/Item) не видаляється.** Існуючі записи (створені
  ``import_curriculum``) підхоплюються за номером; їхні назви не перезаписуються, якщо назва
  з JSON суттєво інша — це потрапляє в ``warnings``.
- Блоки/вправи/підпункти/відповіді, яких більше немає в JSON, видаляються — лише в уроках,
  які є в цьому JSON.
- Усе в ``transaction.atomic()``; ``dry_run`` відкочує транзакцію і нічого не пише (і ImportRun теж).
- Помилка → відкат усього імпорту, а ``ImportRun(status="failed")`` пишеться окремо після відкату.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.utils import timezone

from education.models import (
    Answer, ContentBlock, Exercise, Figure, Grade, ImportRun, Item, Paragraph, Section, Subject, SubExercise,
    Textbook,
)

MODELS = ("Section", "Paragraph", "Item", "ContentBlock", "Exercise", "SubExercise", "Answer", "Figure")
_PREFIX_RE = re.compile(r"^\s*(?:Розділ\s+[IVX\d]+\.?|§\s*\d+\.?|\d+\.)\s*", re.IGNORECASE)


def _norm_title(text: str) -> str:
    """«§ 1. Натуральні числа» і «НАТУРАЛЬНІ ЧИСЛА» → «натуральні числа»."""
    return re.sub(r"\s+", " ", _PREFIX_RE.sub("", text or "").splitlines()[0] if text else "").strip().lower()


def _titles_match(a: str, b: str) -> bool:
    from rapidfuzz import fuzz
    return fuzz.ratio(_norm_title(a), _norm_title(b)) >= 85


class _DryRunRollback(Exception):
    pass


@dataclass
class ImportResult:
    textbook_id: int | None = None
    dry_run: bool = False
    counts: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    warnings: list[str] = field(default_factory=list)
    import_run_id: int | None = None

    def count(self, model: str, status: str, n: int = 1) -> None:
        self.counts[model][status] += n

    def as_stats(self) -> dict[str, dict[str, int]]:
        return {m: {s: self.counts[m].get(s, 0) for s in ("created", "updated", "deleted", "unchanged", "kept_manual")}
                for m in MODELS if m in self.counts}

    def summary(self) -> str:
        lines = []
        for model, c in self.as_stats().items():
            parts = ", ".join(f"{k} {v}" for k, v in c.items() if v)
            lines.append(f"{model:<13} {parts}")
        return "\n".join(lines)


class TextbookImporter:
    def __init__(self, data: dict[str, Any], *, dry_run: bool = False, reset: bool = False,
                 base_dir: Path | str = ".", json_path: str = "", json_sha256: str | None = None):
        self.data = data
        self.dry_run = dry_run
        self.reset = reset
        self.base_dir = Path(base_dir)
        self.json_path = json_path
        self.json_sha256 = json_sha256 or hashlib.sha256(
            json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        self.result = ImportResult(dry_run=dry_run)
        self.figures: dict[str, Figure] = {}

    @classmethod
    def from_file(cls, path: str | Path, **kwargs: Any) -> TextbookImporter:
        path = Path(path)
        raw = path.read_bytes()
        try:
            data = json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            raise ValidationError(f"{path}: не JSON ({exc})") from exc
        kwargs.setdefault("base_dir", Path.cwd())
        return cls(data, json_path=path.as_posix(), json_sha256=hashlib.sha256(raw).hexdigest(), **kwargs)

    # ------------------------------------------------------------------ запуск

    def validate(self) -> None:
        from education.pdf_pipeline.schema import SCHEMA_VERSION, SchemaError, validate_textbook
        version = self.data.get("schema_version") if isinstance(self.data, dict) else None
        if version != SCHEMA_VERSION:
            raise ValidationError(f"schema_version={version!r}, імпортер розуміє {SCHEMA_VERSION}")
        try:
            validate_textbook(self.data)
        except SchemaError as exc:
            raise ValidationError(f"JSON не відповідає схемі: {exc}") from exc

    def run(self) -> ImportResult:
        self.validate()                                  # невалідний JSON — до будь-якого запису
        run: ImportRun | None = None
        if not self.dry_run:
            run = ImportRun.objects.create(json_path=self.json_path, json_sha256=self.json_sha256,
                                           pipeline_version=self.data["pipeline_version"],
                                           schema_version=self.data["schema_version"])
            self.result.import_run_id = run.pk
        try:
            with transaction.atomic():
                textbook = self._import()
                if self.dry_run:
                    raise _DryRunRollback
        except _DryRunRollback:
            pass
        except Exception as exc:
            if run is not None:
                ImportRun.objects.filter(pk=run.pk).update(
                    status="failed", finished_at=timezone.now(), message=f"{type(exc).__name__}: {exc}"[:2000],
                    stats=self.result.as_stats())
            raise
        else:
            if run is not None:
                ImportRun.objects.filter(pk=run.pk).update(
                    textbook=textbook, status="success", finished_at=timezone.now(),
                    stats={"counts": self.result.as_stats(), "warnings": self.result.warnings[:200],
                           "json_stats": self.data.get("stats", {}),
                           "problems": dict(Counter(p["code"] for p in self.data.get("problems", [])))})
        return self.result

    # ------------------------------------------------------------------ синхронізація одного запису

    def _sync(self, model: type[models.Model], lookup: dict[str, Any], values: dict[str, Any],
              protect_manual: bool = False, create: bool = False) -> tuple[models.Model, str]:
        """Знайти за lookup, порівняти values, зберегти лише якщо змінилось. Повертає (obj, статус).

        create=True — шукати не треба, запис точно новий (k-та поява номера, якої ще немає в БД;
        пошук за номером знайшов би першу появу і переписав би її)."""
        name = model.__name__
        obj = None if create else model.objects.filter(**lookup).first()
        if obj is None:
            obj = model.objects.create(**lookup, **values)
            self.result.count(name, "created")
            return obj, "created"
        if protect_manual and getattr(obj, "text_source", None) == "manual":
            self.result.count(name, "kept_manual")
            return obj, "kept_manual"
        changed = [k for k, v in values.items() if _field_value(obj, k) != v]
        if not changed:
            self.result.count(name, "unchanged")
            return obj, "unchanged"
        for k in changed:
            setattr(obj, k, values[k])
        obj.save()
        self.result.count(name, "updated")
        return obj, "updated"

    def _delete_missing(self, queryset: models.QuerySet, keep_ids: set[int]) -> None:
        stale = queryset.exclude(pk__in=keep_ids)
        if "text_source" in {f.name for f in queryset.model._meta.fields}:
            kept = stale.filter(text_source="manual").count()
            if kept:
                self.result.count(queryset.model.__name__, "kept_manual", kept)
            stale = stale.exclude(text_source="manual")
        n = stale.count()
        if n:
            stale.delete()
            self.result.count(queryset.model.__name__, "deleted", n)

    # ------------------------------------------------------------------ дерево

    def _import(self) -> Textbook:
        meta = self.data["meta"]
        subject, _ = Subject.objects.get_or_create(code=meta["subject"], defaults={"name_uk": meta["subject"]})
        grade, _ = Grade.objects.get_or_create(subject=subject, number=meta["grade"],
                                               defaults={"name_uk": f"{meta['grade']} клас"})
        author, year = "", None
        try:
            from education.pdf_pipeline.profiles import get_profile
            profile = get_profile(meta["profile"])
            author, year = profile.author, profile.year
        except KeyError:
            self.result.warnings.append(f"невідомий профіль {meta['profile']!r}: автор/рік не заповнено")
        textbook = Textbook.objects.filter(pdf_sha256=meta["pdf_sha256"]).first()
        created = False
        if textbook is None:
            # Той самий підручник, але інший PDF (напр. повна книга замість стор. 1–46): підручник той самий —
            # перепідв'язуємо до нового файла, ключі уроків/вправ лишаються, тож дані не дублюються.
            textbook = Textbook.objects.filter(profile_code=meta["profile"], grade=grade, subject=subject).first()
            if textbook is not None:
                self.result.warnings.append(
                    f"Підручник {textbook.pk} перепідв'язано до нового PDF ({textbook.pdf_name} → {meta['pdf_name']})")
                textbook.pdf_sha256, textbook.pdf_name = meta["pdf_sha256"], meta["pdf_name"]
                textbook.save(update_fields=["pdf_sha256", "pdf_name"])
            else:
                textbook = Textbook.objects.create(
                    pdf_sha256=meta["pdf_sha256"], subject=subject, grade=grade, profile_code=meta["profile"],
                    title=meta["title"], author=author, year=year, pdf_name=meta["pdf_name"])
                created = True
        if not created and (textbook.grade_id != grade.pk or textbook.subject_id != subject.pk):
            raise ValidationError(f"Підручник {textbook} уже прив'язаний до іншого класу/предмета")
        self.textbook, self.grade = textbook, grade
        self.result.textbook_id = textbook.pk

        for fig in self.data["figures"]:
            self._figure(fig)
        for sec in self.data["sections"]:
            self._section(sec)
        return textbook

    def _section(self, sec: dict[str, Any]) -> None:
        number = sec["index"] or int(sec["number"])
        existing = Section.objects.filter(grade=self.grade, number=number).first()
        if existing is not None and existing.textbook_id not in (None, self.textbook.pk):
            raise ValidationError(f"Розділ {number} класу {self.grade} належить іншому підручнику")
        name = f"Розділ {sec['number']}. {sec['title']}"
        if existing is not None:
            values: dict[str, Any] = {"textbook": self.textbook}
            if not _titles_match(existing.name_uk, sec["title"]):
                self.result.warnings.append(f"Розділ {number}: у БД «{existing.name_uk}», у JSON «{sec['title']}» — назву не змінено")
            section, _ = self._sync(Section, {"pk": existing.pk}, values)
        else:
            section, _ = self._sync(Section, {"grade": self.grade, "number": number},
                                    {"textbook": self.textbook, "name_uk": name})
        for par in sec["paragraphs"]:
            self._paragraph(section, par)

    def _paragraph(self, section: Section, par: dict[str, Any]) -> None:
        number = int(par["number"])
        paragraph = self._structural(Paragraph, {"section": section, "number": number}, "name_uk",
                                     f"§ {number}. {par['title']}", par["title"], f"§ {number}")
        self._lesson_blocks(paragraph, "paragraph", par["blocks"])
        for it in par["items"]:
            number_i = int(it["number"])
            item = self._structural(Item, {"paragraph": paragraph, "number": number_i}, "content",
                                    it["title"], it["title"], f"пункт {number_i}")
            self._lesson_blocks(item, "item", it["blocks"])

    def _structural(self, model, lookup, name_field, new_name, title, label):
        """Paragraph/Item зі змісту: підхопити існуючий за номером; назву не перетирати."""
        existing = model.objects.filter(**lookup).first()
        if existing is None:
            obj, _ = self._sync(model, lookup, {name_field: new_name})
            return obj
        if not _titles_match(getattr(existing, name_field), title):
            self.result.warnings.append(
                f"{label}: у БД «{getattr(existing, name_field)[:60]}», у JSON «{title}» — назву не змінено")
        self.result.count(model.__name__, "unchanged")
        return existing

    # ------------------------------------------------------------------ блоки і вправи

    def _lesson_blocks(self, lesson: Paragraph | Item, fk: str, blocks: list[dict[str, Any]]) -> None:
        qs = ContentBlock.objects.filter(**{fk: lesson})
        if self.reset:
            n = qs.exclude(text_source="manual").count()
            qs.exclude(text_source="manual").delete()
            if n:
                self.result.count("ContentBlock", "deleted", n)
        seen: Counter = Counter()
        keep: set[int] = set()
        for order, data in enumerate(blocks):
            k = seen[data["type"]]
            seen[data["type"]] += 1
            # k-й блок цього типу в уроці (стабільно, навіть якщо попереду з'явився новий блок іншого типу)
            same_type = list(qs.filter(block_type=data["type"]).order_by("order", "pk").values_list("pk", flat=True))
            exists = k < len(same_type)
            lookup = {"pk": same_type[k]} if exists else {fk: lesson, "block_type": data["type"], "order": order}
            values = {"order": order, "title": data.get("title", ""), "text": data["text"], "difficulty": None,
                      "needs_review": data["needs_review"], "text_source": "ocr",
                      **_source_values(data.get("source"))}
            if not exists:
                values = {k2: v for k2, v in values.items() if k2 != "order"}
            block, status = self._sync(ContentBlock, lookup, values, protect_manual=True, create=not exists)
            keep.add(block.pk)
            self._set_m2m(block.figures, data.get("figure_ids", []))
            self._exercises(block, data["exercises"])
        self._delete_missing(qs, keep)

    def _exercises(self, block: ContentBlock, exercises: list[dict[str, Any]]) -> None:
        qs = Exercise.objects.filter(block=block)
        seen: Counter = Counter()
        keep: set[int] = set()
        for order, data in enumerate(exercises):
            number = int(data["number"])
            k = seen[number]
            seen[number] += 1
            same = list(qs.filter(number=number).order_by("order", "pk").values_list("pk", flat=True))
            exists = k < len(same)
            lookup = {"pk": same[k]} if exists else {"block": block, "number": number, "textbook": self.textbook}
            answer = data.get("answer", {})
            values = {
                "order": order, "difficulty": data["difficulty"], "difficulty_ocr": data.get("difficulty_ocr") or "",
                "homework": data.get("homework", False), "condition": data["condition"],
                "condition_tail": data.get("condition_tail", ""), "task_verb": data.get("task_verb") or "",
                "answer_kind": data.get("answer_kind") or "", "is_word_problem": data.get("is_word_problem", False),
                "auto_checkable": data.get("auto_checkable", False), "has_fractions": data.get("has_fractions", False),
                "answer_check": _answer_check(answer), "needs_review": data["needs_review"],
                "text_source": data.get("text_source", "ocr"), "ocr_text": data.get("ocr_text") or "",
                "flags": data.get("flags", []), **_source_values(data.get("source")),
            }
            ex, status = self._sync(Exercise, lookup, values, protect_manual=True, create=not exists)
            keep.add(ex.pk)
            if status == "kept_manual":
                continue                                   # усе, що всередині ручної вправи, — теж ручне
            self._set_m2m(ex.figures, data.get("figure_ids", []))
            subs = self._subexercises(ex, data["subexercises"])
            self._answers(ex, data, subs)
        self._delete_missing(qs, keep)

    def _subexercises(self, ex: Exercise, items: list[dict[str, Any]]) -> list[tuple[SubExercise, dict]]:
        qs = SubExercise.objects.filter(exercise=ex)
        seen: Counter = Counter()
        keep: set[int] = set()
        result = []
        for order, data in enumerate(items):
            k = seen[data["number"]]
            seen[data["number"]] += 1
            same = list(qs.filter(number=data["number"]).order_by("order", "pk").values_list("pk", flat=True))
            exists = k < len(same)
            lookup = {"pk": same[k]} if exists else {"exercise": ex, "number": data["number"]}
            values = {"order": order, "text": data["text"], "expr": data.get("expr") or "",
                      "expr_status": data.get("expr_status") or "", "expr_issues": data.get("expr_issues", []),
                      "answer_check": _answer_check(data.get("answer", {})), "needs_review": data["needs_review"],
                      "text_source": data.get("text_source", "ocr"), "ocr_text": data.get("ocr_text") or ""}
            sub, _ = self._sync(SubExercise, lookup, values, protect_manual=True, create=not exists)
            keep.add(sub.pk)
            result.append((sub, data))
        self._delete_missing(qs, keep)
        return result

    def _answers(self, ex: Exercise, data: dict[str, Any], subs: list[tuple[SubExercise, dict]]) -> None:
        wanted: dict[tuple[int | None, str], str] = {}
        ex_answer = data.get("answer", {})
        book = ex_answer.get("book")
        if not book and data.get("book_answer_parts"):
            book = "; ".join(f"{n}) {v}" if n else v for n, v in data["book_answer_parts"].items())
        if book:
            wanted[(None, "book")] = book
        if ex_answer.get("computed"):
            wanted[(None, "computed")] = ex_answer["computed"]
        for sub, sdata in subs:
            for kind in ("book", "computed"):
                text = sdata.get("answer", {}).get(kind)
                if text:
                    wanted[(sub.pk, kind)] = text
        keep: set[int] = set()
        for (sub_pk, kind), text in wanted.items():
            ans, _ = self._sync(Answer, {"exercise": ex, "subexercise_id": sub_pk, "kind": kind},
                                {"text": text[:500], "value_numeric": _numeric(text)})
            keep.add(ans.pk)
        self._delete_missing(Answer.objects.filter(exercise=ex), keep)

    # ------------------------------------------------------------------ рисунки

    def _figure(self, data: dict[str, Any]) -> None:
        src = data.get("source") or {}
        values = {"number": data.get("number") or "", "caption": data.get("title", ""),
                  "source_page": src.get("pdf_page"), "source_bbox": src.get("bbox")}
        fig, status = self._sync(Figure, {"textbook": self.textbook, "figure_id": data["id"]}, values)
        self.figures[data["id"]] = fig
        path = self._resolve(data.get("path"))
        if path is None:
            if data.get("path"):
                self.result.warnings.append(f"рисунок {data['id']}: файл {data['path']} не знайдено")
            return
        content = path.read_bytes()
        if fig.image and _same_file(fig.image, content):
            return
        fig.image.save(f"{self.textbook.pdf_sha256[:8]}/{data['id']}.png", ContentFile(content), save=True)
        if status == "unchanged":
            self.result.counts["Figure"]["unchanged"] -= 1
            self.result.count("Figure", "updated")

    def _resolve(self, rel: str | None) -> Path | None:
        if not rel:
            return None
        for base in (Path(), self.base_dir):
            candidate = (base / rel)
            if candidate.is_file():
                return candidate
        return None

    def _set_m2m(self, manager, figure_ids: list[str]) -> None:
        wanted = {self.figures[f].pk for f in figure_ids if f in self.figures}
        current = set(manager.values_list("pk", flat=True))
        if wanted != current:
            manager.set(wanted)


# --------------------------------------------------------------------------- дрібниці


def _field_value(obj: models.Model, name: str) -> Any:
    field = obj._meta.get_field(name)
    if field.is_relation:
        return getattr(obj, name)
    return getattr(obj, field.attname)


def _source_values(source: dict[str, Any] | None) -> dict[str, Any]:
    return {"source_page": (source or {}).get("pdf_page"), "source_bbox": (source or {}).get("bbox")}


def _answer_check(answer: dict[str, Any]) -> str:
    if answer.get("mismatch"):
        return "mismatch"
    if answer.get("verified"):
        return "verified"
    return "unchecked"


def _numeric(text: str):
    from education.models import parse_answer_number
    return parse_answer_number(text)


def _same_file(field_file, content: bytes) -> bool:
    try:
        with field_file.open("rb") as fh:
            return hashlib.sha256(fh.read()).digest() == hashlib.sha256(content).digest()
    except (FileNotFoundError, ValueError, OSError):
        return False
