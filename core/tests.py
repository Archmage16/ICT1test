import json
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from .models import Olympiad, Registration, School, User


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
