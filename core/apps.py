from django.apps import AppConfig
from .ui_text import translate_lazy


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = translate_lazy("Платформа")

