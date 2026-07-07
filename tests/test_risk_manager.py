"""Risk yoneticisi testleri."""

from __future__ import annotations

import pytest

from bot.risk_manager import RiskManager
from bot.state import BotState, Position
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


@pytest.fixture
def risk_manager():
    return RiskManager(make_settings())


def test_valid_trade_is_approved(risk_manager):
    decision = risk_manager.evaluate(make_signal(), BotState(), balance=1000.0)
    assert decision.approved
    assert decision.position_size > 0


def test_decision_object_shape(risk_manager):
    decision = risk_manager.evaluate(make_signal(), BotState(), balance=1000.0)
    result = decision.as_dict()
    assert set(result) == {"approved", "reason", "position_size"}
    assert isinstance(result["approved"], bool)
    assert isinstance(result["reason"], str)


def test_rejected_without_stop_loss(risk_manager):
    decision = risk_manager.evaluate(
        make_signal(stop_loss=None), BotState(), balance=1000.0
    )
    assert not decision.approved
    assert "Stop-loss" in decision.reason


def test_rejected_without_take_profit(risk_manager):
    decision = risk_manager.evaluate(
        make_signal(take_profit=None), BotState(), balance=1000.0
    )
    assert not decision.approved
    assert "Take-profit" in decision.reason


def test_rejected_when_daily_loss_limit_exceeded(risk_manager):
    state = BotState()
    # initial_balance=1000, max_daily_loss=0.03 -> limit 30
    state.daily_realized_pnl = -35.0
    decision = risk_manager.evaluate(make_signal(), state, balance=1000.0)
    assert not decision.approved
    assert "zarar limiti" in decision.reason


def test_rejected_when_daily_trade_limit_reached(risk_manager):
    state = BotState()
    state.daily_trade_count = 5  # max_daily_trades=5
    decision = risk_manager.evaluate(make_signal(), state, balance=1000.0)
    assert not decision.approved
    assert "islem limiti" in decision.reason


def test_rejected_when_max_open_positions_reached():
    settings = make_settings(MAX_OPEN_POSITIONS=1)
    risk_manager = RiskManager(settings)
    state = BotState()
    state.open_positions["ETH/USDT"] = Position(
        symbol="ETH/USDT",
        side="long",
        entry_price=2000.0,
        quantity=0.1,
        stop_loss=1960.0,
        take_profit=2080.0,
    )
    decision = risk_manager.evaluate(make_signal(), state, balance=1000.0)
    assert not decision.approved
    assert "acik pozisyon" in decision.reason.lower()


def test_rejected_for_second_position_on_same_symbol(risk_manager):
    state = BotState()
    state.open_positions["BTC/USDT"] = Position(
        symbol="BTC/USDT",
        side="long",
        entry_price=100.0,
        quantity=1.0,
        stop_loss=98.0,
        take_profit=104.0,
    )
    decision = risk_manager.evaluate(make_signal(), state, balance=1000.0)
    assert not decision.approved


def test_rejected_on_duplicate_signal(risk_manager):
    state = BotState()
    signal = make_signal()
    state.record_signal(signal.symbol, signal.fingerprint)
    decision = risk_manager.evaluate(signal, state, balance=1000.0)
    assert not decision.approved
    assert "Ayni sinyal" in decision.reason


def test_rejected_on_invalid_price(risk_manager):
    for bad_price in (None, 0.0, -5.0, float("nan")):
        decision = risk_manager.evaluate(
            make_signal(price=bad_price), BotState(), balance=1000.0
        )
        assert not decision.approved, f"price={bad_price} kabul edilmemeliydi"


def test_rejected_on_invalid_balance(risk_manager):
    for bad_balance in (None, 0.0, -100.0, float("nan")):
        decision = risk_manager.evaluate(
            make_signal(), BotState(), balance=bad_balance
        )
        assert not decision.approved, f"balance={bad_balance} kabul edilmemeliydi"


def test_position_size_calculated_correctly():
    settings = make_settings(MAX_RISK_PER_TRADE=0.01)
    risk_manager = RiskManager(settings)
    # risk tutari = 1000 * 0.01 = 10; stop mesafesi = 100 - 98 = 2
    decision = risk_manager.evaluate(
        make_signal(price=100.0, stop_loss=98.0), BotState(), balance=1000.0
    )
    assert decision.approved
    assert decision.position_size == pytest.approx(5.0)


def test_position_size_capped_by_balance():
    settings = make_settings(MAX_RISK_PER_TRADE=0.5)
    risk_manager = RiskManager(settings)
    # risk = 500, stop mesafesi 0.5 -> ham boyut 1000 birim = 100000 USDT!
    decision = risk_manager.evaluate(
        make_signal(price=100.0, stop_loss=99.5), BotState(), balance=1000.0
    )
    assert decision.approved
    # bakiye/fiyat = 10 birimden fazla olamaz
    assert decision.position_size <= 10.0
