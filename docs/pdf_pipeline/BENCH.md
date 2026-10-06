# Бенчмарк OCR

CER — частка помилкових символів відносно ручної транскрипції (golden).
Нижче = краще. Запуск: `python -m education.pdf_pipeline.bench --out docs/pdf_pipeline/BENCH.md`

> Перший прогін зроблено у віртуальній машині Claude (Tesseract **4.1.1** + tessdata_best),
> не на Windows (Tesseract 5.5.3). Цифри орієнтовні — перезапусти у себе.

### 2026-10-06 — tesseract-4.1.1-tessdata

| конфігурація | сторінка | CER | слів | сер. conf | сек |
|---|---|---|---|---|---|
| raw_psm6 | merzlyak5_p007 | 0.039 | 330 | 89.7 | 40.7 |
| default_psm6 | merzlyak5_p007 | 0.033 | 329 | 90.3 | 54.9 |
| default_psm4 | merzlyak5_p007 | 0.028 | 321 | 90.9 | 50.2 |
| default_psm3 | merzlyak5_p007 | 0.028 | 321 | 90.9 | 52.1 |
| default_psm6_ukr | merzlyak5_p007 | 0.053 | 312 | 88.4 | 39.0 |
| lowres_psm6 | merzlyak5_p007 | 0.038 | 330 | 90.4 | 56.1 |

| конфігурація | середній CER |
|---|---|
| default_psm4 | 0.028 |
| default_psm3 | 0.028 |
| default_psm6 | 0.033 |
| lowres_psm6 | 0.038 |
| raw_psm6 | 0.039 |
| default_psm6_ukr | 0.053 |

### 2026-10-06 — tesseract-5.5.3.20260724-default

| конфігурація | сторінка | CER | слів | сер. conf | сек |
|---|---|---|---|---|---|
| default_psm4 | merzlyak5_p007 | 0.024 | 323 | 93.5 | 3.9 |
| default_psm6 | merzlyak5_p007 | 0.033 | 331 | 92.7 | 3.5 |

| конфігурація | середній CER |
|---|---|
| default_psm4 | 0.024 |
| default_psm6 | 0.033 |
