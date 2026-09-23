import json
from datetime import date, datetime, time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from core.models import Olympiad


API_URL = "https://hackalendar.com/api/events?limit=200"
MODE_MAP = {"online": Olympiad.Format.ONLINE, "in_person": Olympiad.Format.OFFLINE, "hybrid": Olympiad.Format.HYBRID}


def parse_source_date(value):
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        parsed_date = parse_date(value)
        if parsed_date is None:
            return None
        parsed = datetime.combine(parsed_date, time.min)
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


class Command(BaseCommand):
    help = "Синхронизирует проверенные открытые хакатоны из бесплатного API Hackalendar как черновики."

    def handle(self, *args, **options):
        request = Request(API_URL, headers={"User-Agent": "OlympIQ/1.0 (event discovery)"})
        try:
            with urlopen(request, timeout=25) as response:
                payload = json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise CommandError(f"Не удалось получить данные Hackalendar API: {exc}") from exc

        events = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(events, list):
            raise CommandError("Hackalendar API вернул ответ неожиданного формата.")

        created = updated = skipped = 0
        for event in events:
            name = (event.get("name") or "").strip()
            event_id = event.get("id")
            start = parse_source_date(event.get("startAt"))
            end = parse_source_date(event.get("endAt"))
            if not name or not event_id or not event.get("registrationUrl") or not start or not end or end < timezone.now():
                skipped += 1
                continue

            themes = event.get("themes") or []
            subject = ", ".join(str(theme).replace("_", " ").title() for theme in themes[:3]) or "Хакатон"
            mode = MODE_MAP.get(event.get("mode"), "")
            city = event.get("cityLabel") or event.get("venue") or ""
            values = {
                "title": name[:240],
                "event_type": Olympiad.EventType.HACKATHON,
                "subject": subject[:100],
                "description": (event.get("description") or "Подробности и актуальные условия участия — на официальной странице события.")[:5000],
                "organizer": (event.get("organizer") or "Организатор указан на странице события")[:180],
                "format": mode,
                "city": city[:120],
                "venue": (event.get("venue") or "")[:255],
                "starts_at": start,
                "ends_at": end,
                "registration_deadline": parse_source_date(event.get("registrationDeadline")),
                "min_grade": None,
                "max_grade": None,
                "source_url": event.get("url") or "https://hackalendar.com/api",
                "registration_url": event["registrationUrl"],
                "source_synced_at": timezone.now(),
            }
            item, was_created = Olympiad.objects.get_or_create(
                source_key=f"hackalendar:{event_id}",
                defaults={**values, "is_published": False, "is_demo": False},
            )
            if was_created:
                created += 1
            else:
                # Eligibility and level are curator-reviewed; keep them across feed refreshes.
                synced_values = {
                    field: value for field, value in values.items()
                    if field not in {"min_grade", "max_grade"}
                    and (field != "registration_deadline" or value is not None)
                }
                for field, value in synced_values.items():
                    setattr(item, field, value)
                item.save(update_fields=list(synced_values))
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Hackalendar: создано черновиков — {created}, обновлено — {updated}, пропущено — {skipped}."
        ))
        if created or updated:
            self.stdout.write("Перед публикацией подтвердите возрастные условия и срок регистрации на странице организатора.")
