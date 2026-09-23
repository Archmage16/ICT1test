from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from core.models import News, Olympiad, School, User


class Command(BaseCommand):
    help = "Создаёт демонстрационные данные"

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Демо-данные можно создавать только при DJANGO_DEBUG=true.")
        school, _ = School.objects.get_or_create(name="Школа-лицей № 72", city="Астана", defaults={"address": "пр. Мәңгілік Ел, 35"})
        users = [
            ("admin", User.Role.ADMIN, True, None),
            ("teacher", User.Role.TEACHER, False, None),
            ("student", User.Role.STUDENT, False, 9),
        ]
        for username, role, staff, grade in users:
            user, created = User.objects.get_or_create(username=username, defaults={"first_name": {"admin": "Айдана", "teacher": "Алия", "student": "Данияр"}[username], "last_name": "Демо", "role": role, "school": school, "grade": grade, "is_staff": staff, "is_superuser": staff})
            if created:
                user.set_password("Demo12345!")
                user.save()

        now = timezone.now()
        demos = [
            ("Республиканская олимпиада по информатике", "Информатика", 12, "Астана", "Офлайн"),
            ("Жас математик 2026", "Математика", 20, "Алматы", "Гибрид"),
            ("English Challenge", "Английский язык", 28, "Онлайн", "Онлайн"),
        ]
        for title, subject, days, city, fmt in demos:
            Olympiad.objects.get_or_create(title=title, defaults={
                "subject": subject,
                "description": "Проверьте знания, получите опыт и шанс представить школу на следующем этапе. Подробный регламент доступен участникам после регистрации.",
                "organizer": "Республиканский научно-практический центр «Дарын»",
                "format": {"Онлайн": "online", "Офлайн": "offline", "Гибрид": "hybrid"}[fmt],
                "city": city if city != "Онлайн" else "",
                "venue": "Будет указано в личном кабинете",
                "starts_at": now + timedelta(days=days),
                "ends_at": now + timedelta(days=days, hours=3),
                "registration_deadline": now + timedelta(days=days - 4),
                "min_grade": 7,
                "max_grade": 11,
            })
        News.objects.get_or_create(title="Открыта регистрация на осенний сезон", defaults={"text": "В каталоге доступны новые олимпиады по информатике, математике и английскому языку."})
        self.stdout.write(self.style.SUCCESS("Демо-данные созданы. Логины: admin / teacher / student, пароль: Demo12345!"))
