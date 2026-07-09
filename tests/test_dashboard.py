"""Terminal dashboard cikti testleri."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from bot.state import BotState, OpenOrder, Position
from config.settings import Settings
from scripts.dashboard import DashboardStateError, build_dashboard, load_dashboard_state


@pytest.fixture
def dashboard_settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        MODE="testnet",
        ALLOW_LIVE_TRADING=False,
        INITIAL_BALANCE=100,
        MAX_CAPITAL_USDT=100,
        MAX_DAILY_LOSS=0.03,
        MAX_DAILY_TRADES=5,
        MAX_API_ERRORS=5,
        TELEGRAM_NOTIFICATIONS_ENABLED=True,
        TELEGRAM_BOT_TOKEN="secret-token-123",
        TELEGRAM_CHAT_ID="987654321",
        BINANCE_API_KEY="live-key-secret",
        BINANCE_API_SECRET="live-secret-value",
        BINANCE_TESTNET_API_KEY="testnet-key-secret",
        BINANCE_TESTNET_API_SECRET="testnet-secret-value",
        STATE_FILE=str(tmp_path / "state.json"),
    )


def render(settings: Settings, state: BotState | None, state_message: str = "ok") -> str:
    return build_dashboard(settings, state, state_message=state_message)


def test_dashboard_runs_when_state_file_missing(dashboard_settings):
    state, state_message = load_dashboard_state(dashboard_settings.state_file)

    output = render(dashboard_settings, state, state_message)

    assert state is None
    assert "Trade_Bot Dashboard" in output
    assert "State File: state bulunamadı" in output
    assert "Mode: testnet" in output


def test_dashboard_reports_controlled_error_for_broken_state(dashboard_settings):
    state_path = dashboard_settings.state_file
    with open(state_path, "w", encoding="utf-8") as handle:
        handle.write("{bozuk-json")

    with pytest.raises(DashboardStateError, match="Dashboard state hatasi"):
        load_dashboard_state(state_path)


def test_dashboard_shows_open_position(dashboard_settings):
    state = BotState()
    state.open_position(
        Position(
            symbol="BTC/USDT",
            side="long",
            entry_price=50000,
            quantity=0.001,
            stop_loss=49000,
            take_profit=52000,
            opened_at="2026-07-09T10:00:00Z",
        )
    )

    output = render(dashboard_settings, state)

    assert "Open Positions: 1" in output
    assert "BTC/USDT long qty=0.001 entry=50000" in output
    assert "stop=49000" in output
    assert "take_profit=52000" in output


def test_dashboard_shows_open_order(dashboard_settings):
    state = BotState()
    state.record_open_order(
        OpenOrder(
            id="order-1",
            symbol="ETH/USDT",
            side="buy",
            order_type="limit",
            price=2500,
            quantity=0.004,
            status="open",
            created_at="2026-07-09T11:00:00Z",
        )
    )

    output = render(dashboard_settings, state)

    assert "Open Orders: 1" in output
    assert "ETH/USDT buy limit qty=0.004 price=2500 status=open" in output


def test_dashboard_never_prints_secrets_or_tokens(dashboard_settings):
    output = render(dashboard_settings, BotState())

    forbidden_values = [
        "secret-token-123",
        "987654321",
        "live-key-secret",
        "live-secret-value",
        "testnet-key-secret",
        "testnet-secret-value",
    ]
    for value in forbidden_values:
        assert value not in output
    assert "Telegram: enabled" in output


def test_dashboard_shows_trading_halted_status(dashboard_settings):
    state = BotState(trading_status="TRADING_HALTED", halt_reason="daily_loss_limit")

    output = render(dashboard_settings, state)

    assert "Trading Status: TRADING_HALTED" in output
    assert "Circuit Breaker: HALTED" in output
    assert "Halt Reason: daily_loss_limit" in output


@pytest.mark.parametrize(
    ("enabled", "expected"),
    [(True, "Telegram: enabled"), (False, "Telegram: disabled")],
)
def test_dashboard_shows_telegram_enabled_or_disabled(tmp_path, enabled, expected):
    settings = Settings(
        _env_file=None,
        MODE="testnet",
        ALLOW_LIVE_TRADING=False,
        STATE_FILE=str(tmp_path / "state.json"),
        TELEGRAM_NOTIFICATIONS_ENABLED=enabled,
    )

    output = render(settings, BotState())

    assert expected in output


def test_dashboard_cli_runs_from_scripts_path(tmp_path):
    env = os.environ.copy()
    env.update(
        {
            "MODE": "testnet",
            "ALLOW_LIVE_TRADING": "false",
            "STATE_FILE": str(tmp_path / "state.json"),
        }
    )

    result = subprocess.run(
        [sys.executable, "scripts/dashboard.py"],
        cwd="/root/Trade_Bot",
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Trade_Bot Dashboard" in result.stdout
    assert "Mode: testnet" in result.stdout
    assert result.stderr == ""
