from django.db import models

from education.models import Item, Paragraph, Exercise, SubExercise

# BE-S04: перенесено з education/models.py (state-only, без зміни БД — див.
# docs/backend/DECISIONS.md). db_table фіксує старі назви таблиць
# (education_player...), бо дані вже там і фізично не рухаються. Catalog
# (education) нічого не знає про гру — залежність лише в цьому напрямку.

DIFFICULTY_POINTS = {"preparatory": 1, "medium": 1, "sufficient": 2, "high": 3, "olympiad": 5}


class Player(models.Model):
    """Гравець: або акаунт (user), або анонім, прив'язаний до сесії браузера (session_key)."""

    user = models.OneToOneField("auth.User", on_delete=models.CASCADE, null=True, blank=True,
                                related_name="player")
    session_key = models.CharField(max_length=64, null=True, blank=True, unique=True)
    points = models.PositiveIntegerField(default=0)
    streak = models.PositiveIntegerField(default=0)
    last_active = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "education_player"

    def __str__(self):
        return self.user.username if self.user_id else f"Гість {self.pk}"


class Attempt(models.Model):
    """Одна спроба гравця: відповідь на підпункт (auto) або розв'язок задачі для ШІ (ai)."""

    KIND_CHOICES = [("auto", "Автоперевірка"), ("ai", "Перевірка ШІ")]
    VERDICT_CHOICES = [("correct", "Правильно"), ("incorrect", "Неправильно"), ("unclear", "Незрозуміло")]

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="attempts")
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name="attempts")
    subexercise = models.ForeignKey(SubExercise, on_delete=models.CASCADE, null=True, blank=True,
                                    related_name="attempts")
    kind = models.CharField(max_length=5, choices=KIND_CHOICES, default="auto")
    answer_text = models.TextField()
    correct = models.BooleanField(default=False)
    verdict = models.CharField(max_length=10, choices=VERDICT_CHOICES, blank=True)
    feedback = models.TextField(blank=True)
    points = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "education_attempt"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["player", "subexercise"], name="education_a_player__2faf92_idx"),
            models.Index(fields=["player", "exercise"], name="education_a_player__6b6cce_idx"),
        ]

    def __str__(self):
        return f"{self.player} → {self.subexercise or self.exercise}: {'✓' if self.correct else '✗'}"


class LessonProgress(models.Model):
    """Прогрес гравця в уроці (пункт або §): скільки завдань розв'язано, бали, зірки."""

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="progress")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, null=True, blank=True, related_name="progress")
    paragraph = models.ForeignKey(Paragraph, on_delete=models.CASCADE, null=True, blank=True, related_name="progress")
    solved = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    points = models.PositiveIntegerField(default=0)
    stars = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "education_lessonprogress"
        constraints = [
            models.CheckConstraint(condition=(models.Q(item__isnull=False, paragraph__isnull=True)
                                              | models.Q(item__isnull=True, paragraph__isnull=False)),
                                   name="progress_item_xor_paragraph"),
            models.UniqueConstraint(fields=["player", "item"], name="progress_unique_item"),
            models.UniqueConstraint(fields=["player", "paragraph"], name="progress_unique_paragraph"),
        ]

    def __str__(self):
        return f"{self.player}: {self.item or self.paragraph} {'★' * self.stars}"
