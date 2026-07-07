"""Veri saglayici.

- backtest: data/sample/ altinda CSV varsa yukler, yoksa deterministik
  sahte OHLCV verisi uretir (testler cevrimdisi calisir).
- testnet: CCXT Binance baglantisi tembel kurulur; import aninda asla
  ag cagrisi yapilmaz.

Veri formati: timestamp, open, high, low, close, volume
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from bot.logger import get_logger
from config.settings import Settings

logger = get_logger()

OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]
SAMPLE_DATA_DIR = Path("data/sample")


def generate_sample_data(
    symbol: str = "BTC/USDT",
    periods: int = 500,
    seed: int = 42,
    start_price: float = 30000.0,
    timeframe: str = "1h",
) -> pd.DataFrame:
    """Deterministik (seed'li) sahte OHLCV verisi uretir.

    Trend + sinus dalgasi + gurultu birlesimi kullanilir; boylece strateji
    hem alis hem satis fazlari uretir ve backtest anlamli calisir.
    """
    rng = np.random.default_rng(seed)

    t = np.arange(periods)
    trend = start_price * 0.0004 * t
    cycle = start_price * 0.05 * np.sin(2 * np.pi * t / 120.0)
    noise = rng.normal(0.0, start_price * 0.004, periods).cumsum()
    close = start_price + trend + cycle + noise
    close = np.maximum(close, start_price * 0.1)  # fiyat asla sifira inmesin

    spread = np.abs(rng.normal(0.0, start_price * 0.003, periods))
    open_ = np.concatenate(([close[0]], close[:-1]))
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    volume = rng.uniform(10.0, 100.0, periods)

    freq = pd.tseries.frequencies.to_offset(
        timeframe.replace("m", "min").replace("h", "h").replace("d", "D")
    )
    timestamps = pd.date_range(end="2024-01-01", periods=periods, freq=freq)

    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )
    logger.info(
        "Deterministik ornek veri uretildi | {} | {} bar | seed={}",
        symbol,
        periods,
        seed,
    )
    return df


class DataProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._exchange = None  # testnet icin tembel kurulum

    def _sample_file(self, symbol: str) -> Path:
        safe_symbol = symbol.replace("/", "_")
        return SAMPLE_DATA_DIR / f"{safe_symbol}_{self.settings.timeframe}.csv"

    def _get_exchange(self):
        """CCXT Binance istemcisini ilk ihtiyacta kurar (testnet)."""
        if self._exchange is None:
            import ccxt  # tembel import

            exchange = ccxt.binance({"enableRateLimit": True})
            if self.settings.is_testnet:
                exchange.set_sandbox_mode(True)
            self._exchange = exchange
        return self._exchange

    def get_ohlcv(
        self, symbol: str, limit: int = 500, timeframe: Optional[str] = None
    ) -> pd.DataFrame:
        """OHLCV verisini moda gore dondurur."""
        timeframe = timeframe or self.settings.timeframe

        if self.settings.is_backtest:
            sample_file = self._sample_file(symbol)
            if sample_file.exists():
                logger.info("Ornek veri dosyasi yuklendi | {}", sample_file)
                df = pd.read_csv(sample_file, parse_dates=["timestamp"])
                missing = set(OHLCV_COLUMNS) - set(df.columns)
                if missing:
                    raise ValueError(
                        f"{sample_file} dosyasinda eksik kolonlar: {sorted(missing)}"
                    )
                return df.tail(limit).reset_index(drop=True)
            logger.info(
                "Ornek veri dosyasi yok ({}); deterministik veri uretiliyor.",
                sample_file,
            )
            # Sembole gore deterministik seed: her sembol farkli ama her
            # calistirmada ayni veri uretir.
            seed = sum(symbol.encode())
            return generate_sample_data(
                symbol=symbol, periods=limit, timeframe=timeframe, seed=seed
            )

        # testnet / live: CCXT uzerinden gercek veri
        exchange = self._get_exchange()
        raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(
            raw, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        logger.info("CCXT OHLCV alindi | {} | {} bar", symbol, len(df))
        return df
