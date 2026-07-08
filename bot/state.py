"""Bot durumu: acik pozisyonlar, acik emirler ve gunluk limitler.

State JSON dosyasina kaydedilebilir; boylece bot yeniden baslasa bile
risk sayaclari, acik emirler ve acik pozisyonlar kaybolmaz.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Optional


@dataclass
class Position:
    symbol: str
    side: str  # "long" (spot botu sadece long acar)
    entry_price: float
    quantity: float
    stop_loss: Optional[float]
    take_profit: float
    opened_at: Optional[str] = None
    break_even_activated: bool = False
    break_even_price: Optional[float] = None
    original_stop_loss: Optional[float] = None
    current_stop_loss: Optional[float] = None
    trailing_stop_activated: bool = False
    trailing_activation_price: Optional[float] = None
    trailing_stop_price: Optional[float] = None
    highest_price_seen: Optional[float] = None

    def __post_init__(self) -> None:
        if self.original_stop_loss is None:
            self.original_stop_loss = self.stop_loss
        if self.current_stop_loss is None:
            self.current_stop_loss = self.stop_loss
        if self.highest_price_seen is None:
            self.highest_price_seen = self.entry_price

    @property
    def notional(self) -> float:
        return float(self.entry_price) * float(self.quantity)

    @property
    def open_risk(self) -> float:
        if self.stop_loss is None:
            return 0.0
        return abs(float(self.entry_price) - float(self.stop_loss)) * float(self.quantity)


@dataclass
class OpenOrder:
    id: str
    symbol: str
    side: str
    order_type: str
    price: float
    quantity: float
    status: str = "open"
    filled: float = 0.0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_amount: float = 0.0

    @property
    def notional(self) -> float:
        return float(self.price) * float(self.quantity)


@dataclass
class BotState:
    """Botun islem durumunu tutar."""

    open_positions: Dict[str, Position] = field(default_factory=dict)
    open_orders: Dict[str, OpenOrder] = field(default_factory=dict)
    daily_realized_pnl: float = 0.0
    hourly_realized_pnl: float = 0.0
    daily_trade_count: int = 0
    consecutive_losses: int = 0
    api_error_count: int = 0
    exchange_connected: bool = True
    trading_status: str = "TRADING_ACTIVE"
    halt_reason: Optional[str] = None
    halted_at: Optional[str] = None
    last_signal_fingerprints: Dict[str, str] = field(default_factory=dict)
    last_trade_at: Optional[str] = None

    def has_open_position(self, symbol: str) -> bool:
        return symbol in self.open_positions

    def has_open_order(self, symbol: str) -> bool:
        order = self.open_orders.get(symbol)
        return order is not None and order.status in {"open", "new", "partially_filled"}

    def total_open_risk(self) -> float:
        position_risk = sum(p.open_risk for p in self.open_positions.values())
        order_risk = sum(float(o.risk_amount or 0.0) for o in self.open_orders.values())
        return position_risk + order_risk

    def total_open_notional(self) -> float:
        position_notional = sum(p.notional for p in self.open_positions.values())
        order_notional = sum(o.notional for o in self.open_orders.values())
        return position_notional + order_notional

    def open_position(self, position: Position) -> None:
        if self.has_open_position(position.symbol):
            raise ValueError(
                f"{position.symbol} icin zaten acik pozisyon var; "
                "ayni sembolde birden fazla pozisyon acilamaz."
            )
        if self.has_open_order(position.symbol):
            raise ValueError(
                f"{position.symbol} icin zaten acik emir var; "
                "pozisyon acmadan once emir durumu netlesmeli."
            )
        self.open_positions[position.symbol] = position
        self.daily_trade_count += 1
        self.last_trade_at = position.opened_at or self.last_trade_at

    def close_position(self, symbol: str, pnl: float) -> Position:
        if not self.has_open_position(symbol):
            raise ValueError(f"{symbol} icin acik pozisyon yok.")
        position = self.open_positions.pop(symbol)
        self.daily_realized_pnl += pnl
        self.hourly_realized_pnl += pnl
        if pnl < 0:
            self.consecutive_losses += 1
        elif pnl > 0:
            self.consecutive_losses = 0
        return position

    def record_open_order(self, order: OpenOrder) -> None:
        if self.has_open_order(order.symbol):
            raise ValueError(f"{order.symbol} icin zaten acik emir var.")
        self.open_orders[order.symbol] = order
        self.last_trade_at = order.created_at or self.last_trade_at

    def update_order(self, symbol: str, **changes) -> OpenOrder:
        if symbol not in self.open_orders:
            raise ValueError(f"{symbol} icin acik emir yok.")
        order = self.open_orders[symbol]
        for key, value in changes.items():
            if hasattr(order, key):
                setattr(order, key, value)
        return order

    def remove_order(self, symbol: str) -> OpenOrder:
        if symbol not in self.open_orders:
            raise ValueError(f"{symbol} icin acik emir yok.")
        return self.open_orders.pop(symbol)

    def record_signal(self, symbol: str, fingerprint: str) -> None:
        self.last_signal_fingerprints[symbol] = fingerprint

    def is_duplicate_signal(self, symbol: str, fingerprint: str) -> bool:
        return self.last_signal_fingerprints.get(symbol) == fingerprint

    def reset_daily(self) -> None:
        """Gun sonunda gunluk sayaclari sifirlar."""
        self.daily_realized_pnl = 0.0
        self.hourly_realized_pnl = 0.0
        self.daily_trade_count = 0

    def to_dict(self) -> dict:
        return {
            "open_positions": {
                symbol: asdict(position)
                for symbol, position in self.open_positions.items()
            },
            "open_orders": {
                symbol: asdict(order) for symbol, order in self.open_orders.items()
            },
            "daily_realized_pnl": self.daily_realized_pnl,
            "hourly_realized_pnl": self.hourly_realized_pnl,
            "daily_trade_count": self.daily_trade_count,
            "consecutive_losses": self.consecutive_losses,
            "api_error_count": self.api_error_count,
            "exchange_connected": self.exchange_connected,
            "trading_status": self.trading_status,
            "halt_reason": self.halt_reason,
            "halted_at": self.halted_at,
            "last_signal_fingerprints": dict(self.last_signal_fingerprints),
            "last_trade_at": self.last_trade_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BotState":
        positions = {
            symbol: Position(**payload)
            for symbol, payload in data.get("open_positions", {}).items()
        }
        orders = {
            symbol: OpenOrder(**payload)
            for symbol, payload in data.get("open_orders", {}).items()
        }
        return cls(
            open_positions=positions,
            open_orders=orders,
            daily_realized_pnl=float(data.get("daily_realized_pnl", 0.0)),
            hourly_realized_pnl=float(data.get("hourly_realized_pnl", 0.0)),
            daily_trade_count=int(data.get("daily_trade_count", 0)),
            consecutive_losses=int(data.get("consecutive_losses", 0)),
            api_error_count=int(data.get("api_error_count", 0)),
            exchange_connected=bool(data.get("exchange_connected", True)),
            trading_status=data.get("trading_status", "TRADING_ACTIVE"),
            halt_reason=data.get("halt_reason"),
            halted_at=data.get("halted_at"),
            last_signal_fingerprints=dict(data.get("last_signal_fingerprints", {})),
            last_trade_at=data.get("last_trade_at"),
        )

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        path.chmod(0o600)

    @classmethod
    def load(cls, path: str | Path) -> "BotState":
        path = Path(path)
        if not path.exists():
            return cls()
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
