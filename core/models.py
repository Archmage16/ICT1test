from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse


class School(models.Model):
    name = models.CharField("Название", max_length=220)
    bin = models.CharField("БИН", max_length=12, blank=True)
    city = models.CharField("Город", max_length=120)
    address = models.CharField("Адрес", max_length=255, blank=True)

    class Meta:
        ordering = ["city", "name"]
        verbose_name = "Школа"
        verbose_name_plural = "Школы"

    def __str__(self):
        return f"{self.name}, {self.city}"


class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "student", "Ученик"
        TEACHER = "teacher", "Учитель"
        ADMIN = "admin", "Администратор"

    role = models.CharField("Роль", max_length=12, choices=Role.choices, default=Role.STUDENT)
    school = models.ForeignKey(School, on_delete=models.SET_NULL, null=True, blank=True, related_name="users")
    grade = models.PositiveSmallIntegerField("Класс", null=True, blank=True)
    phone = models.CharField("Телефон", max_length=20, blank=True)
    patronymic = models.CharField("Отчество", max_length=120, blank=True)

    @property
    def full_name(self):
        return " ".join(filter(None, [self.last_name, self.first_name, self.patronymic])) or self.username


class Olympiad(models.Model):
    class Format(models.TextChoices):
        ONLINE = "online", "Онлайн"
        OFFLINE = "offline", "Офлайн"
        HYBRID = "hybrid", "Гибрид"

    title = models.CharField("Название", max_length=240)
    subject = models.CharField("Предмет", max_length=100)
    description = models.TextField("Описание")
    organizer = models.CharField("Организатор", max_length=180)
    format = models.CharField("Формат", max_length=10, choices=Format.choices, blank=True, default="")
    city = models.CharField("Город", max_length=120, blank=True)
    venue = models.CharField("Место проведения", max_length=255, blank=True)
    starts_at = models.DateTimeField("Дата и время начала", null=True, blank=True)
    ends_at = models.DateTimeField("Дата и время окончания", null=True, blank=True)
    registration_deadline = models.DateTimeField("Дедлайн регистрации", null=True, blank=True)
    min_grade = models.PositiveSmallIntegerField("С класса", null=True, blank=True, default=5)
    max_grade = models.PositiveSmallIntegerField("По класс", null=True, blank=True, default=11)
    capacity = models.PositiveIntegerField("Количество мест (0 — без ограничений)", default=0)
    level = models.CharField("Уровень", max_length=24, default="national", choices=[
        ("school", "Школьный"), ("district", "Районный"), ("city", "Городской"),
        ("regional", "Областной"), ("national", "Республиканский"), ("international", "Международный"),
    ])
    rules_url = models.URLField("Ссылка на положение", blank=True)
    source_key = models.CharField("Ключ записи источника", max_length=80, unique=True, null=True, blank=True)
    source_url = models.URLField("Источник", blank=True)
    source_synced_at = models.DateTimeField("Синхронизировано", null=True, blank=True)
    is_published = models.BooleanField("Опубликовано", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["starts_at"]
        verbose_name = "Олимпиада"
        verbose_name_plural = "Олимпиады"

    def __str__(self):
        return self.title

    def clean(self):
        errors = {}
        if self.is_published and not (self.starts_at and self.registration_deadline and self.format):
            errors["starts_at"] = "Для публикации укажите дату олимпиады, дедлайн регистрации и формат."
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            errors["ends_at"] = "Дата окончания должна быть позже даты начала."
        if self.registration_deadline and self.starts_at and self.registration_deadline > self.starts_at:
            errors["registration_deadline"] = "Дедлайн регистрации должен наступить до олимпиады."
        if self.min_grade and self.max_grade and self.min_grade > self.max_grade:
            errors["max_grade"] = "Старший класс не может быть меньше младшего."
        if errors:
            raise ValidationError(errors)

    def get_absolute_url(self):
        return reverse("olympiad_detail", args=[self.pk])

    @property
    def approved_count(self):
        return self.registrations.filter(status=Registration.Status.APPROVED).count()

    @property
    def places_left(self):
        if not self.capacity:
            return None
        return max(0, self.capacity - self.registrations.exclude(status=Registration.Status.REJECTED).count())

    @property
    def registration_open(self):
        from django.utils import timezone
        return bool(self.registration_deadline and self.starts_at and self.registration_deadline >= timezone.now() and self.starts_at >= timezone.now() and self.places_left != 0)


class Registration(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "На проверке"
        APPROVED = "approved", "Подтверждена"
        REJECTED = "rejected", "Отклонена"

    olympiad = models.ForeignKey(Olympiad, on_delete=models.CASCADE, related_name="registrations")
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="olympiad_registrations", limit_choices_to={"role": User.Role.STUDENT})
    registered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="created_registrations")
    status = models.CharField("Статус", max_length=12, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    note = models.CharField("Комментарий", max_length=300, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["olympiad", "student"], name="unique_olympiad_student")]
        ordering = ["-created_at"]
        verbose_name = "Регистрация"
        verbose_name_plural = "Регистрации"

    def __str__(self):
        return f"{self.student.full_name} — {self.olympiad.title}"


class Result(models.Model):
    registration = models.OneToOneField(Registration, on_delete=models.CASCADE, related_name="result")
    score = models.DecimalField("Баллы", max_digits=7, decimal_places=2)
    max_score = models.DecimalField("Максимум", max_digits=7, decimal_places=2, default=100)
    place = models.PositiveIntegerField("Место", null=True, blank=True)
    diploma = models.CharField("Награда", max_length=120, blank=True)
    is_published = models.BooleanField("Опубликован", default=False)
    published_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["place", "-score"]
        verbose_name = "Результат"
        verbose_name_plural = "Результаты"

    def clean(self):
        if self.score is not None and self.max_score is not None:
            if self.score < 0 or self.max_score <= 0 or self.score > self.max_score:
                raise ValidationError("Баллы должны быть от 0 до максимального балла.")


class TelegramLink(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="telegram_link")
    chat_id = models.CharField(max_length=40, unique=True, null=True, blank=True)
    pairing_token = models.UUIDField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    connected_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Telegram для {self.user.username}"


class TelegramReminder(models.Model):
    class Kind(models.TextChoices):
        DEADLINE = "deadline", "Дедлайн через сутки"
        OLYMPIAD = "olympiad", "Олимпиада завтра"

    registration = models.ForeignKey(Registration, on_delete=models.CASCADE, related_name="telegram_reminders")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["registration", "kind"], name="unique_registration_telegram_reminder")]
        verbose_name = "Отправленное напоминание"
        verbose_name_plural = "Отправленные напоминания"


class News(models.Model):
    title = models.CharField("Заголовок", max_length=220)
    text = models.TextField("Текст")
    published_at = models.DateTimeField("Дата публикации", auto_now_add=True)
    is_published = models.BooleanField("Опубликовано", default=True)

    class Meta:
        ordering = ["-published_at"]
        verbose_name = "Новость"
        verbose_name_plural = "Новости"

    def __str__(self):
        return self.title
