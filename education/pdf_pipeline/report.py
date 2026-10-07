"""HTML-звіт валідації (фаза 14): один файл без зовнішніх залежностей.

Що в ньому:
1. зведення — скільки пунктів/блоків/вправ/відповідей, проблеми за кодами;
2. таблиця проблем (спершу error, потім warning, info) з вирізкою сторінки за bbox
   (PNG у base64 прямо в HTML) поруч з розпізнаним текстом;
3. статистика нормалізації (які правила скільки разів спрацювали);
4. дерево документа з ``<details>``; ноди з ``needs_review`` підсвічені;
5. посилання на дебаг-PNG розмітки сторінок (layout_debug), якщо вони є.

Звіт відкривається просто в браузері; картинки вбудовані, тож файл можна переслати.
"""
from __future__ import annotations

import base64
import html
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .datatypes import BBox, Node
from .validate import Problem, count_by_code, node_label

MAX_CROPS = 300          # більше вирізок — файл стає важким; решта проблем без картинок
CROP_PAD = 12
CROP_MAX_WIDTH = 700

_CSS = """
:root{--bg:#fff;--fg:#1d1d1f;--muted:#6b7280;--line:#e5e7eb;--err:#b91c1c;--warn:#b45309;--info:#1d4ed8;--rev:#fef3c7}
@media (prefers-color-scheme:dark){:root{--bg:#111827;--fg:#f3f4f6;--muted:#9ca3af;--line:#374151;--err:#f87171;--warn:#fbbf24;--info:#93c5fd;--rev:#422006}}
body{font:14px/1.45 system-ui,sans-serif;background:var(--bg);color:var(--fg);margin:0 auto;max-width:1200px;padding:16px}
h1{font-size:22px}h2{font-size:18px;margin-top:28px;border-bottom:1px solid var(--line);padding-bottom:4px}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid var(--line);padding:6px;vertical-align:top;text-align:left}
.cards{display:flex;flex-wrap:wrap;gap:8px}.card{border:1px solid var(--line);border-radius:8px;padding:8px 12px;min-width:110px}
.card b{display:block;font-size:20px}.muted{color:var(--muted)}
.sev-error{color:var(--err);font-weight:600}.sev-warning{color:var(--warn);font-weight:600}.sev-info{color:var(--info)}
img.crop{max-width:100%;border:1px solid var(--line)}code,pre{font:12px/1.4 ui-monospace,monospace;white-space:pre-wrap}
details{margin-left:14px}summary{cursor:pointer}.review>summary,.review.leaf{background:var(--rev)}
.leaf{margin-left:28px}.filters label{margin-right:12px}
"""

_JS = """
document.querySelectorAll('.filters input').forEach(cb=>cb.addEventListener('change',()=>{
  const on=[...document.querySelectorAll('.filters input:checked')].map(x=>x.value);
  document.querySelectorAll('tr[data-sev]').forEach(tr=>tr.style.display=on.includes(tr.dataset.sev)?'':'none');
}));
"""


def _e(text: Any) -> str:
    return html.escape(str(text), quote=True)


# --------------------------------------------------------------------------- вирізки


def crop_png_b64(image: np.ndarray, box: BBox, pad: int = CROP_PAD, max_width: int = CROP_MAX_WIDTH) -> str:
    """Вирізка сторінки за bbox (з полями) → PNG у base64."""
    h, w = image.shape[:2]
    x0, y0 = max(0, box.x0 - pad), max(0, box.y0 - pad)
    x1, y1 = min(w, box.x1 + pad), min(h, box.y1 + pad)
    crop = image[y0:y1, x0:x1]
    if crop.size == 0:
        return ""
    if crop.shape[1] > max_width:
        scale = max_width / crop.shape[1]
        crop = cv2.resize(crop, (max_width, max(1, int(crop.shape[0] * scale))), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".png", crop)
    return base64.b64encode(buf.tobytes()).decode("ascii") if ok else ""


class _Images:
    """Ліниве завантаження сторінок (кожна читається з диска один раз)."""

    def __init__(self, page_images: Mapping[int, Path] | None):
        self.paths = dict(page_images or {})
        self.cache: dict[int, np.ndarray] = {}

    def get(self, page: int | None) -> np.ndarray | None:
        if page is None or page not in self.paths:
            return None
        if page not in self.cache:
            from .preprocess import load_image
            self.cache[page] = load_image(self.paths[page])
        return self.cache[page]


# --------------------------------------------------------------------------- секції


def _summary_html(stats: Mapping[str, int], problems: Sequence[Problem]) -> str:
    cards = "".join(f'<div class="card"><span class="muted">{_e(k)}</span><b>{v}</b></div>' for k, v in stats.items())
    by_sev = {s: sum(1 for p in problems if p.severity == s) for s in ("error", "warning", "info")}
    sev = " · ".join(f'<span class="sev-{s}">{s}: {n}</span>' for s, n in by_sev.items())
    codes = "".join(f"<tr><td><code>{_e(c)}</code></td><td>{n}</td></tr>" for c, n in count_by_code(problems).items())
    return (f'<div class="cards">{cards}</div><p>{sev}</p>'
            f"<table><tr><th>Код</th><th>Кількість</th></tr>{codes}</table>")


def _problems_html(problems: Sequence[Problem], images: _Images, max_crops: int) -> str:
    rows, crops = [], 0
    for p in problems:
        img_html = ""
        if p.source and p.source.bbox and crops < max_crops:
            image = images.get(p.source.pdf_page)
            if image is not None:
                b64 = crop_png_b64(image, p.source.bbox)
                if b64:
                    img_html = f'<img class="crop" alt="" src="data:image/png;base64,{b64}">'
                    crops += 1
        page = f"{p.pdf_page}" if p.pdf_page else "—"
        rows.append(
            f'<tr data-sev="{p.severity}"><td class="sev-{p.severity}">{p.severity}</td>'
            f"<td><code>{_e(p.code)}</code><br><span class=muted>стор. {page}</span></td>"
            f"<td>{_e(p.message)}<br><span class=muted>{_e(p.node_path)}</span>"
            f"{'<pre>' + _e(p.text) + '</pre>' if p.text else ''}</td><td>{img_html}</td></tr>")
    filters = "".join(f'<label><input type="checkbox" value="{s}" checked> {s}</label>' for s in ("error", "warning", "info"))
    note = f'<p class="muted">Вирізок: {crops} (ліміт {max_crops}).</p>'
    return (f'<div class="filters">{filters}</div>{note}<table><tr><th>Рівень</th><th>Код</th>'
            f"<th>Опис / де / текст</th><th>Сторінка</th></tr>{''.join(rows)}</table>")


def _node_html(node: Node) -> str:
    label = node_label(node)
    title = f" «{_e(node.title)}»" if node.title else ""
    extra = []
    for key in ("difficulty", "expr_status", "answer", "answer_book"):
        if key in node.data:
            extra.append(f"{key}={_e(node.data[key])}")
    page = f" <span class=muted>стор. {node.source.pdf_page}</span>" if node.source else ""
    head = f"<b>{_e(label)}</b>{title}{page} <span class=muted>{' · '.join(extra)}</span>"
    text = node.data.get("condition") or node.text
    body = f"<pre>{_e(text[:400])}</pre>" if text else ""
    cls = " review" if node.needs_review else ""
    if not node.children:
        return f'<div class="leaf{cls}">{head}{body}</div>'
    opened = " open" if node.kind in ("textbook", "section", "paragraph") else ""
    inner = "".join(_node_html(c) for c in node.children)
    return f'<details class="{cls.strip()}"{opened}><summary>{head}</summary>{body}{inner}</details>'


def _norm_html(norm_stats: Mapping[str, int] | None) -> str:
    if not norm_stats:
        return '<p class="muted">Немає даних.</p>'
    rows = "".join(f"<tr><td><code>{_e(k)}</code></td><td>{v}</td></tr>"
                   for k, v in sorted(norm_stats.items(), key=lambda kv: -kv[1]))
    return f"<table><tr><th>Правило</th><th>Спрацювань</th></tr>{rows}</table>"


def _debug_html(debug_pngs: Iterable[Path], report_dir: Path) -> str:
    links = []
    for png in sorted(debug_pngs):
        try:
            href = Path(png).resolve().relative_to(report_dir.resolve()).as_posix()
        except ValueError:
            href = Path(png).resolve().as_uri()
        links.append(f'<a href="{_e(href)}">{_e(Path(png).name)}</a>')
    return " · ".join(links) or '<p class="muted">Немає.</p>'


# --------------------------------------------------------------------------- API


def render_report(root: Node, problems: Sequence[Problem], stats: Mapping[str, int],
                  page_images: Mapping[int, Path] | None = None, norm_stats: Mapping[str, int] | None = None,
                  debug_pngs: Iterable[Path] = (), report_dir: Path = Path("."),
                  max_crops: int = MAX_CROPS, title: str | None = None) -> str:
    images = _Images(page_images)
    name = title or root.title or "Звіт"
    return (
        f'<!doctype html><html lang="uk"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{_e(name)} — звіт</title>'
        f"<style>{_CSS}</style></head><body><h1>{_e(name)} — звіт валідації</h1>"
        f"<h2>Зведення</h2>{_summary_html(stats, problems)}"
        f"<h2>Проблеми ({len(problems)})</h2>{_problems_html(problems, images, max_crops)}"
        f"<h2>Нормалізація</h2>{_norm_html(norm_stats)}"
        f"<h2>Дерево</h2>{_node_html(root)}"
        f"<h2>Дебаг розмітки</h2>{_debug_html(debug_pngs, report_dir)}"
        f"<script>{_JS}</script></body></html>")


def write_report(path: str | Path, root: Node, problems: Sequence[Problem], stats: Mapping[str, int],
                 **kwargs: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = render_report(root, problems, stats, report_dir=path.parent, **kwargs)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return path
