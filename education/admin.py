#education/admin.py
from django.contrib import admin
from .models import Grade, Section, Paragraph, Item, TheoryPractice

class SectionInline(admin.TabularInline):
    model = Section
    extra = 0

class ParagraphInline(admin.TabularInline):
    model = Paragraph
    extra = 0

class ItemInline(admin.TabularInline):
    model = Item
    extra = 0

class TheoryPracticeInline(admin.TabularInline):
    model = TheoryPractice
    extra = 0

@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    inlines = [SectionInline]

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    inlines = [ParagraphInline]

@admin.register(Paragraph)
class ParagraphAdmin(admin.ModelAdmin):
    inlines = [ItemInline]

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    inlines = [TheoryPracticeInline]

@admin.register(TheoryPractice)
class TheoryPracticeAdmin(admin.ModelAdmin):
    pass
