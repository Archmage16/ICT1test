from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import Registration, User
from .contact_validation import (
    EMAIL_DUPLICATE, EMAIL_ERROR, EMAIL_HELP, NAME_ERROR, NAME_HELP,
    PHONE_ERROR, PHONE_HELP, clean_person_name, clean_phone_number,
)
from .ui_text import translate


class ContactValidationMixin:
    """The same rules apply on sign-up and when editing a profile."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, autocomplete in (("first_name", "given-name"), ("last_name", "family-name"), ("patronymic", "additional-name")):
            field = self.fields[name]
            field.required = name != "patronymic"
            field.help_text = NAME_HELP
            field.error_messages["required"] = "Укажите имя." if name == "first_name" else "Укажите фамилию."
            field.widget.attrs.update({"autocomplete": autocomplete, "data-contact-name": "", "data-invalid-message": translate(NAME_ERROR)})
        self.fields["email"].required = True
        self.fields["email"].help_text = EMAIL_HELP
        self.fields["email"].error_messages.update({"required": "Укажите почту.", "invalid": EMAIL_ERROR})
        self.fields["email"].widget.attrs.update({"autocomplete": "email", "placeholder": "student@example.com", "data-contact-email": "", "data-invalid-message": translate(EMAIL_ERROR)})
        # Leave room for formatting; the stored canonical value is <= 16 chars.
        self.fields["phone"] = forms.CharField(
            label=self.fields["phone"].label, required=False, max_length=40, help_text=PHONE_HELP,
            widget=forms.TextInput(attrs={"type": "tel", "inputmode": "tel", "autocomplete": "tel", "placeholder": "+7 701 123 45 67", "data-contact-phone": "", "data-invalid-message": translate(PHONE_ERROR)}),
        )

    def clean_first_name(self):
        return clean_person_name(self.cleaned_data["first_name"])

    def clean_last_name(self):
        return clean_person_name(self.cleaned_data["last_name"])

    def clean_patronymic(self):
        return clean_person_name(self.cleaned_data.get("patronymic", ""))

    def clean_phone(self):
        return clean_phone_number(self.cleaned_data.get("phone", ""))

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if "." not in email.rsplit("@", 1)[1]:
            raise forms.ValidationError(EMAIL_ERROR, code="invalid")
        # Public account forms reject duplicates without altering old accounts.
        accounts = User.objects.filter(email__iexact=email)
        if self.instance.pk:
            accounts = accounts.exclude(pk=self.instance.pk)
        if accounts.exists():
            raise forms.ValidationError(EMAIL_DUPLICATE, code="duplicate_email")
        return email


class SignUpForm(ContactValidationMixin, UserCreationForm):
    class Meta:
        model = User
        fields = ("last_name", "first_name", "patronymic", "username", "email", "school", "grade", "phone", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["school"].required = True
        self.fields["grade"].required = True

    def clean(self):
        data = super().clean()
        grade = data.get("grade")
        if not data.get("school"):
            self.add_error("school", "Выберите школу.")
        if not grade:
            self.add_error("grade", "Укажите класс ученика.")
        if grade and not 1 <= grade <= 11:
            self.add_error("grade", "Класс должен быть от 1 до 11.")
        return data


class ProfileForm(ContactValidationMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "patronymic", "email", "school", "grade", "phone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.role != User.Role.STUDENT:
            self.fields.pop("school", None)
            self.fields.pop("grade", None)
        else:
            self.fields["school"].required = True
            self.fields["grade"].required = True

    def clean_grade(self):
        grade = self.cleaned_data.get("grade")
        if self.instance.role == User.Role.STUDENT and (not grade or not 1 <= grade <= 11):
            raise forms.ValidationError("Класс должен быть от 1 до 11.")
        return grade


class TeacherRegistrationForm(forms.Form):
    students = forms.ModelMultipleChoiceField(
        label="Ученики",
        queryset=User.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Выберите хотя бы одного ученика."},
    )
    note = forms.CharField(label="Комментарий", required=False, max_length=300)

    def __init__(self, *args, teacher=None, **kwargs):
        super().__init__(*args, **kwargs)
        if teacher and teacher.school_id:
            self.fields["students"].queryset = User.objects.filter(role=User.Role.STUDENT, school=teacher.school).order_by("last_name", "first_name")
