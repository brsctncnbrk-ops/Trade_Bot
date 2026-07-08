"""Backtest calistiricisi.

Akis: veri -> gostergeler -> sinyal -> risk yoneticisi -> simule emir ->
portfoy takibi -> metrik raporu.

Binance API anahtari GEREKTIRMEZ; backtest modunda deterministik ornek
veri ile cevrimdisi calisir.

Kullanim:
    python backtests/run_backtest.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.data_provider import DataProvider
from bot.execution import ExecutionEngine
from bot.indicators import add_indicators
from bot.logger import get_logger
from bot.risk_manager import RiskManager
from bot.state import BotState, Position
from bot.strategy import EmaRsiStrategy
from config.settings import Settings, get_settings

logger = get_logger()

REPORT_FILE = "backtest_report.txt"

REQUIRED_METRICS = [
    "initial_balance",
    "final_balance",
    "net_profit",
    "total_trades",
    "win_rate",
    "max_drawdown",
    "profit_factor",
    "avg_trade_return",
    "largest_loss",
    "largest_win",
]


def _calculate_metrics(
    initial_balance: float, equity_curve: list, trade_pnls: list
) -> dict:
    final_balance = equity_curve[-1] if equity_curve else initial_balance
    wins = [p for p in trade_pnls if p > 0]
    losses = [p for p in trade_pnls if p <= 0]

    equity = pd.Series(equity_curve if equity_curve else [initial_balance])
    running_max = equity.cummax()
    drawdowns = (equity - running_max) / running_max
    max_drawdown = float(-drawdowns.min()) if len(drawdowns) else 0.0

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    else:
        profit_factor = float("inf") if gross_profit > 0 else 0.0

    return {
        "initial_balance": initial_balance,
        "final_balance": final_balance,
        "net_profit": final_balance - initial_balance,
        "total_trades": len(trade_pnls),
        "win_rate": (len(wins) / len(trade_pnls)) if trade_pnls else 0.0,
        "max_drawdown": max_drawdown,
        "profit_factor": profit_factor,
        "avg_trade_return": (sum(trade_pnls) / len(trade_pnls)) if trade_pnls else 0.0,
        "largest_loss": min(trade_pnls) if trade_pnls else 0.0,
        "largest_win": max(trade_pnls) if trade_pnls else 0.0,
    }


def run_backtest(
    settings: Optional[Settings] = None,
    df: Optional[pd.DataFrame] = None,
    symbol: Optional[str] = None,
) -> dict:
    """Tek sembol uzerinde backtest calistirir ve metrik sozlugu dondurur."""
    if settings is None:
        settings = get_settings(MODE="backtest")
    symbol = symbol or settings.symbols[0]

    logger.info("Backtest basladi | {} | mod={}", symbol, settings.mode)

    if df is None:
        provider = DataProvider(settings)
        df = provider.get_ohlcv(symbol, limit=500)

    df = add_indicators(df, trend_ema_period=settings.trend_ema_period)

    strategy = EmaRsiStrategy(
        stop_loss_percent=settings.stop_loss_percent,
        take_profit_percent=settings.take_profit_percent,
        stop_atr_multiplier=settings.stop_atr_multiplier,
        min_stop_distance_percent=settings.min_stop_distance_percent,
        max_stop_distance_percent=settings.max_stop_distance_percent,
        min_risk_reward=settings.min_risk_reward,
    )
    risk_manager = RiskManager(settings)
    execution = ExecutionEngine(settings)
    state = BotState()

    balance = settings.initial_balance
    equity_curve: list = [balance]
    trade_pnls: list = []
    last_day = None

    warmup = 50  # EMA50 olusana kadar sinyal aranmaz
    for i in range(warmup, len(df)):
        window = df.iloc[: i + 1]
        row = window.iloc[-1]

        # Gunluk sayaclari yeni gunde sifirla
        current_day = pd.Timestamp(row["timestamp"]).date()
        if last_day is not None and current_day != last_day:
            state.reset_daily()
        last_day = current_day

        open_position = state.open_positions.get(symbol)
        signal = strategy.generate_signal(window, symbol, open_position)

        if signal.action == "BUY":
            decision = risk_manager.evaluate(signal, state, balance)
            if not decision.approved:
                continue
            order = execution.place_order(
                symbol=symbol,
                side="buy",
                quantity=decision.position_size,
                price=signal.price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
            )
            state.record_signal(symbol, signal.fingerprint)
            state.open_position(
                Position(
                    symbol=symbol,
                    side="long",
                    entry_price=signal.price,
                    quantity=order["quantity"],
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    opened_at=str(row["timestamp"]),
                )
            )
            balance -= signal.price * order["quantity"]

        elif signal.action == "SELL" and open_position is not None:
            exit_price = signal.price
            execution.place_order(
                symbol=symbol,
                side="sell",
                quantity=open_position.quantity,
                price=exit_price,
            )
            pnl = (exit_price - open_position.entry_price) * open_position.quantity
            balance += exit_price * open_position.quantity
            state.close_position(symbol, pnl)
            trade_pnls.append(pnl)

        # Portfoy degeri: nakit + acik pozisyonun anlik degeri
        position_value = 0.0
        current = state.open_positions.get(symbol)
        if current is not None:
            position_value = current.quantity * float(row["close"])
        equity_curve.append(balance + position_value)

    # Backtest sonunda acik pozisyonu son fiyattan kapat
    remaining = state.open_positions.get(symbol)
    if remaining is not None:
        last_close = float(df.iloc[-1]["close"])
        pnl = (last_close - remaining.entry_price) * remaining.quantity
        balance += last_close * remaining.quantity
        state.close_position(symbol, pnl)
        trade_pnls.append(pnl)
        equity_curve.append(balance)
        logger.info("Backtest sonu: acik pozisyon son fiyattan kapatildi.")

    metrics = _calculate_metrics(settings.initial_balance, equity_curve, trade_pnls)
    logger.info("Backtest tamamlandi | {} islem", metrics["total_trades"])
    return metrics


def format_report(metrics: dict, symbol: str = "") -> str:
    pf = metrics["profit_factor"]
    pf_text = "inf" if pf == float("inf") else f"{pf:.2f}"
    lines = [
        "==============================================",
        f" BACKTEST RAPORU {('- ' + symbol) if symbol else ''}",
        "==============================================",
        f" Baslangic bakiyesi : {metrics['initial_balance']:.2f}",
        f" Son bakiye         : {metrics['final_balance']:.2f}",
        f" Net kar/zarar      : {metrics['net_profit']:.2f}",
        f" Toplam islem       : {metrics['total_trades']}",
        f" Kazanma orani      : {metrics['win_rate'] * 100:.1f}%",
        f" Maks. dusus (DD)   : {metrics['max_drawdown'] * 100:.2f}%",
        f" Profit factor      : {pf_text}",
        f" Ort. islem getirisi: {metrics['avg_trade_return']:.2f}",
        f" En buyuk zarar     : {metrics['largest_loss']:.2f}",
        f" En buyuk kazanc    : {metrics['largest_win']:.2f}",
        "==============================================",
    ]
    return "\n".join(lines)


def main() -> None:
    settings = get_settings(MODE="backtest")
    logger.info("Yapilandirma yuklendi | {}", settings.masked_summary())

    reports = []
    for symbol in settings.symbols:
        metrics = run_backtest(settings=settings, symbol=symbol)
        report = format_report(metrics, symbol)
        print(report)
        reports.append(report)

    Path(REPORT_FILE).write_text("\n\n".join(reports), encoding="utf-8")
    logger.info("Rapor dosyaya yazildi | {}", REPORT_FILE)


if __name__ == "__main__":
    main()
