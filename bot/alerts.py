"""Telegram bildirimleri (opsiyonel).

Token/chat-id tanimli degilse sessizce loglayip gecer; asla exception
firlatmaz. Testlerde ag cagrisi yapilmaz.
"""

from __future__ import annotations

from bot.logger import get_logger
from config.settings import Settings

logger = get_logger()


def send_telegram_alert(settings: Settings, message: str) -> bool:
    """Telegram'a mesaj gonderir; yapilandirma yoksa no-op.

    Donus degeri: mesaj gonderilmeye calisildiysa True, atlandiysa False.
    """
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        logger.debug("Telegram yapilandirilmamis; bildirim atlandi: {}", message)
        return False

    try:
        import urllib.parse
        import urllib.request

        url = (
            f"https://api.telegram.org/bot{settings.telegram_bot_token}"
            "/sendMessage"
        )
        data = urllib.parse.urlencode(
            {"chat_id": settings.telegram_chat_id, "text": message}
        ).encode()
        with urllib.request.urlopen(url, data=data, timeout=10) as response:
            ok = response.status == 200
        logger.info("Telegram bildirimi gonderildi | ok={}", ok)
        return ok
    except Exception as exc:  # bildirim hatasi botu asla durdurmamali
        logger.error("Telegram bildirimi basarisiz: {}", exc)
        return False
