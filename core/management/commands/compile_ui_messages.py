"""Build the small supplemental Django catalogue without system gettext tools."""
import gettext
import io
import json
import struct

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Compile the supplemental Kazakh authentication/form translations."

    def handle(self, *args, **options):
        folder = settings.BASE_DIR / "locale" / "kk" / "LC_MESSAGES"
        entries = json.loads((folder / "django.json").read_text(encoding="utf-8"))
        # GNU MO: header, original-string table, translation table, string pools.
        pairs = sorted((key.encode("utf-8"), value.encode("utf-8")) for key, value in entries.items())
        size = len(pairs)
        originals = b""
        translated = b""
        first_table = []
        second_table = []
        start = 28 + 16 * size
        for key, value in pairs:
            first_table.extend((len(key), start + len(originals)))
            originals += key + b"\0"
            second_table.extend((len(value), len(translated)))
            translated += value + b"\0"
        for index in range(1, len(second_table), 2):
            second_table[index] += start + len(originals)
        header = struct.pack("<7I", 0x950412DE, 0, size, 28, 28 + 8 * size, 0, 0)
        tables = struct.pack(f"<{4 * size}I", *(first_table + second_table))
        compiled = header + tables + originals + translated
        # Parse with the consumer before writing a build artifact.
        catalogue = gettext.GNUTranslations(io.BytesIO(compiled))
        if catalogue.gettext("email address") != entries["email address"]:
            raise ValueError("Compiled translation verification failed.")
        (folder / "django.mo").write_bytes(compiled)
        self.stdout.write(self.style.SUCCESS(f"Compiled {size - 1} supplemental Kazakh translations."))
