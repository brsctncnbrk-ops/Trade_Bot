"""ATR Trailing Stop system tests."""

from __future__ import annotations

import pytest

from bot.state import BotState, Position
from bot.trailing_stop import TrailingStopManager
from tests.conftest import make_settings


def make_position(**overrides):
    data = dict(
        symbol="BTC/USDT",
        side="long",
        entry_price=100.0,
        quantity=0.1,
        stop_loss=100.0,
        take_profit=108.0,
        original_stop_loss=96.0,
        current_stop_loss=100.0,
        break_even_activated=True,
        highest_price_seen=100.0,
    )
    data.update(overrides)
    return Position(**data)


def test_trailing_not_active_before_2r():
    state = BotState(open_positions={"BTC/USDT": make_position()})
    result = TrailingStopManager(activation_r=2.0, atr_multiplier=2.0).evaluate(
        state, "BTC/USDT", current_price=107.99, atr=2.0
    )
    position = state.open_positions["BTC/USDT"]
    assert not result.activated
    assert position.trailing_stop_activated is False
    assert position.trailing_stop_price is None


def test_trailing_activates_after_2r():
    state = BotState(open_positions={"BTC/USDT": make_position()})
    result = TrailingStopManager(activation_r=2.0, atr_multiplier=2.0).evaluate(
        state, "BTC/USDT", current_price=108.0, atr=2.0
    )
    position = state.open_positions["BTC/USDT"]
    assert result.activated
    assert position.trailing_stop_activated is True
    assert position.trailing_activation_price == pytest.approx(108.0)


def test_atr_trailing_stop_is_calculated():
    state = BotState(open_positions={"BTC/USDT": make_position()})
    TrailingStopManager(activation_r=2.0, atr_multiplier=2.0).evaluate(
        state, "BTC/USDT", current_price=110.0, atr=2.0
    )
    position = state.open_positions["BTC/USDT"]
    # New stop = 110 - 2 * 2 = 106.
    assert position.trailing_stop_price == pytest.approx(106.0)
    assert position.current_stop_loss == pytest.approx(106.0)
    assert position.stop_loss == pytest.approx(106.0)


def test_trailing_stop_never_moves_down():
    position = make_position(
        trailing_stop_activated=True,
        trailing_activation_price=108.0,
        trailing_stop_price=106.0,
        current_stop_loss=106.0,
        stop_loss=106.0,
        highest_price_seen=110.0,
    )
    state = BotState(open_positions={"BTC/USDT": position})
    result = TrailingStopManager(activation_r=2.0, atr_multiplier=2.0).evaluate(
        state, "BTC/USDT", current_price=109.0, atr=2.0
    )
    position = state.open_positions["BTC/USDT"]
    assert not result.updated
    assert position.current_stop_loss == pytest.approx(106.0)
    assert position.trailing_stop_price == pytest.approx(106.0)


def test_trailing_stop_never_drops_below_break_even():
    state = BotState(open_positions={"BTC/USDT": make_position()})
    TrailingStopManager(activation_r=2.0, atr_multiplier=10.0).evaluate(
        state, "BTC/USDT", current_price=108.0, atr=2.0
    )
    position = state.open_positions["BTC/USDT"]
    assert position.current_stop_loss == pytest.approx(100.0)
    assert position.trailing_stop_price == pytest.approx(100.0)


def test_highest_price_seen_updates():
    state = BotState(open_positions={"BTC/USDT": make_position(highest_price_seen=101.0)})
    TrailingStopManager(activation_r=2.0, atr_multiplier=2.0).evaluate(
        state, "BTC/USDT", current_price=111.0, atr=2.0
    )
    assert state.open_positions["BTC/USDT"].highest_price_seen == pytest.approx(111.0)


def test_trailing_invalid_without_atr():
    state = BotState(open_positions={"BTC/USDT": make_position()})
    result = TrailingStopManager(activation_r=2.0, atr_multiplier=2.0).evaluate(
        state, "BTC/USDT", current_price=110.0, atr=None
    )
    assert not result.activated
    assert result.invalid
    assert "ATR" in result.reason


def test_trailing_skips_when_no_position():
    state = BotState()
    result = TrailingStopManager(activation_r=2.0, atr_multiplier=2.0).evaluate(
        state, "BTC/USDT", current_price=110.0, atr=2.0
    )
    assert not result.activated
    assert not result.invalid
    assert "pozisyon" in result.reason.lower()


def test_trailing_state_round_trip(tmp_path):
    path = tmp_path / "state.json"
    state = BotState(open_positions={"BTC/USDT": make_position()})
    TrailingStopManager(activation_r=2.0, atr_multiplier=2.0).evaluate(
        state, "BTC/USDT", current_price=110.0, atr=2.0
    )
    state.save(path)
    loaded = BotState.load(path)
    position = loaded.open_positions["BTC/USDT"]
    assert position.trailing_stop_activated is True
    assert position.trailing_activation_price == pytest.approx(108.0)
    assert position.trailing_stop_price == pytest.approx(106.0)
    assert position.highest_price_seen == pytest.approx(110.0)


def test_trailing_settings_are_configurable():
    settings = make_settings(TRAILING_STOP_ACTIVATION_R=2.5, TRAILING_STOP_ATR_MULTIPLIER=3.0)
    assert settings.trailing_stop_activation_r == 2.5
    assert settings.trailing_stop_atr_multiplier == 3.0
