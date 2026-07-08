"""Execution safety tests for Binance Spot Testnet."""

from __future__ import annotations

import pytest

from bot.execution import ExecutionEngine
from tests.conftest import make_settings


class DummyExchange:
    def __init__(self, urls):
        self.urls = {"api": urls}
        self.created_orders = []
        self.cancelled = []
        self.fetched = []

    def create_order(self, symbol, order_type, side, amount, price=None):
        self.created_orders.append((symbol, order_type, side, amount, price))
        return {"id": "order-1", "symbol": symbol, "status": "open", "filled": 0.0}

    def cancel_order(self, order_id, symbol):
        self.cancelled.append((order_id, symbol))
        return {"id": order_id, "symbol": symbol, "status": "canceled", "filled": 0.0}

    def fetch_order(self, order_id, symbol):
        self.fetched.append((order_id, symbol))
        return {"id": order_id, "symbol": symbol, "status": "canceled", "filled": 0.0}


def test_market_orders_are_disabled_even_in_testnet():
    settings = make_settings(MODE="testnet", ORDER_TYPE="MARKET")
    engine = ExecutionEngine(settings)
    engine._exchange = DummyExchange({"private": "https://testnet.binance.vision/api/v3"})

    with pytest.raises(RuntimeError, match="Market orders are disabled"):
        engine.place_order("BTC/USDT", "buy", 0.001, 100.0, 98.0, 104.0, order_type="market")


def test_testnet_order_requires_testnet_endpoint():
    settings = make_settings(MODE="testnet", ORDER_TYPE="LIMIT")
    engine = ExecutionEngine(settings)
    engine._exchange = DummyExchange({"private": "https://api.binance.com/api/v3"})

    with pytest.raises(RuntimeError, match="testnet.binance.vision"):
        engine.place_order("BTC/USDT", "buy", 0.001, 100.0, 98.0, 104.0)


def test_testnet_limit_order_can_be_created_cancelled_and_fetched():
    settings = make_settings(MODE="testnet", ORDER_TYPE="LIMIT")
    exchange = DummyExchange({"private": "https://testnet.binance.vision/api/v3"})
    engine = ExecutionEngine(settings)
    engine._exchange = exchange

    order = engine.place_order("BTC/USDT", "buy", 0.001, 100.0, 98.0, 104.0)
    assert order["id"] == "order-1"
    assert exchange.created_orders == [("BTC/USDT", "limit", "buy", 0.001, 100.0)]

    canceled = engine.cancel_order("order-1", "BTC/USDT")
    assert canceled["status"] == "canceled"
    assert exchange.cancelled == [("order-1", "BTC/USDT")]

    status = engine.get_order_status("order-1", "BTC/USDT")
    assert status == "canceled"
