"""Initialize a dedicated public UX sandbox without public staff passwords."""
import os
from io import StringIO

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test.utils import override_settings

from core.models import Olympiad, School, User
from core.demo_guides import enrich_demo_events


class Command(BaseCommand):
    help = "Initialize the dedicated OlympIQ UX demonstration database safely."

    @transaction.atomic
    def handle(self, *args, **options):
        if os.environ.get("OLYMPIQ_UX_DEMO", "").lower() != "true":
            raise CommandError("Only allowed in a dedicated OLYMPIQ_UX_DEMO=true sandbox.")
        demo_exists = Olympiad.objects.filter(is_demo=True).exists()
        if not demo_exists and (Olympiad.objects.exists() or User.objects.exists()):
            raise CommandError("Refusing to seed a populated non-demo database.")
        if not demo_exists:
            # This override is restricted to initialization; the web server remains DEBUG=false.
            with override_settings(DEBUG=True):
                call_command("seed_demo", stdout=StringIO())
        for username in ("admin", "teacher"):
            account = User.objects.filter(username=username).first()
            if account:
                account.set_unusable_password()
                account.is_active = False
                account.save(update_fields=["password", "is_active"])
        school = School.objects.get(name="Школа-лицей № 72", city="Астана")
        for username in ("ux01", "ux02", "ux03", "uxcheck"):
            account, created = User.objects.get_or_create(
                username=username,
                defaults={"role": User.Role.STUDENT, "grade": 9, "school": school,
                          "first_name": "UX", "last_name": username},
            )
            if created:
                account.set_password("Demo12345!")
                account.save(update_fields=["password"])
        changed = enrich_demo_events()
        call_command("bootstrap_admin", stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS(
            f"UX demo ready; {changed} sample guides enriched; shared staff accounts disabled."
        ))
