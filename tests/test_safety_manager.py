"""Circuit breaker / SafetyManager tests."""

from __future__ import annotations

from bot.safety_manager import SafetyManager
from bot.state import BotState, OpenOrder
from tests.conftest import make_settings


def test_halts_after_three_consecutive_losses():
    state = BotState(consecutive_losses=3)
    manager = SafetyManager(make_settings())

    assert manager.evaluate(state).halted
    assert state.trading_status == "TRADING_HALTED"
    assert "consecutive_losses" in state.halt_reason


def test_halts_after_hourly_loss_limit():
    state = BotState(hourly_realized_pnl=-2.01)
    manager = SafetyManager(make_settings(INITIAL_BALANCE=100, MAX_HOURLY_LOSS=0.02))

    assert manager.evaluate(state).halted
    assert "hourly_loss" in state.halt_reason


def test_halts_after_five_api_errors():
    state = BotState(api_error_count=5)
    manager = SafetyManager(make_settings(MAX_API_ERRORS=5))

    assert manager.evaluate(state).halted
    assert "api_errors" in state.halt_reason


def test_halt_cancels_open_orders_and_sets_state():
    state = BotState()
    state.open_orders["BTC/USDT"] = OpenOrder(
        id="order-1",
        symbol="BTC/USDT",
        side="buy",
        order_type="limit",
        price=100.0,
        quantity=0.1,
        status="open",
    )
    cancelled = []

    def cancel_order(order):
        cancelled.append((order.id, order.symbol))
        return {"status": "canceled", "filled": 0.0}

    manager = SafetyManager(make_settings())
    result = manager.halt(state, "unit_test", cancel_open_order=cancel_order)

    assert result.halted
    assert state.trading_status == "TRADING_HALTED"
    assert state.halt_reason == "unit_test"
    assert cancelled == [("order-1", "BTC/USDT")]
    assert state.open_orders == {}


def test_blocks_when_already_halted():
    state = BotState(trading_status="TRADING_HALTED", halt_reason="manual")
    manager = SafetyManager(make_settings())

    result = manager.ensure_can_trade(state)

    assert result.halted
    assert "manual" in result.reason


def test_production_endpoint_detection_halts():
    state = BotState()
    manager = SafetyManager(make_settings())

    result = manager.check_endpoint(state, {"private": "https://api.binance.com/api/v3"})

    assert result.halted
    assert state.trading_status == "TRADING_HALTED"
    assert "production_endpoint" in state.halt_reason
