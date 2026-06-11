from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
import json


@dataclass
class Kline:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int
    quote_volume: float
    trades: int
    taker_buy_base: float
    taker_buy_quote: float

    @classmethod
    def from_list(cls, data: list):
        return cls(
            open_time=data[0],
            open=float(data[1]),
            high=float(data[2]),
            low=float(data[3]),
            close=float(data[4]),
            volume=float(data[5]),
            close_time=data[6],
            quote_volume=float(data[7]),
            trades=data[8],
            taker_buy_base=float(data[9]),
            taker_buy_quote=float(data[10]),
        )


@dataclass
class Order:
    order_id: str
    symbol: str
    side: int
    type: int
    price: float
    orig_qty: float
    executed_qty: float
    status: int
    create_time: int
    client_id: str = ""
    stop_price: float = 0.0
    iceberg_qty: float = 0.0
    time_in_force: int = 1

    @property
    def side_str(self) -> str:
        return "BUY" if self.side == 0 else "SELL"

    @property
    def status_str(self) -> str:
        status_map = {
            -2: "PROCESSING", 0: "NEW", 1: "PARTIALLY_FILLED",
            2: "FILLED", 3: "CANCELED", 4: "PENDING_CANCEL",
            5: "REJECTED", 6: "EXPIRED"
        }
        return status_map.get(self.status, "UNKNOWN")

    @property
    def type_str(self) -> str:
        type_map = {
            1: "LIMIT", 2: "MARKET", 3: "STOP_LOSS",
            4: "STOP_LOSS_LIMIT", 5: "TAKE_PROFIT", 6: "TAKE_PROFIT_LIMIT",
            7: "LIMIT_MAKER"
        }
        return type_map.get(self.type, "UNKNOWN")


@dataclass
class Trade:
    trade_id: str
    order_id: str
    symbol: str
    price: float
    qty: float
    quote_qty: float
    commission: float
    commission_asset: str
    is_buyer: bool
    is_maker: bool
    time: int

    @property
    def side_str(self) -> str:
        return "BUY" if self.is_buyer else "SELL"


@dataclass
class AccountBalance:
    asset: str
    free: float
    locked: float

    @property
    def total(self) -> float:
        return self.free + self.locked


@dataclass
class Ticker:
    symbol: str
    price: float
    change_24h: float = 0.0
    volume_24h: float = 0.0


@dataclass
class Position:
    symbol: str
    side: str
    entry_price: float
    quantity: float
    current_price: float
    stop_loss: float
    take_profit: float
    open_time: int
    strategy: str = ""
    order_id: str = ""

    @property
    def pnl(self) -> float:
        if self.side == "BUY":
            return (self.current_price - self.entry_price) * self.quantity
        return (self.entry_price - self.current_price) * self.quantity

    @property
    def pnl_pct(self) -> float:
        return (self.pnl / (self.entry_price * self.quantity)) * 100


@dataclass
class BotSignal:
    symbol: str
    action: str
    price: float
    quantity: float
    strategy: str
    timestamp: int
    stop_loss: float = 0.0
    take_profit: float = 0.0
    reason: str = ""


@dataclass
class PerformanceMetrics:
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0

    @property
    def win_rate_pct(self) -> str:
        return f"{self.win_rate:.1f}%"

    @property
    def profit_factor_str(self) -> str:
        return f"{self.profit_factor:.2f}" if self.profit_factor else "N/A"
