"""EMA + RSI stratejisi.

Bu modul YALNIZCA sinyal uretir; asla emir vermez. Emirler her zaman
risk yoneticisi onayindan gecip execution modulu uzerinden islenir.

Alis kosullari:
- EMA20 > EMA50
- RSI < 70
- Acik pozisyon yok

Satis kosullari:
- Stop-loss seviyesi gorulur
- Take-profit seviyesi gorulur
- EMA20 < EMA50 (trend donusu)

Gunluk zarar/islem limitleri stratejinin isi degildir; risk yoneticisi
tarafindan uygulanir.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from bot.logger import get_logger
from bot.state import Position

logger = get_logger()

RSI_OVERBOUGHT = 70.0


@dataclass
class Signal:
    action: str  # "BUY" | "SELL" | "HOLD"
    symbol: str
    reason: str
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    @property
    def fingerprint(self) -> str:
        """Ayni sinyalin tekrarini tespit etmek icin kimlik."""
        return f"{self.symbol}:{self.action}:{self.price}"


class EmaRsiStrategy:
    def __init__(
        self,
        stop_loss_percent: float = 0.02,
        take_profit_percent: float = 0.04,
        ema_fast: int = 20,
        ema_slow: int = 50,
        rsi_period: int = 14,
    ) -> None:
        self.stop_loss_percent = stop_loss_percent
        self.take_profit_percent = take_profit_percent
        self.ema_fast_col = f"ema_{ema_fast}"
        self.ema_slow_col = f"ema_{ema_slow}"
        self.rsi_col = f"rsi_{rsi_period}"

    def generate_signal(
        self,
        df: pd.DataFrame,
        symbol: str,
        open_position: Optional[Position] = None,
    ) -> Signal:
        """Gosterge kolonlari eklenmis veriden son bar icin sinyal uretir."""
        if df is None or df.empty:
            return Signal("HOLD", symbol, "Veri yok; sinyal uretilemedi.")

        required = {self.ema_fast_col, self.ema_slow_col, self.rsi_col, "close"}
        missing = required - set(df.columns)
        if missing:
            return Signal(
                "HOLD", symbol, f"Gosterge kolonlari eksik: {sorted(missing)}"
            )

        row = df.iloc[-1]
        close = float(row["close"])
        ema_fast = row[self.ema_fast_col]
        ema_slow = row[self.ema_slow_col]
        rsi = row[self.rsi_col]

        if pd.isna(ema_fast) or pd.isna(ema_slow) or pd.isna(rsi):
            return Signal("HOLD", symbol, "Gosterge degerleri henuz olusmadi (NaN).")

        # --- Acik pozisyon varsa cikis kosullari ---
        if open_position is not None:
            low = float(row.get("low", close))
            high = float(row.get("high", close))
            if low <= open_position.stop_loss:
                signal = Signal(
                    "SELL",
                    symbol,
                    f"Stop-loss tetiklendi ({open_position.stop_loss:.4f}).",
                    price=open_position.stop_loss,
                )
            elif high >= open_position.take_profit:
                signal = Signal(
                    "SELL",
                    symbol,
                    f"Take-profit tetiklendi ({open_position.take_profit:.4f}).",
                    price=open_position.take_profit,
                )
            elif ema_fast < ema_slow:
                signal = Signal(
                    "SELL",
                    symbol,
                    "Trend donusu: EMA20 < EMA50.",
                    price=close,
                )
            else:
                signal = Signal("HOLD", symbol, "Pozisyon acik; cikis kosulu yok.")
            logger.info(
                "Strateji sinyali | {} | {} | {}", symbol, signal.action, signal.reason
            )
            return signal

        # --- Pozisyon yoksa giris kosullari ---
        if ema_fast <= ema_slow:
            return Signal("HOLD", symbol, "EMA20 <= EMA50; alis kosulu saglanmadi.")
        if rsi >= RSI_OVERBOUGHT:
            return Signal(
                "HOLD", symbol, f"RSI {rsi:.1f} >= {RSI_OVERBOUGHT}; asiri alim."
            )

        stop_loss = close * (1.0 - self.stop_loss_percent)
        take_profit = close * (1.0 + self.take_profit_percent)
        signal = Signal(
            "BUY",
            symbol,
            f"EMA20 > EMA50 ve RSI {rsi:.1f} < {RSI_OVERBOUGHT}.",
            price=close,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        logger.info(
            "Strateji sinyali | {} | BUY @ {:.4f} (SL {:.4f} / TP {:.4f})",
            symbol,
            close,
            stop_loss,
            take_profit,
        )
        return signal
