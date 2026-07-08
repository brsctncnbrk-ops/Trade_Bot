"""100 USDT testnet risk hard-cap tests."""

from __future__ import annotations

import pytest

from bot.risk_manager import RiskManager
from bot.state import BotState, OpenOrder, Position
from bot.strategy import Signal
from tests.conftest import make_settings


def make_signal(price=100.0, stop_loss=98.0, take_profit=104.0):
    return Signal(
        action="BUY",
        symbol="BTC/USDT",
        reason="test",
        price=price,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )


def test_effective_balance_is_capped_at_max_capital():
    settings = make_settings(
        INITIAL_BALANCE=100,
        MAX_CAPITAL_USDT=100,
        MAX_RISK_PER_TRADE=0.01,
        MAX_NOTIONAL_PER_TRADE_USDT=10,
    )
    decision = RiskManager(settings).evaluate(
        make_signal(price=100.0, stop_loss=99.0), BotState(), balance=1_000_000.0
    )
    assert decision.approved
    # Risk cap: 100 USDT * 1% = 1 USDT; stop distance = 1 -> 1 unit raw,
    # then notional cap clamps to 10 USDT / 100 = 0.1 unit.
    assert decision.position_size == pytest.approx(0.1)
    assert decision.notional == pytest.approx(10.0)
    assert decision.risk_amount <= 1.0


def test_rejects_when_symbol_has_open_order():
    settings = make_settings()
    state = BotState()
    state.open_orders["BTC/USDT"] = OpenOrder(
        id="abc",
        symbol="BTC/USDT",
        side="buy",
        order_type="limit",
        price=90.0,
        quantity=0.1,
        status="open",
    )
    decision = RiskManager(settings).evaluate(make_signal(), state, balance=100.0)
    assert not decision.approved
    assert "acik emir" in decision.reason.lower()


def test_rejects_when_max_concurrent_orders_reached():
    settings = make_settings(MAX_CONCURRENT_ORDERS=1)
    state = BotState()
    state.open_orders["ETH/USDT"] = OpenOrder(
        id="eth-order",
        symbol="ETH/USDT",
        side="buy",
        order_type="limit",
        price=1000.0,
        quantity=0.01,
        status="open",
    )
    decision = RiskManager(settings).evaluate(make_signal(), state, balance=100.0)
    assert not decision.approved
    assert "acik emir" in decision.reason.lower()


def test_total_open_risk_limit_blocks_new_trade():
    settings = make_settings(MAX_TOTAL_OPEN_RISK_USDT=1, MAX_OPEN_POSITIONS=2)
    state = BotState()
    state.open_positions["ETH/USDT"] = Position(
        symbol="ETH/USDT",
        side="long",
        entry_price=100.0,
        quantity=1.0,
        stop_loss=99.0,
        take_profit=110.0,
    )
    decision = RiskManager(settings).evaluate(make_signal(), state, balance=100.0)
    assert not decision.approved
    assert "toplam acik risk" in decision.reason.lower()


def test_daily_loss_limit_uses_virtual_initial_balance():
    settings = make_settings(INITIAL_BALANCE=100, MAX_DAILY_LOSS=0.03)
    state = BotState(daily_realized_pnl=-3.01)
    decision = RiskManager(settings).evaluate(make_signal(), state, balance=1_000_000.0)
    assert not decision.approved
    assert "zarar limiti" in decision.reason
