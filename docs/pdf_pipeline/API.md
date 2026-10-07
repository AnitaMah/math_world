# API гри (фаза 21)

Прості JSON-ендпоінти (`education/api.py`), без DRF. Усі відповіді — UTF-8 JSON.
Помилки завжди в одному форматі:

```json
{"error": "not_found", "detail": "No Exercise matches the given query."}
```

| HTTP | `error` | коли |
|---|---|---|
| 400 | `bad_page`, `empty_answer`, `answer_too_long`, `bad_json` | неправильний запит |
| 403 | — (HTML від Django) | POST без CSRF-токена |
| 404 | `not_found`, `no_image` | немає об'єкта або вправа `needs_review` |
| 405 | `method_not_allowed` | не той метод |
| 409 | `no_answer` | для підпункту немає відповіді, з якою порівнювати |
| 429 | `too_many_attempts` | > 10 перевірок одного підпункту за хвилину |

**Правила:** GET-ендпоінти **ніколи** не віддають відповідей; вправи з `needs_review` у гру не потрапляють.

## Ендпоінти

### `GET /api/textbooks/`
```json
[{"id": 1, "title": "Математика. 5 клас", "author": "Мерзляк А. Г., …", "year": 2018,
  "subject": "math", "grade": 5, "profile": "math_merzlyak_5"}]
```

### `GET /api/textbooks/<id>/tree/` і `GET /api/grades/<n>/map/?subject=math`
Розділ → § → пункти, з кількістю ігрових вправ (для мапи; замінює статичний `map_data_uk.json`).
```json
{"grade": 5, "subject": "math", "sections": [{"id": 8, "number": 1, "title": "Розділ I. …",
  "paragraphs": [{"id": 49, "number": 1, "title": "§ 1. Натуральні числа", "exercises": 0,
    "items": [{"id": 117, "number": 1, "title": "Ряд натуральних чисел", "exercises": 21}]}]}]}
```
`exercises` у § — вправи блоків рівня § (у Тарасенкової урок = §).

### `GET /api/items/<id>/` · `GET /api/paragraphs/<id>/`
Теорія уроку: блоки `theory`, `self_check`, `history_aside`, `rule`, … з рисунками.

### `GET /api/items/<id>/exercises/?difficulty=medium,high&page=1&page_size=20`
(і `/api/paragraphs/<id>/exercises/`) — сторінка вправ уроку; `page_size` ≤ 50.
```json
{"count": 21, "page": 1, "pages": 2, "results": [
  {"id": 501, "number": 12, "difficulty": null, "block_type": "review_exercise",
   "condition": "Обчисліть:", "condition_tail": "", "homework": false, "auto_checkable": true,
   "subexercises": [{"id": 900, "number": "1", "text": "238 + 435;"}],
   "figures": [{"id": 3, "number": "1", "caption": "", "url": "/api/figures/3/image"}]}]}
```

### `GET /api/exercises/<id>/` — одна вправа (той самий формат).
### `GET /api/figures/<id>/image` — PNG рисунка.

### `POST /api/subexercises/<id>/check/`
Тіло — JSON `{"answer": "3,5"}` або форма `answer=3,5`; заголовок `X-CSRFToken`.
```json
{"subexercise": 900, "correct": true, "attempts_left": 9}
```
Порівняння: `3,5` = `3.5` = `7/2`, `0,75` = `3/4`, `−76` = `- 76`, `1 454` = `1454`,
`Так` = `так` = `+`, `12;16` = `12; 16`. Пріоритет — відповідь книги, інакше обчислена
(лише якщо вираз `ok`). Правильна відповідь у відповіді **не** повертається.

### `GET /api/csrf/` — ставить cookie `csrftoken`.

## Приклад з JS

```js
await fetch("/api/csrf/", {credentials: "same-origin"});
const token = document.cookie.match(/csrftoken=([^;]+)/)[1];
const r = await fetch(`/api/subexercises/${id}/check/`, {
  method: "POST", credentials: "same-origin",
  headers: {"Content-Type": "application/json", "X-CSRFToken": token},
  body: JSON.stringify({answer: input.value}),
});
const {correct, error} = await r.json();
```

## curl
```bash
curl http://127.0.0.1:8000/api/grades/5/map/
curl "http://127.0.0.1:8000/api/items/117/exercises/?page_size=5"
```

## Гра (фаза 21Б)

### `GET /api/play/items/<id>/` · `GET /api/play/paragraphs/<id>/`
Усі завдання уроку для екрана гри (без відповідей) і прогрес поточного гравця.
```json
{"lesson": {"id": 117, "kind": "item", "number": 1, "title": "Ряд натуральних чисел"},
 "tasks": [{"id": "s900", "kind": "auto", "points": 1, "solved": false,
            "exercise": {"id": 501, "number": 12, "difficulty": null, "condition": "Обчисліть:", "figures": []},
            "sub": {"id": 900, "number": "1", "text": "238 + 435;"}},
           {"id": "e505", "kind": "ai", "points": 2, "solved": false, "exercise": {…}, "sub": null}],
 "progress": {"solved": 3, "total": 7, "points": 4, "stars": 1}}
```

### `POST /api/subexercises/<id>/check/` (тепер з балами)
```json
{"subexercise": 900, "correct": true, "points": 1, "already_solved": false,
 "total_points": 13, "streak": 3, "progress": {"solved": 4, "total": 7, "points": 5, "stars": 2}}
```

### `POST /api/exercises/<id>/solution/` — ШІ-перевірка текстової задачі
Тіло `{"solution": "5 + 3 = 8. Відповідь: 8"}`.
```json
{"exercise": 505, "correct": false, "verdict": "incorrect",
 "feedback": "Перевір, на скільки більше яблук в Олі.", "points": 0, "progress": {…}}
```
`400 not_ai_task` — вправа не є ШІ-завданням уроку; `503 ai_unavailable` — немає ключа Gemini
або модель недоступна; `429` — більше 5 перевірок задачі за добу.

### `GET /api/me/`
`{"authenticated": false, "name": "Гість", "points": 13, "streak": 3}`

Сторінки: `/play/item/<id>/`, `/play/paragraph/<id>/`, `/accounts/login/`, `/accounts/signup/`.
