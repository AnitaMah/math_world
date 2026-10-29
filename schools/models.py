from django.core.validators import RegexValidator
from django.db import models

# BE-S02: перенесено з education/models.py (state-only, без зміни БД — див.
# docs/backend/DECISIONS.md). db_table фіксує старі назви таблиць
# (education_school...), бо дані вже там і фізично не рухаються.

SCHOOL_COUNTRY_CHOICES = [("UA", "Україна"), ("DE", "Deutschland")]


class School(models.Model):
    """Школа на платформі.

    Школа реєструється сама зі своїм офіційним номером (ЄДЕБО в Україні, Schulnummer у Німеччині)
    і отримує статус «pending». Лише адміністратор платформи (superuser) може її верифікувати.
    Верифікована школа сама додає/видаляє своїх учителів — див. schools/services.py.
    """

    STATUS_PENDING = "pending"
    STATUS_VERIFIED = "verified"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Очікує перевірки"),
        (STATUS_VERIFIED, "Офіційна (верифікована)"),
        (STATUS_REJECTED, "Відхилена"),
    ]

    name = models.CharField(max_length=255)
    country = models.CharField(max_length=2, choices=SCHOOL_COUNTRY_CHOICES, default="UA")
    official_number = models.CharField(
        max_length=32,
        validators=[RegexValidator(r"^[0-9A-Za-z-]{3,32}$", "Лише цифри, латинські літери та дефіс")],
        help_text="Офіційний номер: код ЄДЕБО (UA) або Schulnummer (DE)",
    )
    city = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="verified_schools")
    created_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="registered_schools")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "education_school"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["country", "official_number"], name="school_unique_official_number"),
            # верифікована школа завжди має дату верифікації
            models.CheckConstraint(condition=~models.Q(status="verified") | models.Q(verified_at__isnull=False),
                                   name="school_verified_has_date"),
        ]

    @property
    def is_verified(self):
        return self.status == self.STATUS_VERIFIED

    def __str__(self):
        return f"{self.name} ({self.country}-{self.official_number})"


class SchoolMembership(models.Model):
    """Користувач у школі: адміністратор школи або вчитель. Один користувач — один запис на школу."""

    ROLE_SCHOOL_ADMIN = "school_admin"
    ROLE_TEACHER = "teacher"
    ROLE_CHOICES = [(ROLE_SCHOOL_ADMIN, "Адміністратор школи"), (ROLE_TEACHER, "Вчитель")]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="school_memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_TEACHER)
    added_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "education_schoolmembership"
        ordering = ["school", "role", "user__username"]
        constraints = [models.UniqueConstraint(fields=["school", "user"], name="school_membership_unique")]

    def __str__(self):
        return f"{self.user} — {self.get_role_display()} @ {self.school.name}"


class SchoolClass(models.Model):
    """Клас — група учнів школи, яку веде вчитель (режим вчителя, FE-0640/0645)."""

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="classes")
    teacher = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="taught_classes")
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "education_schoolclass"
        ordering = ["school", "name"]

    def __str__(self):
        return f"{self.name} ({self.school.name})"


class SchoolClassStudent(models.Model):
    """Учень у класі. Один учень — один запис на клас (учень може бути в кількох класах)."""

    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name="students")
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="class_memberships")
    added_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "education_schoolclassstudent"
        ordering = ["school_class", "user__username"]
        constraints = [models.UniqueConstraint(fields=["school_class", "user"], name="class_student_unique")]

    def __str__(self):
        return f"{self.user} — {self.school_class}"
