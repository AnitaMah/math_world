from django.urls import path

from . import api

urlpatterns = [
    path("schools/", api.register, name="api_school_register"),
    path("schools/mine/", api.my_schools, name="api_my_schools"),
    path("schools/<int:pk>/staff/", api.staff, name="api_school_staff"),
    path("schools/<int:pk>/staff/<int:user_id>/", api.staff_member, name="api_school_staff_member"),
    path("classes/", api.create_class, name="api_class_create"),
    path("classes/mine/", api.my_classes, name="api_my_classes"),
    path("classes/<int:pk>/students/", api.class_students, name="api_class_students"),
    path("classes/<int:pk>/students/<int:user_id>/", api.class_student, name="api_class_student"),
]
