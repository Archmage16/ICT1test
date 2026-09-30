"""One-time owner provisioning; no shared password or public recovery endpoint."""
import os

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import User


class Command(BaseCommand):
    help = "Create an owner using a temporary protected deployment environment variable."

    @transaction.atomic
    def handle(self, *args, **options):
        password = os.environ.get("OLYMPIQ_ADMIN_BOOTSTRAP_PASSWORD", "")
        if not password:
            self.stdout.write("Owner provisioning skipped: no temporary password configured.")
            return
        username = os.environ.get("OLYMPIQ_ADMIN_BOOTSTRAP_USERNAME", "olympiq_owner")
        if username in {"admin", "teacher", "student", "ux01", "ux02", "ux03", "uxcheck"}:
            raise CommandError("Use a separate owner account, not a shared demo account.")
        account = User.objects.filter(username=username).first()
        if account:
            if not (account.is_active and account.is_staff and account.is_superuser and account.role == User.Role.ADMIN):
                raise CommandError("Owner name already belongs to a different account; refusing to elevate it.")
            self.stdout.write("Owner already exists; credentials were not changed.")
            return
        account = User(username=username, role=User.Role.ADMIN, is_active=True, is_staff=True, is_superuser=True)
        try:
            validate_password(password, account)
        except ValidationError:
            raise CommandError("The owner password does not meet password security requirements.") from None
        account.set_password(password)
        account.save()
        self.stdout.write(self.style.SUCCESS("Owner created. Remove the temporary provisioning variable."))
