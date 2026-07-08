"""Pre-trade market condition filters.

The filters are pure/read-only: they never create/cancel orders. They decide
whether a BUY/SELL signal is allowed to proceed to RiskManager/ExecutionEngine.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional

import pandas as pd

from bot.logger import get_logger
from config.settings import Settings

logger = get_logger()


@dataclass
class FilterDecision:
    passed: bool
    reason: str
    symbol: str
    value: Optional[float] = None
    threshold: Optional[float] = None
    details: str = ""
    skipped: bool = False

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "symbol": self.symbol,
            "value": self.value,
            "threshold": self.threshold,
            "details": self.details,
            "skipped": self.skipped,
        }


class TradeFilterManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def evaluate(
        self,
        symbol: str,
        side: str,
        df: pd.DataFrame,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
    ) -> FilterDecision:
        s = self.settings
        if not s.enable_trade_filters:
            decision = FilterDecision(True, "FILTER PASSED", symbol, skipped=True, details="filters disabled")
            self._log_pass(decision)
            return decision

        if df is None or df.empty:
            return self._block(symbol, "FILTER BLOCKED", None, None, "market data missing")
        row = df.iloc[-1]
        close = float(row["close"])

        spread_decision = self._check_spread(symbol, close, bid, ask)
        if not spread_decision.passed:
            return spread_decision

        volume_decision = self._check_volume(symbol, row, close)
        if not volume_decision.passed:
            return volume_decision

        atr_decision = self._check_atr(symbol, row, close)
        if not atr_decision.passed:
            return atr_decision

        trend_decision = self._check_trend(symbol, side, row, close)
        if not trend_decision.passed:
            return trend_decision

        decision = FilterDecision(True, "FILTER PASSED", symbol, details="all filters passed")
        self._log_pass(decision)
        return decision

    def _check_spread(self, symbol: str, close: float, bid, ask) -> FilterDecision:
        if bid is None or ask is None:
            # Conservative but non-blocking for backtest/offline data; live/testnet should pass ticker.
            logger.info("FILTER PASSED | {} | spread skipped | ticker missing", symbol)
            return FilterDecision(True, "FILTER PASSED", symbol, details="spread skipped: ticker missing")
        bid = float(bid)
        ask = float(ask)
        mid = (bid + ask) / 2.0
        if mid <= 0 or ask < bid:
            return self._block(symbol, "SPREAD BLOCKED", None, self.settings.max_spread_percent, "invalid bid/ask")
        spread_percent = ((ask - bid) / mid) * 100.0
        if spread_percent > self.settings.max_spread_percent:
            return self._block(symbol, "SPREAD BLOCKED", spread_percent, self.settings.max_spread_percent, "spread too high")
        return FilterDecision(True, "FILTER PASSED", symbol, spread_percent, self.settings.max_spread_percent, "spread ok")

    def _check_volume(self, symbol: str, row, close: float) -> FilterDecision:
        volume = float(row.get("volume", 0.0))
        volume_usdt = close * volume
        if volume_usdt < self.settings.min_volume_usdt:
            return self._block(symbol, "VOLUME BLOCKED", volume_usdt, self.settings.min_volume_usdt, "volume too low")
        return FilterDecision(True, "FILTER PASSED", symbol, volume_usdt, self.settings.min_volume_usdt, "volume ok")

    def _check_atr(self, symbol: str, row, close: float) -> FilterDecision:
        atr = row.get("atr_14")
        if atr is None or not math.isfinite(float(atr)) or float(atr) <= 0:
            return self._block(symbol, "ATR BLOCKED", None, None, "atr missing/invalid")
        atr_percent = (float(atr) / close) * 100.0
        if atr_percent < self.settings.min_atr_percent:
            return self._block(symbol, "ATR BLOCKED", atr_percent, self.settings.min_atr_percent, "atr too low")
        if atr_percent > self.settings.max_atr_percent:
            return self._block(symbol, "ATR BLOCKED", atr_percent, self.settings.max_atr_percent, "atr too high")
        return FilterDecision(True, "FILTER PASSED", symbol, atr_percent, self.settings.max_atr_percent, "atr ok")

    def _check_trend(self, symbol: str, side: str, row, close: float) -> FilterDecision:
        if not self.settings.trend_filter_enabled:
            return FilterDecision(True, "FILTER PASSED", symbol, details="trend disabled")
        ema_col = f"ema_{self.settings.trend_ema_period}"
        ema = row.get(ema_col)
        if ema is None or not math.isfinite(float(ema)):
            return self._block(symbol, "TREND BLOCKED", None, None, f"{ema_col} missing/invalid")
        ema = float(ema)
        if side.upper() == "BUY" and close <= ema:
            return self._block(symbol, "TREND BLOCKED", close, ema, "BUY requires close > trend EMA")
        if side.upper() == "SELL" and close >= ema:
            return self._block(symbol, "TREND BLOCKED", close, ema, "SELL requires close < trend EMA")
        return FilterDecision(True, "FILTER PASSED", symbol, close, ema, "trend ok")

    def _block(self, symbol: str, reason: str, value, threshold, details: str) -> FilterDecision:
        decision = FilterDecision(False, reason, symbol, value=value, threshold=threshold, details=details)
        logger.info(
            "{} | {} | value={} | threshold={} | {}",
            reason,
            symbol,
            value,
            threshold,
            details,
        )
        logger.info("FILTER BLOCKED | {} | {}", symbol, reason)
        return decision

    def _log_pass(self, decision: FilterDecision) -> None:
        logger.info("FILTER PASSED | {} | {}", decision.symbol, decision.details)
