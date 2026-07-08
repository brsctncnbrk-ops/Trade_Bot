"""Break Even system tests."""

from __future__ import annotations

import pytest

from bot.break_even import BreakEvenManager
from bot.state import BotState, Position
from tests.conftest import make_settings


def make_position(**overrides):
    data = dict(
        symbol="BTC/USDT",
        side="long",
        entry_price=100.0,
        quantity=0.1,
        stop_loss=96.0,
        take_profit=108.0,
    )
    data.update(overrides)
    return Position(**data)


def test_break_even_activates_when_buy_reaches_1r():
    state = BotState(open_positions={"BTC/USDT": make_position()})
    manager = BreakEvenManager(trigger_r=1.0)
    result = manager.evaluate(state, "BTC/USDT", current_price=104.0)
    position = state.open_positions["BTC/USDT"]
    assert result.activated
    assert position.break_even_activated is True
    assert position.current_stop_loss == pytest.approx(100.0)
    assert position.stop_loss == pytest.approx(100.0)
    assert position.break_even_price == pytest.approx(104.0)
    assert position.original_stop_loss == pytest.approx(96.0)


def test_break_even_does_not_activate_before_1r():
    state = BotState(open_positions={"BTC/USDT": make_position()})
    result = BreakEvenManager(trigger_r=1.0).evaluate(state, "BTC/USDT", current_price=103.99)
    position = state.open_positions["BTC/USDT"]
    assert not result.activated
    assert position.break_even_activated is False
    assert position.current_stop_loss == pytest.approx(96.0)


def test_break_even_only_activates_once():
    position = make_position(
        break_even_activated=True,
        break_even_price=104.0,
        original_stop_loss=96.0,
        current_stop_loss=100.0,
        stop_loss=100.0,
    )
    state = BotState(open_positions={"BTC/USDT": position})
    result = BreakEvenManager(trigger_r=1.0).evaluate(state, "BTC/USDT", current_price=110.0)
    assert not result.activated
    assert "zaten" in result.reason.lower()
    assert state.open_positions["BTC/USDT"].current_stop_loss == pytest.approx(100.0)


def test_break_even_invalid_without_stop_loss():
    state = BotState(open_positions={"BTC/USDT": make_position(stop_loss=None, current_stop_loss=None)})
    result = BreakEvenManager(trigger_r=1.0).evaluate(state, "BTC/USDT", current_price=110.0)
    assert not result.activated
    assert result.invalid
    assert "stop" in result.reason.lower()


def test_break_even_skips_when_no_position():
    state = BotState()
    result = BreakEvenManager(trigger_r=1.0).evaluate(state, "BTC/USDT", current_price=110.0)
    assert not result.activated
    assert not result.invalid
    assert "pozisyon" in result.reason.lower()


def test_break_even_state_round_trip(tmp_path):
    path = tmp_path / "state.json"
    state = BotState(open_positions={"BTC/USDT": make_position()})
    BreakEvenManager(trigger_r=1.0).evaluate(state, "BTC/USDT", current_price=104.0)
    state.save(path)
    loaded = BotState.load(path)
    position = loaded.open_positions["BTC/USDT"]
    assert position.break_even_activated is True
    assert position.break_even_price == pytest.approx(104.0)
    assert position.original_stop_loss == pytest.approx(96.0)
    assert position.current_stop_loss == pytest.approx(100.0)


def test_sell_break_even_infrastructure_ready():
    position = make_position(side="short", entry_price=100.0, stop_loss=104.0, take_profit=92.0)
    state = BotState(open_positions={"BTC/USDT": position})
    result = BreakEvenManager(trigger_r=1.0).evaluate(state, "BTC/USDT", current_price=96.0)
    position = state.open_positions["BTC/USDT"]
    assert result.activated
    assert position.current_stop_loss == pytest.approx(100.0)
    assert position.stop_loss == pytest.approx(100.0)


def test_break_even_setting_is_configurable():
    settings = make_settings(BREAK_EVEN_TRIGGER_R=1.5)
    assert settings.break_even_trigger_r == 1.5
