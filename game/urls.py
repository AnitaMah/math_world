from django.urls import path

from . import api

urlpatterns = [
    path("subexercises/<int:pk>/check/", api.check, name="api_check"),
    path("exercises/<int:pk>/solution/", api.solution, name="api_solution"),
    path("play/items/<int:pk>/", api.play, {"kind": "item"}, name="api_play_item"),
    path("play/paragraphs/<int:pk>/", api.play, {"kind": "paragraph"}, name="api_play_paragraph"),
    path("me/", api.me, name="api_me"),
]
