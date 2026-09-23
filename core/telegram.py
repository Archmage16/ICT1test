"""Small Telegram Bot API client using Python's standard library."""
import json
import logging
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from .models import Registration, TelegramLink

logger = logging.getLogger(__name__)


def send_message(chat_id, text):
    token = settings.TELEGRAM_BOT_TOKEN
    if not token or not chat_id:
        return False
    payload = json.dumps({"chat_id": chat_id, "text": text, "disable_web_page_preview": True}).encode()
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status == 200 and json.loads(response.read()).get("ok", False)
    except (URLError, TimeoutError, ValueError) as exc:
        logger.warning("Telegram message was not delivered: %s", exc)
        return False


def send_to_user(user, text):
    try:
        link = user.telegram_link
    except TelegramLink.DoesNotExist:
        return False
    return send_message(link.chat_id, text)


def user_summary(chat_id, deadlines=False):
    try:
        link = TelegramLink.objects.select_related("user").get(chat_id=chat_id)
    except TelegramLink.DoesNotExist:
        return "Сначала подключите бота в личном кабинете OlympIQ: профиль → Telegram."
    now = timezone.now()
    qs = Registration.objects.filter(
        student=link.user,
        olympiad__is_published=True,
        olympiad__starts_at__gte=now,
    ).select_related("olympiad").order_by("olympiad__starts_at")
    if deadlines:
        qs = qs.filter(olympiad__registration_deadline__gte=now).order_by("olympiad__registration_deadline")
    rows = list(qs[:8])
    if not rows:
        return "Пока нет предстоящих олимпиад в вашем списке. Откройте каталог OlympIQ, чтобы найти подходящие."
    title = "Ваши ближайшие дедлайны:" if deadlines else "Ваши предстоящие олимпиады:"
    lines = [title]
    for registration in rows:
        item = registration.olympiad
        dt = item.registration_deadline if deadlines else item.starts_at
        label = "Дедлайн" if deadlines else "Начало"
        lines.append(f"• {item.title} — {label}: {timezone.localtime(dt).strftime('%d.%m.%Y %H:%M')} ({registration.get_status_display()})")
    return "\n".join(lines)
