from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from .models import News, Olympiad, Registration, Result, School, TelegramLink, TelegramReminder, User
from .telegram import send_to_user
from .ui_text import translate, translate_lazy as _


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + ((_('Профиль'), {"fields": ("role", "school", "grade", "phone", "patronymic")}),)
    add_fieldsets = UserAdmin.add_fieldsets + ((_('Профиль'), {"fields": ("role", "school", "grade", "phone", "patronymic")}),)
    list_display = ("username", "last_name", "first_name", "role", "school", "is_staff")
    list_filter = ("role", "school", "is_staff")


@admin.register(Olympiad)
class OlympiadAdmin(admin.ModelAdmin):
    list_display = ("title", "event_type", "subject", "level", "starts_at", "registration_deadline", "is_published", "is_demo")
    list_filter = ("event_type", "subject", "format", "level", "is_published", "is_demo")
    search_fields = ("title", "organizer", "city")
    readonly_fields = ("source_key", "source_synced_at")


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("student", "olympiad", "status", "registered_by", "created_at")
    list_filter = ("status", "olympiad")
    search_fields = ("student__last_name", "student__first_name", "olympiad__title")
    actions = ("approve",)

    @admin.action(description=_("Подтвердить выбранные регистрации"), permissions=["change"])
    def approve(self, request, queryset):
        updated = queryset.update(status=Registration.Status.APPROVED)
        self.message_user(request, translate("Подтверждено заявок: {count}.").format(count=updated), messages.SUCCESS)


admin.site.register(School)
@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ("registration", "score", "max_score", "place", "diploma", "is_published")
    list_filter = ("is_published", "registration__olympiad")
    search_fields = ("registration__student__last_name", "registration__student__first_name", "registration__olympiad__title")
    actions = ("publish_results",)

    @admin.action(description=_("Опубликовать выбранные результаты"))
    def publish_results(self, request, queryset):
        for result in queryset.select_related("registration__student", "registration__olympiad"):
            result.is_published = True
            result.save(update_fields=["is_published"])
            send_to_user(result.registration.student, f"Опубликован результат «{result.registration.olympiad.title}»: {result.score}/{result.max_score}, место {result.place or '—'}.")

admin.site.register(News)
admin.site.register(TelegramLink)
admin.site.register(TelegramReminder)
admin.site.site_header = _("OlimpIQ — управление платформой")
admin.site.site_title = "OlimpIQ"
