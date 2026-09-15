#education/admin.py
from django.contrib import admin
from .models import Grade, Section, Paragraph, Item, TheoryPractice, Subject, ContentBlock

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

class ContentBlockInline(admin.TabularInline):
    model = ContentBlock
    extra = 0
    fields = ("block_type", "order", "difficulty", "text", "image_path")

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
    inlines = [TheoryPracticeInline, ContentBlockInline]

@admin.register(TheoryPractice)
class TheoryPracticeAdmin(admin.ModelAdmin):
    pass

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name_uk", "name_de")