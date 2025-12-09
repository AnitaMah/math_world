from django.db import models


class Grade(models.Model):
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
