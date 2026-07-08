"""Persistent bot state tests."""

from __future__ import annotations

from bot.state import BotState, OpenOrder, Position


def test_state_round_trips_to_json_file(tmp_path):
    path = tmp_path / "state.json"
    state = BotState(
        daily_realized_pnl=-1.5,
        daily_trade_count=2,
        last_trade_at="2026-07-08T12:00:00+00:00",
    )
    state.open_orders["BTC/USDT"] = OpenOrder(
        id="order-1",
        symbol="BTC/USDT",
        side="buy",
        order_type="limit",
        price=100.0,
        quantity=0.1,
        status="open",
        created_at="2026-07-08T12:00:00+00:00",
    )
    state.open_positions["ETH/USDT"] = Position(
        symbol="ETH/USDT",
        side="long",
        entry_price=1000.0,
        quantity=0.01,
        stop_loss=980.0,
        take_profit=1040.0,
        opened_at="2026-07-08T12:00:00+00:00",
    )

    state.save(path)
    loaded = BotState.load(path)

    assert loaded.daily_realized_pnl == -1.5
    assert loaded.daily_trade_count == 2
    assert loaded.last_trade_at == "2026-07-08T12:00:00+00:00"
    assert loaded.open_orders["BTC/USDT"].id == "order-1"
    assert loaded.open_positions["ETH/USDT"].quantity == 0.01


def test_missing_state_file_loads_empty_state(tmp_path):
    state = BotState.load(tmp_path / "missing.json")
    assert state.daily_trade_count == 0
    assert state.open_orders == {}
    assert state.open_positions == {}
