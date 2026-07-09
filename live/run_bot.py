"""Surekli testnet calistirici.

`live/run_once.py` icindeki tek dongu mantigini degistirmeden guvenli bir
sonsuz dongu icinde calistirir.

Guvenlik kapilari:
- Yalnizca acikca `MODE=testnet` ile calisir.
- Yalnizca acikca `ALLOW_LIVE_TRADING=false` ile calisir.
- MARKET order ayariyla baslamaz; surekli bot sadece LIMIT emirle calisir.
- Hata alan dongu loglanir, beklenir ve sonraki donguye gecilir.
- Ctrl+C guvenli cikis yapar.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.logger import setup_logger
from config.settings import get_settings
from live.run_once import run_once

logger = setup_logger(log_to_file=True)

DEFAULT_INTERVAL_SECONDS = 60.0


def _env_value(name: str) -> str:
    return os.environ.get(name, "").strip().lower()


def _exit(message: str) -> None:
    logger.critical("RUN BOT BLOCKED | {}", message)
    raise SystemExit(message)


def validate_runtime_guards() -> None:
    """Surekli calisma baslamadan once kapali-guvenli kontrolleri uygula."""

    if _env_value("MODE") != "testnet":
        _exit("MODE=testnet olmadan run_bot.py calismaz.")

    if _env_value("ALLOW_LIVE_TRADING") != "false":
        _exit("ALLOW_LIVE_TRADING=false olmadan run_bot.py calismaz.")

    settings = get_settings()
    if not settings.is_testnet:
        _exit("Ayar dogrulamasi testnet modunda degil; calisma durduruldu.")

    if settings.allow_live_trading:
        _exit("Canli islem izni acik gorundu; calisma durduruldu.")

    if settings.order_type != "limit":
        _exit("ORDER_TYPE=limit olmadan run_bot.py calismaz; market emir yasaktir.")


def _parse_positive_float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        _exit(f"{name} pozitif sayi olmali.")
    if value <= 0:
        _exit(f"{name} pozitif sayi olmali.")
    return value


def _parse_optional_positive_int_env(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        _exit(f"{name} pozitif tam sayi olmali.")
    if value <= 0:
        _exit(f"{name} pozitif tam sayi olmali.")
    return value


def run_loop(
    interval_seconds: float | None = None,
    max_loops: int | None = None,
) -> int:
    """run_once() fonksiyonunu guvenli bekleme araliklariyla tekrarlar."""

    validate_runtime_guards()
    interval = interval_seconds if interval_seconds is not None else _parse_positive_float_env(
        "RUN_BOT_INTERVAL_SECONDS",
        DEFAULT_INTERVAL_SECONDS,
    )
    loops_limit = max_loops if max_loops is not None else _parse_optional_positive_int_env(
        "RUN_BOT_MAX_LOOPS"
    )

    logger.info(
        "Surekli testnet bot basladi | interval_seconds={} | max_loops={}",
        interval,
        loops_limit or "sonsuz",
    )

    completed_loops = 0
    while True:
        try:
            run_once()
            completed_loops += 1
        except KeyboardInterrupt:
            logger.info("Ctrl+C alindi; bot guvenli sekilde kapaniyor.")
            return 0
        except Exception as exc:
            completed_loops += 1
            logger.exception("Dongu hatasi loglandi; bot bekleyip devam edecek | {}", exc)

        if loops_limit is not None and completed_loops >= loops_limit:
            logger.info("Maksimum dongu tamamlandi | loops={}", completed_loops)
            return 0

        try:
            logger.info("Sonraki dongu icin bekleniyor | seconds={}", interval)
            time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Ctrl+C alindi; bot guvenli sekilde kapaniyor.")
            return 0


def main() -> int:
    return run_loop()


if __name__ == "__main__":
    raise SystemExit(main())
