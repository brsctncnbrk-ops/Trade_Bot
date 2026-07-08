"""Telegram bildirimleri (geriye donuk uyumluluk wrapper'i).

Yeni uygulama `bot.notifier.TelegramNotifier` kullanir. Bu dosya eski
`send_telegram_alert(settings, message)` cagri noktalarini kirmamak icin kalir.
"""

from __future__ import annotations

from bot.notifier import NotificationEvent, TelegramNotifier
from config.settings import Settings


def send_telegram_alert(settings: Settings, message: str) -> bool:
    """Basit metni Telegram'a gonderir; config yoksa no-op."""
    notifier = TelegramNotifier(settings)
    return notifier.send(
        NotificationEvent(
            event_type="API ERROR" if "error" in message.lower() else "ORDER CREATED",
            symbol="-",
            mode=settings.mode,
            reason=message,
        )
    )
