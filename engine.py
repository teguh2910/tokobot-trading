import json
import logging
import time
import signal
import sys
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime, timezone
from config import config
from models import Kline, BotSignal, Position
from client.rest import TokocryptoClient
from client.ws import TokocryptoWebSocket
from risk import RiskManager
from signal_manager import SignalManager
from strategies.ma_cross import MACrossoverStrategy
from strategies.rsi import RSIStrategy
from strategies.grid import GridStrategy
from db import init_db, init_risk_settings, add_log, get_active_positions, remove_position
from models import AccountBalance

logger = logging.getLogger("tokobot.engine")


STRATEGY_MAP = {
    "ma_cross": MACrossoverStrategy,
    "rsi": RSIStrategy,
    "grid": GridStrategy,
}


class TradingEngine:
    def __init__(self):
        self.client = TokocryptoClient()
        self.ws = TokocryptoWebSocket()
        self.risk = RiskManager()
        self.signal_manager = SignalManager(self.client, self.risk)

        self.strategies: Dict[str, Dict[str, object]] = {}
        self.running = False
        self.last_equity_save = 0
        self.symbol_prices: Dict[str, float] = {}

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        logger.info("Shutdown signal received")
        self.stop()
        sys.exit(0)

    def _get_dynamic_symbols(self) -> list:
        try:
            f = Path("/tmp/tokobot_selected_symbols.json")
            if f.exists():
                data = json.loads(f.read_text())
                syms = data.get("symbols", [])
                if syms:
                    toko_syms = []
                    for s in syms:
                        if s.endswith("IDR"):
                            name = s[:-3]
                            toko_syms.append(f"{name}_IDR")
                        else:
                            toko_syms.append(s)
                    merged = list(dict.fromkeys(config.BOT_SYMBOLS + toko_syms))
                    return merged
        except Exception:
            pass
        return config.BOT_SYMBOLS

    def _add_symbol(self, symbol: str):
        if symbol in self.strategies:
            return
        active = config.BOT_STRATEGIES
        self.strategies[symbol] = {}
        for sname in active:
            cls = STRATEGY_MAP.get(sname)
            if not cls:
                continue
            self.strategies[symbol][sname] = cls(symbol, config.BOT_INTERVAL)
        try:
            klines = self.client.get_klines(symbol, config.BOT_INTERVAL, limit=100)
            if klines:
                for s in self.strategies[symbol].values():
                    s.update_klines(klines)
        except Exception:
            pass
        ws_sym = symbol.replace("_", "").lower()
        self.ws.subscribe(f"{ws_sym}@kline_{config.BOT_INTERVAL}")
        self.ws.subscribe(f"{ws_sym}@aggTrade")
        names = ", ".join(self.strategies[symbol].keys())
        logger.info(f"[Dynamic] Added {symbol} with strategies [{names}]")

    def init_strategies(self):
        symbols = self._get_dynamic_symbols()
        active = config.BOT_STRATEGIES
        for symbol in symbols:
            self.strategies[symbol] = {}
            for sname in active:
                cls = STRATEGY_MAP.get(sname)
                if not cls:
                    logger.error(f"Unknown strategy: {sname}")
                    continue
                self.strategies[symbol][sname] = cls(symbol, config.BOT_INTERVAL)
            names = ", ".join(self.strategies[symbol].keys())
            logger.info(f"Initialized strategies [{names}] for {symbol}")

    def preload_klines(self):
        symbols = self._get_dynamic_symbols()
        for symbol in symbols:
            try:
                klines = self.client.get_klines(symbol, config.BOT_INTERVAL, limit=100)
                strategies = self.strategies.get(symbol, {})
                if strategies and klines:
                    for sname, strategy in strategies.items():
                        strategy.update_klines(klines)
                    logger.info(f"Preloaded {len(klines)} klines for {symbol} ({len(strategies)} strategies)")
            except Exception as e:
                logger.error(f"Failed to preload klines for {symbol}: {e}")

    def on_ws_message(self, data: dict):
        event_type = data.get("e", "")

        if event_type == "kline":
            k = data.get("k", {})
            symbol = k.get("s", "")
            toko_symbol = self._to_toko_symbol(symbol)

            kline = Kline(
                open_time=k["t"],
                open=float(k["o"]),
                high=float(k["h"]),
                low=float(k["l"]),
                close=float(k["c"]),
                volume=float(k["v"]),
                close_time=k["T"],
                quote_volume=float(k.get("q", 0)),
                trades=k.get("n", 0),
                taker_buy_base=float(k.get("V", 0)),
                taker_buy_quote=float(k.get("Q", 0)),
            )

            self.symbol_prices[toko_symbol] = kline.close

            strategies = self.strategies.get(toko_symbol, {})
            if strategies and k.get("x", False):
                signal_count = 0
                for sname, strategy in strategies.items():
                    try:
                        signal = strategy.on_kline(kline)
                        if signal:
                            signal_count += 1
                            self._process_signal(signal)
                    except Exception as e:
                        logger.error(f"Strategy {sname} error for {toko_symbol}: {e}")
                if signal_count == 0:
                    logger.info(f"[{toko_symbol}] Candle closed: {len(strategies)} strategies analyzed, no signal")
                    add_log("DEBUG", f"[{toko_symbol}] {len(strategies)} strategies analyzed, no signal")

            self._check_positions(toko_symbol, kline.close)

        elif event_type == "aggTrade":
            symbol = data.get("s", "")
            toko_symbol = self._to_toko_symbol(symbol)
            self.symbol_prices[toko_symbol] = float(data["p"])

        elif event_type == "executionReport":
            self._handle_execution_report(data)

        elif event_type == "outboundAccountPosition":
            self._handle_account_update(data)

    def _to_toko_symbol(self, ws_symbol: str) -> str:
        all_syms = list(self.strategies.keys()) or config.BOT_SYMBOLS
        for sym in all_syms:
            if ws_symbol.upper() == sym.replace("_", ""):
                return sym
        return ws_symbol

    def _process_signal(self, signal: BotSignal):
        can_trade, reason = self.risk.can_trade(signal.strategy, signal.symbol, signal.action)
        if not can_trade:
            logger.info(f"Signal blocked: {reason}")
            return

        balance = self._get_balance_for_symbol(signal.symbol, signal.action)
        if balance <= 0:
            logger.warning(f"No balance for {signal.symbol} {signal.action}")
            return

        settings = self.risk.get_risk_settings(signal.strategy)
        min_notional = self.client.get_min_notional()

        max_qty = self.client.round_quantity(signal.symbol, balance / signal.price) if signal.price > 0 else 0
        if max_qty <= 0:
            logger.warning(f"Cannot afford any {signal.symbol}")
            return

        min_qty = self.client.round_quantity(signal.symbol, min_notional / signal.price)
        if min_qty <= 0:
            logger.warning(f"Cannot meet min notional for {signal.symbol}")
            return
        if min_qty * signal.price < min_notional:
            step = float(self.client.get_lot_size(signal.symbol).get("stepSize", 0))
            if step > 0:
                min_qty = self.client.round_quantity(signal.symbol, min_notional / signal.price + step)

        if max_qty < min_qty:
            logger.warning(f"Balance too low for {signal.symbol}: need {min_qty:.6f} but can afford {max_qty:.6f}")
            return

        qty = min(min_qty, max_qty)
        signal.quantity = qty

        if signal.stop_loss == 0:
            sl, tp = self.risk.calculate_sl_tp(signal.strategy, signal.action, signal.price)
            signal.stop_loss = sl
            signal.take_profit = tp

        risk_amount = qty * abs(signal.price - signal.stop_loss) if signal.stop_loss > 0 else 0
        if risk_amount > balance * (settings.get("risk_per_trade", 1.0) / 100):
            logger.warning(f"Risk {risk_amount:.0f} exceeds limit ({settings.get('risk_per_trade', 1.0)}% of {balance:.0f}) for {signal.symbol}")
            return

        order = self.signal_manager.execute_signal(signal)
        if order:
            logger.info(f"Signal executed: {signal.action} {signal.symbol} qty={qty:.6f} val={qty*signal.price:.0f} IDR risk={risk_amount:.0f} SL={signal.stop_loss:.2f} TP={signal.take_profit:.2f}")

    def _check_positions(self, symbol: str, current_price: float):
        positions = get_active_positions()
        for pos in positions:
            if pos.symbol != symbol:
                continue
            pos.current_price = current_price
            result = self.risk.check_sl_tp(pos, current_price)
            if result:
                logger.info(f"{result} for {pos.symbol} {pos.side} @ {current_price}")
                self.signal_manager.close_position(pos, result)
                add_log("INFO", f"{result}: {pos.symbol} {pos.side} @ {current_price}")

    def _handle_execution_report(self, data: dict):
        symbol = data.get("s", "")
        exec_type = data.get("x", "")
        order_status = data.get("X", "")
        order_id = str(data.get("i", ""))

        if exec_type == "TRADE" and order_status == "FILLED":
            side = "BUY" if data.get("S") == "BUY" else "SELL"
            price = float(data.get("L", 0))
            qty = float(data.get("l", 0))
            logger.info(f"Order FILLED: {side} {symbol} {qty} @ {price}")

            if side == "SELL":
                remove_position(symbol, "BUY")
                logger.info(f"Position closed via execution report: {symbol}")

        if exec_type == "CANCELED":
            logger.info(f"Order CANCELED: {symbol} id={order_id}")

    def _handle_account_update(self, data: dict):
        balances = data.get("B", [])
        for b in balances:
            asset = b.get("a", "")
            free = float(b.get("f", 0))
            locked = float(b.get("l", 0))
            logger.debug(f"Balance update: {asset} free={free} locked={locked}")

    def _get_balance_for_symbol(self, symbol: str, side: str) -> float:
        try:
            base, quote = symbol.split("_")
            target = base if side == "SELL" else quote
            balance = self.client.get_asset_balance(target)
            return balance.free if balance else 0
        except Exception as e:
            logger.warning(f"Failed to get balance: {e}")
            return 0

    def _save_equity_periodic(self):
        now = int(time.time())
        if now - self.last_equity_save < 60:
            return
        self.last_equity_save = now

        try:
            balances, _ = self.client.get_account_info()
            total = sum(b.free + b.locked for b in balances)
            self.risk.set_balance(total)
            self.risk.record_equity(total, total)
        except Exception as e:
            logger.debug(f"Equity save skipped: {e}")

    def start(self):
        init_db()
        init_risk_settings()

        self.init_strategies()
        self.preload_klines()

        symbols = self._get_dynamic_symbols()
        logger.info(f"Starting bot in {config.BOT_MODE.upper()} mode | Strategies: {config.BOT_STRATEGIES} | Symbols: {symbols}")

        ws_streams = []
        for symbol in symbols:
            ws_sym = symbol.replace("_", "").lower()
            ws_streams.append(f"{ws_sym}@kline_{config.BOT_INTERVAL}")
            ws_streams.append(f"{ws_sym}@aggTrade")

        self.ws.on_message(self.on_ws_message)
        self.ws.connect(ws_streams)

        if config.BOT_MODE == "live":
            try:
                listen_key = self.client.create_listen_key()
                if listen_key:
                    self.ws.subscribe_user_data(listen_key)
                    logger.info("User data stream connected")
            except Exception as e:
                logger.warning(f"Failed to create listen key: {e}")

        self.running = True
        add_log("INFO", f"Bot started: {config.BOT_MODE.upper()} mode, strategies={','.join(config.BOT_STRATEGIES)}")

        heartbeat = 0
        while self.running:
            try:
                self._save_equity_periodic()
                heartbeat += 1
                if heartbeat % 2 == 0:
                    positions = get_active_positions()
                    active_syms = self._get_dynamic_symbols()
                    for sym in active_syms:
                        if sym not in self.strategies:
                            self._add_symbol(sym)
                    logger.info(f"♥ Bot LIVE | {len(active_syms)} symbols × {len(config.BOT_STRATEGIES)} strategies | {len(positions)} active positions")
                    add_log("INFO", f"Bot LIVE | {len(active_syms)} symbols × {len(config.BOT_STRATEGIES)} strategies | {len(positions)} active positions")
                time.sleep(30)
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Engine loop error: {e}")
                time.sleep(5)

    def stop(self):
        logger.info("Stopping bot engine...")
        self.running = False
        self.ws.close()
        add_log("INFO", "Bot stopped")
