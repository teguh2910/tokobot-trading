import requests
import time
from typing import Optional, List, Dict
from urllib.parse import urlencode
from config import config
from client.signer import signed_params
from models import Kline, Order, Trade, AccountBalance, Ticker

MIN_NOTIONAL = 50000
LOT_SIZE_CACHE: Dict[str, dict] = {}


class TokocryptoClient:
    def __init__(self):
        self.base = config.BASE_URL
        self.base_site = config.BASE_URL_SITE
        self.api_key = config.API_KEY
        self.session = requests.Session()
        self._lot_cache: Dict[str, dict] = {}
        self.session.headers.update({
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        })

    def _get(self, path: str, params: dict = None, signed: bool = False, base_site: bool = False):
        url = f"{self.base_site if base_site else self.base}{path}"
        if signed:
            params = signed_params(params or {})
        resp = self.session.get(url, params=params)
        return self._handle(resp)

    def _post(self, path: str, params: dict = None, signed: bool = False):
        url = f"{self.base}{path}"
        if signed:
            params = signed_params(params or {})
        resp = self.session.post(url, data=params)
        return self._handle(resp)

    def _delete(self, path: str, params: dict = None, signed: bool = False):
        url = f"{self.base}{path}"
        if signed:
            params = signed_params(params or {})
        resp = self.session.delete(url, params=params)
        return self._handle(resp)

    def _handle(self, resp: requests.Response):
        try:
            data = resp.json()
        except:
            data = {"code": -1, "msg": "Invalid JSON response", "raw": resp.text}

        if isinstance(data, dict):
            if data.get("code", 0) != 0:
                raise Exception(f"API Error [{data.get('code', '?')}]: {data.get('msg', data.get('message', 'Unknown'))}")

        return data

    # ── General ──

    def get_server_time(self) -> int:
        data = self._get("/open/v1/common/time")
        return data["timestamp"]

    def get_symbols(self) -> List[dict]:
        data = self._get("/open/v1/common/symbols")
        return data.get("data", {}).get("list", [])

    # ── Market Data ──

    def get_depth(self, symbol: str, limit: int = 100) -> dict:
        symbol_param = symbol.replace("_", "")
        data = self._get("/api/v3/depth", {"symbol": symbol_param, "limit": limit}, base_site=True)
        return data.get("data", data) if isinstance(data, dict) else {}

    def get_klines(self, symbol: str, interval: str = "1m", limit: int = 500,
                   start_time: int = None, end_time: int = None) -> List[Kline]:
        symbol_param = symbol.replace("_", "")
        params = {"symbol": symbol_param, "interval": interval, "limit": limit}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        data = self._get("/api/v3/klines", params, base_site=True)
        raw_klines = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(raw_klines, list) and len(raw_klines) > 0 and isinstance(raw_klines[0], list):
            return [Kline.from_list(k) for k in raw_klines]
        return []

    def get_trades(self, symbol: str, limit: int = 100) -> List[dict]:
        symbol_param = symbol.replace("_", "")
        data = self._get("/api/v3/trades", {"symbol": symbol_param, "limit": limit}, base_site=True)
        raw = data.get("data", data) if isinstance(data, dict) else data
        return raw if isinstance(raw, list) else []

    def get_agg_trades(self, symbol: str, limit: int = 100) -> List[dict]:
        symbol_param = symbol.replace("_", "")
        data = self._get("/api/v3/aggTrades", {"symbol": symbol_param, "limit": limit}, base_site=True)
        raw = data.get("data", data) if isinstance(data, dict) else data
        return raw if isinstance(raw, list) else []

    def get_execution_rules(self, symbol: str = None) -> dict:
        params = {}
        if symbol:
            params["symbol"] = symbol.replace("_", "")
        data = self._get("/api/v3/executionRules", params, base_site=True)
        return data

    def get_lot_size(self, symbol: str) -> dict:
        sym = symbol.replace("_", "")
        if sym in self._lot_cache:
            return self._lot_cache[sym]
        try:
            data = self._get("/api/v3/exchangeInfo", {"symbol": sym}, base_site=True)
            if isinstance(data, dict):
                for s in data.get("symbols", []):
                    for f in s.get("filters", []):
                        if f.get("filterType") == "LOT_SIZE":
                            self._lot_cache[sym] = f
                            return f
        except Exception:
            pass
        return {"minQty": "0", "maxQty": "0", "stepSize": "0"}

    def round_quantity(self, symbol: str, quantity: float) -> float:
        lot = self.get_lot_size(symbol)
        step = float(lot.get("stepSize", 0))
        min_qty = float(lot.get("minQty", 0))
        if step <= 0:
            return 0
        step_str = str(step)
        precision = len(step_str.split(".")[1]) if "." in step_str else 0
        qty = round(quantity // step * step, precision)
        if qty < min_qty:
            if quantity >= min_qty:
                qty = min_qty
            else:
                return 0
        return qty

    def get_min_notional(self) -> float:
        return MIN_NOTIONAL

    def get_ticker(self, symbol: str = None) -> dict:
        params = {}
        if symbol:
            params["symbol"] = symbol.replace("_", "")
        data = self._get("/api/v3/ticker/price", params, base_site=True)
        if isinstance(data, dict) and "symbol" in data:
            return {data["symbol"]: float(data["price"])}
        if isinstance(data, list):
            return {item["symbol"]: float(item["price"]) for item in data}
        return {}

    def get_ticker_24hr(self, symbol: str = None) -> list:
        params = {}
        if symbol:
            params["symbol"] = symbol.replace("_", "")
        data = self._get("/api/v3/ticker/24hr", params, base_site=True)
        if isinstance(data, list):
            return data
        return [data] if isinstance(data, dict) else []

    # ── Account (SIGNED) ──

    def get_account_info(self) -> tuple:
        data = self._get("/open/v1/account/spot", signed=True)
        raw = data.get("data", {})
        balances = []
        for asset in raw.get("accountAssets", []):
            balances.append(AccountBalance(
                asset=asset["asset"],
                free=float(asset["free"]),
                locked=float(asset["locked"])
            ))
        return balances, raw.get("canTrade", False)

    def get_asset_balance(self, asset: str) -> Optional[AccountBalance]:
        data = self._get("/open/v1/account/spot/asset", {"asset": asset}, signed=True)
        raw = data.get("data", {})
        if raw:
            return AccountBalance(asset=raw["asset"], free=float(raw["free"]), locked=float(raw["locked"]))
        return None

    # ── Orders (SIGNED) ──

    def new_order(self, symbol: str, side: int, order_type: int, quantity: str = None,
                  price: str = None, quote_order_qty: str = None,
                  time_in_force: int = None, stop_price: str = None,
                  client_id: str = None, iceberg_qty: str = None,
                  self_trade_prevention: int = None) -> Order:
        params = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
        }
        if quantity:
            params["quantity"] = quantity
        if price:
            params["price"] = price
        if quote_order_qty:
            params["quoteOrderQty"] = quote_order_qty
        if time_in_force:
            params["timeInForce"] = time_in_force
        if stop_price:
            params["stopPrice"] = stop_price
        if client_id:
            params["clientId"] = client_id
        if iceberg_qty:
            params["icebergQty"] = iceberg_qty
        if self_trade_prevention is not None:
            params["selfTradePreventionMode"] = self_trade_prevention

        data = self._post("/open/v1/orders", params, signed=True)
        raw = data.get("data", {})
        return Order(
            order_id=str(raw.get("orderId", "")),
            symbol=raw.get("symbol", symbol),
            side=raw.get("side", side),
            type=raw.get("type", order_type),
            price=float(raw.get("price", price or 0)),
            orig_qty=float(raw.get("origQty", quantity or 0)),
            executed_qty=float(raw.get("executedQty", 0)),
            cum_quote_qty=float(raw.get("cummulativeQuoteQty", 0)),
            status=raw.get("status", 0),
            create_time=raw.get("createTime", int(time.time() * 1000)),
            client_id=raw.get("clientId", client_id or ""),
            stop_price=float(raw.get("stopPrice", 0)),
            time_in_force=raw.get("timeInForce", 1)
        )

    def cancel_order(self, symbol: str, order_id: str = None, client_id: str = None) -> dict:
        params = {"symbol": symbol}
        if order_id:
            params["orderId"] = order_id
        if client_id:
            params["clientId"] = client_id
        data = self._post("/open/v1/orders/cancel", params, signed=True)
        return data.get("data", {})

    def get_order(self, order_id: str) -> Optional[Order]:
        data = self._get("/open/v1/orders/detail", {"orderId": order_id}, signed=True)
        raw = data.get("data", {})
        if raw:
            return Order(
                order_id=str(raw.get("orderId", "")),
                symbol=raw.get("symbol", ""),
                side=raw.get("side", 0),
                type=raw.get("type", 1),
                price=float(raw.get("price", 0)),
                orig_qty=float(raw.get("origQty", 0)),
                executed_qty=float(raw.get("executedQty", 0)),
                cum_quote_qty=float(raw.get("cummulativeQuoteQty", 0)),
                status=raw.get("status", 0),
                create_time=raw.get("createTime", 0),
                client_id=raw.get("clientId", ""),
                stop_price=float(raw.get("stopPrice", 0))
            )
        return None

    def get_all_orders(self, symbol: str, order_type: int = -1, side: int = None,
                       limit: int = 50, from_id: str = None, direct: str = None) -> List[Order]:
        params = {"symbol": symbol, "type": order_type, "limit": limit}
        if side is not None:
            params["side"] = side
        if from_id:
            params["fromId"] = from_id
            params["direct"] = direct or "next"
        data = self._get("/open/v1/orders", params, signed=True)
        raw_list = data.get("data", {}).get("list", [])
        return [
            Order(
                order_id=str(r.get("orderId", "")),
                symbol=r.get("symbol", symbol),
                side=r.get("side", 0),
                type=r.get("type", 1),
                price=float(r.get("price", 0)),
                orig_qty=float(r.get("origQty", 0)),
                executed_qty=float(r.get("executedQty", 0)),
                status=r.get("status", 0),
                create_time=r.get("createTime", 0),
                client_id=r.get("clientId", ""),
                stop_price=float(r.get("stopPrice", 0)),
                time_in_force=r.get("timeInForce", 1)
            )
            for r in raw_list
        ]

    def get_trade_history(self, symbol: str, limit: int = 100, from_id: int = None) -> List[Trade]:
        params = {"symbol": symbol, "limit": limit}
        if from_id:
            params["fromId"] = from_id
        data = self._get("/open/v1/orders/trades", params, signed=True)
        raw_list = data.get("data", {}).get("list", [])
        return [
            Trade(
                trade_id=str(r.get("tradeId", "")),
                order_id=str(r.get("orderId", "")),
                symbol=r.get("symbol", symbol),
                price=float(r.get("price", 0)),
                qty=float(r.get("qty", 0)),
                quote_qty=float(r.get("quoteQty", 0)),
                commission=float(r.get("commission", 0)),
                commission_asset=r.get("commissionAsset", ""),
                is_buyer=r.get("isBuyer", 0) == 1,
                is_maker=r.get("isMaker", 0) == 1,
                time=r.get("time", 0)
            )
            for r in raw_list
        ]

    def new_oco_order(self, symbol: str, side: int, quantity: str, price: str,
                      stop_price: str, stop_limit_price: str,
                      list_client_id: str = None, limit_client_id: str = None,
                      stop_client_id: str = None) -> dict:
        params = {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "stopPrice": stop_price,
            "stopLimitPrice": stop_limit_price,
        }
        if list_client_id:
            params["listClientId"] = list_client_id
        if limit_client_id:
            params["limitClientId"] = limit_client_id
        if stop_client_id:
            params["stopClientId"] = stop_client_id
        data = self._post("/open/v1/orders/oco", params, signed=True)
        return data.get("data", {})

    # ── Wallet (SIGNED) ──

    def withdraw(self, asset: str, address: str, amount: str, network: str = None,
                 address_tag: str = None, client_id: str = None) -> str:
        params = {"asset": asset, "address": address, "amount": amount}
        if network:
            params["network"] = network
        if address_tag:
            params["addressTag"] = address_tag
        if client_id:
            params["clientId"] = client_id
        data = self._post("/open/v1/withdraws", params, signed=True)
        return data.get("data", {}).get("withdrawId", "")

    def get_withdraw_history(self, asset: str = None, status: int = None, limit: int = 50) -> List[dict]:
        params = {}
        if asset:
            params["asset"] = asset
        if status is not None:
            params["status"] = status
        data = self._get("/open/v1/withdraws", params, signed=True)
        return data.get("data", {}).get("list", [])

    def get_deposit_history(self, asset: str = None, status: int = None, limit: int = 50) -> List[dict]:
        params = {}
        if asset:
            params["asset"] = asset
        if status is not None:
            params["status"] = status
        data = self._get("/open/v1/deposits", params, signed=True)
        return data.get("data", {}).get("list", [])

    def get_deposit_address(self, asset: str, network: str) -> dict:
        data = self._get("/open/v1/deposits/address", {"asset": asset, "network": network}, signed=True)
        return data.get("data", {})

    # ── User Data Stream ──

    def create_listen_key(self) -> str:
        data = self._post("/open/v1/user-data-stream", signed=True)
        return data.get("data", "")

    def create_listen_token(self, validity_ms: int = 86400000) -> dict:
        params = {"validity": validity_ms}
        data = self._post("/open/v1/user-listen-token", params, signed=True)
        return data.get("data", {})

    def keepalive_listen_key(self, listen_key: str):
        self._put("/open/v1/user-data-stream", {"listenKey": listen_key})

    def _put(self, path: str, params: dict = None):
        url = f"{self.base}{path}"
        resp = self.session.put(url, data=params)
        return self._handle(resp)
