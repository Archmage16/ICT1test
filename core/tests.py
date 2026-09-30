import json
import os
from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from .models import Olympiad, Registration, School, User
from .demo_guides import enrich_demo_events
from .ui_text import TEXT
from pathlib import Path
import re


class PublicUXDemoTests(TestCase):
    def test_initializer_requires_explicit_sandbox_mode(self):
        with patch.dict(os.environ, {"OLYMPIQ_UX_DEMO": "false"}):
            with self.assertRaises(CommandError):
                call_command("prepare_ux_demo", stdout=StringIO())
        self.assertFalse(User.objects.exists())

    def test_initializer_refuses_non_demo_database(self):
        User.objects.create_user(username="real-account", password="unique-password")
        with patch.dict(os.environ, {"OLYMPIQ_UX_DEMO": "true"}):
            with self.assertRaises(CommandError):
                call_command("prepare_ux_demo", stdout=StringIO())
        self.assertEqual(User.objects.count(), 1)

    def test_public_demo_is_student_only_and_repeatable(self):
        with patch.dict(os.environ, {"OLYMPIQ_UX_DEMO": "true"}):
            call_command("prepare_ux_demo", stdout=StringIO())
            event = Olympiad.objects.get(source_key="demo:16")
            student = User.objects.get(username="uxcheck")
            Registration.objects.create(olympiad=event, student=student, registered_by=student)
            starts_at = event.starts_at
            call_command("prepare_ux_demo", stdout=StringIO())
        self.assertEqual(Olympiad.objects.filter(is_demo=True).count(), 24)
        self.assertEqual(Registration.objects.count(), 1)
        event.refresh_from_db()
        self.assertEqual(event.starts_at, starts_at)
        for username in ("admin", "teacher"):
            account = User.objects.get(username=username)
            self.assertFalse(account.is_active)
            self.assertFalse(account.has_usable_password())
        for username in ("ux01", "ux02", "ux03", "uxcheck"):
            account = User.objects.get(username=username)
            self.assertEqual(account.role, User.Role.STUDENT)
            self.assertEqual(account.grade, 9)
            self.assertFalse(account.is_staff)
            self.assertTrue(account.check_password("Demo12345!"))


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class PlatformFlowTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Тестовая школа", city="Астана")
        self.student = User.objects.create_user(username="student", password="pass12345", role=User.Role.STUDENT, school=self.school, grade=9)
        self.teacher = User.objects.create_user(username="teacher", password="pass12345", role=User.Role.TEACHER, school=self.school)
        now = timezone.now()
        self.olympiad = Olympiad.objects.create(
            title="Тестовая олимпиада", subject="Информатика", description="Описание",
            organizer="Организатор", format=Olympiad.Format.ONLINE, level="national",
            starts_at=now + timedelta(days=10), ends_at=now + timedelta(days=10, hours=2),
            registration_deadline=now + timedelta(days=5), min_grade=7, max_grade=11,
        )

    def test_public_pages_are_available(self):
        for url in [reverse("home"), reverse("olympiad_list"), self.olympiad.get_absolute_url()]:
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_student_can_register(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse("register_self", args=[self.olympiad.pk]))
        self.assertRedirects(response, self.olympiad.get_absolute_url())
        self.assertTrue(Registration.objects.filter(student=self.student, olympiad=self.olympiad).exists())

    def test_teacher_sees_registration_form(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("teacher_register", args=[self.olympiad.pk])).status_code, 200)

    def test_missing_school_shows_profile_recovery_before_submission(self):
        self.student.school = None
        self.student.save(update_fields=["school"])
        self.client.force_login(self.student)
        response = self.client.get(self.olympiad.get_absolute_url())
        self.assertContains(response, "Заполнить профиль")
        self.assertNotContains(response, "Подать заявку</button>")
        self.client.post(reverse("register_self", args=[self.olympiad.pk]))
        self.assertFalse(Registration.objects.filter(student=self.student).exists())

    def test_missing_grade_shows_profile_recovery_before_submission(self):
        self.student.grade = None
        self.student.save(update_fields=["grade"])
        self.client.force_login(self.student)
        response = self.client.get(self.olympiad.get_absolute_url())
        self.assertContains(response, "Заполнить профиль")
        self.assertNotContains(response, "Подать заявку</button>")

    def test_ineligible_grade_shows_suitable_events_before_submission(self):
        self.student.grade = 5
        self.student.save(update_fields=["grade"])
        self.client.force_login(self.student)
        response = self.client.get(self.olympiad.get_absolute_url())
        self.assertContains(response, "Ваш класс: 5")
        self.assertContains(response, "Найти подходящую олимпиаду")
        self.assertNotContains(response, "Подать заявку</button>")
        self.client.post(reverse("register_self", args=[self.olympiad.pk]))
        self.assertFalse(Registration.objects.filter(student=self.student).exists())

    def test_eligible_student_keeps_registration_action(self):
        self.client.force_login(self.student)
        response = self.client.get(self.olympiad.get_absolute_url())
        self.assertContains(response, "Подать заявку</button>")
        self.assertContains(response, "Заявка от student")

    def test_unknown_grade_limits_keep_event_closed_without_crashing(self):
        self.olympiad.min_grade = None
        self.olympiad.max_grade = None
        self.olympiad.save()
        self.client.force_login(self.student)
        response = self.client.post(reverse("register_self", args=[self.olympiad.pk]))
        self.assertRedirects(response, self.olympiad.get_absolute_url())
        self.assertFalse(Registration.objects.filter(student=self.student, olympiad=self.olympiad).exists())

    def test_external_event_links_to_organizer_instead_of_faking_registration(self):
        self.olympiad.registration_url = "https://example.org/apply"
        self.olympiad.save()
        self.client.force_login(self.student)
        response = self.client.post(reverse("register_self", args=[self.olympiad.pk]))
        self.assertRedirects(response, self.olympiad.get_absolute_url())
        self.assertFalse(Registration.objects.filter(student=self.student, olympiad=self.olympiad).exists())
        self.assertContains(self.client.get(self.olympiad.get_absolute_url()), "https://example.org/apply")

    def test_events_api_filters_by_type_and_hides_drafts(self):
        self.olympiad.event_type = Olympiad.EventType.HACKATHON
        self.olympiad.registration_url = "https://example.org/apply"
        self.olympiad.save()
        draft = Olympiad.objects.create(
            title="Скрытый черновик", subject="Робототехника", description="Описание",
            organizer="Организатор", format="", starts_at=None, registration_deadline=None,
            min_grade=None, max_grade=None, is_published=False,
        )
        response = self.client.get(reverse("events_api"), {"type": "hackathon", "open": "1"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["events"][0]["title"], self.olympiad.title)
        self.assertTrue(payload["events"][0]["registration_open"])
        self.assertNotIn(draft.title, json.dumps(payload))

    @override_settings(TELEGRAM_WEBHOOK_SECRET="test-secret")
    def test_telegram_webhook_rejects_malformed_payload_shape(self):
        response = self.client.post(
            reverse("telegram_webhook"), data="[]", content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="test-secret",
        )
        self.assertEqual(response.status_code, 400)

    def test_pending_application_explains_saved_vs_approved(self):
        self.client.force_login(self.student)
        self.client.post(reverse("register_self", args=[self.olympiad.pk]))
        response = self.client.get(self.olympiad.get_absolute_url())
        self.assertContains(response, "Заявка сохранена. Ничего больше отправлять не нужно")
        self.assertContains(response, "Срок подтверждения пока не указан")
        self.assertNotContains(response, "Подать заявку</button>")
        self.client.post(reverse("register_self", args=[self.olympiad.pk]))
        self.assertEqual(Registration.objects.filter(student=self.student).count(), 1)

    def test_all_supported_languages_persist_across_pages_and_filters(self):
        for code, title in [("ru", "Как подать заявку"), ("en", "How to apply"), ("kk", "Өтінімді қалай беруге болады")]:
            response = self.client.post(reverse("set_language"), {"language": code, "next": "/olympiads/?grade=9&open=1"})
            self.assertEqual(response.url, "/olympiads/?grade=9&open=1")
            self.assertEqual(self.client.cookies["olympiq_language"].value, code)
            self.assertContains(self.client.get(reverse("home")), title)
            for url in [reverse("olympiad_list"), reverse("calendar"), reverse("login"), reverse("signup"), self.olympiad.get_absolute_url()]:
                self.assertEqual(self.client.get(url).status_code, 200)
            self.client.force_login(self.student)
            for url in [reverse("dashboard"), reverse("profile"), reverse("password_change")]:
                self.assertEqual(self.client.get(url).status_code, 200)
            self.client.logout()

    def test_language_setting_rejects_cross_origin_redirect_and_get_changes(self):
        response = self.client.post(reverse("set_language"), {"language": "en", "next": "https://attacker.example/"})
        self.assertEqual(response.url, "/")
        self.client.get(reverse("set_language"), {"language": "kk"})
        self.assertEqual(self.client.cookies["olympiq_language"].value, "en")

    def test_language_post_requires_csrf(self):
        self.assertEqual(Client(enforce_csrf_checks=True).post(reverse("set_language"), {"language": "en"}).status_code, 403)

    def test_static_ui_strings_have_both_translations(self):
        templates = Path(__file__).resolve().parent.parent / "templates"
        keys = set()
        for path in templates.rglob("*.html"):
            keys.update(match[1] for match in re.findall(r"{% tr (['\"])(.*?)\1 %}", path.read_text(encoding="utf-8")))
        self.assertFalse(keys.difference(TEXT))
        self.assertTrue(all(len(TEXT[key]) == 2 and all(TEXT[key]) for key in keys))

    def test_student_cannot_open_admin_or_edit_owner_permissions(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get("/admin/").status_code, 302)
        self.client.post(reverse("profile"), {"first_name": "Test", "last_name": "Student", "school": self.school.pk, "grade": 9, "role": "admin", "is_staff": "1", "is_superuser": "1"})
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, User.Role.STUDENT)
        self.assertFalse(self.student.is_staff)
        self.assertFalse(self.student.is_superuser)


class OwnerProvisioningTests(TestCase):
    def test_without_secret_no_owner_is_created(self):
        with patch.dict(os.environ, {"OLYMPIQ_ADMIN_BOOTSTRAP_PASSWORD": ""}):
            call_command("bootstrap_admin", stdout=StringIO())
        self.assertFalse(User.objects.exists())

    def test_owner_created_without_logging_secret_and_no_password_reset(self):
        password = "Test-owner-access-732!"
        output = StringIO()
        with patch.dict(os.environ, {"OLYMPIQ_ADMIN_BOOTSTRAP_PASSWORD": password, "OLYMPIQ_ADMIN_BOOTSTRAP_USERNAME": "owner_test"}):
            call_command("bootstrap_admin", stdout=output)
        owner = User.objects.get(username="owner_test")
        self.assertTrue(owner.is_staff and owner.is_superuser and owner.is_active)
        self.assertEqual(owner.role, User.Role.ADMIN)
        self.assertTrue(owner.check_password(password))
        self.assertNotIn(password, output.getvalue())
        with patch.dict(os.environ, {"OLYMPIQ_ADMIN_BOOTSTRAP_PASSWORD": "Different-temporary-password-9!", "OLYMPIQ_ADMIN_BOOTSTRAP_USERNAME": "owner_test"}):
            call_command("bootstrap_admin", stdout=output)
        owner.refresh_from_db()
        self.assertTrue(owner.check_password(password))

    def test_refuses_shared_names_weak_passwords_and_existing_student(self):
        for username, password in [("admin", "Long-enough-test-password-1!"), ("unique_owner", "123"), ("existing_student", "Long-enough-test-password-1!")]:
            if username == "existing_student":
                User.objects.create_user(username=username, password="existing-password")
            with patch.dict(os.environ, {"OLYMPIQ_ADMIN_BOOTSTRAP_PASSWORD": password, "OLYMPIQ_ADMIN_BOOTSTRAP_USERNAME": username}):
                with self.assertRaises(CommandError):
                    call_command("bootstrap_admin", stdout=StringIO())
        self.assertFalse(User.objects.filter(is_staff=True).exists())

    def test_demo_refresh_preserves_owner_and_human_edited_guides(self):
        with patch.dict(os.environ, {"OLYMPIQ_UX_DEMO": "true"}):
            call_command("prepare_ux_demo", stdout=StringIO())
            with patch.dict(os.environ, {"OLYMPIQ_ADMIN_BOOTSTRAP_PASSWORD": "Test-owner-access-732!", "OLYMPIQ_ADMIN_BOOTSTRAP_USERNAME": "owner_test"}):
                call_command("bootstrap_admin", stdout=StringIO())
            events = list(Olympiad.objects.filter(is_demo=True))
            self.assertEqual(len({event.description for event in events}), 24)
            self.assertTrue(all(event.participation_details and event.preparation and event.assessment for event in events))
            event = events[0]
            event.preparation = "Human-edited content"
            event.save(update_fields=["preparation"])
            dates = [item.starts_at for item in events]
            call_command("prepare_ux_demo", stdout=StringIO())
        event.refresh_from_db()
        self.assertEqual(event.preparation, "Human-edited content")
        self.assertEqual(dates, list(Olympiad.objects.filter(is_demo=True).values_list("starts_at", flat=True)))
        self.assertTrue(User.objects.get(username="owner_test").is_active)

    def test_enrichment_never_changes_official_event(self):
        event = Olympiad.objects.create(title="Official", subject="Math", description="Official description", organizer="School", is_demo=False, source_key="demo:1")
        self.assertEqual(enrich_demo_events(), 0)
        event.refresh_from_db()
        self.assertEqual(event.description, "Official description")
        self.assertEqual(event.preparation, "")
