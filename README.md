# OlympIQ

OlympIQ is a responsive Django platform for school olympiads in Kazakhstan. It brings discovery, registration, school coordination, schedules, results, and optional Telegram updates into one place.

## Features

- Public catalogue with search and filters for subject, format, grade, and registration availability.
- Olympiad detail pages with eligibility, registration deadline, location, level, rules, and remaining seats.
- Student accounts with self-registration, a personal calendar, participation history, and private published results.
- Teacher accounts managed by an administrator; teachers can select multiple students from their own school for registration.
- Staff-only admin console for schools, users, olympiads, registrations, news, and result publication; CSV export for registrations.
- Optional Telegram connection, `/my` and `/deadlines` commands, and messages after registration/result publication.
- Import of current olympiad announcements from the public Daryn.kz WordPress REST API. Imported records are private drafts until an administrator verifies the event dates, deadline, and format.
- SQLite for local use; configurable PostgreSQL for deployment. Environment-based secrets and production security settings.

## Local setup

Requires Python 3.12+.

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/. The public catalogue and calendar work without an account. Students can self-register. Create teacher accounts through `/admin/` and assign them to a school; public signup intentionally cannot grant teacher or administrator privileges.

For sample data in local development only:

```powershell
python manage.py seed_demo
```

To sync recent official announcements from the Daryn.kz API into the local database:

```powershell
python manage.py import_daryn_olympiads
```

The command reads `https://daryn.kz/wp-json/wp/v2/posts`, upserts by the source post ID, and keeps imported records unpublished for review. Use `--days 30` or `--max-pages 1` to narrow the sync. The API publishes news as well as event information, so review each source page and fill in confirmed dates, eligibility, and registration details in `/admin/` before publishing. This importer does not access participant accounts or registration data.

The demo command creates `admin`, `teacher`, and `student` accounts with a shared sample password. Never run it on a public deployment.

## Telegram bot setup (optional)

1. Create a bot with BotFather. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_BOT_USERNAME` in `.env`.
2. Set a long random `TELEGRAM_WEBHOOK_SECRET` and expose the site over HTTPS.
3. Register the webhook URL `https://YOUR_HOST/integrations/telegram/webhook/`, passing the secret as Telegram's `secret_token` parameter. Keep the token secret; never commit `.env`.
4. A signed-in user connects Telegram from their dashboard. The one-time `/start` code expires after 15 minutes. The bot supports `/my`, `/deadlines`, and `/help`.
5. Schedule `python manage.py send_telegram_reminders` once each morning (for example, cron `0 8 * * *`) to send idempotent reminders about deadlines closing within 24 hours and olympiads starting tomorrow.

Telegram is opt-in. Messages are sent only to a chat explicitly connected by the user; disabling or removing the bot stops delivery.

## Deployment configuration

Set `DJANGO_DEBUG=false`, a unique `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, and the `DB_*` values shown in `.env.example`. For PostgreSQL set `DB_ENGINE=django.db.backends.postgresql`. Run migrations and `collectstatic` during release. TLS termination must send `X-Forwarded-Proto: https`.

## Roles and data access

- Anonymous visitors see published olympiads and announcements.
- Students see their own registrations and published results. Result scores are not exposed before publication or to other students.
- Teachers can view registrations only for students associated with their school.
- Staff can administer all platform data. Public signup always creates a student account.

## Assignment scope

This repository implements the working MVP described by the technical specification: student, teacher, and administrator flows, catalogue, registration, calendar, results, notifications, and a Telegram integration. Demo content is illustrative and is not evidence of real olympiad availability.
