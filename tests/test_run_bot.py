from __future__ import annotations

import importlib

import pytest


def import_run_bot():
    return importlib.import_module("live.run_bot")


def test_requires_explicit_testnet_mode(monkeypatch):
    monkeypatch.delenv("MODE", raising=False)
    monkeypatch.setenv("ALLOW_LIVE_TRADING", "false")
    run_bot = import_run_bot()

    with pytest.raises(SystemExit, match="MODE=testnet"):
        run_bot.validate_runtime_guards()


def test_requires_live_trading_disabled(monkeypatch):
    monkeypatch.setenv("MODE", "testnet")
    monkeypatch.setenv("ALLOW_LIVE_TRADING", "true")
    run_bot = import_run_bot()

    with pytest.raises(SystemExit, match="ALLOW_LIVE_TRADING=false"):
        run_bot.validate_runtime_guards()


def test_rejects_market_order_before_loop(monkeypatch):
    monkeypatch.setenv("MODE", "testnet")
    monkeypatch.setenv("ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("ORDER_TYPE", "market")
    run_bot = import_run_bot()

    with pytest.raises(SystemExit, match="ORDER_TYPE=limit"):
        run_bot.validate_runtime_guards()


def test_loop_continues_after_run_once_error(monkeypatch):
    monkeypatch.setenv("MODE", "testnet")
    monkeypatch.setenv("ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("ORDER_TYPE", "limit")
    run_bot = import_run_bot()
    calls = []

    def fake_run_once():
        calls.append("run")
        if len(calls) == 1:
            raise RuntimeError("boom")

    sleeps = []
    monkeypatch.setattr(run_bot, "run_once", fake_run_once)
    monkeypatch.setattr(run_bot.time, "sleep", lambda seconds: sleeps.append(seconds))

    exit_code = run_bot.run_loop(interval_seconds=0.01, max_loops=2)

    assert exit_code == 0
    assert calls == ["run", "run"]
    assert sleeps == [0.01]


def test_ctrl_c_exits_cleanly(monkeypatch):
    monkeypatch.setenv("MODE", "testnet")
    monkeypatch.setenv("ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("ORDER_TYPE", "limit")
    run_bot = import_run_bot()

    monkeypatch.setattr(run_bot, "run_once", lambda: (_ for _ in ()).throw(KeyboardInterrupt()))

    assert run_bot.run_loop(interval_seconds=0.01) == 0
