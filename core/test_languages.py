import os
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.html import escape
from django.utils.translation import override

from .admin import RegistrationAdmin
from .models import Olympiad, Registration, School, User
from .ui_text import TEXT, translate


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class CompleteLanguageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with patch.dict(os.environ, {"OLYMPIQ_UX_DEMO": "true"}):
            call_command("prepare_ux_demo", stdout=StringIO())
        cls.student = User.objects.get(username="uxcheck")
        cls.owner = User.objects.create(username="language_owner", is_superuser=True, is_staff=True, role=User.Role.ADMIN)
        cls.teacher = User.objects.create(username="language_teacher", role=User.Role.TEACHER, school=cls.student.school)
        cls.event = Olympiad.objects.get(source_key="demo:1")
        Registration.objects.create(student=cls.student, olympiad=cls.event)

    def switch(self, language, next_url="/"):
        response = self.client.post(reverse("set_language"), {"language": language, "next": next_url})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, next_url)
        self.assertEqual(self.client.cookies["olympiq_language"].value, language)

    def test_every_demo_title_and_full_guide_translates_on_detail_pages(self):
        for language in ("ru", "en", "kk"):
            self.switch(language)
            for event in Olympiad.objects.filter(is_demo=True):
                with self.subTest(language=language, event=event.source_key), override(language):
                    response = self.client.get(event.get_absolute_url())
                    for field in ("title", "subject", "description", "organizer", "participation_details", "preparation", "assessment"):
                        source = getattr(event, field)
                        self.assertIn(source, TEXT)
                        self.assertContains(response, escape(translate(source)))
                    self.assertContains(response, "<h1>" + translate(event.title) + "</h1>", html=True)

    def test_public_pages_and_all_three_role_dashboards_translate_titles(self):
        for language in ("en", "kk"):
            self.switch(language)
            with override(language):
                for url in (reverse("home"), reverse("olympiad_list"), reverse("calendar")):
                    response = self.client.get(url)
                    self.assertContains(response, translate(self.event.title))
                    self.assertNotContains(response, self.event.title)
                for user in (self.student, self.teacher, self.owner):
                    self.client.force_login(user)
                    self.assertContains(self.client.get(reverse("dashboard")), translate(self.event.title))
                    self.client.logout()

    def test_school_and_form_labels_use_the_selected_language(self):
        for language in ("ru", "en", "kk"):
            self.switch(language)
            with override(language):
                response = self.client.get(reverse("signup"))
                self.assertContains(response, '<label for="id_school">' + translate("Школа") + ' *</label>', html=True)
                self.assertContains(response, translate("Школа-лицей № 72"))
                self.assertContains(response, translate("Астана"))
                self.client.force_login(self.student)
                response = self.client.get(reverse("profile"))
                self.assertContains(response, translate("Школа-лицей № 72"))
                self.assertContains(response, translate("Отчество"))
                self.client.logout()

    def test_name_phone_email_validation_messages_match_selected_language(self):
        for language in ("en", "kk"):
            self.switch(language)
            with override(language):
                response = self.client.post(reverse("signup"), {"first_name": "123", "last_name": "456", "email": "invalid", "phone": "abc"})
                for source in ("Используйте только буквы, пробелы, дефис или апостроф между частями имени.", "Введите корректную почту, например student@example.com.", "Введите корректный телефон: +7 701 123 45 67 или номер другой страны с кодом +."):
                    self.assertContains(response, escape(translate(source)))
                    self.assertNotContains(response, source)

    def test_kazakh_builtin_auth_labels_password_hints_and_login_errors_do_not_fall_back_to_russian(self):
        self.switch("kk")
        response = self.client.get(reverse("signup"))
        self.assertContains(response, "Электрондық пошта")
        self.assertContains(response, "Құпия сөзіңіз кемінде 10 таңбадан тұруы керек.")
        self.assertContains(response, "Растау үшін сол құпия сөзді қайта енгізіңіз.")
        self.assertNotContains(response, "Пароль не должен")
        self.assertNotContains(response, "Обязательное поле")
        self.assertNotContains(response, "Адрес электронной почты")
        with override("kk"):
            form = AuthenticationForm(data={"username": "missing_language_user", "password": "invalid"})
            self.assertFalse(form.is_valid())
            self.assertIn("Бас және кіші әріптерді ескеріңіз", str(form.non_field_errors()))
            password = PasswordChangeForm(self.student)
            self.assertEqual(str(password.fields["old_password"].label), "Қазіргі құпия сөз")
            self.assertIn("Құпия сөзіңіз кемінде 10", str(password.fields["new_password1"].help_text))

    def test_calendar_city_and_online_labels_are_translated(self):
        for language in ("en", "kk"):
            self.switch(language)
            with override(language):
                response = self.client.get(reverse("calendar"))
                self.assertContains(response, translate("Астана"))
                self.assertContains(response, translate("Онлайн"))
                if language == "en":
                    self.assertNotContains(response, "Онлайн")

    def test_translated_search_and_combined_filters_find_the_same_records(self):
        for language, query in (("en", "National Computer Science"), ("kk", "Информатикадан республикалық"), ("ru", "Республиканская олимпиада по информатике")):
            self.switch(language)
            response = self.client.get(reverse("olympiad_list"), {"q": query, "subject": "Информатика", "grade": "9", "format": "offline", "open": "1"})
            self.assertQuerySetEqual(response.context["olympiads"], [self.event], ordered=False)
            self.assertTrue(response.context["open_only"])
            self.assertEqual(response.context["selected_subject"], "Информатика")
        self.assertFalse(self.client.get(reverse("olympiad_list"), {"q": "National Computer Science", "grade": "5"}).context["olympiads"].exists())
        self.assertGreater(self.client.get(reverse("olympiad_list"), {"type": "hackathon"}).context["olympiads"].count(), 0)

    def test_switch_preserves_filters_and_translated_city_search_works(self):
        next_url = reverse("olympiad_list") + "?grade=9&format=online&open=1"
        self.switch("kk", next_url)
        response = self.client.get(next_url)
        self.assertEqual(response.context["selected_grade"], "9")
        self.assertEqual(response.context["selected_format"], "online")
        self.switch("en")
        events = self.client.get(reverse("olympiad_list"), {"q": "Astana"}).context["olympiads"]
        self.assertTrue(events.exists())
        self.assertTrue(all(event.city == "Астана" for event in events))

    def test_admin_labels_action_and_csv_follow_language_without_changing_records(self):
        self.client.force_login(self.owner)
        for language in ("en", "kk"):
            self.switch(language)
            with override(language):
                response = self.client.get(reverse("admin:core_registration_changelist"))
                self.assertContains(response, translate("Подтвердить выбранные регистрации"))
                self.assertContains(response, translate("OlimpIQ — управление платформой"))
                self.assertContains(response, translate("Статус"))
                csv = self.client.get(reverse("export_registrations")).content.decode("utf-8-sig")
                self.assertIn(translate(self.event.title), csv)
                self.assertIn(translate("На проверке"), csv)
        self.assertEqual(Registration.objects.get(student=self.student).status, "pending")
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, "Республиканская олимпиада по информатике")

    def test_language_switch_is_immediate_and_has_no_js_fallback(self):
        javascript = (Path(__file__).resolve().parent.parent / "static/js/preferences.js").read_text(encoding="utf-8")
        self.assertIn("language.addEventListener('change', () => language.form.requestSubmit())", javascript)
        self.assertContains(self.client.get(reverse("home")), '<button type="submit" class="btn btn-ghost">Применить</button>', html=True)

    def test_unknown_author_text_and_personal_names_are_not_rewritten(self):
        for language in ("ru", "en", "kk"):
            with override(language):
                self.assertEqual(translate("Сергей Иванов"), "Сергей Иванов")
                self.assertEqual(translate("Текст нового организатора"), "Текст нового организатора")
