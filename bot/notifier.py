"""Telegram notification system for Trade_Bot.

Notifications are best-effort: missing config or Telegram/network failures never
stop trading logic. Secrets are never logged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Callable, Optional
import urllib.parse
import urllib.request

from bot.logger import get_logger
from config.settings import Settings

logger = get_logger()

NOTIFIABLE_EVENTS = {
    "ENTRY",
    "EXIT",
    "ORDER CREATED",
    "ORDER FILLED",
    "ORDER CANCELLED",
    "STOP LOSS",
    "TAKE PROFIT",
    "BREAK EVEN ACTIVATED",
    "TRAILING STOP ACTIVATED",
    "TRAILING STOP UPDATED",
    "RISK BLOCKED",
    "FILTER BLOCKED",
    "DAILY LIMIT REACHED",
    "TRADING HALTED",
    "API ERROR",
    "DAILY REPORT",
}


@dataclass
class NotificationEvent:
    event_type: str
    symbol: str = "-"
    mode: str = "-"
    price: Optional[float] = None
    quantity: Optional[float] = None
    pnl: Optional[float] = None
    reason: str = ""
    timestamp: Optional[str] = None


class TelegramNotifier:
    def __init__(
        self,
        settings: Settings,
        transport: Optional[Callable[[str, str, str], bool]] = None,
        now_fn: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings
        self.transport = transport or self._send_http
        self.now_fn = now_fn
        self._last_sent_at: dict[tuple[str, str], float] = {}

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.telegram_notifications_enabled
            and self.settings.telegram_bot_token
            and self.settings.telegram_chat_id
        )

    def send(self, event: NotificationEvent) -> bool:
        if not self.enabled:
            logger.debug("Telegram notification skipped: disabled or unconfigured")
            return False

        event_type = event.event_type.upper()
        if event_type not in NOTIFIABLE_EVENTS:
            logger.debug("Telegram notification skipped: unsupported event {}", event.event_type)
            return False

        key = (event_type, event.symbol or "-")
        now = self.now_fn()
        cooldown = float(self.settings.notification_cooldown_seconds)
        last_sent = self._last_sent_at.get(key)
        if last_sent is not None and now - last_sent < cooldown:
            logger.debug("Telegram notification skipped by cooldown | event={} | symbol={}", event_type, event.symbol)
            return False

        message = self.format_message(event)
        try:
            ok = bool(
                self.transport(
                    self.settings.telegram_bot_token,
                    self.settings.telegram_chat_id,
                    message,
                )
            )
            if ok:
                self._last_sent_at[key] = now
                logger.info("Telegram notification sent | event={} | symbol={}", event_type, event.symbol)
            return ok
        except Exception as exc:
            logger.error(
                "Telegram notification failed | event={} | symbol={} | error={}",
                event_type,
                event.symbol,
                type(exc).__name__,
            )
            return False

    def format_message(self, event: NotificationEvent) -> str:
        timestamp = event.timestamp or datetime.now(timezone.utc).isoformat()
        lines = [
            f"Event: {event.event_type.upper()}",
            f"Symbol: {event.symbol}",
            f"Mode: {event.mode}",
            f"Time: {timestamp}",
        ]
        if event.price is not None:
            lines.append(f"Price: {event.price}")
        if event.quantity is not None:
            lines.append(f"Quantity: {event.quantity}")
        if event.pnl is not None:
            lines.append(f"PnL: {event.pnl}")
        if event.reason:
            lines.append(f"Reason: {event.reason}")
        return "\n".join(lines)

    @staticmethod
    def _send_http(token: str, chat_id: str, text: str) -> bool:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
        with urllib.request.urlopen(url, data=data, timeout=10) as response:
            return response.status == 200


def send_daily_report(
    notifier: TelegramNotifier,
    mode: str,
    total_trades: int,
    win_rate: float,
    pnl: float,
    profit_factor: float,
    max_drawdown: float,
    sharpe: float,
    expectancy: float,
    average_win: float,
    average_loss: float,
    timestamp: Optional[str] = None,
) -> bool:
    if not notifier.settings.telegram_daily_report_enabled:
        logger.debug("Daily report notification skipped: disabled")
        return False
    reason = "\n".join(
        [
            f"Total trades: {total_trades}",
            f"Win rate: {win_rate}",
            f"PnL: {pnl}",
            f"Profit Factor: {profit_factor}",
            f"Max Drawdown: {max_drawdown}",
            f"Sharpe: {sharpe}",
            f"Expectancy: {expectancy}",
            f"Average Win: {average_win}",
            f"Average Loss: {average_loss}",
        ]
    )
    return notifier.send(
        NotificationEvent(
            event_type="DAILY REPORT",
            symbol="ALL",
            mode=mode,
            pnl=pnl,
            reason=reason,
            timestamp=timestamp,
        )
    )
