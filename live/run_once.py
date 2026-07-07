"""Tek dongu calistirici (gelecekteki VPS giris noktasi).

Bir kez calisir: yapilandirma -> veri -> sinyal -> risk -> emir.
Zamanlanmis calistirma (cron/systemd) sonraki surumde eklenecek.

Guvenlik: MODE=live yalnizca ALLOW_LIVE_TRADING=true ile yuklenebilir
(config/settings.py bunu zorlar) ve ilk surumde canli emir yolu zaten
devre disidir (bot/execution.py NotImplementedError firlatir).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.alerts import send_telegram_alert
from bot.data_provider import DataProvider
from bot.execution import ExecutionEngine
from bot.indicators import add_indicators
from bot.logger import setup_logger
from bot.risk_manager import RiskManager
from bot.state import BotState, Position
from bot.strategy import EmaRsiStrategy
from config.settings import get_settings

logger = setup_logger(log_to_file=True)


def run_once() -> None:
    logger.info("Bot basladi (tek dongu).")
    settings = get_settings()
    logger.info("Yapilandirma yuklendi | {}", settings.masked_summary())

    if settings.is_live:
        logger.warning(
            "MODE=live secildi; ilk surumde gercek emir yolu devre disidir."
        )

    provider = DataProvider(settings)
    strategy = EmaRsiStrategy(
        stop_loss_percent=settings.stop_loss_percent,
        take_profit_percent=settings.take_profit_percent,
    )
    risk_manager = RiskManager(settings)
    execution = ExecutionEngine(settings)
    state = BotState()  # v1: her calistirmada temiz durum

    for symbol in settings.symbols:
        try:
            df = provider.get_ohlcv(symbol, limit=200)
            df = add_indicators(df)
            open_position = state.open_positions.get(symbol)
            signal = strategy.generate_signal(df, symbol, open_position)
            logger.info("Sinyal | {} | {} | {}", symbol, signal.action, signal.reason)

            if signal.action != "BUY":
                continue

            balance = settings.initial_balance  # v1: bakiye takibi basit
            decision = risk_manager.evaluate(signal, state, balance)
            logger.info("Risk karari | {} | {}", symbol, decision.as_dict())
            if not decision.approved:
                continue

            order = execution.place_order(
                symbol=symbol,
                side="buy",
                quantity=decision.position_size,
                price=signal.price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
            )
            state.record_signal(symbol, signal.fingerprint)
            state.open_position(
                Position(
                    symbol=symbol,
                    side="long",
                    entry_price=signal.price,
                    quantity=order["quantity"],
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                )
            )
            send_telegram_alert(
                settings,
                f"{symbol} BUY emri islendi ({settings.mode}): "
                f"{order['quantity']:.6f} @ {signal.price:.4f}",
            )
        except Exception as exc:
            logger.error("{} islenirken hata: {}", symbol, exc)

    logger.info("Bot durdu (tek dongu tamamlandi).")


if __name__ == "__main__":
    run_once()
