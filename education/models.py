#education/models.py
from django.db import models

class Grade(models.Model):
    number = models.IntegerField()
    name_uk = models.CharField(max_length=100)
    name_de = models.CharField(max_length=100, blank=True, null=True)
    theme_uk = models.CharField(max_length=200, blank=True, null=True)
    theme_de = models.CharField(max_length=200, blank=True, null=True)

class Section(models.Model):
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE)
    number = models.IntegerField()
    name_uk = models.CharField(max_length=200)
    name_de = models.CharField(max_length=200, blank=True, null=True)

class Paragraph(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    number = models.IntegerField()
    name_uk = models.CharField(max_length=200)
    name_de = models.CharField(max_length=200, blank=True, null=True)

class Item(models.Model):
    paragraph = models.ForeignKey(Paragraph, on_delete=models.CASCADE)
    number = models.IntegerField()
    content = models.TextField()
    content_de = models.TextField(blank=True, null=True)
    type = models.CharField(max_length=50, default='основний')
    image_path = models.CharField(max_length=255, blank=True, null=True)
    theory = models.TextField(blank=True, null=True)  # 👈 Додано


class TheoryPractice(models.Model):
    item = models.OneToOneField(Item, on_delete=models.CASCADE)  # 🔁 Один-до-одного, щоб не дублювати
    theory = models.TextField(blank=True)
    practice = models.TextField(blank=True)
    image_path = models.CharField(max_length=255, blank=True, null=True)  # 🖼 зображення з PDF (якщо є)

    def __str__(self):
        return f"Theory for Item {self.item.id}: {self.theory[:30]}..."

class Lesson(models.Model):
    title = models.CharField(max_length=255)
    content = models.TextField()
    image = models.ImageField(upload_to='lessons/', null=True, blank=True)

    def __str__(self):
        return self.title