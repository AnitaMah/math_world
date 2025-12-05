from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from education import views as education_views


urlpatterns = [
    path("", education_views.mint_overview, name="mint_overview"),
    path("grades/", education_views.grade_list, name="grade_list"),
    path("grades/<int:grade_id>/sections/", education_views.section_list, name="section_list"),
    path("sections/<int:section_id>/paragraphs/", education_views.paragraph_list, name="paragraph_list"),
    path("paragraphs/<int:paragraph_id>/items/", education_views.item_list, name="item_list"),
    path("items/<int:item_id>/", education_views.item_detail, name="item_detail"),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
