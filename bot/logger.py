"""Loglama altyapisi (loguru).

Tum moduller logger'i buradan alir. API sirlari asla loglanmaz;
`mask_secret()` yardimcisi hassas degerleri maskelemek icin kullanilir.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

_configured = False


def mask_secret(value: str) -> str:
    """Hassas bir degeri log icin guvenli hale getirir."""
    if not value:
        return "(bos)"
    if len(value) <= 4:
        return "***"
    return f"{value[:3]}***{value[-1]}"


def setup_logger(log_to_file: bool = False, log_dir: str = "logs") -> "logger.__class__":
    """Logger'i yapilandirir. Tekrarli cagrilarda yeniden kurulum yapmaz."""
    global _configured
    if _configured:
        return logger

    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan> - <level>{message}</level>"
        ),
    )
    if log_to_file:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        logger.add(
            f"{log_dir}/bot.log",
            level="DEBUG",
            rotation="10 MB",
            retention="14 days",
        )
    _configured = True
    return logger


def get_logger():
    """Yapilandirilmis logger'i dondurur (gerekirse kurar)."""
    return setup_logger()
