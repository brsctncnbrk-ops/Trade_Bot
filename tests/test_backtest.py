"""Backtest testleri — tamamen cevrimdisi, API anahtarsiz."""

from __future__ import annotations

import math

from backtests.run_backtest import REQUIRED_METRICS, format_report, run_backtest
from bot.data_provider import generate_sample_data
from tests.conftest import make_settings


def test_backtest_runs_without_api_keys(monkeypatch):
    # clean_env fixture'i tum BINANCE_* degiskenlerini zaten temizliyor;
    # yine de acikca dogrulayalim.
    settings = make_settings(MODE="backtest")
    assert settings.binance_api_key == ""
    metrics = run_backtest(settings=settings)
    assert isinstance(metrics, dict)


def test_backtest_returns_required_metrics():
    metrics = run_backtest(settings=make_settings())
    for key in REQUIRED_METRICS:
        assert key in metrics, f"Eksik metrik: {key}"


def test_backtest_metrics_are_consistent():
    settings = make_settings()
    metrics = run_backtest(settings=settings)
    assert metrics["initial_balance"] == settings.initial_balance
    assert metrics["net_profit"] == metrics["final_balance"] - metrics["initial_balance"]
    assert 0.0 <= metrics["win_rate"] <= 1.0
    assert metrics["max_drawdown"] >= 0.0
    assert metrics["total_trades"] >= 0
    assert not math.isnan(metrics["final_balance"])


def test_backtest_runs_on_generated_sample_data():
    df = generate_sample_data(periods=300, seed=123)
    metrics = run_backtest(settings=make_settings(), df=df)
    assert metrics["total_trades"] >= 0
    assert metrics["final_balance"] > 0


def test_backtest_is_deterministic():
    settings = make_settings()
    first = run_backtest(settings=settings)
    second = run_backtest(settings=settings)
    assert first == second


def test_backtest_produces_trades_on_sample_data():
    # Uretilen veri trend + dongulu; strateji en az bir islem yapmali.
    metrics = run_backtest(settings=make_settings())
    assert metrics["total_trades"] > 0


def test_format_report_contains_all_sections():
    metrics = run_backtest(settings=make_settings())
    report = format_report(metrics, "BTC/USDT")
    for text in (
        "BACKTEST RAPORU",
        "Baslangic bakiyesi",
        "Son bakiye",
        "Net kar/zarar",
        "Toplam islem",
        "Kazanma orani",
        "Maks. dusus",
        "Profit factor",
    ):
        assert text in report
