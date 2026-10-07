"""Генерує моки API з локальної db.sqlite3 (назви й id — справжні, прогрес — вигаданий).

Запуск: python tools/frontend/make_mocks.py   (з кореня репозиторію)
Формат = контракт із бекенд-чатом (docs/frontend/DECISIONS.md, «Контракт з бекендом»).
Перевірка моків — tools/frontend/check_mocks.py (запускається в тестах Django).
"""
import json
import math
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "education" / "static" / "education" / "mock"
DB = ROOT / "db.sqlite3"

BLOCK_ORDER = ["theory", "self_check", "oral_exercise", "exercise", "review_exercise", "wise_owl", "history_aside"]


def solved_for(stars, total):
    """Скільки розв’язано, щоб вийшло stars зірок (пороги 30 / 70 / 100 %)."""
    if not total:
        return 0
    return {3: total, 2: math.ceil(total * 0.75), 1: math.ceil(total * 0.4), 0: 0}[stars]


def lesson(id_, number, title, state="soon", stars=0, auto=0, ai=0, blocks=(), solved=None):
    total = auto + ai
    return {
        "id": id_, "number": number, "title": title, "state": state, "stars": stars,
        "solved": solved_for(stars, total) if solved is None else solved, "total": total,
        "tasks": {"auto": auto, "ai": ai}, "blocks": list(blocks), "map": {"x": None, "y": None},
    }


def load(db):
    c = sqlite3.connect(db)
    grades = {}
    for gid, number in c.execute("select id, number from education_grade order by number"):
        sections = []
        for sid, snum, stitle in c.execute(
                "select id, number, name_uk from education_section where grade_id=? order by number", (gid,)):
            paragraphs = []
            for pid, pnum, ptitle in c.execute(
                    "select id, number, name_uk from education_paragraph where section_id=? order by number", (sid,)):
                items = []
                for iid, inum, content in c.execute(
                        "select id, number, content from education_item where paragraph_id=? order by number", (pid,)):
                    row = c.execute(
                        """select coalesce(sum(e.auto_checkable),0), coalesce(sum(e.is_word_problem),0)
                           from education_contentblock b join education_exercise e on e.block_id=b.id and e.needs_review=0
                           where b.item_id=?""", (iid,)).fetchone()
                    blocks = {r[0] for r in c.execute(
                        "select distinct block_type from education_contentblock where item_id=?", (iid,))}
                    items.append({"id": iid, "number": inum, "title": (content or "").strip().splitlines()[0],
                                  "auto": int(row[0]), "ai": min(3, int(row[1])),
                                  "blocks": [b for b in BLOCK_ORDER if b in blocks]})
                paragraphs.append({"id": pid, "number": pnum, "title": ptitle, "items": items})
            sections.append({"id": sid, "number": snum, "title": stitle, "paragraphs": paragraphs})
        tb = c.execute("select author, year from education_textbook where grade_id=?", (gid,)).fetchone()
        grades[number] = {"sections": sections, "textbook": {"author": tb[0], "year": tb[1]} if tb else None}
    return grades


DEMO_TASKS = {"auto": 12, "ai": 2}   # умовні завдання для уроків, яких ще немає в БД (лише демо-моки)
DEMO_BLOCKS = ["theory", "self_check", "oral_exercise", "exercise", "review_exercise", "wise_owl"]


def grade5(src, progress, demo_tasks=False):
    """progress(item) → dict(state, stars) для уроку; решта полів — з БД.

    demo_tasks=True: урокам без вправ у БД (7–38) даємо умовні 12 + 2 завдання, щоб демо-стани
    (done/open/locked) не суперечили контракту («урок без завдань — завжди soon»)."""
    current = None
    sections = []
    for s in src["sections"]:
        paragraphs = []
        for p in s["paragraphs"]:
            items = []
            for it in p["items"]:
                pr = progress(it)
                if demo_tasks and it["auto"] + it["ai"] == 0 and pr["state"] != "soon":
                    it = {**it, "auto": DEMO_TASKS["auto"], "ai": DEMO_TASKS["ai"], "blocks": DEMO_BLOCKS}
                if pr["state"] == "current":
                    current = {"kind": "item", "id": it["id"]}
                items.append(lesson(it["id"], it["number"], it["title"], pr["state"], pr["stars"],
                                    it["auto"], it["ai"], it["blocks"], pr.get("solved")))
            paragraphs.append({"id": p["id"], "number": p["number"], "title": p["title"], "items": items})
        sections.append({"id": s["id"], "number": s["number"], "title": s["title"], "paragraphs": paragraphs})
    return {"grade": 5, "subject": "math", "textbook": src["textbook"], "current": current, "sections": sections}


def main():
    db = load(DB)
    g5, g6 = db[5], db[6]
    stars_real = {1: 3, 2: 2, 3: 3}

    def real(it):  # реальний стан БД: вправи є лише в уроках 1–6
        has = it["auto"] + it["ai"] > 0
        if not has:
            return {"state": "soon", "stars": 0}
        n = it["number"]
        if n in stars_real:
            return {"state": "done", "stars": stars_real[n]}
        if n == 4:
            return {"state": "current", "stars": 0, "solved": 4}
        return {"state": "locked", "stars": 0}

    pattern = [3, 2, 3, 3, 1, 3, 2, 3, 3]

    def demo(it):  # «багато зірок»: 1–9 пройдено, 10 поточний
        n = it["number"]
        if n < 10:
            return {"state": "done", "stars": pattern[n - 1]}
        if n == 10:
            return {"state": "current", "stars": 0}
        return {"state": "locked", "stars": 0}

    cycle = ["done", "current", "open", "locked", "soon"]

    def states(it):  # кожен стан у кожному параграфі
        st = cycle[(it["number"] - 1) % 5]
        return {"state": st, "stars": 2 if st == "done" else 0}

    files = {
        "grade-5.json": grade5(g5, real),
        "grade-5.demo.json": grade5(g5, demo, demo_tasks=True),
        "grade-5.states.json": grade5(g5, states, demo_tasks=True),
    }

    # 6 клас: урок = §, полів уроку — прямо на параграфі, items порожні
    files["grade-6.json"] = {
        "grade": 6, "subject": "math", "textbook": g6["textbook"] or {"author": "Тарасенкова Н. А.", "year": None},
        "current": None,
        "sections": [{"id": s["id"], "number": s["number"], "title": s["title"], "paragraphs": [
            {**lesson(p["id"], p["number"], p["title"]), "items": []} for p in s["paragraphs"]
        ]} for s in g6["sections"]],
    }

    def summary(m):
        lessons = [it for s in m["sections"] for p in s["paragraphs"] for it in (p["items"] or [p])]
        cur = m["current"]
        cur_lesson = next((l for l in lessons if cur and l["id"] == cur["id"]), None)
        return {
            "number": m["grade"], "subject": "math",
            "author": (m["textbook"] or {}).get("author", ""), "year": (m["textbook"] or {}).get("year"),
            "sections": len(m["sections"]), "lessons": len(lessons),
            "playable_lessons": sum(1 for l in lessons if l["total"]),
            "stars": sum(l["stars"] for l in lessons), "max_stars": 3 * len(lessons),
            "current": {**cur, "number": cur_lesson["number"]} if cur_lesson else None,
        }

    files["grades.json"] = [summary(files["grade-5.json"]), summary(files["grade-6.json"])]
    stars5 = files["grades.json"][0]["stars"]
    files["me.guest.json"] = {"authenticated": False, "name": "Гість", "points": 0, "streak": 0, "stars": 0}
    files["me.user.json"] = {"authenticated": True, "name": "anita", "points": stars5 * 7, "streak": 4, "stars": stars5}

    for name, data in files.items():
        (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("wrote", name)


if __name__ == "__main__":
    main()
