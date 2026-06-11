import logging
import uuid
from typing import Optional
from config import config
from models import BotSignal, Order, Position, Trade
from client.rest import TokocryptoClient
from risk import RiskManager
from db import save_order, save_trade, save_position, remove_position
from datetime import datetime

logger = logging.getLogger("tokobot.signal")


class SignalManager:
    def __init__(self, client: TokocryptoClient, risk: RiskManager):
        self.client = client
        self.risk = risk

    def execute_signal(self, signal: BotSignal) -> Optional[Order]:
        if config.BOT_MODE == "paper":
            return self._paper_execute(signal)

        return self._live_execute(signal)

    def _paper_execute(self, signal: BotSignal) -> Optional[Order]:
        logger.info(f"[PAPER] {signal.action} {signal.symbol} @ {signal.price} | {signal.reason}")

        order = Order(
            order_id=f"paper_{uuid.uuid4().hex[:12]}",
            symbol=signal.symbol,
            side=0 if signal.action == "BUY" else 1,
            type=2,
            price=signal.price,
            orig_qty=signal.quantity,
            executed_qty=signal.quantity,
            status=2,
            create_time=int(datetime.now().timestamp() * 1000),
            client_id=f"paper_{uuid.uuid4().hex[:8]}",
        )
        save_order(order)

        trade = Trade(
            trade_id=f"t_{uuid.uuid4().hex[:12]}",
            order_id=order.order_id,
            symbol=signal.symbol,
            price=signal.price,
            qty=signal.quantity,
            quote_qty=signal.price * signal.quantity,
            commission=0,
            commission_asset="",
            is_buyer=(signal.action == "BUY"),
            is_maker=False,
            time=order.create_time,
        )

        fake_pnl = 0
        if signal.action == "SELL":
            positions = self._get_model("position", signal.symbol, "BUY")
            for pos in positions:
                fake_pnl = (signal.price - pos.entry_price) * signal.quantity
                break

        save_trade(trade, pnl=fake_pnl, strategy=signal.strategy)

        if signal.stop_loss > 0 and signal.take_profit > 0:
            pos = Position(
                symbol=signal.symbol,
                side=signal.action,
                entry_price=signal.price,
                quantity=signal.quantity,
                current_price=signal.price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                open_time=order.create_time,
                strategy=signal.strategy,
                order_id=order.order_id,
            )
            save_position(pos)

        return order

    def _live_execute(self, signal: BotSignal):
        side = 0 if signal.action == "BUY" else 1
        qty_str = str(signal.quantity)

        try:
            order = self.client.new_order(
                symbol=signal.symbol,
                side=side,
                order_type=2,
                quantity=qty_str,
            )
            save_order(order)

            if order.status == 2 and side == 0:
                entry_price = order.price if order.price > 0 else signal.price
                if order.cum_quote_qty > 0 and order.executed_qty > 0:
                    entry_price = order.cum_quote_qty / order.executed_qty
                pos = Position(
                    symbol=signal.symbol,
                    side="BUY",
                    entry_price=entry_price,
                    quantity=order.executed_qty or signal.quantity,
                    current_price=entry_price,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    open_time=order.create_time,
                    strategy=signal.strategy,
                    order_id=order.order_id,
                )
                save_position(pos)

                entry_trade = Trade(
                    trade_id=f"t_{uuid.uuid4().hex[:12]}",
                    order_id=order.order_id,
                    symbol=signal.symbol,
                    price=entry_price,
                    qty=pos.quantity,
                    quote_qty=entry_price * pos.quantity,
                    commission=0,
                    commission_asset="",
                    is_buyer=True,
                    is_maker=False,
                    time=order.create_time,
                )
                save_trade(entry_trade, pnl=0, strategy=signal.strategy)
                logger.info(f"[LIVE] Position opened: BUY {signal.symbol} qty={pos.quantity} @ {entry_price:.2f}")

            logger.info(f"[LIVE] Order placed: {order.order_id} {signal.action} {signal.symbol} qty={signal.quantity}")
            return order

        except Exception as e:
            logger.error(f"[LIVE] Order failed: {e}")
            return None

    def close_position(self, position: Position, reason: str):
        if config.BOT_MODE == "paper":
            side = "SELL" if position.side == "BUY" else "BUY"
            close_price = position.stop_loss if "SL" in reason else position.take_profit
            pnl = (close_price - position.entry_price) * position.quantity
            if position.side == "SELL":
                pnl = (position.entry_price - close_price) * position.quantity

            logger.info(f"[PAPER] Close {position.symbol} {position.side} @ {close_price} PnL={pnl:.2f} | {reason}")

            trade = Trade(
                trade_id=f"t_{uuid.uuid4().hex[:12]}",
                order_id=position.order_id,
                symbol=position.symbol,
                price=close_price,
                qty=position.quantity,
                quote_qty=close_price * position.quantity,
                commission=0,
                commission_asset="",
                is_buyer=(side == "BUY"),
                is_maker=False,
                time=int(datetime.now().timestamp() * 1000),
            )
            save_trade(trade, pnl=pnl, strategy=position.strategy)
            remove_position(position.symbol, position.side)
        else:
            try:
                base_asset = position.symbol.split("_")[0]
                balance = self.client.get_asset_balance(base_asset)
                actual_qty = min(balance.free, position.quantity) if balance else position.quantity
                if actual_qty <= 0:
                    logger.warning(f"Cannot close {position.symbol}: no {base_asset} balance")
                    remove_position(position.symbol, position.side)
                    return

                side = 1 if position.side == "BUY" else 0
                order = self.client.new_order(
                    symbol=position.symbol,
                    side=side,
                    order_type=2,
                    quantity=f"{actual_qty:.8f}",
                )

                close_price = order.price
                if close_price <= 0 and order.cum_quote_qty > 0 and order.executed_qty > 0:
                    close_price = order.cum_quote_qty / order.executed_qty
                if close_price <= 0:
                    close_price = position.current_price

                pnl = (close_price - position.entry_price) * position.quantity
                if position.side == "SELL":
                    pnl = (position.entry_price - close_price) * position.quantity

                trade = Trade(
                    trade_id=f"t_{uuid.uuid4().hex[:12]}",
                    order_id=order.order_id,
                    symbol=position.symbol,
                    price=close_price,
                    qty=position.quantity,
                    quote_qty=close_price * position.quantity,
                    commission=0,
                    commission_asset="",
                    is_buyer=(side == 0),
                    is_maker=False,
                    time=int(datetime.now().timestamp() * 1000),
                )
                save_trade(trade, pnl=pnl, strategy=position.strategy)
                remove_position(position.symbol, position.side)
                logger.info(f"[LIVE] Closed {position.symbol} {position.side} @ {close_price:.2f} PnL={pnl:.2f} | {reason}")
            except Exception as e:
                logger.error(f"[LIVE] Close position failed: {e}")

    def _get_model(self, model_type: str, symbol: str, side: str):
        from db import get_active_positions
        positions = get_active_positions()
        return [p for p in positions if p.symbol == symbol and p.side == side]
