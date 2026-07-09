"""Manual daily performance report CLI for Trade_Bot.

Read-only command. It never starts the bot, never sends exchange requests, never
places orders, and never installs timers/cron jobs.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.performance_report import (  # noqa: E402
    DEFAULT_TRADE_LOG_PATHS,
    build_performance_report,
    generate_report_from_files,
    send_telegram_report,
)
from config.settings import get_settings  # noqa: E402


def main() -> int:
    settings = get_settings()
    snapshot = generate_report_from_files(
        settings,
        state_path=settings.state_file,
        trade_log_paths=DEFAULT_TRADE_LOG_PATHS,
    )
    report_text = build_performance_report(snapshot)
    print(report_text, end="")

    if settings.telegram_daily_report_enabled:
        sent = send_telegram_report(settings, report_text)
        print(f"Telegram Daily Report: {'sent' if sent else 'skipped'}")
    else:
        print("Telegram Daily Report: disabled")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
