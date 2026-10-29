from django.db import models


class Subject(models.Model):
    """
    A school subject (math, Ukrainian language, ...). Added so Grade can
    stop being keyed only by number -- two subjects' 5th grade curricula
    would otherwise collide under the same Grade row. Not yet linked to
    Grade (see Step 5 of the refactor plan); this step only introduces
    the table.
    """
    code = models.CharField(max_length=50, unique=True)
    name_uk = models.CharField(max_length=100)
    name_de = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.name_uk


class Grade(models.Model):
    # Required as of Step 7 of the refactor plan. Step 6's data migration
    # backfilled every pre-existing row to the "math" Subject first, so
    # this tightening doesn't break anything already in the database.
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    number = models.IntegerField()
    name_uk = models.CharField(max_length=100)
    name_de = models.CharField(max_length=100, blank=True, null=True)
    theme_uk = models.CharField(max_length=200, blank=True, null=True)
    theme_de = models.CharField(max_length=200, blank=True, null=True)

    def get_name(self, lang="uk"):
        return self.name_de if lang == "de" and self.name_de else self.name_uk

    def __str__(self):
        return f"{self.number} клас – {self.name_uk}"


class Textbook(models.Model):
    """Один конкретний підручник (PDF), з якого імпортовано розділи/уроки/вправи.

    pdf_sha256 — унікальний «паспорт» файлу: той самий PDF не імпортується двічі
    як різні книжки, а повторний імпорт оновлює наявну (фаза 19).
    """
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="textbooks")
    grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name="textbooks")
    profile_code = models.CharField(max_length=50)            # math_merzlyak_5, math_tarasenkova_6
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    pdf_name = models.CharField(max_length=255, blank=True)
    pdf_sha256 = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["grade__number", "title"]

    def __str__(self):
        author = f" ({self.author})" if self.author else ""
        return f"{self.title}{author}"


class Section(models.Model):
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE)
    # null — розділи, створені старим імпортом до появи Textbook
    textbook = models.ForeignKey(Textbook, on_delete=models.CASCADE, null=True, blank=True,
                                 related_name="sections")
    number = models.IntegerField()
    name_uk = models.CharField(max_length=200)
    name_de = models.CharField(max_length=200, blank=True, null=True)
    map_x = models.IntegerField(null=True, blank=True)
    map_y = models.IntegerField(null=True, blank=True)

    def get_name(self, lang="uk"):
        return self.name_de if lang == "de" and self.name_de else self.name_uk

    def __str__(self):
        return f"Розділ {self.number}: {self.name_uk}"


class Paragraph(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    number = models.IntegerField()
    name_uk = models.CharField(max_length=200)
    name_de = models.CharField(max_length=200, blank=True, null=True)
    map_x = models.IntegerField(null=True, blank=True)
    map_y = models.IntegerField(null=True, blank=True)

    def get_name(self, lang="uk"):
        return self.name_de if lang == "de" and self.name_de else self.name_uk

    def __str__(self):
        return f"§ {self.number}: {self.name_uk}"


class Item(models.Model):
    paragraph = models.ForeignKey(Paragraph, on_delete=models.CASCADE)
    number = models.IntegerField()
    content = models.TextField()
    content_de = models.TextField(blank=True, null=True)
    type = models.CharField(max_length=50, default='основний')
    image_path = models.CharField(max_length=255, blank=True, null=True)
    # Ручна позиція вузла на мапі (viewBox 1080×820); null — розкладка рахується на фронтенді
    map_x = models.IntegerField(null=True, blank=True)
    map_y = models.IntegerField(null=True, blank=True)

    def details_list(self, lang='uk'):
        import re
        text = self.content_de if lang == 'de' and self.content_de else self.content
        if not text:
            return []
        text = text.strip()
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if len(lines) <= 1:
            parts = re.split(r'(?<=[\.\!\?])\s+', text)
            lines = [p.strip() for p in parts if p.strip()]
        return lines

    def get_theory_practice(self):
        try:
            return self.theorypractice
        except:
            return None

    def __str__(self):
        return f"Завдання {self.number} ({self.paragraph})"


# Спільні для пайплайна і БД переліки. Мають збігатися з education/pdf_pipeline/output/schema.py
# (тест education.tests.ChoicesMatchPipelineTests це перевіряє).
DIFFICULTY_CHOICES = [
    ("preparatory", "Підготовчий (′)"),
    ("medium", "Середній (°)"),
    ("sufficient", "Достатній (•)"),
    ("high", "Високий (••, *)"),
    ("olympiad", "Олімпіадний"),
    ("unknown", "Невідомий значок"),
]

TEXT_SOURCE_CHOICES = [
    ("ocr", "OCR"),
    ("vision", "Vision-LLM"),
    ("manual", "Вручну"),
]

ANSWER_CHECK_CHOICES = [
    ("unchecked", "Не перевірено"),
    ("verified", "Збігається з книгою"),
    ("mismatch", "Не збігається з книгою"),
]


class SourceMixin(models.Model):
    """Звідки в PDF узявся запис: сторінка і прямокутник [x0, y0, x1, y1] на картинці сторінки."""

    source_page = models.PositiveIntegerField(null=True, blank=True)
    source_bbox = models.JSONField(null=True, blank=True)
    needs_review = models.BooleanField(default=False, db_index=True)
    text_source = models.CharField(max_length=10, choices=TEXT_SOURCE_CHOICES, default="ocr")

    class Meta:
        abstract = True


class ContentBlock(SourceMixin):
    """
    Один шматок змісту уроку: теорія, рубрика, блок вправ тощо. Урок — це пункт (Item)
    у Мерзляка або параграф у Тарасенкової, тому блок належить або пункту, або параграфу
    (рівно одному — див. constraint). Блоки рівня параграфа в Мерзляка — «Перевірте себе»,
    «Головне в параграфі».
    """

    BLOCK_TYPE_CHOICES = [
        ("theory", "Теорія"),
        ("self_check", "Самоперевірка (❓)"),
        ("oral_exercise", "Розв'язуємо усно"),
        ("exercise", "Вправи"),
        ("review_exercise", "Вправи для повторення"),
        ("wise_owl", "Задача від Мудрої Сови"),
        ("history_aside", "Коли зроблено уроки"),
        ("self_test", "Перевірте себе"),
        ("summary", "Головне в параграфі"),
        ("applied_exercise", "Застосуйте на практиці"),
        ("worked_example", "Розв'язана задача"),
        ("rule", "Запам'ятайте"),
        ("note", "Зверніть увагу"),
        ("extra_reading", "Дізнайтеся більше"),
    ]
    DIFFICULTY_CHOICES = DIFFICULTY_CHOICES

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="content_blocks",
                             null=True, blank=True)
    paragraph = models.ForeignKey(Paragraph, on_delete=models.CASCADE, related_name="content_blocks",
                                  null=True, blank=True)
    block_type = models.CharField(max_length=20, choices=BLOCK_TYPE_CHOICES, db_index=True)
    order = models.PositiveIntegerField(default=0)
    title = models.CharField(max_length=255, blank=True)
    text = models.TextField(blank=True)
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, blank=True, null=True)
    image_path = models.CharField(max_length=255, blank=True, null=True)
    conf = models.FloatField(null=True, blank=True)
    figures = models.ManyToManyField("Figure", blank=True, related_name="content_blocks")

    class Meta:
        ordering = ["item", "paragraph", "order"]
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(item__isnull=False, paragraph__isnull=True)
                       | models.Q(item__isnull=True, paragraph__isnull=False)),
                name="contentblock_item_xor_paragraph",
            ),
        ]

    @property
    def lesson(self):
        return self.item or self.paragraph

    def __str__(self):
        return f"{self.get_block_type_display()} для {self.lesson} (#{self.order})"


class Exercise(SourceMixin):
    """Вправа підручника. Номер — як у книзі; письмові вправи нумеруються наскрізно в межах
    підручника, усні — заново в кожному пункті (тому унікальність не накладаємо, див. DECISIONS)."""

    textbook = models.ForeignKey(Textbook, on_delete=models.CASCADE, related_name="exercises")
    block = models.ForeignKey(ContentBlock, on_delete=models.CASCADE, related_name="exercises")
    number = models.PositiveIntegerField()
    order = models.PositiveIntegerField(default=0)
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, blank=True, null=True)
    difficulty_ocr = models.CharField(max_length=20, blank=True)
    homework = models.BooleanField(default=False)
    condition = models.TextField(blank=True)
    condition_tail = models.TextField(blank=True)
    task_verb = models.CharField(max_length=30, blank=True)
    answer_kind = models.CharField(max_length=30, blank=True)
    is_word_problem = models.BooleanField(default=False)
    auto_checkable = models.BooleanField(default=False)
    has_fractions = models.BooleanField(default=False)
    answer_check = models.CharField(max_length=10, choices=ANSWER_CHECK_CHOICES, default="unchecked")
    ocr_text = models.TextField(blank=True)
    flags = models.JSONField(default=list, blank=True)
    review_skipped = models.BooleanField(default=False, help_text="Пропущено на /review/: не ігрова, у черзі не показується")
    figures = models.ManyToManyField("Figure", blank=True, related_name="exercises")

    class Meta:
        ordering = ["block", "order"]
        indexes = [models.Index(fields=["textbook", "number"])]

    @property
    def is_oral(self):
        return self.block.block_type == "oral_exercise"

    def __str__(self):
        return f"№{self.number}" + (" (усна)" if self.is_oral else "")


class SubExercise(models.Model):
    """Підпункт вправи «1) 238 + 435»."""

    EXPR_STATUS_CHOICES = [
        ("ok", "Вираз коректний"),
        ("suspect", "Підозрілий"),
        ("malformed", "Зламаний"),
        ("not_expression", "Не вираз"),
    ]

    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name="subexercises")
    number = models.CharField(max_length=5)                 # «1», «12», «а»
    order = models.PositiveIntegerField(default=0)
    text = models.TextField()
    expr = models.CharField(max_length=255, blank=True)
    expr_status = models.CharField(max_length=20, choices=EXPR_STATUS_CHOICES, blank=True)
    expr_issues = models.JSONField(default=list, blank=True)
    answer_check = models.CharField(max_length=10, choices=ANSWER_CHECK_CHOICES, default="unchecked")
    needs_review = models.BooleanField(default=False, db_index=True)
    text_source = models.CharField(max_length=10, choices=TEXT_SOURCE_CHOICES, default="ocr")
    ocr_text = models.TextField(blank=True)
    review_skipped = models.BooleanField(default=False)

    class Meta:
        ordering = ["exercise", "order"]

    @property
    def expr_well_formed(self):
        return self.expr_status == "ok"

    def __str__(self):
        return f"{self.exercise} {self.number})"


def parse_answer_number(text):
    """Числове значення відповіді для порівняння/перевірки гравця, або None.

    «-3,5» → Decimal('-3.5'); «− 76» → Decimal('-76'); «3/4» → Decimal('0.75');
    «2 1/3» → Decimal('2.333333'); «так», «12; 16» → None.
    """
    import re
    from decimal import Decimal, InvalidOperation
    from fractions import Fraction

    if text is None:
        return None
    value = str(text).strip().rstrip(".;").replace("−", "-").replace("–", "-").replace(" ", " ")
    value = re.sub(r"^-\s+", "-", value)
    m = re.fullmatch(r"(-?)(\d+)\s+(\d+)/(\d+)", value)            # мішане число
    try:
        if m:
            sign = -1 if m.group(1) else 1
            frac = Fraction(int(m.group(2))) + Fraction(int(m.group(3)), int(m.group(4)))
            return (Decimal(sign * frac.numerator) / Decimal(frac.denominator)).quantize(Decimal("0.000001"))
        if re.fullmatch(r"-?\d+/\d+", value):
            frac = Fraction(value)
            return (Decimal(frac.numerator) / Decimal(frac.denominator)).quantize(Decimal("0.000001"))
        if re.fullmatch(r"-?\d+(?:[.,]\d+)?", value):
            return Decimal(value.replace(",", "."))
    except (InvalidOperation, ZeroDivisionError, ValueError):
        return None
    return None


class Answer(models.Model):
    """Відповідь до вправи або підпункту: з розділу «Відповіді» книги чи обчислена пайплайном."""

    KIND_CHOICES = [("manual", "Вручну (вчитель)"), ("book", "З книги"), ("computed", "Обчислено")]

    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name="answers")
    subexercise = models.ForeignKey(SubExercise, on_delete=models.CASCADE, null=True, blank=True,
                                    related_name="answers")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    text = models.CharField(max_length=500)
    value_numeric = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)

    class Meta:
        ordering = ["exercise", "subexercise", "kind"]
        constraints = [
            models.UniqueConstraint(fields=["exercise", "subexercise", "kind"], name="answer_unique_per_kind"),
        ]

    def save(self, *args, **kwargs):
        if self.value_numeric is None:
            self.value_numeric = parse_answer_number(self.text)
        super().save(*args, **kwargs)

    def __str__(self):
        target = self.subexercise or self.exercise
        return f"{target}: {self.text} ({self.kind})"


class Figure(models.Model):
    """Рисунок, вирізаний пайплайном зі сторінки. figure_id — стабільний id з JSON (p006_y300)."""

    textbook = models.ForeignKey(Textbook, on_delete=models.CASCADE, related_name="figures")
    figure_id = models.CharField(max_length=50)
    number = models.CharField(max_length=10, blank=True)
    caption = models.CharField(max_length=255, blank=True)
    image = models.ImageField(upload_to="textbook_figures/", null=True, blank=True)
    source_page = models.PositiveIntegerField(null=True, blank=True)
    source_bbox = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["textbook", "source_page", "figure_id"]
        constraints = [models.UniqueConstraint(fields=["textbook", "figure_id"], name="figure_unique_id")]

    def __str__(self):
        return f"Рис. {self.number}" if self.number else self.figure_id


class ImportRun(models.Model):
    """Журнал імпорту textbook.json у базу (фаза 19): що, коли і з яким результатом."""

    STATUS_CHOICES = [("running", "Триває"), ("success", "Успішно"), ("failed", "Помилка")]

    textbook = models.ForeignKey(Textbook, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="import_runs")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    json_path = models.CharField(max_length=500, blank=True)
    json_sha256 = models.CharField(max_length=64)
    pipeline_version = models.CharField(max_length=20, blank=True)
    schema_version = models.PositiveIntegerField(null=True, blank=True)
    stats = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="running")
    message = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Імпорт {self.started_at:%Y-%m-%d %H:%M} — {self.get_status_display()}"


class TheoryPractice(models.Model):
    item = models.OneToOneField(Item, on_delete=models.CASCADE)
    theory = models.TextField(blank=True)
    practice = models.TextField(blank=True)
    image_path = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"ТП для завдання {self.item.id}"


# Гра (Player, Attempt, LessonProgress, DIFFICULTY_POINTS) живе у застосунку `game`
# (BE-S04, docs/backend/PLAN.md) — залежить від каталогу (Item/Paragraph/Exercise/
# SubExercise), але каталог нічого не знає про гру; винесено без зміни таблиць.


class ManualEdit(models.Model):
    """Журнал ручної перевірки (/review/): хто, коли, що було і що стало.

    Ключ запису не залежить від pk (textbook + тип блоку + номер вправи + сторінка + підпункт), тож журнал
    можна вивантажити в JSON і застосувати до свіжої БД (export_manual_edits / import_manual_edits).
    """

    ACTIONS = [
        ("edit", "Виправлено текст"),
        ("confirm", "Підтверджено без змін"),
        ("skip", "Пропущено / не ігрова"),
        ("unskip", "Повернуто в чергу"),
    ]

    user = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="manual_edits")
    created_at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=10, choices=ACTIONS)
    textbook = models.ForeignKey(Textbook, on_delete=models.CASCADE, related_name="manual_edits")
    kind = models.CharField(max_length=12, choices=[("exercise", "Вправа"), ("subexercise", "Підпункт")])
    block_type = models.CharField(max_length=30, blank=True)
    exercise_number = models.PositiveIntegerField()
    source_page = models.PositiveIntegerField(null=True, blank=True)
    sub_number = models.CharField(max_length=5, blank=True)
    old_text = models.TextField(blank=True)
    new_text = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["textbook", "exercise_number"])]

    def __str__(self):
        sub = f" {self.sub_number})" if self.sub_number else ""
        return f"{self.get_action_display()}: №{self.exercise_number}{sub} (стор. {self.source_page})"


# Школи/класи (School, SchoolMembership, SchoolClass, SchoolClassStudent) живуть
# у застосунку `schools` (BE-S02, docs/backend/PLAN.md) — нуль FK у каталог,
# тому винесені без зміни таблиць (schools/models.py: db_table = education_school...).
