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


class Section(models.Model):
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE)
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


class ContentBlock(models.Model):
    """
    One piece of a lesson's real content: a theory paragraph, a self-check
    question, an oral warm-up exercise, a written exercise (with its
    difficulty marker), a review exercise, the "Задача від Мудрої Сови"
    problem, or a "Коли зроблено уроки" historical aside. A lesson repeats
    each of these a variable number of times (0 asides, 8 exercises, ...),
    which is why this is a separate table keyed to Item rather than more
    flat fields on Item -- see Section 2 of the refactor plan for the
    reasoning. Empty for now: this step only adds the table, no parsing
    writes to it yet (see Steps 12+).
    """

    BLOCK_TYPE_CHOICES = [
        ("theory", "Теорія"),
        ("self_check", "Самоперевірка (❓)"),
        ("oral_exercise", "Розв'язуємо усно"),
        ("exercise", "Вправа"),
        ("review_exercise", "Вправа для повторення"),
        ("wise_owl", "Задача від Мудрої Сови"),
        ("history_aside", "Коли зроблено уроки"),
    ]

    # Difficulty markers used by "Вправи" exercises in this textbook:
    # ° (basic), plain/no mark (standard), ·· (advanced), * (olympiad/club).
    DIFFICULTY_CHOICES = [
        ("basic", "° початковий"),
        ("standard", "стандартний"),
        ("advanced", "·· високий"),
        ("olympiad", "* гурток/факультатив"),
    ]

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="content_blocks")
    block_type = models.CharField(max_length=20, choices=BLOCK_TYPE_CHOICES)
    order = models.PositiveIntegerField(default=0)
    text = models.TextField()
    difficulty = models.CharField(
        max_length=20, choices=DIFFICULTY_CHOICES, blank=True, null=True
    )
    image_path = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ["item", "order"]

    def __str__(self):
        return f"{self.get_block_type_display()} для {self.item} (#{self.order})"


class TheoryPractice(models.Model):
    item = models.OneToOneField(Item, on_delete=models.CASCADE)
    theory = models.TextField(blank=True)
    practice = models.TextField(blank=True)
    image_path = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"ТП для завдання {self.item.id}"


class Lesson(models.Model):
    title = models.CharField(max_length=255)
    content = models.TextField()
    image = models.ImageField(upload_to='lessons/', null=True, blank=True)

    def __str__(self):
        return self.title
