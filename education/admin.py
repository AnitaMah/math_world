# education/admin.py
from django.contrib import admin, messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
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


@admin.action(description="Позначити перевіреним (needs_review=False, text_source=manual)")
def mark_reviewed(modeladmin, request, queryset):
    n = queryset.update(needs_review=False, text_source="manual")
    modeladmin.message_user(request, f"Позначено перевіреними: {n}", messages.SUCCESS)


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ("number", "textbook", "block", "difficulty", "homework", "answer_check", "needs_review",
                    "source_page", "text_source")
    list_filter = ("textbook", "needs_review", "difficulty", "answer_check", "homework", "text_source",
                   "block__block_type", ("block__item__paragraph", admin.RelatedOnlyFieldListFilter))
    search_fields = ("=number", "condition")
    list_select_related = ("textbook", "block")
    filter_horizontal = ("figures",)
    readonly_fields = ("page_crop", "ocr_text", "flags")
    fields = ("page_crop", "textbook", "block", "number", "order", "difficulty", "difficulty_ocr", "homework",
              "condition", "condition_tail", "task_verb", "answer_kind", "is_word_problem", "auto_checkable",
              "has_fractions", "answer_check", "needs_review", "text_source", "ocr_text", "flags",
              "source_page", "source_bbox", "figures")
    inlines = [SubExerciseInline, AnswerInline]
    actions = [mark_reviewed]

    def get_urls(self):
        return [path("<int:pk>/crop.png", self.admin_site.admin_view(self.crop_view), name="education_exercise_crop"),
                *super().get_urls()]

    def crop_view(self, request, pk):
        from .services import page_crop_png
        ex = get_object_or_404(Exercise.objects.select_related("textbook"), pk=pk)
        if not ex.source_page:
            raise Http404("У вправи немає сторінки")
        png = page_crop_png(ex.textbook, ex.source_page, ex.source_bbox)
        if png is None:
            raise Http404("Немає ні кешу сторінок, ні PDF")
        return HttpResponse(png, content_type="image/png")

    @admin.display(description="Сторінка PDF")
    def page_crop(self, obj):
        if not obj.pk or not obj.source_page:
            return "—"
        url = reverse("admin:education_exercise_crop", args=[obj.pk])
        return format_html('<img src="{}" style="max-width:720px;border:1px solid #ccc" alt="стор. {}">'
                           '<div>стор. {}</div>', url, obj.source_page, obj.source_page)

    def save_formset(self, request, form, formset, change):
        """Правка підпункту в адмінці = ручна правка (імпорт її не перезапише)."""
        instances = formset.save(commit=False)
        for inst in instances:
            if isinstance(inst, SubExercise) and inst.pk and formset.has_changed():
                inst.text_source = "manual"
            inst.save()
        for obj in formset.deleted_objects:
            obj.delete()
        formset.save_m2m()

    def save_model(self, request, obj, form, change):
        content_fields = {"condition", "condition_tail", "difficulty", "number"}
        if change and content_fields & set(form.changed_data):
            obj.text_source = "manual"
        super().save_model(request, obj, form, change)


@admin.register(SubExercise)
class SubExerciseAdmin(admin.ModelAdmin):
    list_display = ("__str__", "text", "expr_status", "answer_check", "needs_review", "text_source")
    list_filter = ("needs_review", "expr_status", "answer_check", "exercise__textbook")
    search_fields = ("text", "=exercise__number")
    list_select_related = ("exercise",)
    actions = [mark_reviewed]


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
