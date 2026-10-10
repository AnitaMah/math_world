# Ручна перевірка: сторінка `/review/`

Лише для персоналу (`is_staff`; анонімам — 302 на логін).

- `/review/` — черга вправ і підпунктів з `needs_review`, фільтри (підручник, §, тип, «пропущені»), лічильник «лишилось» по кожному §.
- `/review/<exercise|subexercise>/<pk>/` — вирізка сторінки книги, поточний текст, статус виразу; кнопки:
  **Зберегти й далі** (текст змінено → `edit`), **Усе правильно** (`confirm`), **Не ігрова / пропустити** (`skip`).
- Збереження: `text_source="manual"`, `needs_review=False`; для обчислювальних підпунктів вираз і відповідь перераховуються.
- Пропуск: `needs_review` лишається True (гра таку вправу не показує), `review_skipped=True` (з черги зникає; повернути — фільтр «пропущені» → «Повернути в чергу»).
- Кожна дія пишеться в `ManualEdit` (хто, коли, старий/новий текст). Ключ журналу — підручник + тип блоку + номер + сторінка + підпункт, не pk.
- Правки переживають `import_textbook` (`protect_manual`).

Перенос правок на іншу/свіжу БД:

    python manage.py export_manual_edits --out review/manual_edits.json
    python manage.py import_manual_edits --json review/manual_edits.json --dry-run
    python manage.py import_manual_edits --json review/manual_edits.json

Беруться остання дія по кожному ключу; повторний запуск нічого не змінює.
