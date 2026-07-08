"""Professional Take Profit planning and validation.

V1 closes the full position at a single TP level. The datamodel already supports
multiple levels for future partial take-profit extensions (25/50/75%).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from bot.logger import get_logger

logger = get_logger()


@dataclass
class TakeProfitLevel:
    price: float
    percent: float = 1.0


@dataclass
class TakeProfitPlan:
    side: str
    entry_price: float
    stop_loss: float
    stop_distance: float
    take_profit: float
    risk_reward: float
    expected_profit_per_unit: float
    levels: List[TakeProfitLevel]


class TakeProfitManager:
    def __init__(self, min_risk_reward: float = 2.0) -> None:
        self.min_risk_reward = float(min_risk_reward)

    def create_plan(
        self,
        side: str,
        entry_price: float,
        stop_loss: float,
        stop_distance: float,
    ) -> TakeProfitPlan:
        if stop_distance is None or float(stop_distance) <= 0:
            logger.warning("TAKE PROFIT INVALID | stop distance missing")
            raise RuntimeError("Take Profit could not be calculated.")

        side = side.lower()
        entry = float(entry_price)
        distance = float(stop_distance) * self.min_risk_reward
        if side == "buy":
            take_profit = entry + distance
        elif side == "sell":
            take_profit = entry - distance
        else:
            raise RuntimeError("Take Profit invalid: unknown side.")

        risk_reward = self.validate(side, entry, stop_loss, take_profit)
        expected_profit = abs(float(take_profit) - entry)
        logger.info(
            "TAKE PROFIT CREATED | side={} | entry {:.6f} | tp {:.6f}",
            side.upper(),
            entry,
            take_profit,
        )
        logger.info("RISK REWARD | {:.4f}", risk_reward)
        logger.info("EXPECTED PROFIT | per_unit {:.6f}", expected_profit)
        return TakeProfitPlan(
            side=side,
            entry_price=entry,
            stop_loss=float(stop_loss),
            stop_distance=float(stop_distance),
            take_profit=take_profit,
            risk_reward=risk_reward,
            expected_profit_per_unit=expected_profit,
            levels=[TakeProfitLevel(price=take_profit, percent=1.0)],
        )

    def validate(
        self,
        side: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
    ) -> float:
        if take_profit is None:
            logger.warning("TAKE PROFIT INVALID | missing")
            raise RuntimeError("Take Profit is required before opening a position.")
        entry = float(entry_price)
        stop = float(stop_loss)
        tp = float(take_profit)
        side = side.lower()

        risk = abs(entry - stop)
        reward = abs(tp - entry)
        if risk <= 0 or reward <= 0:
            logger.warning("TAKE PROFIT INVALID | risk/reward distance invalid")
            raise RuntimeError("Take Profit invalid: risk/reward distance invalid.")

        if side == "buy":
            if not (stop < entry < tp):
                logger.warning("TAKE PROFIT INVALID | BUY side ordering")
                raise RuntimeError("Take Profit invalid: BUY requires stop < entry < take profit.")
        elif side == "sell":
            if not (tp < entry < stop):
                logger.warning("TAKE PROFIT INVALID | SELL side ordering")
                raise RuntimeError("Take Profit invalid: SELL requires take profit < entry < stop.")
        else:
            raise RuntimeError("Take Profit invalid: unknown side.")

        risk_reward = reward / risk
        if risk_reward + 1e-12 < self.min_risk_reward:
            logger.warning(
                "TAKE PROFIT INVALID | Risk/Reward {:.4f} < {:.4f}",
                risk_reward,
                self.min_risk_reward,
            )
            raise RuntimeError(
                f"Risk/Reward {risk_reward:.4f} is below minimum {self.min_risk_reward:.4f}."
            )
        return risk_reward
