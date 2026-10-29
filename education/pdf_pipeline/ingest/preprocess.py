"""Етап 2: підготовка картинки сторінки для OCR.

Кожен крок — окрема чиста функція «картинка → картинка». Кроки збираються
в ``PreprocessSpec`` (рецепт), а ``apply()`` виконує рецепт і повертає
``Transform`` — як координати змінилися (збільшення, обрізка, поворот).
Через ``Transform.to_original(bbox)`` координати слів з OCR повертаються
в систему оригінальної картинки — саме їх ми зберігаємо в SourceRef.

Картинки — numpy-масиви OpenCV: кольорові в порядку BGR, сірі — 2D.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ..cache import load_json, load_json_or_none, save_json, short_hash
from ..datatypes import BBox, PageImage

Image = np.ndarray
Matrix = np.ndarray   # 3×3 афінна матриця: точка_нова = M @ [x, y, 1]

WHITE = 255


# =========================================================================== Transform


@dataclass(frozen=True)
class Transform:
    """Як координати оригінальної картинки перейшли в координати обробленої.

    Зберігається як 3×3 матриця (9 чисел). Кроки комбінуються множенням матриць.
    """

    matrix: tuple[float, ...] = (1, 0, 0, 0, 1, 0, 0, 0, 1)

    @property
    def m(self) -> Matrix:
        return np.array(self.matrix, dtype=float).reshape(3, 3)

    def then(self, step: Matrix) -> Transform:
        """Новий Transform: спочатку self, потім step."""
        return Transform(tuple(float(v) for v in (step @ self.m).ravel()))

    def to_original(self, bbox: BBox) -> BBox:
        """Переводить прямокутник з обробленої картинки в оригінальну.

        Беремо 4 кути, застосовуємо обернену матрицю і обводимо прямокутником
        (після повороту кути вже не лежать на одній горизонталі).
        """
        inv = np.linalg.inv(self.m)
        corners = np.array([[bbox.x0, bbox.y0, 1], [bbox.x1, bbox.y0, 1],
                            [bbox.x0, bbox.y1, 1], [bbox.x1, bbox.y1, 1]], dtype=float).T
        xs, ys, _ = inv @ corners
        return BBox(math.floor(xs.min()), math.floor(ys.min()),
                    math.ceil(xs.max()), math.ceil(ys.max()))

    def to_dict(self) -> list[float]:
        return list(self.matrix)

    @classmethod
    def from_dict(cls, data: list[float]) -> Transform:
        return cls(tuple(float(v) for v in data))


def _scale_matrix(factor: float) -> Matrix:
    return np.array([[factor, 0, 0], [0, factor, 0], [0, 0, 1]], dtype=float)


def _shift_matrix(dx: float, dy: float) -> Matrix:
    return np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1]], dtype=float)


# =========================================================================== кроки (чисті функції)


def to_gray(img: Image) -> Image:
    """Кольорова (BGR) → сіра. Сіра лишається як є."""
    if img.ndim == 2:
        return img.copy()
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def upscale(img: Image, factor: float = 2.0) -> tuple[Image, Matrix]:
    """Збільшує картинку в ``factor`` разів (бікубічна інтерполяція).

    Tesseract найкраще читає літери висотою ~25–35 px; у сканах 150 ppi вони ~12–15 px.
    """
    if factor == 1:
        return img.copy(), _scale_matrix(1)
    out = cv2.resize(img, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)
    return out, _scale_matrix(factor)


def denoise(img: Image, h: float = 10.0) -> Image:
    """Прибирає зернистість скану (Non-Local Means). h — сила: більше = сильніше, але розмиває."""
    if img.ndim == 2:
        return cv2.fastNlMeansDenoising(img, None, h=h)
    return cv2.fastNlMeansDenoisingColored(img, None, h, h)


def normalize_contrast(img: Image, clip_limit: float = 2.0, tile: int = 8) -> Image:
    """Локальне вирівнювання контрасту (CLAHE) — для блідих або нерівно освітлених сканів."""
    gray = to_gray(img)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile, tile))
    return clahe.apply(gray)


def remove_color_background(img: Image, max_saturation: int = 110, min_value: int = 190) -> Image:
    """Світлі кольорові плашки (жовтий/блакитний фон рамок) → білий.

    Пастельний фон: світлий (V ≥ min_value) і помірно насичений (S ≤ max_saturation).
    Кольоровий **текст** (червоний заголовок «Задача від Мудрої Сови», сині/зелені
    номери) сильно насичений — його не чіпаємо. Працює лише з кольоровою картинкою.
    """
    if img.ndim == 2:
        return img.copy()
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    s, v = hsv[..., 1], hsv[..., 2]
    background = (v >= min_value) & (s <= max_saturation) & (s > 15)
    out = img.copy()
    out[background] = (WHITE, WHITE, WHITE)
    return out


def binarize_otsu(img: Image) -> Image:
    """Чорно-біла картинка з автоматичним порогом (Otsu) — добре для рівного освітлення."""
    _, out = cv2.threshold(to_gray(img), 0, WHITE, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return out


def binarize_adaptive(img: Image, block_size: int = 31, c: int = 15) -> Image:
    """Адаптивний поріг (окремий для кожної ділянки) — для нерівного освітлення/тіней."""
    return cv2.adaptiveThreshold(to_gray(img), WHITE, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY, block_size, c)


def estimate_skew(img: Image, max_angle: float = 5.0, step: float = 0.25) -> float:
    """Кут (у градусах), на який треба повернути картинку, щоб рядки тексту стали горизонтальні.

    Конвенція OpenCV: додатний кут — поворот проти годинникової стрілки.

    Метод проєкцій: повертаємо зменшену чорно-білу копію на різні кути і рахуємо,
    наскільки «смугастою» стає сума пікселів по рядках. Коли рядки тексту
    горизонтальні, рядки-з-текстом і проміжки між ними чергуються найрізкіше
    (найбільша дисперсія).
    """
    gray = to_gray(img)
    scale = 800 / max(gray.shape)
    small = cv2.resize(gray, None, fx=min(scale, 1.0), fy=min(scale, 1.0), interpolation=cv2.INTER_AREA)
    _, ink = cv2.threshold(small, 0, 1, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = ink.shape
    center = (w / 2, h / 2)

    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-max_angle, max_angle + step / 2, step):
        rot = cv2.getRotationMatrix2D(center, float(angle), 1.0)
        rotated = cv2.warpAffine(ink, rot, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        score = float(np.var(rotated.sum(axis=1)))
        if score > best_score:
            best_angle, best_score = float(angle), score
    return best_angle


def rotate(img: Image, angle: float) -> tuple[Image, Matrix]:
    """Повертає картинку на ``angle`` градусів навколо центру (поля заповнюються білим)."""
    h, w = img.shape[:2]
    rot = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    border = WHITE if img.ndim == 2 else (WHITE, WHITE, WHITE)
    out = cv2.warpAffine(img, rot, (w, h), flags=cv2.INTER_CUBIC, borderValue=border)
    return out, np.vstack([rot, [0, 0, 1]])


def deskew(img: Image, max_angle: float = 5.0, min_angle: float = 0.2) -> tuple[Image, Matrix]:
    """Вирівнює нахил: знаходить кут (estimate_skew) і повертає. Дрібний нахил (< min_angle) не чіпає."""
    angle = estimate_skew(img, max_angle=max_angle)
    if abs(angle) < min_angle:
        return img.copy(), _scale_matrix(1)
    return rotate(img, angle)


def crop_margins(img: Image, pad: int = 10, ink_threshold: int = 200) -> tuple[Image, Matrix]:
    """Обрізає білі поля навколо вмісту (з запасом ``pad``)."""
    gray = to_gray(img)
    ys, xs = np.where(gray < ink_threshold)
    if len(xs) == 0:
        return img.copy(), _scale_matrix(1)
    h, w = gray.shape
    x0, y0 = max(int(xs.min()) - pad, 0), max(int(ys.min()) - pad, 0)
    x1, y1 = min(int(xs.max()) + pad + 1, w), min(int(ys.max()) + pad + 1, h)
    return img[y0:y1, x0:x1].copy(), _shift_matrix(-x0, -y0)


# =========================================================================== рецепт (spec)

# Реєстр кроків: назва → функція. Геометричні кроки повертають (картинка, матриця).
_PIXEL_STEPS: dict[str, Callable[..., Image]] = {
    "to_gray": to_gray,
    "denoise": denoise,
    "normalize_contrast": normalize_contrast,
    "remove_color_background": remove_color_background,
    "binarize_otsu": binarize_otsu,
    "binarize_adaptive": binarize_adaptive,
}
_GEOMETRY_STEPS: dict[str, Callable[..., tuple[Image, Matrix]]] = {
    "upscale": upscale,
    "deskew": deskew,
    "rotate": rotate,
    "crop_margins": crop_margins,
}
STEP_NAMES = frozenset(_PIXEL_STEPS) | frozenset(_GEOMETRY_STEPS)


@dataclass(frozen=True)
class Step:
    """Один крок рецепту: назва + параметри (як кортеж пар, щоб об'єкт був незмінним)."""

    name: str
    params: tuple[tuple[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.name not in STEP_NAMES:
            raise ValueError(f"Невідомий крок {self.name!r}; є: {sorted(STEP_NAMES)}")


def step(name: str, **params: Any) -> Step:
    """Зручний конструктор: step("upscale", factor=2)."""
    return Step(name, tuple(sorted(params.items())))


@dataclass(frozen=True)
class PreprocessSpec:
    """Рецепт препроцесингу: впорядкований список кроків."""

    name: str
    steps: tuple[Step, ...] = field(default_factory=tuple)

    def cache_key(self) -> str:
        """Стабільний короткий хеш рецепту — назва папки кешу.

        Залежить лише від кроків і параметрів (не від назви): той самий рецепт
        під іншою назвою дасть той самий ключ.
        """
        return short_hash([[s.name, list(s.params)] for s in self.steps])


PRESET_RAW = PreprocessSpec("raw", ())
PRESET_DEFAULT = PreprocessSpec("default", (
    step("remove_color_background"),
    step("to_gray"),
    step("denoise", h=10.0),          # до збільшення: у 4 рази менше пікселів → швидше
    step("upscale", factor=2.0),
    step("deskew"),
))
PRESET_LOWRES = PreprocessSpec("lowres", (
    step("remove_color_background"),
    step("to_gray"),
    step("denoise", h=12.0),
    step("upscale", factor=3.0),
    step("deskew"),
))
PRESETS = {p.name: p for p in (PRESET_RAW, PRESET_DEFAULT, PRESET_LOWRES)}


def choose_preset(page: PageImage) -> PreprocessSpec:
    """Сторінки з низькою роздільністю (Тарасенкова, ~76 ppi) збільшуємо сильніше."""
    return PRESET_LOWRES if page.low_res else PRESET_DEFAULT


def apply(img: Image, spec: PreprocessSpec) -> tuple[Image, Transform]:
    """Виконує рецепт. Повертає оброблену картинку і Transform для координат."""
    transform = Transform()
    for st in spec.steps:
        params = dict(st.params)
        if st.name in _GEOMETRY_STEPS:
            img, matrix = _GEOMETRY_STEPS[st.name](img, **params)
            transform = transform.then(matrix)
        else:
            img = _PIXEL_STEPS[st.name](img, **params)
    return img, transform


# =========================================================================== робота з файлами і кеш


def load_image(path: str | Path) -> Image:
    """Читає картинку з диска (працює і з кириличними шляхами у Windows)."""
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Не вдалося прочитати картинку: {path}")
    return img


class PageImageCache:
    """Невеликий LRU-кеш декодованих сторінок: тримає не більше `size` картинок (кожна ~10–30 МБ у пам'яті),
    а не всю книгу. Порядок звернень майже завжди посторінковий, тож повторних читань з диска мало."""

    def __init__(self, paths: dict, size: int = 3):
        from collections import OrderedDict
        self.paths = dict(paths or {})
        self.size = max(1, size)
        self._items: "OrderedDict[int, Image]" = OrderedDict()
        self.loads = 0                       # скільки разів читали з диска (для тестів)

    def __contains__(self, page) -> bool:
        return page in self.paths

    def get(self, page):
        if page is None or page not in self.paths:
            return None
        if page in self._items:
            self._items.move_to_end(page)
            return self._items[page]
        img = load_image(self.paths[page])
        self.loads += 1
        self._items[page] = img
        while len(self._items) > self.size:
            self._items.popitem(last=False)
        return img


def save_image(path: str | Path, img: Image) -> None:
    """Записує PNG (теж безпечно для кириличних шляхів)."""
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError(f"Не вдалося закодувати картинку: {path}")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    buf.tofile(str(path))


@dataclass(frozen=True)
class PreparedPage:
    """Оброблена сторінка: де лежить картинка і як повернути координати в оригінал."""

    page: PageImage
    path: Path
    spec_name: str
    spec_key: str
    transform: Transform

    def to_dict(self) -> dict[str, Any]:
        return {"page": self.page.to_dict(), "path": self.path.as_posix(),
                "spec_name": self.spec_name, "spec_key": self.spec_key,
                "transform": self.transform.to_dict()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PreparedPage:
        return cls(page=PageImage.from_dict(data["page"]), path=Path(data["path"]),
                   spec_name=data["spec_name"], spec_key=data["spec_key"],
                   transform=Transform.from_dict(data["transform"]))


def prepared_path(page: PageImage, spec: PreprocessSpec) -> Path:
    """``<cache>/<sha>/prep/<spec_key>/p-007.png`` — поруч із папкою pages/ цього ж PDF."""
    sha_dir = page.path.parent.parent
    return sha_dir / "prep" / spec.cache_key() / page.path.name


def preprocess_page(page: PageImage, spec: PreprocessSpec | None = None, force: bool = False) -> PreparedPage:
    """Обробляє картинку сторінки за рецептом (за замовчуванням — choose_preset) з кешем."""
    spec = spec or choose_preset(page)
    out = prepared_path(page, spec)
    meta = out.with_suffix(".json")
    if not force and out.exists() and meta.exists():
        cached = load_json_or_none(meta)
        if cached is not None:
            try:
                return PreparedPage.from_dict(cached)
            except (KeyError, TypeError, ValueError):
                pass                      # зіпсований кеш — обробимо наново

    img, transform = apply(load_image(page.path), spec)
    save_image(out, img)
    result = PreparedPage(page=page, path=out, spec_name=spec.name,
                          spec_key=spec.cache_key(), transform=transform)
    save_json(meta, result.to_dict())
    return result
