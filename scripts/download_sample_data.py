"""Ornek OHLCV verisi indirme araci.

Binance'in halka acik (API anahtari gerektirmeyen) OHLCV ucundan veri
ceker ve data/sample/ altina CSV olarak yazar. Ag yoksa deterministik
uretilmis veriye geri duser — boylece backtest her kosulda calisir.

Kullanim:
    python scripts/download_sample_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from bot.data_provider import SAMPLE_DATA_DIR, generate_sample_data
from bot.logger import get_logger
from config.settings import get_settings

logger = get_logger()


def download_symbol(symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
    """Halka acik CCXT ucundan OHLCV ceker (API anahtari gerekmez)."""
    import ccxt

    exchange = ccxt.binance({"enableRateLimit": True})
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(
        raw, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def main() -> int:
    settings = get_settings()
    SAMPLE_DATA_DIR.mkdir(parents=True, exist_ok=True)

    for symbol in settings.symbols:
        target = SAMPLE_DATA_DIR / (
            f"{symbol.replace('/', '_')}_{settings.timeframe}.csv"
        )
        try:
            df = download_symbol(symbol, settings.timeframe)
            logger.info("{} verisi indirildi ({} bar).", symbol, len(df))
        except Exception as exc:
            logger.warning(
                "{} indirilemedi ({}); deterministik veri uretiliyor.", symbol, exc
            )
            df = generate_sample_data(symbol=symbol, timeframe=settings.timeframe)
        df.to_csv(target, index=False)
        logger.info("Yazildi: {}", target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
