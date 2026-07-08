"""Telegram notification system tests."""

from __future__ import annotations

import logging

from types import SimpleNamespace

import pandas as pd

from bot.notifier import NotificationEvent, TelegramNotifier, send_daily_report
from bot.strategy import Signal
from tests.conftest import make_settings


class DummyTransport:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def __call__(self, token, chat_id, text):
        self.calls.append((token, chat_id, text))
        if self.fail:
            raise RuntimeError("network down")
        return True


def test_token_missing_disables_notifications():
    transport = DummyTransport()
    notifier = TelegramNotifier(make_settings(TELEGRAM_NOTIFICATIONS_ENABLED=True), transport=transport)
    event = NotificationEvent(event_type="ORDER CREATED", symbol="BTC/USDT", mode="testnet")
    assert notifier.send(event) is False
    assert transport.calls == []


def test_token_present_formats_and_sends_message():
    transport = DummyTransport()
    settings = make_settings(
        TELEGRAM_NOTIFICATIONS_ENABLED=True,
        TELEGRAM_BOT_TOKEN="secret-token",
        TELEGRAM_CHAT_ID="12345",
        MODE="testnet",
    )
    notifier = TelegramNotifier(settings, transport=transport, now_fn=lambda: 1000.0)
    event = NotificationEvent(
        event_type="ORDER CREATED",
        symbol="BTC/USDT",
        mode=settings.mode,
        price=100.0,
        quantity=0.1,
        pnl=1.2,
        reason="test reason",
        timestamp="2026-07-08T20:00:00+00:00",
    )
    assert notifier.send(event) is True
    _, _, text = transport.calls[0]
    assert "ORDER CREATED" in text
    assert "BTC/USDT" in text
    assert "testnet" in text
    assert "100" in text
    assert "0.1" in text
    assert "1.2" in text
    assert "test reason" in text
    assert "2026-07-08" in text


def test_secret_token_is_not_logged(caplog):
    transport = DummyTransport(fail=True)
    settings = make_settings(
        TELEGRAM_NOTIFICATIONS_ENABLED=True,
        TELEGRAM_BOT_TOKEN="super-secret-token",
        TELEGRAM_CHAT_ID="12345",
    )
    notifier = TelegramNotifier(settings, transport=transport)
    with caplog.at_level(logging.ERROR):
        assert notifier.send(NotificationEvent(event_type="API ERROR", symbol="BTC/USDT", mode="testnet")) is False
    assert "super-secret-token" not in caplog.text


def test_transport_error_does_not_crash_bot():
    transport = DummyTransport(fail=True)
    settings = make_settings(
        TELEGRAM_NOTIFICATIONS_ENABLED=True,
        TELEGRAM_BOT_TOKEN="token",
        TELEGRAM_CHAT_ID="12345",
    )
    notifier = TelegramNotifier(settings, transport=transport)
    assert notifier.send(NotificationEvent(event_type="API ERROR", symbol="BTC/USDT", mode="testnet")) is False


def test_cooldown_blocks_repeated_event():
    transport = DummyTransport()
    settings = make_settings(
        TELEGRAM_NOTIFICATIONS_ENABLED=True,
        TELEGRAM_BOT_TOKEN="token",
        TELEGRAM_CHAT_ID="12345",
        NOTIFICATION_COOLDOWN_SECONDS=30,
    )
    now = {"value": 1000.0}
    notifier = TelegramNotifier(settings, transport=transport, now_fn=lambda: now["value"])
    event = NotificationEvent(event_type="ORDER FILLED", symbol="BTC/USDT", mode="testnet")
    assert notifier.send(event) is True
    assert notifier.send(event) is False
    now["value"] += 31
    assert notifier.send(event) is True
    assert len(transport.calls) == 2


def test_daily_report_message_is_created():
    transport = DummyTransport()
    settings = make_settings(
        TELEGRAM_NOTIFICATIONS_ENABLED=True,
        TELEGRAM_DAILY_REPORT_ENABLED=True,
        TELEGRAM_BOT_TOKEN="token",
        TELEGRAM_CHAT_ID="12345",
        MODE="testnet",
    )
    notifier = TelegramNotifier(settings, transport=transport, now_fn=lambda: 1000.0)
    assert send_daily_report(
        notifier,
        mode=settings.mode,
        total_trades=5,
        win_rate=60.0,
        pnl=2.5,
        profit_factor=1.8,
        max_drawdown=1.1,
        sharpe=0.7,
        expectancy=0.5,
        average_win=1.2,
        average_loss=-0.8,
    ) is True
    text = transport.calls[0][2]
    assert "DAILY REPORT" in text
    assert "Total trades: 5" in text
    assert "Win rate: 60.0" in text
    assert "PnL: 2.5" in text


def test_run_once_sends_order_created_notification(monkeypatch, tmp_path):
    """Order creation must use the new notifier integration, not legacy globals."""
    import live.run_once as run_once_module

    sent_events = []
    settings = make_settings(
        MODE="backtest",
        STATE_FILE=str(tmp_path / "state.json"),
        SYMBOLS="BTC/USDT",
        TELEGRAM_NOTIFICATIONS_ENABLED=True,
        TELEGRAM_BOT_TOKEN="token",
        TELEGRAM_CHAT_ID="12345",
        ENABLE_TRADE_FILTERS=False,
    )

    class FakeNotifier:
        def __init__(self, settings):
            self.settings = settings

        def send(self, event):
            sent_events.append(event)
            return True

    class FakeProvider:
        def __init__(self, settings):
            pass

        def get_ohlcv(self, symbol, limit=200):
            return pd.DataFrame({"close": [100.0], "atr_14": [1.0]})

        def get_ticker(self, symbol):
            return {"bid": 99.9, "ask": 100.1}

    class FakeStrategy:
        def __init__(self, **kwargs):
            pass

        def generate_signal(self, df, symbol, open_position=None):
            return Signal(
                "BUY",
                symbol,
                "test buy",
                price=100.0,
                stop_loss=98.0,
                take_profit=104.0,
                stop_distance=2.0,
            )

    class FakeFilterManager:
        def __init__(self, settings):
            pass

        def evaluate(self, symbol, side, df, bid=None, ask=None):
            return SimpleNamespace(passed=True, as_dict=lambda: {"passed": True})

    class FakeRiskManager:
        def __init__(self, settings):
            pass

        def evaluate(self, signal, state, balance):
            return SimpleNamespace(
                approved=True,
                position_size=0.05,
                risk_amount=0.1,
                reason="approved",
                as_dict=lambda: {"approved": True, "position_size": 0.05},
            )

    class FakeExecution:
        def __init__(self, settings):
            pass

        def place_order(self, *args, **kwargs):
            return {"id": "order-1", "price": 100.0, "quantity": 0.05, "status": "open", "filled": 0.0}

    class FakeSafetyManager:
        def __init__(self, settings):
            pass

        def evaluate(self, state):
            return SimpleNamespace(halted=False, reason="")

        def record_unexpected_exception(self, state, exc, cancel_open_order=None):
            raise AssertionError(f"unexpected exception in run_once: {exc}")

    monkeypatch.setattr(run_once_module, "get_settings", lambda: settings)
    monkeypatch.setattr(run_once_module, "TelegramNotifier", FakeNotifier)
    monkeypatch.setattr(run_once_module, "DataProvider", FakeProvider)
    monkeypatch.setattr(run_once_module, "EmaRsiStrategy", FakeStrategy)
    monkeypatch.setattr(run_once_module, "TradeFilterManager", FakeFilterManager)
    monkeypatch.setattr(run_once_module, "RiskManager", FakeRiskManager)
    monkeypatch.setattr(run_once_module, "ExecutionEngine", FakeExecution)
    monkeypatch.setattr(run_once_module, "SafetyManager", FakeSafetyManager)
    monkeypatch.setattr(run_once_module, "add_indicators", lambda df, trend_ema_period: df)

    run_once_module.run_once()

    assert any(event.event_type == "ORDER CREATED" for event in sent_events)
