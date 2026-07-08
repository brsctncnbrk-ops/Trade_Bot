"""Uygulama yapilandirmasi.

Tum ayarlar ortam degiskenlerinden (veya .env dosyasindan) okunur ve
pydantic ile dogrulanir. Guvenlik kurallari:

- Varsayilan mod "backtest" — hicbir API anahtari gerektirmez.
- MODE=live yalnizca ALLOW_LIVE_TRADING=true ile birlikte kabul edilir.
- Sirlar asla loglanmaz ve kodda sabitlenmez.
"""

from __future__ import annotations

from typing import List

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ALLOWED_MODES = {"backtest", "testnet", "live"}


class LiveTradingNotAllowedError(ValueError):
    """MODE=live secildi ancak ALLOW_LIVE_TRADING=true degil."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Calisma modu
    mode: str = Field(default="backtest", alias="MODE")
    allow_live_trading: bool = Field(default=False, alias="ALLOW_LIVE_TRADING")

    # Binance API (live)
    binance_api_key: str = Field(default="", alias="BINANCE_API_KEY")
    binance_api_secret: str = Field(default="", alias="BINANCE_API_SECRET")

    # Binance API (testnet)
    binance_testnet_api_key: str = Field(default="", alias="BINANCE_TESTNET_API_KEY")
    binance_testnet_api_secret: str = Field(
        default="", alias="BINANCE_TESTNET_API_SECRET"
    )

    # Islem ayarlari
    base_currency: str = Field(default="USDT", alias="BASE_CURRENCY")
    symbols_raw: str = Field(default="BTC/USDT,ETH/USDT", alias="SYMBOLS")
    timeframe: str = Field(default="1h", alias="TIMEFRAME")

    # Risk yonetimi
    initial_balance: float = Field(default=1000.0, gt=0, alias="INITIAL_BALANCE")
    max_capital_usdt: float = Field(default=1_000_000.0, gt=0, alias="MAX_CAPITAL_USDT")
    max_risk_per_trade: float = Field(
        default=0.01, gt=0, le=1, alias="MAX_RISK_PER_TRADE"
    )
    max_daily_loss: float = Field(default=0.03, gt=0, le=1, alias="MAX_DAILY_LOSS")
    max_hourly_loss: float = Field(default=0.02, gt=0, le=1, alias="MAX_HOURLY_LOSS")
    max_open_positions: int = Field(default=1, ge=1, alias="MAX_OPEN_POSITIONS")
    max_daily_trades: int = Field(default=5, ge=1, alias="MAX_DAILY_TRADES")
    max_notional_per_trade_usdt: float = Field(
        default=1_000_000.0, gt=0, alias="MAX_NOTIONAL_PER_TRADE_USDT"
    )
    max_total_open_risk_usdt: float = Field(
        default=1_000_000.0, gt=0, alias="MAX_TOTAL_OPEN_RISK_USDT"
    )
    max_concurrent_orders: int = Field(default=1, ge=0, alias="MAX_CONCURRENT_ORDERS")
    max_api_errors: int = Field(default=5, ge=1, alias="MAX_API_ERRORS")

    stop_loss_percent: float = Field(
        default=0.02, gt=0, lt=1, alias="STOP_LOSS_PERCENT"
    )
    stop_atr_multiplier: float = Field(default=2.0, gt=0, alias="STOP_ATR_MULTIPLIER")
    min_stop_distance_percent: float = Field(
        default=0.003, gt=0, lt=1, alias="MIN_STOP_DISTANCE_PERCENT"
    )
    max_stop_distance_percent: float = Field(
        default=0.05, gt=0, lt=1, alias="MAX_STOP_DISTANCE_PERCENT"
    )
    take_profit_percent: float = Field(
        default=0.04, gt=0, lt=1, alias="TAKE_PROFIT_PERCENT"
    )
    min_risk_reward: float = Field(default=2.0, gt=0, alias="MIN_RISK_REWARD")
    break_even_trigger_r: float = Field(default=1.0, gt=0, alias="BREAK_EVEN_TRIGGER_R")
    trailing_stop_activation_r: float = Field(default=2.0, gt=0, alias="TRAILING_STOP_ACTIVATION_R")
    trailing_stop_atr_multiplier: float = Field(default=2.0, gt=0, alias="TRAILING_STOP_ATR_MULTIPLIER")

    # Islem filtreleri
    enable_trade_filters: bool = Field(default=True, alias="ENABLE_TRADE_FILTERS")
    max_spread_percent: float = Field(default=0.10, ge=0, alias="MAX_SPREAD_PERCENT")
    min_volume_usdt: float = Field(default=100000.0, ge=0, alias="MIN_VOLUME_USDT")
    min_atr_percent: float = Field(default=0.20, ge=0, alias="MIN_ATR_PERCENT")
    max_atr_percent: float = Field(default=5.00, gt=0, alias="MAX_ATR_PERCENT")
    trend_filter_enabled: bool = Field(default=True, alias="TREND_FILTER_ENABLED")
    trend_ema_period: int = Field(default=200, ge=1, alias="TREND_EMA_PERIOD")

    # Emir guvenligi
    order_type: str = Field(default="limit", alias="ORDER_TYPE")
    open_order_timeout_seconds: int = Field(
        default=60, ge=1, alias="OPEN_ORDER_TIMEOUT_SECONDS"
    )
    state_file: str = Field(default="state.json", alias="STATE_FILE")

    # Telegram (opsiyonel)
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in ALLOWED_MODES:
            raise ValueError(
                f"Gecersiz MODE: {value!r}. Izin verilen modlar: "
                f"{sorted(ALLOWED_MODES)}"
            )
        return normalized

    @field_validator("order_type")
    @classmethod
    def validate_order_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"limit", "market"}:
            raise ValueError("ORDER_TYPE yalnizca limit veya market olabilir.")
        return normalized

    @model_validator(mode="after")
    def enforce_live_trading_gate(self) -> "Settings":
        if self.mode == "live" and not self.allow_live_trading:
            raise LiveTradingNotAllowedError(
                "MODE=live kullanilamaz: canli islem varsayilan olarak kapalidir. "
                "Gercekten canli islem istiyorsaniz ALLOW_LIVE_TRADING=true "
                "ortam degiskenini de acikca ayarlamalisiniz."
            )
        if self.min_atr_percent > self.max_atr_percent:
            raise ValueError("MIN_ATR_PERCENT, MAX_ATR_PERCENT degerinden buyuk olamaz.")
        return self

    @property
    def symbols(self) -> List[str]:
        return [s.strip() for s in self.symbols_raw.split(",") if s.strip()]

    @property
    def is_backtest(self) -> bool:
        return self.mode == "backtest"

    @property
    def is_testnet(self) -> bool:
        return self.mode == "testnet"

    @property
    def is_live(self) -> bool:
        return self.mode == "live"

    def masked_summary(self) -> dict:
        """Sirlari maskeleyerek loglanabilir bir ozet dondurur."""

        def mask(value: str) -> str:
            if not value:
                return "(bos)"
            return f"{value[:3]}***" if len(value) > 3 else "***"

        return {
            "mode": self.mode,
            "allow_live_trading": self.allow_live_trading,
            "base_currency": self.base_currency,
            "symbols": self.symbols,
            "timeframe": self.timeframe,
            "initial_balance": self.initial_balance,
            "max_capital_usdt": self.max_capital_usdt,
            "max_risk_per_trade": self.max_risk_per_trade,
            "max_daily_loss": self.max_daily_loss,
            "max_hourly_loss": self.max_hourly_loss,
            "max_open_positions": self.max_open_positions,
            "max_daily_trades": self.max_daily_trades,
            "max_notional_per_trade_usdt": self.max_notional_per_trade_usdt,
            "max_total_open_risk_usdt": self.max_total_open_risk_usdt,
            "max_concurrent_orders": self.max_concurrent_orders,
            "max_api_errors": self.max_api_errors,
            "order_type": self.order_type,
            "open_order_timeout_seconds": self.open_order_timeout_seconds,
            "state_file": self.state_file,
            "stop_loss_percent": self.stop_loss_percent,
            "stop_atr_multiplier": self.stop_atr_multiplier,
            "min_stop_distance_percent": self.min_stop_distance_percent,
            "max_stop_distance_percent": self.max_stop_distance_percent,
            "take_profit_percent": self.take_profit_percent,
            "min_risk_reward": self.min_risk_reward,
            "break_even_trigger_r": self.break_even_trigger_r,
            "trailing_stop_activation_r": self.trailing_stop_activation_r,
            "trailing_stop_atr_multiplier": self.trailing_stop_atr_multiplier,
            "enable_trade_filters": self.enable_trade_filters,
            "max_spread_percent": self.max_spread_percent,
            "min_volume_usdt": self.min_volume_usdt,
            "min_atr_percent": self.min_atr_percent,
            "max_atr_percent": self.max_atr_percent,
            "trend_filter_enabled": self.trend_filter_enabled,
            "trend_ema_period": self.trend_ema_period,
            "binance_api_key": mask(self.binance_api_key),
            "binance_testnet_api_key": mask(self.binance_testnet_api_key),
            "telegram_bot_token": mask(self.telegram_bot_token),
        }


def get_settings(**overrides) -> Settings:
    """Ayarları ortamdan yukleyen fabrika.

    Testlerin .env dosyasindan etkilenmemesi icin `_env_file=None`
    gecilebilir; ek anahtar kelime argumanlari Settings'e aktarilir.
    """
    return Settings(**overrides)
