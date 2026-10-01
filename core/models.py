from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from .ui_text import translate, translate_lazy as _


class School(models.Model):
    name = models.CharField(_("Название"), max_length=220)
    bin = models.CharField(_("БИН"), max_length=12, blank=True)
    city = models.CharField(_("Город"), max_length=120)
    address = models.CharField(_("Адрес"), max_length=255, blank=True)

    class Meta:
        ordering = ["city", "name"]
        verbose_name = _("Школа")
        verbose_name_plural = _("Школы")

    def __str__(self):
        return f"{translate(self.name)}, {translate(self.city)}"


class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "student", _("Ученик")
        TEACHER = "teacher", _("Учитель")
        ADMIN = "admin", _("Администратор")

    role = models.CharField(_("Роль"), max_length=12, choices=Role.choices, default=Role.STUDENT)
    school = models.ForeignKey(School, verbose_name=_("Школа"), on_delete=models.SET_NULL, null=True, blank=True, related_name="users")
    grade = models.PositiveSmallIntegerField(_("Класс"), null=True, blank=True)
    phone = models.CharField(_("Телефон"), max_length=20, blank=True)
    patronymic = models.CharField(_("Отчество"), max_length=120, blank=True)

    @property
    def full_name(self):
        return " ".join(filter(None, [self.last_name, self.first_name, self.patronymic])) or self.username


class Olympiad(models.Model):
    class Format(models.TextChoices):
        ONLINE = "online", _("Онлайн")
        OFFLINE = "offline", _("Офлайн")
        HYBRID = "hybrid", _("Гибрид")

    class EventType(models.TextChoices):
        OLYMPIAD = "olympiad", _("Олимпиада")
        HACKATHON = "hackathon", _("Хакатон")
        CONTEST = "contest", _("Конкурс")
        QUIZ = "quiz", _("Викторина")
        OTHER = "other", _("Другое")

    title = models.CharField(_("Название"), max_length=240)
    event_type = models.CharField(_("Тип события"), max_length=12, choices=EventType.choices, default=EventType.OLYMPIAD)
    subject = models.CharField(_("Предмет"), max_length=100)
    description = models.TextField(_("Описание"))
    participation_details = models.TextField(_("Условия и порядок участия"), blank=True)
    preparation = models.TextField(_("Темы и подготовка"), blank=True)
    assessment = models.TextField(_("Оценивание и результаты"), blank=True)
    organizer = models.CharField(_("Организатор"), max_length=180)
    format = models.CharField(_("Формат"), max_length=10, choices=Format.choices, blank=True, default="")
    city = models.CharField(_("Город"), max_length=120, blank=True)
    venue = models.CharField(_("Место проведения"), max_length=255, blank=True)
    starts_at = models.DateTimeField(_("Дата и время начала"), null=True, blank=True)
    ends_at = models.DateTimeField(_("Дата и время окончания"), null=True, blank=True)
    registration_deadline = models.DateTimeField(_("Дедлайн регистрации"), null=True, blank=True)
    min_grade = models.PositiveSmallIntegerField(_("С класса"), null=True, blank=True, default=5)
    max_grade = models.PositiveSmallIntegerField(_("По класс"), null=True, blank=True, default=11)
    capacity = models.PositiveIntegerField(_("Количество мест (0 — без ограничений)"), default=0)
    level = models.CharField(_("Уровень"), max_length=24, default="", blank=True, choices=[
        ("school", _("Школьный")), ("district", _("Районный")), ("city", _("Городской")),
        ("regional", _("Областной")), ("national", _("Республиканский")), ("international", _("Международный")),
    ])
    rules_url = models.URLField(_("Ссылка на положение"), blank=True)
    source_key = models.CharField(_("Ключ записи источника"), max_length=80, unique=True, null=True, blank=True)
    source_url = models.URLField(_("Источник"), blank=True)
    registration_url = models.URLField(_("Ссылка для регистрации у организатора"), blank=True)
    source_synced_at = models.DateTimeField(_("Синхронизировано"), null=True, blank=True)
    is_demo = models.BooleanField(_("Демонстрационная запись"), default=False)
    is_published = models.BooleanField(_("Опубликовано"), default=True)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)

    class Meta:
        ordering = ["starts_at"]
        verbose_name = _("Олимпиада")
        verbose_name_plural = _("Олимпиады")

    def __str__(self):
        return translate(self.title)

    def clean(self):
        errors = {}
        if self.is_published:
            required_for_publication = {
                "starts_at": self.starts_at,
                "registration_deadline": self.registration_deadline,
                "format": self.format,
                "level": self.level,
                "min_grade": self.min_grade,
                "max_grade": self.max_grade,
            }
            for field, value in required_for_publication.items():
                if not value:
                    errors[field] = _("Заполните это поле перед публикацией.")
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            errors["ends_at"] = _("Дата окончания должна быть позже даты начала.")
        if self.registration_deadline and self.starts_at and self.registration_deadline > self.starts_at:
            errors["registration_deadline"] = _("Дедлайн регистрации должен наступить до олимпиады.")
        if self.min_grade and self.max_grade and self.min_grade > self.max_grade:
            errors["max_grade"] = _("Старший класс не может быть меньше младшего.")
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
        return bool(
            self.is_published
            and self.registration_deadline
            and self.starts_at
            and self.min_grade is not None
            and self.max_grade is not None
            and self.level
            and self.registration_deadline >= timezone.now()
            and self.starts_at >= timezone.now()
            and self.places_left != 0
        )


class Registration(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("На проверке")
        APPROVED = "approved", _("Подтверждена")
        REJECTED = "rejected", _("Отклонена")

    olympiad = models.ForeignKey(Olympiad, verbose_name=_("Олимпиада"), on_delete=models.CASCADE, related_name="registrations")
    student = models.ForeignKey(User, verbose_name=_("Ученик"), on_delete=models.CASCADE, related_name="olympiad_registrations", limit_choices_to={"role": User.Role.STUDENT})
    registered_by = models.ForeignKey(User, verbose_name=_("Зарегистрировал"), on_delete=models.SET_NULL, null=True, related_name="created_registrations")
    status = models.CharField(_("Статус"), max_length=12, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(_("Дата заявки"), auto_now_add=True)
    note = models.CharField(_("Комментарий"), max_length=300, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["olympiad", "student"], name="unique_olympiad_student")]
        ordering = ["-created_at"]
        verbose_name = _("Регистрация")
        verbose_name_plural = _("Регистрации")

    def __str__(self):
        return f"{self.student.full_name} — {translate(self.olympiad.title)}"


class Result(models.Model):
    registration = models.OneToOneField(Registration, verbose_name=_("Регистрация на событие"), on_delete=models.CASCADE, related_name="result")
    score = models.DecimalField(_("Баллы"), max_digits=7, decimal_places=2)
    max_score = models.DecimalField(_("Максимум"), max_digits=7, decimal_places=2, default=100)
    place = models.PositiveIntegerField(_("Место"), null=True, blank=True)
    diploma = models.CharField(_("Награда"), max_length=120, blank=True)
    is_published = models.BooleanField(_("Опубликован"), default=False)
    published_at = models.DateTimeField(_("Дата публикации результата"), auto_now_add=True)

    class Meta:
        ordering = ["place", "-score"]
        verbose_name = _("Результат")
        verbose_name_plural = _("Результаты")

    def clean(self):
        if self.score is not None and self.max_score is not None:
            if self.score < 0 or self.max_score <= 0 or self.score > self.max_score:
                raise ValidationError(_("Баллы должны быть от 0 до максимального балла."))


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
        DEADLINE = "deadline", _("Дедлайн через сутки")
        OLYMPIAD = "olympiad", _("Олимпиада завтра")

    registration = models.ForeignKey(Registration, on_delete=models.CASCADE, related_name="telegram_reminders")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["registration", "kind"], name="unique_registration_telegram_reminder")]
        verbose_name = _("Отправленное напоминание")
        verbose_name_plural = _("Отправленные напоминания")


class News(models.Model):
    title = models.CharField(_("Заголовок"), max_length=220)
    text = models.TextField(_("Текст"))
    published_at = models.DateTimeField(_("Дата публикации"), auto_now_add=True)
    is_published = models.BooleanField(_("Опубликовано"), default=True)

    class Meta:
        ordering = ["-published_at"]
        verbose_name = _("Новость")
        verbose_name_plural = _("Новости")

    def __str__(self):
        return translate(self.title)
