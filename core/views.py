import csv
import json
import uuid
from datetime import timedelta
from django.contrib import messages
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import csrf_exempt
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .forms import ProfileForm, SignUpForm, TeacherRegistrationForm
from .models import News, Olympiad, Registration, Result, TelegramLink, User
from .telegram import send_message, send_to_user, user_summary


def csv_safe(value):
    text = str(value or "")
    if text.lstrip("\t\r\n ").startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def home(request):
    now = timezone.now()
    upcoming = Olympiad.objects.filter(is_published=True, starts_at__gte=now)[:6]
    return render(request, "core/home.html", {
        "upcoming": upcoming,
        "news": News.objects.filter(is_published=True)[:3],
        "olympiad_count": Olympiad.objects.filter(is_published=True).count(),
        "student_count": User.objects.filter(role=User.Role.STUDENT).count(),
        "school_count": User.objects.exclude(school=None).values("school").distinct().count(),
    })


def signup(request):
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Аккаунт создан. Добро пожаловать в OlimpIQ!")
        return redirect("dashboard")
    return render(request, "registration/signup.html", {"form": form})


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Профиль обновлён.")
        return redirect("dashboard")
    telegram_link = TelegramLink.objects.filter(user=request.user).first()
    return render(request, "core/profile.html", {"form": form, "telegram_link": telegram_link})


def olympiad_list(request):
    qs = Olympiad.objects.filter(is_published=True)
    q = request.GET.get("q", "").strip()
    subject = request.GET.get("subject", "")
    olympiad_format = request.GET.get("format", "")
    event_type = request.GET.get("type", "")
    grade_value = request.GET.get("grade", "")
    open_only = request.GET.get("open", "") == "1"
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(organizer__icontains=q) | Q(city__icontains=q))
    if subject:
        qs = qs.filter(subject=subject)
    if olympiad_format in Olympiad.Format.values:
        qs = qs.filter(format=olympiad_format)
    if event_type in Olympiad.EventType.values:
        qs = qs.filter(event_type=event_type)
    try:
        grade = int(grade_value)
    except (TypeError, ValueError):
        grade = None
        grade_value = ""
    if grade and 1 <= grade <= 11:
        qs = qs.filter(min_grade__lte=grade, max_grade__gte=grade)
    else:
        grade_value = ""
    if open_only:
        qs = qs.filter(registration_deadline__gte=timezone.now(), starts_at__gte=timezone.now())
    return render(request, "core/olympiad_list.html", {
        "olympiads": qs,
        "subjects": Olympiad.objects.filter(is_published=True).values_list("subject", flat=True).distinct().order_by("subject"),
        "q": q,
        "selected_subject": subject,
        "selected_format": olympiad_format,
        "selected_event_type": event_type,
        "selected_grade": grade_value,
        "open_only": open_only,
    })


@cache_control(public=True, max_age=300)
def events_api(request):
    qs = Olympiad.objects.filter(is_published=True)
    query = request.GET.get("q", "").strip()
    event_type = request.GET.get("type", "")
    if query:
        qs = qs.filter(Q(title__icontains=query) | Q(subject__icontains=query) | Q(organizer__icontains=query))
    if event_type in Olympiad.EventType.values:
        qs = qs.filter(event_type=event_type)
    if request.GET.get("open") == "1":
        qs = [item for item in qs if item.registration_open]
    return JsonResponse({
        "count": len(qs) if isinstance(qs, list) else qs.count(),
        "events": [{
            "id": item.pk,
            "title": item.title,
            "type": item.event_type,
            "subject": item.subject,
            "description": item.description,
            "organizer": item.organizer,
            "format": item.format,
            "city": item.city,
            "starts_at": item.starts_at.isoformat() if item.starts_at else None,
            "ends_at": item.ends_at.isoformat() if item.ends_at else None,
            "registration_deadline": item.registration_deadline.isoformat() if item.registration_deadline else None,
            "min_grade": item.min_grade,
            "max_grade": item.max_grade,
            "level": item.level,
            "registration_open": item.registration_open,
            "registration_url": item.registration_url or None,
            "source_url": item.source_url or None,
            "is_demo": item.is_demo,
        } for item in qs[:200]],
    })


def calendar(request):
    now = timezone.now()
    upcoming = Olympiad.objects.filter(is_published=True, starts_at__gte=now).order_by("starts_at")
    my_registrations = Registration.objects.none()
    if request.user.is_authenticated:
        my_registrations = Registration.objects.filter(
            student=request.user,
            olympiad__is_published=True,
            olympiad__starts_at__gte=now,
        ).select_related("olympiad").order_by("olympiad__starts_at")
    return render(request, "core/calendar.html", {
        "upcoming": upcoming,
        "my_registrations": my_registrations,
        "now": now,
    })


def olympiad_detail(request, pk):
    olympiad = get_object_or_404(Olympiad, pk=pk, is_published=True)
    registration = None
    if request.user.is_authenticated and request.user.role == User.Role.STUDENT:
        registration = Registration.objects.filter(olympiad=olympiad, student=request.user).first()
    results = Result.objects.filter(registration__olympiad=olympiad, is_published=True).select_related("registration__student")
    if request.user.is_authenticated and request.user.is_staff:
        pass
    elif request.user.is_authenticated and request.user.role == User.Role.STUDENT:
        results = results.filter(registration__student=request.user)
    else:
        results = results.none()
    return render(request, "core/olympiad_detail.html", {"olympiad": olympiad, "registration": registration, "results": results})


@login_required
def register_self(request, pk):
    if request.method != "POST":
        return redirect("olympiad_detail", pk=pk)
    olympiad = get_object_or_404(Olympiad, pk=pk, is_published=True)
    if olympiad.registration_url:
        messages.info(request, "Заявка подаётся на официальной странице события.")
    elif request.user.role != User.Role.STUDENT:
        messages.error(request, "Самостоятельная регистрация доступна только ученикам.")
    elif not olympiad.registration_open:
        messages.error(request, "Регистрация закрыта или свободные места закончились.")
    elif not request.user.school_id:
        messages.error(request, "Сначала добавьте школу в свой профиль.")
    elif not request.user.grade or not olympiad.min_grade <= request.user.grade <= olympiad.max_grade:
        messages.error(request, "Ваш класс не соответствует возрастной категории олимпиады.")
    else:
        try:
            with transaction.atomic():
                locked = Olympiad.objects.select_for_update().get(pk=olympiad.pk)
                if not locked.registration_open:
                    raise ValueError("Регистрация закрыта или свободные места закончились.")
                if not (locked.min_grade <= request.user.grade <= locked.max_grade):
                    raise ValueError("Класс больше не соответствует возрастной категории события.")
                _, created = Registration.objects.get_or_create(olympiad=locked, student=request.user, defaults={"registered_by": request.user})
            messages.success(request, "Заявка отправлена." if created else "Вы уже зарегистрированы.")
            if created:
                send_to_user(request.user, f"Заявка принята системой OlympIQ: {olympiad.title}. Дата: {timezone.localtime(olympiad.starts_at).strftime('%d.%m.%Y %H:%M')}.")
        except (IntegrityError, ValueError) as error:
            messages.error(request, str(error) or "Вы уже зарегистрированы.")
    return redirect(olympiad)


@login_required
def dashboard(request):
    user = request.user
    telegram_link = TelegramLink.objects.filter(user=user).first()
    if user.is_staff or user.role == User.Role.ADMIN:
        return render(request, "core/dashboard_admin.html", {
            "registrations": Registration.objects.select_related("student", "olympiad")[:12],
            "pending_count": Registration.objects.filter(status=Registration.Status.PENDING).count(),
            "olympiads": Olympiad.objects.annotate(total=Count("registrations"))[:8],
            "telegram_link": telegram_link,
        })
    if user.role == User.Role.TEACHER:
        registrations = Registration.objects.filter(student__school=user.school) if user.school_id else Registration.objects.none()
        registrations = registrations.select_related("student", "olympiad")
        return render(request, "core/dashboard_teacher.html", {
            "registrations": registrations,
            "students_count": User.objects.filter(role=User.Role.STUDENT, school=user.school).count() if user.school_id else 0,
            "upcoming": Olympiad.objects.filter(is_published=True, registration_deadline__gte=timezone.now(), starts_at__gte=timezone.now())[:5],
            "telegram_link": telegram_link,
        })
    return render(request, "core/dashboard_student.html", {
        "registrations": Registration.objects.filter(student=user).select_related("olympiad", "result"),
        "recommended": Olympiad.objects.filter(is_published=True, registration_deadline__gte=timezone.now(), min_grade__lte=user.grade or 11, max_grade__gte=user.grade or 1)[:4],
        "telegram_link": telegram_link,
    })


@login_required
def telegram_connect(request):
    if request.method != "POST":
        return redirect("dashboard")
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_BOT_USERNAME:
        messages.error(request, "Telegram-бот пока не настроен администратором.")
        return redirect("dashboard")
    link, _ = TelegramLink.objects.get_or_create(user=request.user, defaults={"pairing_token": uuid.uuid4()})
    link.pairing_token = uuid.uuid4()
    link.chat_id = None
    link.connected_at = None
    link.created_at = timezone.now()
    link.save(update_fields=["pairing_token", "chat_id", "connected_at", "created_at"])
    bot_url = f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={link.pairing_token}"
    messages.success(request, f"Откройте бота и нажмите Start: {bot_url} (код действует 15 минут).")
    return redirect("dashboard")


@csrf_exempt
def telegram_webhook(request):
    if request.method != "POST" or not settings.TELEGRAM_WEBHOOK_SECRET:
        return JsonResponse({"ok": False}, status=403)
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != settings.TELEGRAM_WEBHOOK_SECRET:
        return JsonResponse({"ok": False}, status=403)
    try:
        update = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False}, status=400)
    if not isinstance(update, dict):
        return JsonResponse({"ok": False}, status=400)
    message = update.get("message", {})
    if not isinstance(message, dict):
        return JsonResponse({"ok": True})
    chat = message.get("chat")
    if not isinstance(chat, dict):
        return JsonResponse({"ok": True})
    chat_id = chat.get("id")
    raw_text = message.get("text")
    text = raw_text.strip() if isinstance(raw_text, str) else ""
    if not chat_id or not text:
        return JsonResponse({"ok": True})
    command, _, argument = text.partition(" ")
    command = command.split("@", 1)[0].lower()
    reply = None
    if command == "/start" and argument:
        try:
            link = TelegramLink.objects.select_related("user").get(pairing_token=uuid.UUID(argument), chat_id__isnull=True)
            if timezone.now() - link.created_at > timedelta(minutes=15):
                reply = "Ссылка истекла. Создайте новую в личном кабинете OlympIQ."
            else:
                link.chat_id = str(chat_id)
                link.connected_at = timezone.now()
                link.pairing_token = uuid.uuid4()
                link.save(update_fields=["chat_id", "connected_at", "pairing_token"])
                reply = f"Telegram подключён к OlympIQ для {link.user.first_name or link.user.username}. Используйте /my или /deadlines."
        except (TelegramLink.DoesNotExist, ValueError):
            reply = "Ссылка недействительна или уже использована. Создайте новую в OlympIQ."
    elif command == "/my":
        reply = user_summary(chat_id)
    elif command == "/deadlines":
        reply = user_summary(chat_id, deadlines=True)
    elif command == "/help":
        reply = "Команды OlympIQ: /my — ближайшие олимпиады, /deadlines — сроки регистрации, /help — помощь."
    elif command == "/start":
        reply = "Привет! Подключите аккаунт через кнопку «Подключить Telegram» в кабинете OlympIQ."
    if reply:
        send_message(chat_id, reply)
    return JsonResponse({"ok": True})


@login_required
def teacher_register(request, pk):
    if request.user.role != User.Role.TEACHER:
        messages.error(request, "Раздел доступен только учителям.")
        return redirect("dashboard")
    if not request.user.school_id:
        messages.error(request, "Ваш аккаунт учителя не привязан к школе.")
        return redirect("dashboard")
    olympiad = get_object_or_404(Olympiad, pk=pk, is_published=True)
    if olympiad.registration_url:
        messages.info(request, "Заявка на это событие подаётся на официальной странице организатора.")
        return redirect(olympiad)
    if not olympiad.registration_open:
        messages.error(request, "Регистрация закрыта или свободные места закончились.")
        return redirect(olympiad)
    form = TeacherRegistrationForm(request.POST or None, teacher=request.user)
    if request.method == "POST" and form.is_valid():
        if not olympiad.registration_open:
            form.add_error(None, "Регистрация закрыта или свободные места закончились.")
        else:
            students = list(form.cleaned_data["students"])
            eligible = [student for student in students if student.school_id == request.user.school_id and student.grade and olympiad.min_grade <= student.grade <= olympiad.max_grade]
            if len(eligible) != len(students):
                form.add_error("students", "В списке есть ученик не из вашей школы или неподходящего класса.")
            else:
                created = 0
                new_students = []
                with transaction.atomic():
                    locked = Olympiad.objects.select_for_update().get(pk=olympiad.pk)
                    if not locked.registration_open:
                        form.add_error(None, "Регистрация закрылась или свободные места закончились.")
                        return render(request, "core/teacher_register.html", {"form": form, "olympiad": olympiad})
                    if any(not (locked.min_grade <= student.grade <= locked.max_grade) for student in eligible):
                        form.add_error("students", "Возрастные условия события изменились. Обновите форму и выберите подходящих учеников.")
                        return render(request, "core/teacher_register.html", {"form": form, "olympiad": olympiad})
                    for student in eligible:
                        if not locked.registration_open:
                            break
                        _, was_created = Registration.objects.get_or_create(
                            olympiad=locked, student=student,
                            defaults={"registered_by": request.user, "note": form.cleaned_data["note"]},
                        )
                        created += int(was_created)
                        if was_created:
                            new_students.append(student)
                for student in new_students:
                    send_to_user(student, f"Учитель зарегистрировал вас на олимпиаду «{olympiad.title}». Начало: {timezone.localtime(olympiad.starts_at).strftime('%d.%m.%Y %H:%M')}.")
                messages.success(request, f"Создано заявок: {created} из {len(eligible)}.")
                return redirect("dashboard")
    return render(request, "core/teacher_register.html", {"form": form, "olympiad": olympiad})


@staff_member_required
def export_registrations(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="registrations.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(["Олимпиада", "ФИО", "Школа", "Класс", "Статус", "Дата заявки"])
    for item in Registration.objects.select_related("student__school", "olympiad"):
        writer.writerow([csv_safe(item.olympiad.title), csv_safe(item.student.full_name), csv_safe(item.student.school or ""), csv_safe(item.student.grade or ""), csv_safe(item.get_status_display()), item.created_at.strftime("%d.%m.%Y %H:%M")])
    return response
