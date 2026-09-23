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
            ("Республиканская олимпиада по информатике", "Информатика", 12, "Астана", "offline", "national", "olympiad", 7, 11),
            ("Жас математик 2026", "Математика", 14, "Алматы", "hybrid", "regional", "olympiad", 5, 8),
            ("English Challenge", "Английский язык", 16, "", "online", "international", "olympiad", 7, 11),
            ("Открытая олимпиада по физике", "Физика", 18, "Караганда", "offline", "city", "olympiad", 8, 11),
            ("Турнир юных химиков", "Химия", 19, "Шымкент", "hybrid", "regional", "olympiad", 8, 11),
            ("Биология: исследовательский этап", "Биология", 20, "", "online", "national", "olympiad", 7, 11),
            ("Олимпиада по географии Казахстана", "География", 21, "Астана", "offline", "national", "olympiad", 6, 10),
            ("Юный историк", "История", 22, "Кызылорда", "hybrid", "regional", "olympiad", 7, 10),
            ("Лингвистический марафон", "Лингвистика", 23, "", "online", "international", "olympiad", 8, 11),
            ("Олимпиада по казахскому языку", "Казахский язык", 24, "Тараз", "offline", "national", "olympiad", 5, 9),
            ("Младшая олимпиада по математике", "Математика", 25, "", "online", "school", "olympiad", 3, 6),
            ("Алгоритмический старт", "Информатика", 26, "Алматы", "hybrid", "city", "olympiad", 6, 9),
            ("Олимпиада по астрономии", "Астрономия", 27, "Астана", "offline", "national", "olympiad", 8, 11),
            ("Экология и устойчивое развитие", "Экология", 28, "", "online", "international", "olympiad", 7, 11),
            ("Олимпиада по финансовой грамотности", "Финансовая грамотность", 29, "Павлодар", "hybrid", "regional", "olympiad", 7, 11),
            ("Кибербезопасность для школьников", "Информатика", 30, "", "online", "national", "olympiad", 8, 11),
            ("Инженерная олимпиада", "Инженерия", 31, "Актобе", "offline", "regional", "olympiad", 7, 11),
            ("Олимпиада по естествознанию", "Естествознание", 32, "Костанай", "hybrid", "district", "olympiad", 5, 7),
            ("Открытая олимпиада по английскому языку", "Английский язык", 33, "", "online", "international", "olympiad", 5, 11),
            ("Дебаты: школьная лига", "Дебаты", 34, "Астана", "offline", "national", "olympiad", 8, 11),
            ("Green City: школьный хакатон", "Экология и технологии", 35, "Алматы", "hybrid", "city", "hackathon", 8, 11),
            ("EdTech Weekend", "Образовательные технологии", 36, "", "online", "international", "hackathon", 9, 11),
            ("Конкурс научных проектов", "Научный проект", 37, "Караганда", "offline", "regional", "contest", 7, 11),
            ("Робототехнический хакатон", "Робототехника", 38, "Астана", "hybrid", "national", "hackathon", 6, 11),
        ]
        for index, (title, subject, days, city, fmt, level, event_type, min_grade, max_grade) in enumerate(demos, start=1):
            starts_at = now + timedelta(days=days)
            Olympiad.objects.update_or_create(title=title, defaults={
                "event_type": event_type,
                "subject": subject,
                "description": "Демонстрационный пример для проверки каталога и процесса регистрации OlympIQ. Это тестовое событие; даты и условия не являются официальным объявлением организатора.",
                "organizer": "Демонстрационный каталог OlympIQ",
                "format": fmt,
                "city": city,
                "venue": "Адрес уточняется в примере",
                "starts_at": starts_at,
                "ends_at": starts_at + timedelta(hours=3),
                "registration_deadline": starts_at - timedelta(days=2),
                "min_grade": min_grade,
                "max_grade": max_grade,
                "level": level,
                "is_published": True,
                "is_demo": True,
                "source_key": f"demo:{index}",
                "source_url": "",
                "registration_url": "",
            })
        News.objects.get_or_create(title="Открыта регистрация на осенний сезон", defaults={"text": "В каталоге доступны новые олимпиады по информатике, математике и английскому языку."})
        open_demo_count = Olympiad.objects.filter(is_demo=True, is_published=True, registration_deadline__gte=now, starts_at__gte=now).count()
        self.stdout.write(self.style.SUCCESS(f"Демо-данные созданы: {open_demo_count} открытых примеров событий. Логины: admin / teacher / student, пароль: Demo12345!"))
