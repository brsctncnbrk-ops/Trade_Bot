"""ATR based trailing stop management.

Trailing starts after a position moves in profit by N R. V1 mutates the local
Position in BotState only; exchange-side protected order replacement can be wired
later when stop orders are implemented.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from bot.logger import get_logger
from bot.state import BotState, Position

logger = get_logger()


@dataclass
class TrailingStopResult:
    activated: bool = False
    updated: bool = False
    reason: str = ""
    invalid: bool = False
    activation_price: float | None = None
    stop_price: float | None = None


class TrailingStopManager:
    def __init__(self, activation_r: float = 2.0, atr_multiplier: float = 2.0) -> None:
        if float(activation_r) <= 0:
            raise ValueError("TRAILING_STOP_ACTIVATION_R pozitif olmali.")
        if float(atr_multiplier) <= 0:
            raise ValueError("TRAILING_STOP_ATR_MULTIPLIER pozitif olmali.")
        self.activation_r = float(activation_r)
        self.atr_multiplier = float(atr_multiplier)

    def evaluate(
        self,
        state: BotState,
        symbol: str,
        current_price: float,
        atr: float | None,
    ) -> TrailingStopResult:
        position = state.open_positions.get(symbol)
        if position is None:
            logger.info("TRAILING STOP SKIPPED | {} | pozisyon yok", symbol)
            return TrailingStopResult(reason="Pozisyon yok; trailing stop uygulanmadi.")
        return self.evaluate_position(position, current_price=current_price, atr=atr)

    def evaluate_position(
        self,
        position: Position,
        current_price: float,
        atr: float | None,
    ) -> TrailingStopResult:
        symbol = position.symbol
        if atr is None or not math.isfinite(float(atr)) or float(atr) <= 0:
            logger.warning("TRAILING STOP INVALID | {} | ATR yok/gecersiz", symbol)
            return TrailingStopResult(reason="ATR yok/gecersiz; trailing stop uygulanamaz.", invalid=True)

        current = float(current_price)
        atr_value = float(atr)
        entry = float(position.entry_price)
        side = position.side.lower()
        original_stop = position.original_stop_loss if position.original_stop_loss is not None else position.stop_loss
        current_stop = position.current_stop_loss if position.current_stop_loss is not None else position.stop_loss
        if original_stop is None or current_stop is None:
            logger.warning("TRAILING STOP INVALID | {} | stop loss yok", symbol)
            return TrailingStopResult(reason="Stop Loss yok; trailing stop uygulanamaz.", invalid=True)
        original_stop = float(original_stop)
        current_stop = float(current_stop)

        if side in {"long", "buy"}:
            if current <= entry:
                logger.info("TRAILING STOP SKIPPED | {} | pozisyon karda degil", symbol)
                return TrailingStopResult(reason="Pozisyon karda degil.")
            risk_distance = entry - original_stop
            if risk_distance <= 0:
                logger.warning("TRAILING STOP INVALID | {} | long original stop gecersiz", symbol)
                return TrailingStopResult(reason="Long pozisyon icin original stop entry altinda olmali.", invalid=True)
            activation_price = entry + risk_distance * self.activation_r
            position.highest_price_seen = max(float(position.highest_price_seen or entry), current)
            if current < activation_price and not position.trailing_stop_activated:
                logger.info(
                    "TRAILING STOP SKIPPED | {} | current {:.6f} < activation {:.6f}",
                    symbol,
                    current,
                    activation_price,
                )
                return TrailingStopResult(reason="2R aktivasyon seviyesine ulasilmadi.", activation_price=activation_price)
            raw_stop = current - atr_value * self.atr_multiplier
            floor_stop = entry if position.break_even_activated else current_stop
            new_stop = max(raw_stop, floor_stop, current_stop)
        elif side in {"short", "sell"}:
            if current >= entry:
                logger.info("TRAILING STOP SKIPPED | {} | short pozisyon karda degil", symbol)
                return TrailingStopResult(reason="Pozisyon karda degil.")
            risk_distance = original_stop - entry
            if risk_distance <= 0:
                logger.warning("TRAILING STOP INVALID | {} | short original stop gecersiz", symbol)
                return TrailingStopResult(reason="Short pozisyon icin original stop entry ustunde olmali.", invalid=True)
            activation_price = entry - risk_distance * self.activation_r
            # For shorts this tracks most favorable low price.
            position.highest_price_seen = min(float(position.highest_price_seen or entry), current)
            if current > activation_price and not position.trailing_stop_activated:
                logger.info(
                    "TRAILING STOP SKIPPED | {} | current {:.6f} > activation {:.6f}",
                    symbol,
                    current,
                    activation_price,
                )
                return TrailingStopResult(reason="2R aktivasyon seviyesine ulasilmadi.", activation_price=activation_price)
            raw_stop = current + atr_value * self.atr_multiplier
            ceiling_stop = entry if position.break_even_activated else current_stop
            new_stop = min(raw_stop, ceiling_stop, current_stop)
        else:
            logger.warning("TRAILING STOP INVALID | {} | bilinmeyen side {}", symbol, position.side)
            return TrailingStopResult(reason="Bilinmeyen pozisyon yonu.", invalid=True)

        just_activated = not position.trailing_stop_activated
        position.trailing_stop_activated = True
        position.trailing_activation_price = position.trailing_activation_price or activation_price

        if side in {"long", "buy"} and new_stop <= current_stop + 1e-12:
            if just_activated:
                position.trailing_stop_price = current_stop
                logger.info(
                    "TRAILING STOP ACTIVATED | {} | activation {:.6f} | stop {:.6f}",
                    symbol,
                    activation_price,
                    current_stop,
                )
            logger.info("TRAILING STOP SKIPPED | {} | stop yukari tasinmadi", symbol)
            return TrailingStopResult(
                activated=just_activated,
                updated=False,
                reason="Trailing aktif ama stop iyilestirmesi yok.",
                activation_price=activation_price,
                stop_price=current_stop,
            )
        if side in {"short", "sell"} and new_stop >= current_stop - 1e-12:
            if just_activated:
                position.trailing_stop_price = current_stop
                logger.info(
                    "TRAILING STOP ACTIVATED | {} | activation {:.6f} | stop {:.6f}",
                    symbol,
                    activation_price,
                    current_stop,
                )
            logger.info("TRAILING STOP SKIPPED | {} | short stop asagi tasinmadi", symbol)
            return TrailingStopResult(
                activated=just_activated,
                updated=False,
                reason="Trailing aktif ama stop iyilestirmesi yok.",
                activation_price=activation_price,
                stop_price=current_stop,
            )

        position.trailing_stop_price = new_stop
        position.current_stop_loss = new_stop
        position.stop_loss = new_stop
        if just_activated:
            logger.info(
                "TRAILING STOP ACTIVATED | {} | activation {:.6f} | stop {:.6f}",
                symbol,
                activation_price,
                new_stop,
            )
        logger.info(
            "TRAILING STOP UPDATED | {} | current {:.6f} | atr {:.6f} | stop {:.6f}",
            symbol,
            current,
            atr_value,
            new_stop,
        )
        return TrailingStopResult(
            activated=just_activated,
            updated=True,
            reason="Trailing stop guncellendi.",
            activation_price=activation_price,
            stop_price=new_stop,
        )
