"""Terminal dashboard for Trade_Bot.

Read-only status view. This script never starts the bot, never talks to an
exchange, and never prints secret/token/chat_id values.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.state import BotState, OpenOrder, Position
from config.settings import Settings, get_settings


class DashboardStateError(RuntimeError):
    """State file exists but cannot be parsed into a dashboard state."""


def format_bool(value: bool) -> str:
    return "true" if value else "false"


def format_money(value: float, currency: str = "USDT") -> str:
    return f"{float(value):.2f} {currency}"


def format_value(value: object) -> str:
    if value is None or value == "":
        return "none"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def load_dashboard_state(path: str | Path) -> Tuple[Optional[BotState], str]:
    """Load state for dashboard only.

    Missing state is informational. A present but broken state is reported as a
    controlled dashboard error; the bot is not started or modified here.
    """

    state_path = Path(path)
    if not state_path.exists():
        return None, "state bulunamadı"

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("state JSON nesnesi degil")
        return BotState.from_dict(payload), "ok"
    except Exception as exc:  # noqa: BLE001 - CLI must show controlled error.
        raise DashboardStateError(f"Dashboard state hatasi: {exc}") from exc


def active_open_orders(state: BotState) -> list[OpenOrder]:
    return [order for order in state.open_orders.values() if state.has_open_order(order.symbol)]


def position_line(position: Position) -> str:
    return (
        f"- {position.symbol} {position.side} "
        f"qty={format_value(position.quantity)} "
        f"entry={format_value(position.entry_price)} "
        f"stop={format_value(position.current_stop_loss)} "
        f"take_profit={format_value(position.take_profit)}"
    )


def order_line(order: OpenOrder) -> str:
    return (
        f"- {order.symbol} {order.side} {order.order_type} "
        f"qty={format_value(order.quantity)} "
        f"price={format_value(order.price)} "
        f"status={order.status}"
    )


def build_dashboard(
    settings: Settings,
    state: Optional[BotState],
    *,
    state_message: str = "ok",
) -> str:
    """Build a plain-text read-only dashboard without exposing secrets."""

    effective_state = state or BotState()
    positions = list(effective_state.open_positions.values())
    orders = active_open_orders(effective_state)
    halted = effective_state.trading_status == "TRADING_HALTED"
    daily_loss_limit_usdt = settings.initial_balance * settings.max_daily_loss
    telegram_status = "enabled" if settings.telegram_notifications_enabled else "disabled"
    circuit_breaker = "HALTED" if halted else "OK"

    lines = [
        "Trade_Bot Dashboard",
        "===================",
        "",
        f"Mode: {settings.mode}",
        f"Live Trading: {format_bool(settings.allow_live_trading)}",
        f"Trading Status: {effective_state.trading_status}",
        "",
        "Capital",
        "-------",
        f"Initial Balance: {format_money(settings.initial_balance, settings.base_currency)}",
        f"Max Capital: {format_money(settings.max_capital_usdt, settings.base_currency)}",
        f"Daily PnL: {format_money(effective_state.daily_realized_pnl, settings.base_currency)}",
        f"Hourly PnL: {format_money(effective_state.hourly_realized_pnl, settings.base_currency)}",
        "",
        "Risk",
        "----",
        f"Daily Loss Limit: {format_money(daily_loss_limit_usdt, settings.base_currency)}",
        f"Daily Trades: {effective_state.daily_trade_count} / {settings.max_daily_trades}",
        f"API Errors: {effective_state.api_error_count} / {settings.max_api_errors}",
        "",
        "Positions",
        "---------",
        f"Open Positions: {len(positions)}",
    ]

    if positions:
        lines.extend(position_line(position) for position in positions)

    lines.extend(
        [
            "",
            "Orders",
            "------",
            f"Open Orders: {len(orders)}",
        ]
    )

    if orders:
        lines.extend(order_line(order) for order in orders)

    lines.extend(
        [
            "",
            "Safety",
            "------",
            f"Circuit Breaker: {circuit_breaker}",
            f"Halt Reason: {format_value(effective_state.halt_reason)}",
            f"Last Trade: {format_value(effective_state.last_trade_at)}",
            "",
            "Notifications",
            "-------------",
            f"Telegram: {telegram_status}",
            "",
            "State",
            "-----",
            f"State File: {state_message}",
        ]
    )

    return "\n".join(lines) + "\n"


def main() -> int:
    settings = get_settings()
    try:
        state, state_message = load_dashboard_state(settings.state_file)
    except DashboardStateError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(build_dashboard(settings, state, state_message=state_message), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
