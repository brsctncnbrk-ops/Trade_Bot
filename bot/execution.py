"""Emir yurutme motoru.

- backtest: kuru calisma (dry-run) — emirler bellekte simule edilir.
- testnet: CCXT Binance sandbox baglantisi tembel (lazy) kurulur;
  testler cevrimdisi calisir.
- live: ilk surumde KAPALI. Ayarlar canli kapiyi gecse bile gercek emir
  yolu NotImplementedError firlatir.

Her emir denemesi loglanir. Tum parametreler emir oncesi dogrulanir.
"""

from __future__ import annotations

import itertools
import math
from typing import Dict, Optional

from bot.logger import get_logger
from config.settings import Settings

logger = get_logger()

VALID_SIDES = {"buy", "sell"}


class OrderValidationError(ValueError):
    """Emir parametreleri gecersiz."""


class ExecutionEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mode = settings.mode
        self._orders: Dict[str, dict] = {}
        self._order_ids = itertools.count(1)
        self._exchange = None  # testnet icin tembel kurulum

    # ------------------------------------------------------------------
    # Dogrulama
    # ------------------------------------------------------------------
    def _validate_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        stop_loss: Optional[float],
        take_profit: Optional[float],
    ) -> None:
        if not symbol or "/" not in symbol:
            raise OrderValidationError(f"Gecersiz sembol: {symbol!r}")
        if side not in VALID_SIDES:
            raise OrderValidationError(
                f"Gecersiz islem yonu: {side!r} (buy/sell olmali)"
            )
        for name, value in (("quantity", quantity), ("price", price)):
            if (
                value is None
                or not isinstance(value, (int, float))
                or math.isnan(float(value))
                or float(value) <= 0
            ):
                raise OrderValidationError(f"Gecersiz {name}: {value!r}")
        if side == "buy":
            # Alis emirlerinde SL/TP zorunludur — risk kurali.
            if stop_loss is None or float(stop_loss) <= 0:
                raise OrderValidationError("Alis emri icin stop_loss zorunludur.")
            if take_profit is None or float(take_profit) <= 0:
                raise OrderValidationError("Alis emri icin take_profit zorunludur.")
        if self.mode not in {"backtest", "testnet", "live"}:
            raise OrderValidationError(f"Gecersiz mod: {self.mode!r}")

    # ------------------------------------------------------------------
    # Testnet borsasi (tembel)
    # ------------------------------------------------------------------
    def _get_exchange(self):
        """CCXT Binance testnet istemcisini ilk ihtiyacta kurar."""
        if self._exchange is None:
            if not (
                self.settings.binance_testnet_api_key
                and self.settings.binance_testnet_api_secret
            ):
                raise RuntimeError(
                    "Testnet islemi icin BINANCE_TESTNET_API_KEY ve "
                    "BINANCE_TESTNET_API_SECRET ortam degiskenleri gerekli."
                )
            import ccxt  # tembel import: testler cevrimdisi kalsin

            exchange = ccxt.binance(
                {
                    "apiKey": self.settings.binance_testnet_api_key,
                    "secret": self.settings.binance_testnet_api_secret,
                    "enableRateLimit": True,
                }
            )
            exchange.set_sandbox_mode(True)
            self._exchange = exchange
        return self._exchange

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> dict:
        """Emir verir. backtest modunda simulasyon, testnet modunda sandbox.

        live modu ilk surumde devre disidir.
        """
        logger.info(
            "Emir denemesi | mod={} | {} {} {:.6f} @ {:.4f} | SL={} TP={}",
            self.mode,
            side.upper(),
            symbol,
            quantity,
            price,
            f"{stop_loss:.4f}" if stop_loss else "-",
            f"{take_profit:.4f}" if take_profit else "-",
        )
        self._validate_order(symbol, side, quantity, price, stop_loss, take_profit)

        if self.mode == "live":
            # Cifte guvenlik: ayarlar canli kapiyi gecmis olsa bile ilk
            # surumde gercek emir yolu yoktur.
            if not self.settings.allow_live_trading:
                raise RuntimeError(
                    "Canli islem engellendi: ALLOW_LIVE_TRADING=true degil."
                )
            raise NotImplementedError(
                "Canli emir gonderimi ilk surumde devre disidir. "
                "Once testnet asamasini tamamlayin."
            )

        if self.mode == "testnet":
            exchange = self._get_exchange()
            order = exchange.create_order(symbol, "market", side, quantity)
            logger.info("Testnet emri gonderildi | id={}", order.get("id"))
            return order

        # backtest / dry-run simulasyonu
        order_id = f"sim-{next(self._order_ids)}"
        order = {
            "id": order_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "status": "filled",
            "mode": self.mode,
            "simulated": True,
        }
        self._orders[order_id] = order
        logger.info("Emir simule edildi | id={} | status=filled", order_id)
        return order

    def cancel_order(self, order_id: str) -> dict:
        logger.info("Emir iptal denemesi | mod={} | id={}", self.mode, order_id)
        if self.mode == "testnet":
            raise NotImplementedError(
                "Testnet emir iptali icin sembol bilgisiyle CCXT cancel_order "
                "entegrasyonu sonraki surumde eklenecek."
            )
        order = self._orders.get(order_id)
        if order is None:
            raise ValueError(f"Emir bulunamadi: {order_id}")
        if order["status"] == "filled":
            raise ValueError(f"Gerceklesen emir iptal edilemez: {order_id}")
        order["status"] = "canceled"
        return order

    def get_order_status(self, order_id: str) -> str:
        order = self._orders.get(order_id)
        if order is None:
            raise ValueError(f"Emir bulunamadi: {order_id}")
        return order["status"]
