"""Risk yoneticisi.

Hicbir emir bu modulun onayi olmadan verilemez. Kontroller:

1. Gecerli fiyat verisi
2. Gecerli bakiye
3. Stop-loss zorunlu
4. Take-profit zorunlu
5. Gunluk zarar limiti
6. Gunluk islem limiti
7. Maksimum acik pozisyon / sembol basina tek pozisyon
8. Ayni sinyale tekrar emir yok
9. Pozisyon buyuklugu hesabi (risk bazli)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from bot.logger import get_logger
from bot.state import BotState
from bot.strategy import Signal
from config.settings import Settings

logger = get_logger()


@dataclass
class RiskDecision:
    approved: bool
    reason: str
    position_size: float = 0.0

    def as_dict(self) -> dict:
        return {
            "approved": self.approved,
            "reason": self.reason,
            "position_size": self.position_size,
        }


class RiskManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _reject(self, reason: str, signal: Signal) -> RiskDecision:
        logger.warning("Risk RED | {} | {} | {}", signal.symbol, signal.action, reason)
        return RiskDecision(approved=False, reason=reason)

    def evaluate(
        self, signal: Signal, state: BotState, balance: float
    ) -> RiskDecision:
        """Bir alis sinyalini degerlendirir ve karar dondurur."""
        s = self.settings

        # 1) Fiyat verisi gecerli mi?
        if (
            signal.price is None
            or not isinstance(signal.price, (int, float))
            or math.isnan(float(signal.price))
            or float(signal.price) <= 0
        ):
            return self._reject("Fiyat verisi eksik veya gecersiz.", signal)

        # 2) Bakiye gecerli mi?
        if (
            balance is None
            or not isinstance(balance, (int, float))
            or math.isnan(float(balance))
            or float(balance) <= 0
        ):
            return self._reject(f"Bakiye gecersiz: {balance!r}.", signal)

        # 3) Stop-loss zorunlu
        if signal.stop_loss is None or float(signal.stop_loss) <= 0:
            return self._reject("Stop-loss degeri olmadan islem yapilamaz.", signal)

        # 4) Take-profit zorunlu
        if signal.take_profit is None or float(signal.take_profit) <= 0:
            return self._reject("Take-profit degeri olmadan islem yapilamaz.", signal)

        # 5) Gunluk zarar limiti
        max_daily_loss_amount = s.initial_balance * s.max_daily_loss
        if state.daily_realized_pnl <= -max_daily_loss_amount:
            return self._reject(
                f"Gunluk zarar limiti asildi "
                f"(PnL {state.daily_realized_pnl:.2f} <= -{max_daily_loss_amount:.2f}). "
                "Bot bugun yeni islem acmayacak.",
                signal,
            )

        # 6) Gunluk islem limiti
        if state.daily_trade_count >= s.max_daily_trades:
            return self._reject(
                f"Gunluk islem limiti doldu ({state.daily_trade_count}/"
                f"{s.max_daily_trades}).",
                signal,
            )

        # 7) Acik pozisyon limitleri
        if state.has_open_position(signal.symbol):
            return self._reject(
                f"{signal.symbol} icin zaten acik pozisyon var; "
                "sembol basina tek pozisyon kurali.",
                signal,
            )
        if len(state.open_positions) >= s.max_open_positions:
            return self._reject(
                f"Maksimum acik pozisyon sayisina ulasildi "
                f"({len(state.open_positions)}/{s.max_open_positions}).",
                signal,
            )

        # 8) Ayni sinyale tekrar emir yok
        if state.is_duplicate_signal(signal.symbol, signal.fingerprint):
            return self._reject("Ayni sinyal icin zaten emir verildi.", signal)

        # 9) Pozisyon buyuklugu: riske edilen tutar / stop mesafesi
        entry = float(signal.price)
        stop = float(signal.stop_loss)
        stop_distance = abs(entry - stop)
        if stop_distance <= 0:
            return self._reject("Stop-loss girise esit; pozisyon hesaplanamaz.", signal)

        risk_amount = balance * s.max_risk_per_trade
        position_size = risk_amount / stop_distance

        # Bakiyeyi asan pozisyon acilmaz (spot, kaldiracsiz)
        max_affordable = balance / entry
        position_size = min(position_size, max_affordable)

        if position_size <= 0:
            return self._reject("Hesaplanan pozisyon buyuklugu sifir.", signal)

        logger.info(
            "Risk ONAY | {} | boyut {:.6f} | risk {:.2f} {}",
            signal.symbol,
            position_size,
            risk_amount,
            s.base_currency,
        )
        return RiskDecision(
            approved=True,
            reason="Tum risk kontrolleri gecildi.",
            position_size=position_size,
        )
