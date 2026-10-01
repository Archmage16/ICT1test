import json
import os
from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from .models import Olympiad, Registration, School, User
from .forms import ProfileForm, SignUpForm
from .contact_validation import EMAIL_DUPLICATE, EMAIL_ERROR, EMAIL_HELP, NAME_ERROR, NAME_HELP, PHONE_ERROR, PHONE_HELP
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
        self.client.post(reverse("profile"), {"first_name": "Test", "last_name": "Student", "email": "student@example.com", "school": self.school.pk, "grade": 9, "role": "admin", "is_staff": "1", "is_superuser": "1"})
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, User.Role.STUDENT)
        self.assertFalse(self.student.is_staff)
        self.assertFalse(self.student.is_superuser)


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class ContactValidationTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Contact test school", city="Астана")
        self.student = User.objects.create_user(
            username="contact_student", password="Test-contact-access-928!",
            first_name="Иван", last_name="Петров", email="existing@example.com",
            school=self.school, grade=9, phone="+77011234567",
        )

    def signup_data(self, **changes):
        data = {
            "first_name": "Әли", "last_name": "Омаров", "patronymic": "",
            "username": "contact_new_student", "email": "new.student@example.com",
            "school": self.school.pk, "grade": 9, "phone": "",
            "password1": "Test-new-student-821!", "password2": "Test-new-student-821!",
        }
        data.update(changes)
        return data

    def profile_data(self, **changes):
        data = {"first_name": "Иван", "last_name": "Петров", "patronymic": "", "email": self.student.email, "school": self.school.pk, "grade": 9, "phone": self.student.phone}
        data.update(changes)
        return data

    def test_names_and_email_are_required_but_phone_and_patronymic_are_optional(self):
        for form in (SignUpForm(self.signup_data(first_name="", last_name="", email="")), ProfileForm(self.profile_data(first_name="", last_name="", email=""), instance=self.student)):
            self.assertFalse(form.is_valid())
            for name in ("first_name", "last_name", "email"):
                self.assertIn(name, form.errors)
            self.assertNotIn("phone", form.errors)
            self.assertNotIn("patronymic", form.errors)

    def test_valid_multilingual_and_compound_names(self):
        for name in ("Әли", "Қасым-Жомарт", "Anne Marie", "O’Neill", "José", "Jose\u0301", "李", "अर्जुन"):
            with self.subTest(name=name):
                form = SignUpForm(self.signup_data(first_name=name, last_name=name, patronymic=name))
                self.assertTrue(form.is_valid(), form.errors)

    def test_invalid_names_rejected_in_each_name_field(self):
        for field in ("first_name", "last_name", "patronymic"):
            for value in ("Ivan123", "123", "<script>", "@Ivan", "-Ivan", "Ivan-", "O''Neill", "Ivan\nPetrov", "Ivan\tPetrov", "Иван😀", "Иван\u200b"):
                with self.subTest(field=field, value=value):
                    form = SignUpForm(self.signup_data(**{field: value}))
                    self.assertFalse(form.is_valid())
                    self.assertIn(field, form.errors)

    def test_name_spaces_and_unicode_are_normalized(self):
        form = SignUpForm(self.signup_data(first_name="  Anne   Marie  ", last_name="O’Neill", patronymic="Jose\u0301"))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["first_name"], "Anne Marie")
        self.assertEqual(form.cleaned_data["last_name"], "O'Neill")
        self.assertEqual(form.cleaned_data["patronymic"], "José")

    def test_kazakhstan_and_international_phone_formats(self):
        for value, expected in (
            ("+7 701 123 45 67", "+77011234567"), ("8 (701) 123-45-67", "+77011234567"),
            ("7 (701) 123-45-67", "+77011234567"), ("7011234567", "+77011234567"),
            ("+44 20 8366 1177", "+442083661177"), ("+1 650 253 0000", "+16502530000"),
            ("+7 (701) 123 - 45 - 67", "+77011234567"),
        ):
            with self.subTest(value=value):
                form = SignUpForm(self.signup_data(phone=value))
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data["phone"], expected)

    def test_invalid_phone_numbers_are_rejected(self):
        for value in ("123", "00000000000", "+7 000 000 00 00", "+99912345678", "+770112345678999", "call +77011234567", "+77011234567 ext 4", "+7+7011234567", "+7701abc4567", "++77011234567", "８７０１１２３４５６７"):
            with self.subTest(value=value):
                form = SignUpForm(self.signup_data(phone=value))
                self.assertFalse(form.is_valid())
                self.assertIn("phone", form.errors)

    def test_invalid_email_formats_are_rejected(self):
        for value in ("not-an-email", "name@", "@example.com", "a b@example.com", "a..b@example.com", "student@localhost", "a@example", "a@example..com", "a@example.com\nb@example.com"):
            with self.subTest(value=value):
                form = SignUpForm(self.signup_data(email=value))
                self.assertFalse(form.is_valid())
                self.assertIn("email", form.errors)

    def test_email_normalization_and_plus_addressing(self):
        form = SignUpForm(self.signup_data(email="  New.Student+ux@Example.COM  "))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["email"], "new.student+ux@example.com")

    def test_duplicate_email_is_case_insensitive(self):
        form = SignUpForm(self.signup_data(email="  EXISTING@EXAMPLE.COM  "))
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["email"], [EMAIL_DUPLICATE])

    def test_profile_keeps_own_email_but_rejects_another_accounts_email(self):
        User.objects.create_user(username="contact_other", email="another@example.com")
        form = ProfileForm(self.profile_data(email="EXISTING@EXAMPLE.COM"), instance=self.student)
        self.assertTrue(form.is_valid(), form.errors)
        form = ProfileForm(self.profile_data(email="ANOTHER@example.com"), instance=self.student)
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_signup_saves_normalized_contacts(self):
        response = self.client.post(reverse("signup"), self.signup_data(first_name="  Әли  ", email="NEW@EXAMPLE.COM", phone="8 (701) 123-45-67"))
        self.assertRedirects(response, reverse("dashboard"))
        user = User.objects.get(username="contact_new_student")
        self.assertEqual((user.first_name, user.email, user.phone), ("Әли", "new@example.com", "+77011234567"))
        self.assertFalse(user.is_staff or user.is_superuser)

    def test_invalid_signup_post_cannot_bypass_browser_checks(self):
        response = self.client.post(reverse("signup"), self.signup_data(first_name="Name123", phone="123", email="broken"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="contact_new_student").exists())
        for field in ("first_name", "phone", "email"):
            self.assertIn(field, response.context["form"].errors)

    def test_profile_rejects_invalid_values_without_changing_saved_data(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse("profile"), self.profile_data(first_name="Иван123", phone="000", email="bad"))
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual((self.student.first_name, self.student.email, self.student.phone), ("Иван", "existing@example.com", "+77011234567"))

    def test_profile_saves_valid_normalized_values(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse("profile"), self.profile_data(first_name="Қасым-Жомарт", email="EXISTING@EXAMPLE.COM", phone="+44 20 8366 1177"))
        self.assertRedirects(response, reverse("dashboard"))
        self.student.refresh_from_db()
        self.assertEqual((self.student.first_name, self.student.email, self.student.phone), ("Қасым-Жомарт", "existing@example.com", "+442083661177"))

    def test_teacher_profile_uses_same_contact_rules_without_school_and_grade(self):
        self.student.role = User.Role.TEACHER
        self.student.save(update_fields=["role"])
        form = ProfileForm(self.profile_data(phone="123"), instance=self.student)
        self.assertNotIn("school", form.fields)
        self.assertNotIn("grade", form.fields)
        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_existing_incomplete_account_can_login_and_get_profile(self):
        self.student.first_name = ""
        self.student.email = ""
        self.student.save(update_fields=["first_name", "email"])
        self.assertTrue(self.client.login(username="contact_student", password="Test-contact-access-928!"))
        self.assertEqual(self.client.get(reverse("profile")).status_code, 200)

    def test_form_hints_and_invalid_message_are_translated_in_all_languages(self):
        from django.utils.translation import override
        for code in ("ru", "en", "kk"):
            with override(code):
                form = SignUpForm()
                self.assertTrue(form.fields["first_name"].widget.attrs["data-invalid-message"])
                if code != "ru":
                    self.assertNotEqual(form.fields["first_name"].widget.attrs["data-invalid-message"], NAME_ERROR)
        for message in (NAME_ERROR, PHONE_ERROR, EMAIL_ERROR, EMAIL_DUPLICATE, NAME_HELP, PHONE_HELP, EMAIL_HELP, "Укажите имя.", "Укажите фамилию.", "Укажите почту."):
            self.assertIn(message, TEXT)
            self.assertTrue(all(TEXT[message]))

    def test_rendered_errors_are_linked_to_inputs_and_preserve_other_fields(self):
        response = self.client.post(reverse("signup"), self.signup_data(first_name="Invalid123", phone="123"))
        self.assertContains(response, 'id="id_first_name_error"')
        self.assertContains(response, 'id="id_first_name_helptext"')
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, 'value="Омаров"')
        self.assertContains(response, "data-contact-validation")
        self.assertContains(response, "js/contact-validation.js")


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


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class RegistrationApprovalTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser(username="approval_owner", password="Test-approval-owner-782!", role=User.Role.ADMIN)
        self.student = User.objects.create_user(username="approval_student", grade=9)
        self.other_student = User.objects.create_user(username="approval_other", grade=9)
        self.event = Olympiad.objects.create(title="Approval test", subject="Math", description="Test", organizer="School")
        self.selected = Registration.objects.create(student=self.student, olympiad=self.event)
        self.unselected = Registration.objects.create(student=self.other_student, olympiad=self.event)
        self.url = reverse("admin:core_registration_changelist")
        self.action = {"action": "approve", "index": "0", "select_across": "0", "_selected_action": [str(self.selected.pk)]}

    def assert_pending(self):
        self.selected.refresh_from_db()
        self.unselected.refresh_from_db()
        self.assertEqual(self.selected.status, Registration.Status.PENDING)
        self.assertEqual(self.unselected.status, Registration.Status.PENDING)

    def test_dashboard_links_directly_to_pending_applications_and_explains_approval(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, self.url + "?status__exact=pending")
        self.assertContains(response, "Как подтвердить заявку ученика")
        self.assertContains(response, "Подтвердить выбранные регистрации")
        self.assertContains(response, "Заявки на проверке (2)")
        self.assert_pending()

    def test_owner_approves_only_selected_application_and_student_sees_status(self):
        self.client.force_login(self.owner)
        response = self.client.post(self.url, self.action, follow=True)
        self.assertContains(response, "Подтверждено заявок: 1.")
        self.selected.refresh_from_db()
        self.unselected.refresh_from_db()
        self.assertEqual(self.selected.status, Registration.Status.APPROVED)
        self.assertEqual(self.unselected.status, Registration.Status.PENDING)
        self.client.force_login(self.student)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, 'class="pill approved"')
        self.assertContains(response, "Подтверждена")
        self.assertNotContains(response, "approval_other")

    def test_get_requests_do_not_approve_anything(self):
        self.client.force_login(self.owner)
        self.client.get(self.url, self.action)
        self.assert_pending()

    def test_anonymous_and_student_cannot_approve(self):
        self.assertEqual(self.client.post(self.url, self.action).status_code, 302)
        self.client.force_login(self.student)
        self.assertEqual(self.client.post(self.url, self.action).status_code, 302)
        self.assert_pending()
        self.assertNotContains(self.client.get(reverse("dashboard")), self.url)

    def test_view_only_staff_cannot_use_approval_action(self):
        viewer = User.objects.create_user(username="approval_viewer", is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename="view_registration"))
        self.client.force_login(viewer)
        self.assertNotContains(self.client.get(self.url), '<option value="approve"')
        self.client.post(self.url, self.action)
        self.assert_pending()

    def test_admin_action_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(self.url, self.action).status_code, 403)
        self.assert_pending()


class ThemeContrastTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = (Path(__file__).resolve().parent.parent / "static/css/app.css").read_text(encoding="utf-8")
        blocks = {"light": re.findall(r":root\s*\{([^}]+)\}", cls.css)[-1],
                  "dark": re.findall(r"html\[data-theme=dark\]\s*\{([^}]+)\}", cls.css)[-1]}
        cls.palettes = {theme: dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", block)) for theme, block in blocks.items()}

    @staticmethod
    def contrast(first, second):
        def luminance(colour):
            channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
            return sum(c * weight for c, weight in zip(linear, (.2126, .7152, .0722)))
        light, dark = sorted((luminance(first), luminance(second)), reverse=True)
        return (light + .05) / (dark + .05)

    def test_body_secondary_and_primary_button_text_have_readable_contrast(self):
        pairs = [("ink", "page"), ("ink", "surface"), ("muted", "surface"),
                 ("muted", "hero-bg"), ("muted", "soft"), ("blue", "surface"),
                 ("primary-ink", "blue"), ("primary-ink", "blue2"), ("selection-ink", "selection-bg")]
        for theme, colours in self.palettes.items():
            for text, background in pairs:
                with self.subTest(theme=theme, text=text, background=background):
                    self.assertGreaterEqual(self.contrast(colours[text], colours[background]), 4.5)

    def test_status_and_error_text_have_readable_contrast(self):
        for theme, colours in self.palettes.items():
            for status in ("success", "pending", "error"):
                with self.subTest(theme=theme, status=status):
                    self.assertGreaterEqual(self.contrast(colours[status + "-ink"], colours[status + "-bg"]), 4.5)

    def test_native_control_boundaries_remain_visible_in_both_themes(self):
        for theme, colours in self.palettes.items():
            with self.subTest(theme=theme):
                self.assertGreaterEqual(self.contrast(colours["control-border"], colours["surface"]), 3)

    def test_final_mobile_navigation_and_native_controls_use_theme_tokens(self):
        last_nav = re.findall(r"\.nav-links a\s*\{([^}]+)\}", self.css)[-1]
        self.assertIn("background:var(--surface)", last_nav)
        self.assertIn("color:var(--ink)", last_nav)
        self.assertIn(".nav-actions .btn-primary:hover{color:var(--primary-ink)}", self.css)
        self.assertIn("select option,select optgroup{background:var(--surface);color:var(--ink)}", self.css)
        self.assertIn("input::placeholder,textarea::placeholder{color:var(--muted);opacity:1}", self.css)
        self.assertIn(".form-card ul.errorlist,.errorlist{color:var(--error-ink)}", self.css)

    def test_narrow_calendar_places_actions_below_event_details(self):
        self.assertIn(".agenda-item{display:grid;grid-template-columns:52px minmax(0,1fr)", self.css)
        self.assertIn(".agenda-item>.btn,.agenda-item>.pill{grid-column:2;justify-self:start}", self.css)
