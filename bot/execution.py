"""Emir yurutme motoru.

- backtest: kuru calisma (dry-run) — emirler bellekte simule edilir.
- testnet: CCXT Binance Spot sandbox baglantisi tembel (lazy) kurulur.
- live: ilk surumde KAPALI.

Guvenlik kurallari:
- MARKET order tamamen yasaktir.
- Testnet emirlerinden once endpoint `testnet.binance.vision` assert edilir.
- Production Spot endpoint gorulurse emir gonderimi durdurulur.
"""

from __future__ import annotations

import itertools
import math
import time
from typing import Dict, Optional

from bot.logger import get_logger
from bot.take_profit import TakeProfitManager
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
        order_type: str,
    ) -> None:
        if order_type.lower() == "market":
            raise RuntimeError("Market orders are disabled.")
        if order_type.lower() != "limit":
            raise OrderValidationError("Yalnizca LIMIT emir desteklenir.")
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
                raise RuntimeError("Stop Loss is required before opening a position.")
            if take_profit is None or float(take_profit) <= 0:
                raise RuntimeError("Take Profit is required before opening a position.")
            TakeProfitManager(self.settings.min_risk_reward).validate(
                side,
                entry_price=float(price),
                stop_loss=float(stop_loss),
                take_profit=float(take_profit),
            )
        if self.mode not in {"backtest", "testnet", "live"}:
            raise OrderValidationError(f"Gecersiz mod: {self.mode!r}")
        if side == "buy" and float(quantity) * float(price) > self.settings.max_notional_per_trade_usdt + 1e-9:
            raise RuntimeError(
                "Tek islem notional limiti asildi: "
                f"{float(quantity) * float(price):.2f} > "
                f"{self.settings.max_notional_per_trade_usdt:.2f}"
            )

    # ------------------------------------------------------------------
    # Testnet borsasi (tembel)
    # ------------------------------------------------------------------
    def _assert_testnet_endpoint(self, exchange=None) -> str:
        exchange = exchange or self._get_exchange()
        urls = exchange.urls.get("api")
        urls_text = str(urls)
        if "testnet.binance.vision" not in urls_text:
            raise RuntimeError(
                "Testnet endpoint guvenlik kontrolu basarisiz: "
                "testnet.binance.vision bulunamadi."
            )
        if "https://api.binance.com/api" in urls_text:
            raise RuntimeError("Production Spot endpoint detected; order blocked.")
        if isinstance(urls, dict):
            return urls.get("private") or urls.get("public") or urls_text
        return urls_text

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
                    "options": {"defaultType": "spot"},
                }
            )
            exchange.set_sandbox_mode(True)
            self._assert_testnet_endpoint(exchange)
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
        order_type: Optional[str] = None,
    ) -> dict:
        """LIMIT emir verir. backtest modunda simulasyon, testnet modunda sandbox."""
        order_type = (order_type or self.settings.order_type).lower()
        logger.info(
            "ENTRY | mod={} | type={} | {} {} {:.6f} @ {:.4f} | SL={} TP={}",
            self.mode,
            order_type.upper(),
            side.upper(),
            symbol,
            quantity,
            price,
            f"{stop_loss:.4f}" if stop_loss else "-",
            f"{take_profit:.4f}" if take_profit else "-",
        )
        self._validate_order(symbol, side, quantity, price, stop_loss, take_profit, order_type)

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
            endpoint = self._assert_testnet_endpoint(exchange)
            order = exchange.create_order(symbol, "limit", side, quantity, price)
            order.setdefault("quantity", quantity)
            order.setdefault("price", price)
            order.setdefault("filled", 0.0)
            logger.info(
                "ORDER CREATED | endpoint={} | id={} | {} {} {:.6f} @ {:.4f}",
                endpoint,
                order.get("id"),
                side.upper(),
                symbol,
                quantity,
                price,
            )
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
            "type": "limit",
            "filled": quantity,
            "simulated": True,
        }
        self._orders[order_id] = order
        logger.info("ORDER FILLED | id={} | simulated=true", order_id)
        return order

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> dict:
        logger.info("Emir iptal denemesi | mod={} | id={}", self.mode, order_id)
        if self.mode == "testnet":
            if not symbol:
                raise ValueError("Testnet emir iptali icin symbol zorunludur.")
            exchange = self._get_exchange()
            self._assert_testnet_endpoint(exchange)
            order = exchange.cancel_order(order_id, symbol)
            logger.info("ORDER CANCELLED | id={} | symbol={}", order_id, symbol)
            return order
        order = self._orders.get(order_id)
        if order is None:
            raise ValueError(f"Emir bulunamadi: {order_id}")
        if order["status"] == "filled":
            raise ValueError(f"Gerceklesen emir iptal edilemez: {order_id}")
        order["status"] = "canceled"
        logger.info("ORDER CANCELLED | id={} | symbol={}", order_id, order.get("symbol"))
        return order

    def get_order_status(self, order_id: str, symbol: Optional[str] = None) -> str:
        if self.mode == "testnet":
            if not symbol:
                raise ValueError("Testnet emir durumu icin symbol zorunludur.")
            exchange = self._get_exchange()
            self._assert_testnet_endpoint(exchange)
            order = exchange.fetch_order(order_id, symbol)
            status = order.get("status") or "unknown"
            filled = float(order.get("filled") or 0.0)
            if status == "closed" or filled > 0:
                logger.info("ORDER FILLED | id={} | filled={}", order_id, filled)
            return status
        order = self._orders.get(order_id)
        if order is None:
            raise ValueError(f"Emir bulunamadi: {order_id}")
        return order["status"]

    def cancel_if_unfilled_after_timeout(
        self,
        order_id: str,
        symbol: str,
        created_at_epoch: float,
        timeout_seconds: Optional[int] = None,
    ) -> dict | None:
        """Suresi dolan ve filled==0 olan LIMIT emri iptal eder."""
        timeout = timeout_seconds or self.settings.open_order_timeout_seconds
        if time.time() - created_at_epoch < timeout:
            return None
        if self.mode == "testnet":
            exchange = self._get_exchange()
            self._assert_testnet_endpoint(exchange)
            order = exchange.fetch_order(order_id, symbol)
            if float(order.get("filled") or 0.0) == 0.0:
                return self.cancel_order(order_id, symbol)
            logger.info("ORDER FILLED | id={} | filled={}", order_id, order.get("filled"))
            return order
        order = self._orders.get(order_id)
        if order and float(order.get("filled") or 0.0) == 0.0:
            return self.cancel_order(order_id, symbol)
        return order
