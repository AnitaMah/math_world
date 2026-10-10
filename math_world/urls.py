from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from education import views as education_views
from education import views_review, views_ui


urlpatterns = [
    path("", views_ui.world_page, name="home"),   # «Світ» — вибір класу
    path("grades/<int:number>/", views_ui.grade_map_page, name="grade_map_page"),
    path("paragraphs/<int:paragraph_id>/", views_ui.paragraph_page, name="paragraph_page"),
    path("items/<int:item_id>/", education_views.item_detail, name="item_detail"),
    path("play/item/<int:pk>/", education_views.play_lesson, {"kind": "item"}, name="play_item"),
    path("play/paragraph/<int:pk>/", education_views.play_lesson, {"kind": "paragraph"}, name="play_paragraph"),
    path("accounts/signup/", education_views.signup, name="signup"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("api/", include("education.api_urls")),
    path("review/", views_review.review_index, name="review_index"),
    path("review/<str:kind>/<int:pk>/", views_review.review_detail, name="review_detail"),
    path("review/<str:kind>/<int:pk>/crop.png", views_review.review_crop, name="review_crop"),
    path("admin/", admin.site.urls),
    # Вкладки нижньої навігації (поки заглушки)
    path("progress/", views_ui.progress_page, name="progress"),
    path("profile/", views_ui.profile_page, name="profile"),
    # Старий UI видалено (фаза 18): старі адреси — 301 на нову мапу. Імена лишені для сумісності
    # (map_builder.py ще робить reverse на них — бекенд-чату повідомлено, що він більше не потрібен).
    path("grades/", education_views.old_grade_list, name="grade_list"),
    path("grades/<int:grade_id>/sections/", education_views.old_section_list, name="section_list"),
    path("sections/<int:section_id>/paragraphs/", education_views.old_paragraph_list, name="paragraph_list"),
    path("paragraphs/<int:paragraph_id>/items/", education_views.old_item_list, name="item_list"),
    # Службові сторінки (лише DEBUG, інакше 404)
    path("ui/tokens/", views_ui.ui_tokens, name="ui_tokens"),
    path("ui/kit/", views_ui.ui_kit, name="ui_kit"),
    path("ui/api/", views_ui.ui_api, name="ui_api"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)