from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from education import views as education_views
from education import views_ui


urlpatterns = [
    path('', education_views.grade_list, name='home'),  # ← додай цей рядок
    path("grades/", education_views.grade_list, name="grade_list"),
    path("grades/<int:grade_id>/sections/", education_views.section_list, name="section_list"),
    path("sections/<int:section_id>/paragraphs/", education_views.paragraph_list, name="paragraph_list"),
    path("paragraphs/<int:paragraph_id>/items/", education_views.item_list, name="item_list"),
    path("items/<int:item_id>/", education_views.item_detail, name="item_detail"),
    path("play/item/<int:pk>/", education_views.play_lesson, {"kind": "item"}, name="play_item"),
    path("play/paragraph/<int:pk>/", education_views.play_lesson, {"kind": "paragraph"}, name="play_paragraph"),
    path("accounts/signup/", education_views.signup, name="signup"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("api/", include("education.api_urls")),
    path("admin/", admin.site.urls),
    # Новий UI: вкладки нижньої навігації (поки заглушки)
    path("progress/", views_ui.progress_page, name="progress"),
    path("profile/", views_ui.profile_page, name="profile"),
    # Службові сторінки нового UI (лише DEBUG, інакше 404)
    path("ui/tokens/", views_ui.ui_tokens, name="ui_tokens"),
    path("ui/kit/", views_ui.ui_kit, name="ui_kit"),
    path("ui/api/", views_ui.ui_api, name="ui_api"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)