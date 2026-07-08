"""Teknik gostergeler.

Saf pandas ile hesaplanir (EMA: ewm, RSI: Wilder yumusatmasi).
Kucuk veri setlerinde cokmez; eksik degerler NaN olarak kalir.
"""

from __future__ import annotations

import pandas as pd

from bot.logger import get_logger

logger = get_logger()

REQUIRED_COLUMNS = {"close"}
OHLC_COLUMNS = {"high", "low", "close"}


def _validate_input(df: pd.DataFrame) -> None:
    if df is None:
        raise ValueError("Gosterge hesabi icin veri (DataFrame) gerekli, None verildi.")
    if not isinstance(df, pd.DataFrame):
        raise ValueError(f"DataFrame bekleniyordu, {type(df).__name__} verildi.")
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Veride zorunlu kolonlar eksik: {sorted(missing)}")


def calculate_ema(df: pd.DataFrame, period: int) -> pd.Series:
    """Ustel hareketli ortalama (EMA)."""
    _validate_input(df)
    if period <= 0:
        raise ValueError(f"EMA periyodu pozitif olmali, {period} verildi.")
    return df["close"].ewm(span=period, adjust=False).mean()


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Goreceli guc endeksi (RSI), Wilder yumusatmasi ile."""
    _validate_input(df)
    if period <= 0:
        raise ValueError(f"RSI periyodu pozitif olmali, {period} verildi.")

    delta = df["close"].diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)

    avg_gain = gains.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    # avg_loss == 0 -> tum hareketler kazanc: RSI 100
    rsi = rsi.where(avg_loss != 0, 100.0)
    # veri yetersizken NaN kalir
    rsi[avg_gain.isna() | avg_loss.isna()] = float("nan")
    return rsi


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (ATR), Wilder yumusatmasi ile."""
    _validate_input(df)
    missing = OHLC_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"ATR icin zorunlu kolonlar eksik: {sorted(missing)}")
    if period <= 0:
        raise ValueError(f"ATR periyodu pozitif olmali, {period} verildi.")

    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


def add_indicators(
    df: pd.DataFrame,
    ema_fast: int = 20,
    ema_slow: int = 50,
    rsi_period: int = 14,
    atr_period: int = 14,
) -> pd.DataFrame:
    """Stratejinin ihtiyac duydugu tum gosterge kolonlarini ekler.

    Eklenen kolonlar: ema_20, ema_50, rsi_14, atr_14 (varsayilan periyotlarla).
    Orijinal DataFrame degistirilmez; kopya dondurulur.
    """
    _validate_input(df)
    result = df.copy()
    if result.empty:
        logger.warning("add_indicators bos veri ile cagrildi; NaN kolonlar eklendi.")
        result[f"ema_{ema_fast}"] = pd.Series(dtype=float)
        result[f"ema_{ema_slow}"] = pd.Series(dtype=float)
        result[f"rsi_{rsi_period}"] = pd.Series(dtype=float)
        result[f"atr_{atr_period}"] = pd.Series(dtype=float)
        return result

    result[f"ema_{ema_fast}"] = calculate_ema(result, ema_fast)
    result[f"ema_{ema_slow}"] = calculate_ema(result, ema_slow)
    result[f"rsi_{rsi_period}"] = calculate_rsi(result, rsi_period)
    result[f"atr_{atr_period}"] = calculate_atr(result, atr_period)
    return result
