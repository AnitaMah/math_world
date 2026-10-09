"""Усі тести фронтенду однією командою (фаза 19). Працює і на Windows (без make).

    python tools/frontend/run_tests.py              # юніт-тести JS + Django-тести UI + візуальні
    python tools/frontend/run_tests.py --baseline   # перезаписати еталони docs/frontend/baseline/
    python tools/frontend/run_tests.py --no-visual  # без Playwright (швидко)

Візуальні тести йдуть на окремій базі tools/frontend/ui.sqlite3 (міграції + seed_ui.py), робоча
db.sqlite3 не змінюється. Потрібні: Node ≥ 20, `npm ci` у tools/frontend, `npx playwright install chromium`.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
UI_DB = HERE / "ui.sqlite3"


def run(cmd, cwd=ROOT, env=None):
    print("\n$ " + " ".join(str(c) for c in cmd), flush=True)
    code = subprocess.call([str(c) for c in cmd], cwd=cwd, env=env, shell=(os.name == "nt" and cmd[0] in ("npm", "npx")))
    if code:
        sys.exit(code)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", action="store_true", help="оновити еталонні знімки")
    ap.add_argument("--no-visual", action="store_true", help="пропустити Playwright")
    a = ap.parse_args()
    py = sys.executable

    run(["npm", "test"], cwd=HERE)                                             # юніт-тести JS
    run([py, "manage.py", "test", "education.tests_ui"])                       # шаблони, views, CSS
    run([py, HERE / "check_mocks.py"])                                         # моки = контракт
    if a.no_visual:
        return

    env = {**os.environ, "DB_PATH": str(UI_DB), "PYTHON": py}
    if UI_DB.exists():
        UI_DB.unlink()
    run([py, "manage.py", "migrate", "-v0"], env=env)
    run([py, HERE / "seed_ui.py"], env=env)
    if shutil.which("npx") is None:
        sys.exit("npx не знайдено — встанови Node.js")
    run(["npx", "playwright", "test", *(["--update-snapshots"] if a.baseline else [])], cwd=HERE, env=env)


if __name__ == "__main__":
    main()
