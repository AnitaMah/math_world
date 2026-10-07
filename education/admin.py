# education/admin.py
from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Answer, ContentBlock, Exercise, Figure, Grade, ImportRun, Item, Paragraph, Section, Subject,
    SubExercise, Textbook, TheoryPractice,
)


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
    fk_name = "item"
    extra = 0
    fields = ("block_type", "order", "difficulty", "needs_review", "text")
    show_change_link = True


class ParagraphBlockInline(ContentBlockInline):
    fk_name = "paragraph"


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    inlines = [SectionInline]


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "grade", "textbook")
    list_filter = ("grade", "textbook")
    inlines = [ParagraphInline]


@admin.register(Paragraph)
class ParagraphAdmin(admin.ModelAdmin):
    inlines = [ItemInline, ParagraphBlockInline]


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    inlines = [TheoryPracticeInline, ContentBlockInline]


@admin.register(TheoryPractice)
class TheoryPracticeAdmin(admin.ModelAdmin):
    pass


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name_uk", "name_de")


@admin.register(Textbook)
class TextbookAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "grade", "profile_code", "year", "created_at")
    list_filter = ("subject", "grade", "profile_code")
    search_fields = ("title", "author", "pdf_name", "pdf_sha256")
    readonly_fields = ("pdf_sha256", "created_at")


class ExerciseInline(admin.TabularInline):
    model = Exercise
    extra = 0
    fields = ("number", "difficulty", "condition", "needs_review")
    show_change_link = True


@admin.register(ContentBlock)
class ContentBlockAdmin(admin.ModelAdmin):
    list_display = ("__str__", "block_type", "needs_review", "source_page", "text_source")
    list_filter = ("needs_review", "block_type", "text_source")
    search_fields = ("text", "title")
    filter_horizontal = ("figures",)
    inlines = [ExerciseInline]


class SubExerciseInline(admin.TabularInline):
    model = SubExercise
    extra = 0
    fields = ("number", "order", "text", "expr_status", "answer_check", "needs_review")


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    fields = ("subexercise", "kind", "text", "value_numeric")
    readonly_fields = ("value_numeric",)


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ("number", "textbook", "block", "difficulty", "homework", "answer_check", "needs_review",
                    "source_page")
    list_filter = ("textbook", "needs_review", "difficulty", "answer_check", "homework", "block__block_type")
    search_fields = ("condition", "=number")
    filter_horizontal = ("figures",)
    inlines = [SubExerciseInline, AnswerInline]


def _thumb(figure, size=80):
    if not figure.image:
        return "—"
    return format_html('<img src="{}" style="max-height:{}px;max-width:240px">', figure.image.url, size)


@admin.register(Figure)
class FigureAdmin(admin.ModelAdmin):
    list_display = ("__str__", "textbook", "source_page", "preview")
    list_filter = ("textbook",)
    search_fields = ("figure_id", "number", "caption")
    readonly_fields = ("large_preview",)

    @admin.display(description="Прев'ю")
    def preview(self, obj):
        return _thumb(obj)

    @admin.display(description="Картинка")
    def large_preview(self, obj):
        return _thumb(obj, 400)


@admin.register(ImportRun)
class ImportRunAdmin(admin.ModelAdmin):
    list_display = ("started_at", "textbook", "status", "schema_version", "pipeline_version", "finished_at")
    list_filter = ("status", "textbook")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
