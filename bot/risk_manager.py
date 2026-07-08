"""Risk yoneticisi.

Hicbir emir bu modulun onayi olmadan verilemez. Kontroller:

1. Gecerli fiyat verisi
2. Gecerli sanal bakiye ve 100 USDT hard-cap
3. Stop-loss zorunlu
4. Take-profit zorunlu
5. Gunluk zarar limiti
6. Gunluk islem limiti
7. Maksimum acik pozisyon / sembol basina tek pozisyon
8. Ayni sembolde acik emir yok
9. Maksimum eszamanli acik emir limiti
10. Ayni sinyale tekrar emir yok
11. Pozisyon buyuklugu hesabi (risk bazli)
12. Tek islem notional cap
13. Toplam acik risk cap
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from bot.logger import get_logger
from bot.state import BotState
from bot.strategy import Signal
from bot.take_profit import TakeProfitManager
from config.settings import Settings

logger = get_logger()


@dataclass
class RiskDecision:
    approved: bool
    reason: str
    position_size: float = 0.0
    risk_amount: float = 0.0
    notional: float = 0.0

    def as_dict(self) -> dict:
        # Backward-compatible public shape used by existing tests/log callers.
        return {
            "approved": self.approved,
            "reason": self.reason,
            "position_size": self.position_size,
        }


class RiskManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _reject(self, reason: str, signal: Signal) -> RiskDecision:
        logger.warning("RISK BLOCKED | {} | {} | {}", signal.symbol, signal.action, reason)
        return RiskDecision(approved=False, reason=reason)

    def _effective_balance(self, balance: float) -> float:
        """Testnet bakiyesi yuksek olsa bile bot sermayesini hard-cap ile sinirla."""
        return min(float(balance), float(self.settings.max_capital_usdt))

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

        effective_balance = self._effective_balance(float(balance))
        if effective_balance <= 0:
            return self._reject("Efektif sermaye sifir.", signal)

        # 3) Stop-loss zorunlu
        if signal.stop_loss is None or float(signal.stop_loss) <= 0:
            return self._reject("Stop-loss degeri olmadan islem yapilamaz.", signal)

        # 4) Take-profit zorunlu ve minimum Risk/Reward kontrolu
        if signal.take_profit is None or float(signal.take_profit) <= 0:
            return self._reject("Take-profit / Take Profit is required before opening a position.", signal)
        try:
            TakeProfitManager(s.min_risk_reward).validate(
                "buy",
                entry_price=float(signal.price),
                stop_loss=float(signal.stop_loss),
                take_profit=float(signal.take_profit),
            )
        except RuntimeError as exc:
            return self._reject(str(exc), signal)

        # 5) Gunluk zarar limiti: sanal baslangic kasasi uzerinden hesaplanir.
        max_daily_loss_amount = s.initial_balance * s.max_daily_loss
        if state.daily_realized_pnl <= -max_daily_loss_amount:
            logger.warning("DAILY LIMIT REACHED | daily_pnl={:.2f}", state.daily_realized_pnl)
            return self._reject(
                f"Gunluk zarar limiti asildi "
                f"(PnL {state.daily_realized_pnl:.2f} <= -{max_daily_loss_amount:.2f}). "
                "Bot bugun yeni islem acmayacak.",
                signal,
            )

        # 6) Gunluk islem limiti
        if state.daily_trade_count >= s.max_daily_trades:
            logger.warning("DAILY LIMIT REACHED | daily_trade_count={}", state.daily_trade_count)
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

        # 8) Ayni sembolde acik emir yok
        if state.has_open_order(signal.symbol):
            return self._reject(
                f"{signal.symbol} icin zaten acik emir var; yeni emir acilmayacak.",
                signal,
            )

        # 9) Toplam acik emir limiti
        active_orders = sum(1 for symbol in state.open_orders if state.has_open_order(symbol))
        if active_orders >= s.max_concurrent_orders:
            return self._reject(
                f"Maksimum acik emir sayisina ulasildi "
                f"({active_orders}/{s.max_concurrent_orders}).",
                signal,
            )

        # 10) Ayni sinyale tekrar emir yok
        if state.is_duplicate_signal(signal.symbol, signal.fingerprint):
            return self._reject("Ayni sinyal icin zaten emir verildi.", signal)

        # 11) Pozisyon buyuklugu: riske edilen tutar / stop mesafesi
        entry = float(signal.price)
        stop = float(signal.stop_loss)
        stop_distance = abs(entry - stop)
        if stop_distance <= 0:
            return self._reject("Stop-loss girise esit; pozisyon hesaplanamaz.", signal)

        risk_amount = effective_balance * s.max_risk_per_trade
        position_size = risk_amount / stop_distance

        # Bakiyeyi asan pozisyon acilmaz (spot, kaldiracsiz)
        max_affordable = effective_balance / entry
        position_size = min(position_size, max_affordable)

        # 12) Tek islem notional cap
        max_notional_size = s.max_notional_per_trade_usdt / entry
        position_size = min(position_size, max_notional_size)
        notional = position_size * entry
        actual_risk = position_size * stop_distance

        if notional > s.max_notional_per_trade_usdt + 1e-9:
            return self._reject(
                f"Tek islem notional limiti asildi ({notional:.2f} > "
                f"{s.max_notional_per_trade_usdt:.2f}).",
                signal,
            )

        # 13) Toplam acik risk cap
        total_risk_after = state.total_open_risk() + actual_risk
        if total_risk_after > s.max_total_open_risk_usdt + 1e-9:
            return self._reject(
                f"Toplam acik risk limiti asildi ({total_risk_after:.2f} > "
                f"{s.max_total_open_risk_usdt:.2f}).",
                signal,
            )

        if position_size <= 0:
            return self._reject("Hesaplanan pozisyon buyuklugu sifir.", signal)

        logger.info(
            "RISK AMOUNT | {} | {:.6f} {} | effective_balance {:.2f}",
            signal.symbol,
            actual_risk,
            s.base_currency,
            effective_balance,
        )
        logger.info(
            "POSITION SIZE | {} | {:.8f} | notional {:.2f}",
            signal.symbol,
            position_size,
            notional,
        )
        logger.info(
            "Risk ONAY | {} | boyut {:.6f} | risk {:.2f} {} | notional {:.2f}",
            signal.symbol,
            position_size,
            actual_risk,
            s.base_currency,
            notional,
        )
        return RiskDecision(
            approved=True,
            reason="Tum risk kontrolleri gecildi.",
            position_size=position_size,
            risk_amount=actual_risk,
            notional=notional,
        )
