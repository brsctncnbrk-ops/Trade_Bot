from __future__ import annotations

import json

import pytest

from bot.state import BotState, OpenOrder, Position
from config.settings import Settings
from tests.conftest import make_settings


@pytest.fixture
def report_settings(tmp_path) -> Settings:
    return make_settings(
        MODE="testnet",
        ALLOW_LIVE_TRADING=False,
        INITIAL_BALANCE=100,
        MAX_DAILY_TRADES=5,
        MAX_DAILY_LOSS=0.03,
        STATE_FILE=str(tmp_path / "state.json"),
        TELEGRAM_NOTIFICATIONS_ENABLED=True,
        TELEGRAM_DAILY_REPORT_ENABLED=True,
        TELEGRAM_BOT_TOKEN="secret-token-123",
        TELEGRAM_CHAT_ID="987654321",
        NOTIFICATION_COOLDOWN_SECONDS=0,
    )


def test_empty_state_creates_no_data_report(report_settings):
    from bot.performance_report import build_performance_report, generate_performance_report

    snapshot = generate_performance_report(report_settings, state=None, trades=[])
    output = build_performance_report(snapshot)

    assert snapshot.no_data is True
    assert "Veri Durumu: veri yok" in output
    assert "Toplam İşlem Sayısı: 0" in output
    assert "Mode: testnet" in output
    assert "Live Trading: false" in output


def test_profitable_trades_calculate_win_rate(report_settings):
    from bot.performance_report import generate_performance_report

    snapshot = generate_performance_report(
        report_settings,
        state=BotState(),
        trades=[{"pnl": 10}, {"pnl": -5}, {"pnl": 15}],
    )

    assert snapshot.total_trades == 3
    assert snapshot.winning_trades == 2
    assert snapshot.losing_trades == 1
    assert snapshot.win_rate == pytest.approx(66.6667)
    assert snapshot.net_pnl == pytest.approx(20)
    assert snapshot.gross_profit == pytest.approx(25)


def test_losing_trades_calculate_max_drawdown(report_settings):
    from bot.performance_report import generate_performance_report

    snapshot = generate_performance_report(
        report_settings,
        state=BotState(),
        trades=[{"pnl": -5}, {"pnl": -10}, {"pnl": 2}],
    )

    assert snapshot.gross_loss == pytest.approx(-15)
    assert snapshot.max_drawdown == pytest.approx(15)


def test_profit_factor_is_gross_profit_divided_by_absolute_gross_loss(report_settings):
    from bot.performance_report import generate_performance_report

    snapshot = generate_performance_report(
        report_settings,
        state=BotState(),
        trades=[{"pnl": 12}, {"pnl": 8}, {"pnl": -5}],
    )

    assert snapshot.profit_factor == pytest.approx(4.0)


def test_expectancy_is_average_pnl_per_trade(report_settings):
    from bot.performance_report import generate_performance_report

    snapshot = generate_performance_report(
        report_settings,
        state=BotState(),
        trades=[{"pnl": 10}, {"pnl": -4}, {"pnl": -2}],
    )

    assert snapshot.average_win == pytest.approx(10)
    assert snapshot.average_loss == pytest.approx(-3)
    assert snapshot.expectancy == pytest.approx(4 / 3)


def test_sharpe_ratio_uses_trade_pnl_distribution(report_settings):
    from bot.performance_report import generate_performance_report

    snapshot = generate_performance_report(
        report_settings,
        state=BotState(),
        trades=[{"pnl": 1}, {"pnl": 2}, {"pnl": 3}],
    )

    assert snapshot.sharpe_ratio == pytest.approx(3.4641016)


def test_telegram_report_does_not_include_token_or_chat_id(report_settings):
    from bot.performance_report import build_performance_report, generate_performance_report, send_telegram_report

    sent_messages: list[str] = []

    def capture_transport(token: str, chat_id: str, text: str) -> bool:
        sent_messages.append(text)
        return True

    snapshot = generate_performance_report(
        report_settings,
        state=BotState(),
        trades=[{"pnl": 7}, {"pnl": -2}],
    )
    report_text = build_performance_report(snapshot)

    assert "secret-token-123" not in report_text
    assert "987654321" not in report_text
    assert send_telegram_report(report_settings, report_text, transport=capture_transport) is True
    assert sent_messages
    assert "secret-token-123" not in sent_messages[0]
    assert "987654321" not in sent_messages[0]


def test_circuit_breaker_status_enters_report(report_settings):
    from bot.performance_report import build_performance_report, generate_performance_report

    state = BotState(trading_status="TRADING_HALTED", halt_reason="daily_loss_limit")
    state.open_positions["BTC/USDT"] = Position(
        symbol="BTC/USDT",
        side="long",
        entry_price=100,
        quantity=0.1,
        stop_loss=95,
        take_profit=110,
    )
    state.open_orders["ETH/USDT"] = OpenOrder(
        id="order-1",
        symbol="ETH/USDT",
        side="buy",
        order_type="limit",
        price=50,
        quantity=0.2,
        status="open",
    )

    snapshot = generate_performance_report(report_settings, state=state, trades=[])
    output = build_performance_report(snapshot)

    assert snapshot.circuit_breaker_status == "HALTED"
    assert "Circuit Breaker Durumu: HALTED" in output
    assert "Halt Sebebi: daily_loss_limit" in output
    assert "Açık Pozisyon Sayısı: 1" in output
    assert "Açık Emir Sayısı: 1" in output


def test_report_can_load_state_and_trade_logs_from_files(report_settings, tmp_path):
    from bot.performance_report import generate_report_from_files

    state_path = tmp_path / "state.json"
    BotState(daily_realized_pnl=-1.5, daily_trade_count=2).save(state_path)
    trade_log_path = tmp_path / "trades.jsonl"
    trade_log_path.write_text(
        "\n".join([json.dumps({"pnl": 5}), json.dumps({"realized_pnl": -2})]),
        encoding="utf-8",
    )

    snapshot = generate_report_from_files(
        report_settings,
        state_path=state_path,
        trade_log_paths=[trade_log_path],
    )

    assert snapshot.total_trades == 2
    assert snapshot.net_pnl == pytest.approx(3)
    assert snapshot.state_message == "ok"
