from django.urls import include, path

from . import api

urlpatterns = [
    path("csrf/", api.csrf, name="api_csrf"),
    path("textbooks/", api.textbooks, name="api_textbooks"),
    path("textbooks/<int:textbook_id>/tree/", api.textbook_tree, name="api_textbook_tree"),
    path("grades/", api.grades, name="api_grades"),
    path("grades/<int:number>/map/", api.grade_map, name="api_grade_map"),
    path("items/<int:pk>/", api.lesson_detail, {"kind": "item"}, name="api_item"),
    path("items/<int:pk>/exercises/", api.lesson_exercise_list, {"kind": "item"}, name="api_item_exercises"),
    path("paragraphs/<int:pk>/", api.lesson_detail, {"kind": "paragraph"}, name="api_paragraph"),
    path("paragraphs/<int:pk>/exercises/", api.lesson_exercise_list, {"kind": "paragraph"},
         name="api_paragraph_exercises"),
    path("exercises/<int:pk>/", api.exercise_detail, name="api_exercise"),
    path("figures/<int:pk>/image", api.figure_image, name="api_figure_image"),
    path("", include("game.urls")),
    path("", include("schools.urls")),
]
