"""Yapilandirma dogrulama araci.

Ayarlari yukler, dogrular ve sirlari maskeleyerek ozetini basar.
Hata varsa sifir olmayan cikis koduyla sonlanir.

Kullanim:
    python scripts/check_config.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.logger import get_logger
from config.settings import get_settings

logger = get_logger()


def main() -> int:
    try:
        settings = get_settings()
    except Exception as exc:
        logger.error("Yapilandirma HATASI: {}", exc)
        return 1

    logger.info("Yapilandirma gecerli.")
    for key, value in settings.masked_summary().items():
        print(f"  {key:28s} = {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
