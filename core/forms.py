from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import Registration, User


class SignUpForm(UserCreationForm):
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


class ProfileForm(forms.ModelForm):
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
