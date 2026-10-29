# schools/admin.py — BE-S03: перенесено з education/admin.py
from django.contrib import admin, messages

from .models import School, SchoolClass, SchoolClassStudent, SchoolMembership


class SchoolMembershipInline(admin.TabularInline):
    model = SchoolMembership
    fk_name = "school"
    extra = 0
    fields = ("user", "role", "added_by", "created_at")
    readonly_fields = ("added_by", "created_at")
    autocomplete_fields = ("user",)


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    """Статус змінюється лише діями «Верифікувати» / «Відхилити» (тільки superuser) — так завжди
    записується, хто і коли верифікував."""

    list_display = ("name", "country", "official_number", "city", "status", "verified_at", "verified_by")
    list_filter = ("status", "country")
    search_fields = ("name", "official_number", "city")
    readonly_fields = ("status", "verified_at", "verified_by", "created_by", "created_at")
    inlines = [SchoolMembershipInline]
    actions = ["verify_selected", "reject_selected"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        for membership in formset.save(commit=False):
            if membership.pk is None:
                membership.added_by = request.user
            membership.save()
        for obj in formset.deleted_objects:
            obj.delete()

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser:
            actions.pop("verify_selected", None)
            actions.pop("reject_selected", None)
        return actions

    @admin.action(description="Верифікувати вибрані школи (офіційні)")
    def verify_selected(self, request, queryset):
        from .services import verify_school
        for school in queryset:
            verify_school(request.user, school)
        self.message_user(request, f"Верифіковано: {queryset.count()}", messages.SUCCESS)

    @admin.action(description="Відхилити / відкликати верифікацію")
    def reject_selected(self, request, queryset):
        from .services import reject_school
        for school in queryset:
            reject_school(request.user, school)
        self.message_user(request, f"Відхилено: {queryset.count()}", messages.WARNING)


class SchoolClassStudentInline(admin.TabularInline):
    model = SchoolClassStudent
    fk_name = "school_class"
    extra = 0
    fields = ("user", "added_by", "created_at")
    readonly_fields = ("added_by", "created_at")
    autocomplete_fields = ("user",)


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "teacher", "created_at")
    list_filter = ("school",)
    search_fields = ("name", "teacher__username")
    autocomplete_fields = ("school", "teacher")
    inlines = [SchoolClassStudentInline]

    def save_formset(self, request, form, formset, change):
        for student in formset.save(commit=False):
            if student.pk is None:
                student.added_by = request.user
            student.save()
        for obj in formset.deleted_objects:
            obj.delete()
