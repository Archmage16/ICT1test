from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from core import views as core_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("accounts/password/change/", auth_views.PasswordChangeView.as_view(template_name="registration/password_change.html", success_url="/profile/"), name="password_change"),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("integrations/telegram/webhook/", core_views.telegram_webhook, name="telegram_webhook"),
    path("", include("core.urls")),
]
