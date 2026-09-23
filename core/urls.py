from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("api/v1/events/", views.events_api, name="events_api"),
    path("signup/", views.signup, name="signup"),
    path("profile/", views.profile, name="profile"),
    path("olympiads/", views.olympiad_list, name="olympiad_list"),
    path("calendar/", views.calendar, name="calendar"),
    path("telegram/connect/", views.telegram_connect, name="telegram_connect"),
    path("olympiads/<int:pk>/", views.olympiad_detail, name="olympiad_detail"),
    path("olympiads/<int:pk>/register/", views.register_self, name="register_self"),
    path("olympiads/<int:pk>/register-student/", views.teacher_register, name="teacher_register"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("export/registrations.csv", views.export_registrations, name="export_registrations"),
]
