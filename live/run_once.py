"""Tek dongu calistirici (gelecekteki VPS giris noktasi).

Bir kez calisir: yapilandirma -> kalici state -> veri -> sinyal -> risk -> emir.
Zamanlanmis calistirma (cron/systemd) sonraki surumde eklenecek.

Guvenlik:
- MODE=live yalnizca ALLOW_LIVE_TRADING=true ile yuklenebilir ve ilk surumde
  canli emir yolu devre disidir.
- Testnet emirleri ExecutionEngine tarafinda LIMIT + endpoint assert ile korunur.
- Bot sermayesi Settings/RiskManager tarafinda sanal kasa ve hard-cap ile sinirlanir.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.alerts import send_telegram_alert
from bot.break_even import BreakEvenManager
from bot.data_provider import DataProvider
from bot.execution import ExecutionEngine
from bot.indicators import add_indicators
from bot.logger import setup_logger
from bot.risk_manager import RiskManager
from bot.safety_manager import SafetyManager
from bot.state import BotState, OpenOrder, Position
from bot.strategy import EmaRsiStrategy
from bot.trailing_stop import TrailingStopManager
from bot.trade_filters import TradeFilterManager
from config.settings import get_settings

logger = setup_logger(log_to_file=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_state_or_halt(state_path: Path, safety_manager: SafetyManager) -> BotState:
    try:
        return BotState.load(state_path)
    except Exception as exc:
        state = BotState()
        safety_manager.halt(state, f"state_json_unreadable:{type(exc).__name__}")
        state.save(state_path)
        logger.critical("TRADING HALTED | state.json okunamadi | {}", exc)
        return state


def _cancel_order_callback(execution: ExecutionEngine):
    def _cancel(order: OpenOrder) -> dict:
        return execution.cancel_order(order.id, order.symbol)

    return _cancel


def _cancel_expired_orders(state: BotState, execution: ExecutionEngine, settings) -> None:
    """filled==0 ve timeout'u dolan acik LIMIT emirleri iptal eder."""
    now = time.time()
    for symbol, order in list(state.open_orders.items()):
        created = order.created_at
        try:
            created_epoch = datetime.fromisoformat(created).timestamp() if created else now
        except ValueError:
            created_epoch = now
        if now - created_epoch < settings.open_order_timeout_seconds:
            continue
        result = execution.cancel_if_unfilled_after_timeout(
            order.id,
            symbol,
            created_epoch,
            timeout_seconds=settings.open_order_timeout_seconds,
        )
        if result is None:
            continue
        filled = float(result.get("filled") or 0.0)
        status = result.get("status") or "unknown"
        if filled == 0.0 and status in {"canceled", "cancelled"}:
            state.update_order(symbol, status="canceled", filled=0.0, updated_at=_now_iso())
            state.remove_order(symbol)
            logger.info("ORDER CANCELLED | {} | id={}", symbol, order.id)
        elif filled > 0:
            state.update_order(symbol, status=status, filled=filled, updated_at=_now_iso())
            logger.info("ORDER FILLED | {} | id={} | filled={}", symbol, order.id, filled)


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
        stop_atr_multiplier=settings.stop_atr_multiplier,
        min_stop_distance_percent=settings.min_stop_distance_percent,
        max_stop_distance_percent=settings.max_stop_distance_percent,
        min_risk_reward=settings.min_risk_reward,
    )
    risk_manager = RiskManager(settings)
    filter_manager = TradeFilterManager(settings)
    break_even_manager = BreakEvenManager(settings.break_even_trigger_r)
    trailing_stop_manager = TrailingStopManager(
        activation_r=settings.trailing_stop_activation_r,
        atr_multiplier=settings.trailing_stop_atr_multiplier,
    )
    safety_manager = SafetyManager(settings)
    execution = ExecutionEngine(settings)
    state_path = Path(settings.state_file)
    state = _load_state_or_halt(state_path, safety_manager)

    try:
        decision = safety_manager.evaluate(state)
        if decision.halted:
            logger.critical("TRADING HALTED | {}", decision.reason)
            return
        _cancel_expired_orders(state, execution, settings)
        decision = safety_manager.evaluate(state)
        if decision.halted:
            logger.critical("TRADING HALTED | {}", decision.reason)
            return

        for symbol in settings.symbols:
            try:
                if state.has_open_order(symbol):
                    logger.info("RISK BLOCKED | {} | acik emir var", symbol)
                    continue
                df = provider.get_ohlcv(symbol, limit=200)
                df = add_indicators(df, trend_ema_period=settings.trend_ema_period)
                open_position = state.open_positions.get(symbol)
                if open_position is not None:
                    current_price = float(df.iloc[-1]["close"])
                    atr_value = df.iloc[-1].get("atr_14")
                    break_even_manager.evaluate(state, symbol, current_price)
                    trailing_stop_manager.evaluate(state, symbol, current_price, atr_value)
                    open_position = state.open_positions.get(symbol)
                signal = strategy.generate_signal(df, symbol, open_position)
                logger.info("Sinyal | {} | {} | {}", symbol, signal.action, signal.reason)

                if signal.action != "BUY":
                    if signal.action == "SELL":
                        if "Stop" in signal.reason or "stop" in signal.reason:
                            logger.info("STOP LOSS | {} | {}", symbol, signal.reason)
                        if "Take" in signal.reason or "take" in signal.reason:
                            logger.info("TAKE PROFIT | {} | {}", symbol, signal.reason)
                    continue

                ticker = provider.get_ticker(symbol)
                filter_decision = filter_manager.evaluate(
                    symbol,
                    signal.action,
                    df,
                    bid=ticker.get("bid"),
                    ask=ticker.get("ask"),
                )
                if not filter_decision.passed:
                    logger.info("RISK BLOCKED | {} | {}", symbol, filter_decision.as_dict())
                    continue

                # Hard-cap: testnet hesabi yuksek olsa bile sanal kasa kullanilir.
                balance = min(settings.initial_balance, settings.max_capital_usdt)
                decision = risk_manager.evaluate(signal, state, balance)
                logger.info("Risk karari | {} | {}", symbol, decision.as_dict())
                if not decision.approved:
                    logger.info("RISK BLOCKED | {} | {}", symbol, decision.reason)
                    continue

                safety_decision = safety_manager.evaluate(state)
                if safety_decision.halted:
                    logger.critical("TRADING HALTED | {}", safety_decision.reason)
                    break

                order = execution.place_order(
                    symbol=symbol,
                    side="buy",
                    quantity=decision.position_size,
                    price=signal.price,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    order_type=settings.order_type,
                )
                order_id = str(order.get("id"))
                state.record_signal(symbol, signal.fingerprint)
                state.record_open_order(
                    OpenOrder(
                        id=order_id,
                        symbol=symbol,
                        side="buy",
                        order_type="limit",
                        price=float(order.get("price") or signal.price),
                        quantity=float(order.get("quantity") or decision.position_size),
                        status=order.get("status") or "open",
                        filled=float(order.get("filled") or 0.0),
                        created_at=_now_iso(),
                        stop_loss=signal.stop_loss,
                        take_profit=signal.take_profit,
                        risk_amount=decision.risk_amount,
                    )
                )
                logger.info("ORDER CREATED | {} | id={}", symbol, order_id)

                # Backtest emirleri simule filled gelir; pozisyonu state'e isleyelim.
                if settings.is_backtest and float(order.get("filled") or 0.0) > 0:
                    state.remove_order(symbol)
                    state.open_position(
                        Position(
                            symbol=symbol,
                            side="long",
                            entry_price=signal.price,
                            quantity=float(order["quantity"]),
                            stop_loss=signal.stop_loss,
                            take_profit=signal.take_profit,
                            opened_at=_now_iso(),
                        )
                    )
                    logger.info("ORDER FILLED | {} | id={}", symbol, order_id)

                send_telegram_alert(
                    settings,
                    f"{symbol} BUY LIMIT emri islendi ({settings.mode}): "
                    f"{decision.position_size:.6f} @ {signal.price:.4f}",
                )
            except Exception as exc:
                logger.error("{} islenirken hata: {}", symbol, exc)
                safety_manager.record_unexpected_exception(
                    state,
                    exc,
                    cancel_open_order=_cancel_order_callback(execution),
                )
                break
    finally:
        state.save(state_path)
        logger.info("State kaydedildi | {}", state_path)

    logger.info("Bot durdu (tek dongu tamamlandi).")


if __name__ == "__main__":
    run_once()
