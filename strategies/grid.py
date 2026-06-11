from typing import Optional, List
from models import Kline, BotSignal, Position
from strategies.base import Strategy
from config import config


class GridStrategy(Strategy):
    def __init__(self, symbol: str, interval: str = "1m",
                 levels: int = None, spread_pct: float = None,
                 total_investment: float = None):
        super().__init__("grid", symbol, interval)
        self.levels = levels or config.GRID_LEVELS
        self.spread_pct = spread_pct or config.GRID_SPREAD_PCT
        self.total_investment = total_investment or config.GRID_TOTAL_INVESTMENT
        self.grid_orders: List[dict] = []
        self.initialized = False
        self.base_price: float = 0.0

    def initialize_grid(self, current_price: float):
        self.base_price = current_price
        self.grid_orders = []
        half_levels = self.levels // 2

        investment_per_level = self.total_investment / self.levels

        for i in range(1, half_levels + 1):
            buy_price = current_price * (1 - self.spread_pct / 100 * i)
            buy_qty = investment_per_level / buy_price
            self.grid_orders.append({
                "side": "BUY",
                "price": round(buy_price, 8),
                "quantity": round(buy_qty, 8),
                "filled": False,
                "level": i
            })

        for i in range(1, half_levels + 1):
            sell_price = current_price * (1 + self.spread_pct / 100 * i)
            sell_qty = investment_per_level / sell_price
            self.grid_orders.append({
                "side": "SELL",
                "price": round(sell_price, 8),
                "quantity": round(sell_qty, 8),
                "filled": False,
                "level": i
            })

        self.initialized = True

    def analyze(self) -> Optional[BotSignal]:
        if not self.klines:
            return None

        current_price = self.klines[-1].close

        if not self.initialized:
            self.initialize_grid(current_price)
            return None

        for order in self.grid_orders:
            if order["filled"]:
                continue

            if order["side"] == "BUY" and current_price <= order["price"]:
                order["filled"] = True
                return BotSignal(
                    symbol=self.symbol,
                    action="BUY",
                    price=order["price"],
                    quantity=order["quantity"],
                    strategy=self.name,
                    timestamp=int(self.klines[-1].close_time),
                    reason=f"Grid buy at level {order['level']}: {order['price']}"
                )

            if order["side"] == "SELL" and current_price >= order["price"]:
                order["filled"] = True
                return BotSignal(
                    symbol=self.symbol,
                    action="SELL",
                    price=order["price"],
                    quantity=order["quantity"],
                    strategy=self.name,
                    timestamp=int(self.klines[-1].close_time),
                    reason=f"Grid sell at level {order['level']}: {order['price']}"
                )

        return None

    def refill_grid_order(self, side: str, level: int):
        for order in self.grid_orders:
            if order["side"] == side and order["level"] == level and order["filled"]:
                order["filled"] = False

    def reset(self):
        super().reset()
        self.grid_orders = []
        self.initialized = False
        self.base_price = 0.0
