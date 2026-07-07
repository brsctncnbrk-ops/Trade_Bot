"""Bot durumu: acik pozisyonlar, gunluk PnL, gunluk islem sayisi.

Ilk surumde bellek ici tutulur; kalicilik (dosya/DB) sonraki surumlerde
eklenebilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class Position:
    symbol: str
    side: str  # "long" (spot botu sadece long acar)
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    opened_at: Optional[str] = None


@dataclass
class BotState:
    """Botun islem durumunu tutar."""

    open_positions: Dict[str, Position] = field(default_factory=dict)
    daily_realized_pnl: float = 0.0
    daily_trade_count: int = 0
    last_signal_fingerprints: Dict[str, str] = field(default_factory=dict)

    def has_open_position(self, symbol: str) -> bool:
        return symbol in self.open_positions

    def open_position(self, position: Position) -> None:
        if self.has_open_position(position.symbol):
            raise ValueError(
                f"{position.symbol} icin zaten acik pozisyon var; "
                "ayni sembolde birden fazla pozisyon acilamaz."
            )
        self.open_positions[position.symbol] = position
        self.daily_trade_count += 1

    def close_position(self, symbol: str, pnl: float) -> Position:
        if not self.has_open_position(symbol):
            raise ValueError(f"{symbol} icin acik pozisyon yok.")
        position = self.open_positions.pop(symbol)
        self.daily_realized_pnl += pnl
        return position

    def record_signal(self, symbol: str, fingerprint: str) -> None:
        self.last_signal_fingerprints[symbol] = fingerprint

    def is_duplicate_signal(self, symbol: str, fingerprint: str) -> bool:
        return self.last_signal_fingerprints.get(symbol) == fingerprint

    def reset_daily(self) -> None:
        """Gun sonunda gunluk sayaclari sifirlar."""
        self.daily_realized_pnl = 0.0
        self.daily_trade_count = 0
