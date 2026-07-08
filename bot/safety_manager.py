"""Circuit breaker / acil durum kilidi.

SafetyManager yeni emir acilmadan once ve kritik hata anlarinda calisir.
Trading halt durumunda:
- yeni emir acilmaz,
- acik limit emirleri iptal edilmeye calisilir,
- state TRADING_HALTED olarak kaydedilir,
- log olusturulur.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from bot.logger import get_logger
from bot.state import BotState, OpenOrder
from config.settings import Settings

logger = get_logger()


@dataclass
class SafetyDecision:
    halted: bool
    reason: str = ""


class SafetyManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def ensure_can_trade(self, state: BotState) -> SafetyDecision:
        if state.trading_status == "TRADING_HALTED":
            return SafetyDecision(True, state.halt_reason or "trading_halted")
        return SafetyDecision(False, "")

    def evaluate(self, state: BotState) -> SafetyDecision:
        """Circuit breaker kosullarini degerlendirir."""
        existing = self.ensure_can_trade(state)
        if existing.halted:
            return existing

        if state.consecutive_losses >= 3:
            return self.halt(state, "consecutive_losses>=3")

        hourly_limit = self.settings.initial_balance * self.settings.max_hourly_loss
        if state.hourly_realized_pnl <= -hourly_limit:
            return self.halt(state, "hourly_loss_limit")

        daily_limit = self.settings.initial_balance * self.settings.max_daily_loss
        if state.daily_realized_pnl <= -daily_limit:
            return self.halt(state, "daily_loss_limit")

        if state.api_error_count >= self.settings.max_api_errors:
            return self.halt(state, "api_errors>=max_api_errors")

        if not state.exchange_connected:
            return self.halt(state, "exchange_disconnected")

        return SafetyDecision(False, "")

    def check_endpoint(self, state: BotState, urls) -> SafetyDecision:
        urls_text = str(urls)
        if "testnet.binance.vision" not in urls_text:
            return self.halt(state, "production_endpoint_or_unknown_endpoint")
        if "https://api.binance.com/api" in urls_text:
            return self.halt(state, "production_endpoint_detected")
        return SafetyDecision(False, "")

    def record_api_error(
        self,
        state: BotState,
        exc: Exception,
        cancel_open_order: Optional[Callable[[OpenOrder], dict]] = None,
    ) -> SafetyDecision:
        state.api_error_count += 1
        logger.error("API ERROR | count={} | {}", state.api_error_count, exc)
        if state.api_error_count >= self.settings.max_api_errors:
            return self.halt(state, "api_errors>=max_api_errors", cancel_open_order)
        return SafetyDecision(False, "")

    def record_exchange_disconnected(
        self,
        state: BotState,
        cancel_open_order: Optional[Callable[[OpenOrder], dict]] = None,
    ) -> SafetyDecision:
        state.exchange_connected = False
        return self.halt(state, "exchange_disconnected", cancel_open_order)

    def record_unexpected_exception(
        self,
        state: BotState,
        exc: Exception,
        cancel_open_order: Optional[Callable[[OpenOrder], dict]] = None,
    ) -> SafetyDecision:
        logger.exception("UNEXPECTED EXCEPTION | {}", exc)
        return self.halt(state, f"unexpected_exception:{type(exc).__name__}", cancel_open_order)

    def halt(
        self,
        state: BotState,
        reason: str,
        cancel_open_order: Optional[Callable[[OpenOrder], dict]] = None,
    ) -> SafetyDecision:
        state.trading_status = "TRADING_HALTED"
        state.halt_reason = reason
        state.halted_at = self._now_iso()
        logger.critical("TRADING HALTED | reason={}", reason)

        if cancel_open_order is not None:
            for symbol, order in list(state.open_orders.items()):
                try:
                    result = cancel_open_order(order)
                    status = result.get("status") if isinstance(result, dict) else "canceled"
                    filled = float(result.get("filled") or 0.0) if isinstance(result, dict) else 0.0
                    state.update_order(
                        symbol,
                        status=status or "canceled",
                        filled=filled,
                        updated_at=self._now_iso(),
                    )
                    if filled == 0.0:
                        state.remove_order(symbol)
                    logger.info("ORDER CANCELLED | {} | id={} | halt", symbol, order.id)
                except Exception as exc:  # Halt path must not raise before state is saved.
                    logger.error("ORDER CANCEL FAILED | {} | id={} | {}", symbol, order.id, exc)
        return SafetyDecision(True, reason)
