from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError
from django.utils import timezone

from core.models import Registration, TelegramReminder
from core.telegram import send_to_user


class Command(BaseCommand):
    help = "Отправляет подключённым пользователям ежедневные напоминания о дедлайнах и олимпиадах."

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError("Сначала задайте TELEGRAM_BOT_TOKEN.")
        now = timezone.now()
        sent = 0
        windows = (
            (TelegramReminder.Kind.DEADLINE, now, now + timedelta(hours=24)),
            (TelegramReminder.Kind.OLYMPIAD, now + timedelta(hours=20), now + timedelta(hours=28)),
        )
        for kind, start, end in windows:
            date_field = "olympiad__registration_deadline" if kind == TelegramReminder.Kind.DEADLINE else "olympiad__starts_at"
            candidates = Registration.objects.filter(
                student__telegram_link__chat_id__isnull=False,
                olympiad__is_published=True,
                **{f"{date_field}__gte": start, f"{date_field}__lte": end},
            ).select_related("student", "olympiad").exclude(telegram_reminders__kind=kind)
            for registration in candidates.iterator():
                if kind == TelegramReminder.Kind.DEADLINE:
                    text = f"Напоминание OlympIQ: регистрация на «{registration.olympiad.title}» закрывается завтра, {timezone.localtime(registration.olympiad.registration_deadline).strftime('%d.%m в %H:%M')}."
                else:
                    text = f"Завтра олимпиада «{registration.olympiad.title}». Начало: {timezone.localtime(registration.olympiad.starts_at).strftime('%d.%m в %H:%M')}. Проверьте место и условия в OlympIQ."
                if send_to_user(registration.student, text):
                    try:
                        TelegramReminder.objects.create(registration=registration, kind=kind)
                        sent += 1
                    except IntegrityError:
                        pass
        self.stdout.write(self.style.SUCCESS(f"Отправлено напоминаний: {sent}"))
