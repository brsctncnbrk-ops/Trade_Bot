"""Break Even management.

Moves stop loss to entry once price advances in favour of the position by N R.
V1 mutates in-memory BotState/Position only; exchange-side stop-order updates can
be wired later when protected orders are implemented.
"""

from __future__ import annotations

from dataclasses import dataclass

from bot.logger import get_logger
from bot.state import BotState, Position

logger = get_logger()


@dataclass
class BreakEvenResult:
    activated: bool
    reason: str
    invalid: bool = False
    trigger_price: float | None = None


class BreakEvenManager:
    def __init__(self, trigger_r: float = 1.0) -> None:
        if float(trigger_r) <= 0:
            raise ValueError("BREAK_EVEN_TRIGGER_R pozitif olmali.")
        self.trigger_r = float(trigger_r)

    def evaluate(self, state: BotState, symbol: str, current_price: float) -> BreakEvenResult:
        position = state.open_positions.get(symbol)
        if position is None:
            logger.info("BREAK EVEN SKIPPED | {} | pozisyon yok", symbol)
            return BreakEvenResult(False, "Pozisyon yok; break-even uygulanmadi.")
        return self.evaluate_position(position, current_price)

    def evaluate_position(self, position: Position, current_price: float) -> BreakEvenResult:
        symbol = position.symbol
        if position.break_even_activated:
            logger.info("BREAK EVEN SKIPPED | {} | zaten aktif", symbol)
            return BreakEvenResult(False, "Break-even zaten aktif.")

        stop = position.current_stop_loss
        if stop is None:
            stop = position.stop_loss
        if stop is None or float(stop) <= 0:
            logger.warning("BREAK EVEN INVALID | {} | stop loss yok", symbol)
            return BreakEvenResult(False, "Stop Loss yok; break-even uygulanamaz.", invalid=True)

        entry = float(position.entry_price)
        stop = float(stop)
        current = float(current_price)
        side = position.side.lower()

        if side in {"long", "buy"}:
            risk_distance = entry - stop
            if risk_distance <= 0:
                logger.warning("BREAK EVEN INVALID | {} | long stop entry altinda degil", symbol)
                return BreakEvenResult(False, "Long pozisyon icin stop entry altinda olmali.", invalid=True)
            trigger = entry + risk_distance * self.trigger_r
            if current < trigger:
                logger.info(
                    "BREAK EVEN SKIPPED | {} | current {:.6f} < trigger {:.6f}",
                    symbol,
                    current,
                    trigger,
                )
                return BreakEvenResult(False, "1R seviyesine ulasilmadi.", trigger_price=trigger)
            new_stop = entry
        elif side in {"short", "sell"}:
            risk_distance = stop - entry
            if risk_distance <= 0:
                logger.warning("BREAK EVEN INVALID | {} | short stop entry ustunde degil", symbol)
                return BreakEvenResult(False, "Short pozisyon icin stop entry ustunde olmali.", invalid=True)
            trigger = entry - risk_distance * self.trigger_r
            if current > trigger:
                logger.info(
                    "BREAK EVEN SKIPPED | {} | current {:.6f} > trigger {:.6f}",
                    symbol,
                    current,
                    trigger,
                )
                return BreakEvenResult(False, "1R seviyesine ulasilmadi.", trigger_price=trigger)
            new_stop = entry
        else:
            logger.warning("BREAK EVEN INVALID | {} | bilinmeyen side {}", symbol, position.side)
            return BreakEvenResult(False, "Bilinmeyen pozisyon yonu.", invalid=True)

        # Guvenlik: break-even stop entry'nin otesine tasinmaz.
        position.original_stop_loss = position.original_stop_loss or stop
        position.current_stop_loss = new_stop
        position.stop_loss = new_stop
        position.break_even_price = trigger
        position.break_even_activated = True
        logger.info(
            "BREAK EVEN ACTIVATED | {} | entry {:.6f} | trigger {:.6f} | stop {:.6f}",
            symbol,
            entry,
            trigger,
            new_stop,
        )
        return BreakEvenResult(True, "Break-even aktif edildi.", trigger_price=trigger)
