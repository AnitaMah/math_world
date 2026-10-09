"""Звіряє структуру реальних відповідей API з моками фронтенду (фаза 17, крок 0588).

Моки — контракт (education/static/education/mock/). Порівнюється форма, не значення: шляхи ключів і
типи. Масиви зводяться до одного «елемента» (об'єднання ключів усіх елементів).

    python tools/frontend/diff_contract.py                    # http://127.0.0.1:8000
    python tools/frontend/diff_contract.py --base http://127.0.0.1:8002 --grade 5

Код виходу 1, якщо в реальній відповіді бракує полів контракту або тип інший.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

MOCK = Path(__file__).resolve().parents[2] / "education/static/education/mock"
MOCK_ONLY = {"_mock_answers"}           # службові поля моків


def tname(v):
    if v is None:
        return "null"
    return {bool: "bool", int: "number", float: "number", str: "string", list: "array", dict: "object"}[type(v)]


def shape(v, path="", out=None):
    """{шлях: {типи}}; елементи масиву — під шляхом `[]`."""
    out = {} if out is None else out
    out.setdefault(path or "$", set()).add(tname(v))
    if isinstance(v, dict):
        for k, x in v.items():
            if k not in MOCK_ONLY:
                shape(x, f"{path}.{k}", out)
    elif isinstance(v, list):
        for x in v:
            shape(x, f"{path}[]", out)
    return out


def compare(name, mock, real):
    m, r = shape(mock), shape(real)
    problems, notes = [], []
    for p, types in sorted(m.items()):
        if p not in r:
            if not any(p.startswith(q + ".") or p.startswith(q + "[]") for q in m if q != p and q in r and r[q] == {"null"}):
                problems.append(f"  бракує   {p}  ({'/'.join(sorted(types))})")
            continue
        real_t = r[p] - {"null"} if "null" not in types else r[p]
        if real_t and not (real_t & (types | {"null"})):
            problems.append(f"  тип      {p}: контракт {'/'.join(sorted(types))}, реально {'/'.join(sorted(r[p]))}")
    for p in sorted(set(r) - set(m)):
        notes.append(f"  зайве    {p}")
    print(f"== {name}: {'OK' if not problems else f'{len(problems)} розбіжн.'}")
    print("\n".join(problems + notes) or "  (структура збігається)")
    return not problems


def get(base, url):
    try:
        with urllib.request.urlopen(base + url, timeout=30) as resp:
            return json.load(resp)
    except OSError as exc:
        sys.exit(f"Не вдалося отримати {base + url}: {exc}. Чи запущено `python manage.py runserver`?")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--grade", type=int, default=5)
    a = ap.parse_args()
    mock = lambda n: json.loads((MOCK / n).read_text(encoding="utf-8"))
    ok = True
    ok &= compare("/api/grades/", mock("grades.json"), get(a.base, "/api/grades/"))
    gmap = get(a.base, f"/api/grades/{a.grade}/map/")
    ok &= compare(f"/api/grades/{a.grade}/map/", mock(f"grade-{a.grade}.json"), gmap)
    ok &= compare("/api/me/ (гість)", mock("me.guest.json"), get(a.base, "/api/me/"))
    first = next((it for s in gmap["sections"] for p in s["paragraphs"] for it in (p["items"] or [p])
                  if it.get("state") in ("current", "open", "done")), None)
    if first:
        kind = "items" if any(first is it for s in gmap["sections"] for p in s["paragraphs"] for it in p["items"]) else "paragraphs"
        ok &= compare(f"/api/play/{kind}/{first['id']}/", mock("play.json"), get(a.base, f"/api/play/{kind}/{first['id']}/"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
