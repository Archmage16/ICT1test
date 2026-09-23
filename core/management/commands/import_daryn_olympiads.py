import json
import re
from datetime import timedelta
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import Olympiad


API_URL = "https://daryn.kz/wp-json/wp/v2/posts"
OLYMPIAD = re.compile(r"олимпиад", re.IGNORECASE)
COMPLETED = re.compile(r"победител|победил|победила|показал.{0,25}результат|историческ.{0,20}результат|сборная.{0,30}вошла|приз[её]р|медал|итоги|награжд|встретил|абсолютн.{0,20}чемпион|успешно выступил|завершил|жеңімпаз|жеңіске жетті|нәтиже көрсетті|үздік оқушы|қорытындысы", re.IGNORECASE)
SUBJECTS = {
    "Математика": ("математ", "math"),
    "Информатика": ("информат", "computer science", "informatics"),
    "Физика": ("физик", "physics"),
    "Химия": ("хими", "chemistry"),
    "Биология": ("биолог", "biology"),
    "География": ("географ", "geography"),
    "История": ("истори", "history"),
    "Лингвистика": ("лингв", "linguistic"),
}


def plain_text(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", unescape(value)).strip()


class Command(BaseCommand):
    help = "Импортирует объявления олимпиад из публичного API сайта РНПЦ «Дарын» как черновики."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=60, help="Сколько дней назад искать публикации (по умолчанию: 60).")
        parser.add_argument("--max-pages", type=int, default=3, help="Лимит страниц API, по 100 записей в каждой.")

    def handle(self, *args, **options):
        if options["days"] < 1 or options["max_pages"] < 1:
            raise CommandError("Параметры --days и --max-pages должны быть положительными.")

        after = (timezone.now() - timedelta(days=options["days"])).strftime("%Y-%m-%dT%H:%M:%S")
        created = updated = skipped = 0
        for page in range(1, options["max_pages"] + 1):
            query = urlencode({
                "per_page": 100,
                "page": page,
                "after": after,
                "_fields": "id,date,link,title,excerpt",
            })
            request = Request(f"{API_URL}?{query}", headers={"User-Agent": "OlympIQ/1.0 (educational olympiad catalog)"})
            try:
                with urlopen(request, timeout=20) as response:
                    posts = json.load(response)
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
                raise CommandError(f"Не удалось получить данные Daryn API: {exc}") from exc

            if not isinstance(posts, list):
                raise CommandError("Daryn API вернул ответ неожиданного формата.")
            if not posts:
                break

            for post in posts:
                title = plain_text(post.get("title", {}).get("rendered", ""))
                excerpt = plain_text(post.get("excerpt", {}).get("rendered", ""))
                if not title or not OLYMPIAD.search(title) or COMPLETED.search(title):
                    skipped += 1
                    continue

                corpus = f"{title} {excerpt}".lower()
                subject = next((name for name, words in SUBJECTS.items() if any(word in corpus for word in words)), "Общее")
                key = f"daryn-wp:{post['id']}"
                values = {
                    "title": title[:240],
                    "subject": subject,
                    "description": (excerpt or "Официальное объявление РНПЦ «Дарын». Откройте ссылку на первоисточник для подробностей.")[:5000],
                    "organizer": "Республиканский научно-практический центр «Дарын»",
                    "source_url": post.get("link", ""),
                    "source_synced_at": timezone.now(),
                }
                item, was_created = Olympiad.objects.get_or_create(
                    source_key=key,
                    defaults={**values, "is_published": False, "format": "", "min_grade": None, "max_grade": None},
                )
                if not was_created:
                    for field, value in values.items():
                        setattr(item, field, value)
                    item.save(update_fields=[*values, "updated_at"] if hasattr(item, "updated_at") else list(values))
                created += int(was_created)
                updated += int(not was_created)

            if len(posts) < 100:
                break

        self.stdout.write(self.style.SUCCESS(
            f"Импорт завершён: создано черновиков — {created}, обновлено — {updated}, пропущено записей — {skipped}."
        ))
        if created or updated:
            self.stdout.write("Проверьте черновики в админ-панели: укажите подтверждённые даты, формат и классы перед публикацией.")
