"""Read-only performance report generation for Trade_Bot.

This module only reads state/trade-log files and optionally sends the rendered
report to Telegram when explicitly called. It never starts trading, never talks
to an exchange, and never exposes secret/token/chat_id values.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, stdev
from typing import Callable, Iterable, Optional, Sequence

from bot.notifier import NotificationEvent, TelegramNotifier
from bot.state import BotState
from config.settings import Settings

PNL_KEYS = ("pnl", "realized_pnl", "profit", "profit_loss", "net_pnl")
DEFAULT_TRADE_LOG_PATHS = (
    "logs/trades.jsonl",
    "logs/trades.json",
    "logs/trade_log.jsonl",
    "logs/trade_log.json",
    "trades.jsonl",
    "trades.json",
    "trades.csv",
)


@dataclass(frozen=True)
class PerformanceSnapshot:
    mode: str
    allow_live_trading: bool
    state_message: str
    no_data: bool
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    net_pnl: float
    gross_profit: float
    gross_loss: float
    profit_factor: float
    max_drawdown: float
    average_win: float
    average_loss: float
    expectancy: float
    sharpe_ratio: float
    daily_trade_limit_usage: float
    daily_loss_limit_usage: float
    circuit_breaker_status: str
    halt_reason: str
    open_position_count: int
    open_order_count: int
    daily_trade_count: int
    max_daily_trades: int
    daily_realized_pnl: float
    daily_loss_limit_amount: float


def _to_float(value: object) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_trade_pnls(trades: Iterable[dict]) -> list[float]:
    """Extract realized PnL values from flexible trade-log dictionaries."""

    pnls: list[float] = []
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        for key in PNL_KEYS:
            pnl = _to_float(trade.get(key))
            if pnl is not None:
                pnls.append(pnl)
                break
    return pnls


def calculate_max_drawdown(pnls: Sequence[float]) -> float:
    """Return absolute max drawdown of cumulative trade PnL curve."""

    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return max_drawdown


def calculate_sharpe_ratio(pnls: Sequence[float]) -> float:
    """Simple per-trade Sharpe ratio: mean(PnL) / sample stdev(PnL) * sqrt(n)."""

    if len(pnls) < 2:
        return 0.0
    volatility = stdev(pnls)
    if volatility == 0:
        return 0.0
    return (mean(pnls) / volatility) * math.sqrt(len(pnls))


def _active_open_orders(state: BotState) -> int:
    return sum(1 for order in state.open_orders.values() if state.has_open_order(order.symbol))


def generate_performance_report(
    settings: Settings,
    *,
    state: Optional[BotState],
    trades: Iterable[dict],
    state_message: str = "ok",
) -> PerformanceSnapshot:
    """Generate a complete report snapshot from settings, state, and trade rows."""

    effective_state = state or BotState()
    pnls = extract_trade_pnls(trades)
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    total_trades = len(pnls)
    gross_profit = sum(wins)
    gross_loss = sum(losses)
    net_pnl = sum(pnls)
    win_rate = (len(wins) / total_trades * 100.0) if total_trades else 0.0
    average_win = mean(wins) if wins else 0.0
    average_loss = mean(losses) if losses else 0.0
    profit_factor = (
        gross_profit / abs(gross_loss)
        if gross_loss < 0
        else (math.inf if gross_profit > 0 else 0.0)
    )
    expectancy = mean(pnls) if pnls else 0.0
    daily_loss_limit_amount = settings.initial_balance * settings.max_daily_loss
    daily_trade_limit_usage = (
        effective_state.daily_trade_count / settings.max_daily_trades * 100.0
        if settings.max_daily_trades
        else 0.0
    )
    daily_loss_limit_usage = (
        abs(min(effective_state.daily_realized_pnl, 0.0)) / daily_loss_limit_amount * 100.0
        if daily_loss_limit_amount
        else 0.0
    )
    halted = effective_state.trading_status == "TRADING_HALTED"

    return PerformanceSnapshot(
        mode=settings.mode,
        allow_live_trading=settings.allow_live_trading,
        state_message=state_message,
        no_data=(state is None and total_trades == 0) or (state_message != "ok" and total_trades == 0),
        total_trades=total_trades,
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate=win_rate,
        net_pnl=net_pnl,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=profit_factor,
        max_drawdown=calculate_max_drawdown(pnls),
        average_win=average_win,
        average_loss=average_loss,
        expectancy=expectancy,
        sharpe_ratio=calculate_sharpe_ratio(pnls),
        daily_trade_limit_usage=daily_trade_limit_usage,
        daily_loss_limit_usage=daily_loss_limit_usage,
        circuit_breaker_status="HALTED" if halted else "OK",
        halt_reason=effective_state.halt_reason or "none",
        open_position_count=len(effective_state.open_positions),
        open_order_count=_active_open_orders(effective_state),
        daily_trade_count=effective_state.daily_trade_count,
        max_daily_trades=settings.max_daily_trades,
        daily_realized_pnl=effective_state.daily_realized_pnl,
        daily_loss_limit_amount=daily_loss_limit_amount,
    )


def load_state_for_report(path: str | Path) -> tuple[Optional[BotState], str]:
    state_path = Path(path)
    if not state_path.exists():
        return None, "veri yok"
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("state JSON nesnesi degil")
        return BotState.from_dict(payload), "ok"
    except Exception as exc:  # noqa: BLE001 - controlled report error for CLI.
        return None, f"state okunamadı: {type(exc).__name__}"


def load_trade_logs(paths: Iterable[str | Path]) -> list[dict]:
    trades: list[dict] = []
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists() or not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".csv":
            with path.open("r", encoding="utf-8", newline="") as handle:
                trades.extend(dict(row) for row in csv.DictReader(handle))
        elif suffix == ".jsonl":
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                if isinstance(payload, dict):
                    trades.append(payload)
        elif suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                trades.extend(row for row in payload if isinstance(row, dict))
            elif isinstance(payload, dict):
                rows = payload.get("trades")
                if isinstance(rows, list):
                    trades.extend(row for row in rows if isinstance(row, dict))
    return trades


def generate_report_from_files(
    settings: Settings,
    *,
    state_path: str | Path,
    trade_log_paths: Iterable[str | Path] = DEFAULT_TRADE_LOG_PATHS,
) -> PerformanceSnapshot:
    state, state_message = load_state_for_report(state_path)
    trades = load_trade_logs(trade_log_paths)
    return generate_performance_report(
        settings,
        state=state,
        trades=trades,
        state_message=state_message,
    )


def _format_number(value: float) -> str:
    if math.isinf(value):
        return "inf"
    return f"{value:.2f}"


def _format_percent(value: float) -> str:
    return f"{value:.2f}%"


def build_performance_report(snapshot: PerformanceSnapshot) -> str:
    """Render a secret-safe plain-text report."""

    lines = [
        "Trade_Bot Performans Raporu",
        "============================",
        "",
        f"Mode: {snapshot.mode}",
        f"Live Trading: {'true' if snapshot.allow_live_trading else 'false'}",
        f"Veri Durumu: {'veri yok' if snapshot.no_data else snapshot.state_message}",
        "",
        "Performans",
        "----------",
        f"Toplam İşlem Sayısı: {snapshot.total_trades}",
        f"Kazanan İşlem Sayısı: {snapshot.winning_trades}",
        f"Kaybeden İşlem Sayısı: {snapshot.losing_trades}",
        f"Win Rate: {_format_percent(snapshot.win_rate)}",
        f"Net PnL: {_format_number(snapshot.net_pnl)}",
        f"Gross Profit: {_format_number(snapshot.gross_profit)}",
        f"Gross Loss: {_format_number(snapshot.gross_loss)}",
        f"Profit Factor: {_format_number(snapshot.profit_factor)}",
        f"Max Drawdown: {_format_number(snapshot.max_drawdown)}",
        f"Average Win: {_format_number(snapshot.average_win)}",
        f"Average Loss: {_format_number(snapshot.average_loss)}",
        f"Expectancy: {_format_number(snapshot.expectancy)}",
        f"Sharpe Ratio: {_format_number(snapshot.sharpe_ratio)}",
        "",
        "Limitler ve Durum",
        "-----------------",
        (
            "Günlük İşlem Limiti Kullanımı: "
            f"{snapshot.daily_trade_count}/{snapshot.max_daily_trades} "
            f"({_format_percent(snapshot.daily_trade_limit_usage)})"
        ),
        (
            "Günlük Zarar Limiti Kullanımı: "
            f"{_format_number(abs(min(snapshot.daily_realized_pnl, 0.0)))}/"
            f"{_format_number(snapshot.daily_loss_limit_amount)} "
            f"({_format_percent(snapshot.daily_loss_limit_usage)})"
        ),
        f"Circuit Breaker Durumu: {snapshot.circuit_breaker_status}",
        f"Halt Sebebi: {snapshot.halt_reason}",
        f"Açık Pozisyon Sayısı: {snapshot.open_position_count}",
        f"Açık Emir Sayısı: {snapshot.open_order_count}",
    ]
    return "\n".join(lines) + "\n"


def send_telegram_report(
    settings: Settings,
    report_text: str,
    *,
    transport: Optional[Callable[[str, str, str], bool]] = None,
) -> bool:
    """Best-effort manual Telegram report delivery when daily reports are enabled."""

    if not settings.telegram_daily_report_enabled:
        return False
    notifier = TelegramNotifier(settings, transport=transport)
    return notifier.send(
        NotificationEvent(
            event_type="DAILY REPORT",
            symbol="ALL",
            mode=settings.mode,
            reason=report_text,
        )
    )
