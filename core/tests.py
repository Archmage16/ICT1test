import json
import os
from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from .models import Olympiad, Registration, School, User


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
