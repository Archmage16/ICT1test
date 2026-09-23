from django.test import TestCase
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
            organizer="Организатор", format=Olympiad.Format.ONLINE,
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
