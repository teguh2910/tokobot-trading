import logging
from datetime import datetime, timezone
from typing import Optional, Tuple
from config import config
from models import Position, AccountBalance
from db import get_risk_settings, get_active_positions, get_performance_metrics, save_equity_snapshot

logger = logging.getLogger("tokobot.risk")


class RiskManager:
    def __init__(self):
        self.daily_start_balance: float = 0.0
        self.current_balance: float = 0.0
        self.daily_pnl: float = 0.0
        self.last_reset_day: int = datetime.now(timezone.utc).day

    def set_balance(self, balance: float):
        today = datetime.now(timezone.utc).day
        if today != self.last_reset_day:
            self.daily_start_balance = balance
            self.daily_pnl = 0.0
            self.last_reset_day = today

        if self.daily_start_balance == 0:
            self.daily_start_balance = balance

        diff = balance - self.current_balance
        if diff > self.current_balance * 0.5 and self.current_balance > 0:
            self.daily_start_balance += diff

        self.current_balance = balance
        self.daily_pnl = balance - self.daily_start_balance

    def get_risk_settings(self, strategy: str) -> dict:
        settings = get_risk_settings(strategy)
        if not settings:
            return {
                "risk_per_trade": config.RISK_PER_TRADE,
                "reward_ratio_num": config.RISK_REWARD_NUM,
                "reward_ratio_den": config.RISK_REWARD_DEN,
                "sl_type": config.SL_TYPE,
                "sl_value": config.SL_VALUE,
                "tp_value": (config.RISK_REWARD_DEN / config.RISK_REWARD_NUM) * config.SL_VALUE
                if config.RISK_REWARD_NUM > 0 else config.SL_VALUE * 2,
                "max_daily_loss": config.MAX_DAILY_LOSS,
                "max_open_positions": config.MAX_OPEN_POSITIONS,
                "enabled": 1,
            }
        return settings

    def can_trade(self, strategy: str, symbol: str = "", side: str = "") -> Tuple[bool, str]:
        if config.BOT_MODE == "paper":
            return True, "paper"

        settings = self.get_risk_settings(strategy)
        if not settings.get("enabled"):
            return False, "Strategy disabled"

        daily_loss_pct = 0
        if self.daily_start_balance > 0:
            daily_loss_pct = abs(self.daily_pnl) / self.daily_start_balance * 100

        max_loss = settings.get("max_daily_loss", config.MAX_DAILY_LOSS)
        if daily_loss_pct >= max_loss:
            return False, f"Daily loss limit reached: {daily_loss_pct:.1f}% >= {max_loss}%"

        active_positions = get_active_positions()
        max_pos = settings.get("max_open_positions", config.MAX_OPEN_POSITIONS)
        if len(active_positions) >= max_pos:
            return False, f"Max open positions reached: {len(active_positions)}"

        return True, "ok"

    def calculate_position_size(self, strategy: str, balance: float,
                                entry_price: float, stop_loss_price: float) -> float:
        settings = self.get_risk_settings(strategy)
        risk_pct = settings.get("risk_per_trade", config.RISK_PER_TRADE) / 100
        risk_amount = balance * risk_pct

        price_risk = abs(entry_price - stop_loss_price)
        if price_risk <= 0:
            return 0

        quantity = risk_amount / price_risk
        return max(quantity, 0)

    def calculate_sl_tp(self, strategy: str, side: str, entry_price: float) -> Tuple[float, float]:
        settings = self.get_risk_settings(strategy)
        sl_type = settings.get("sl_type", config.SL_TYPE)
        sl_value = settings.get("sl_value", config.SL_VALUE) / 100
        rr_num = settings.get("reward_ratio_num", config.RISK_REWARD_NUM)
        rr_den = settings.get("reward_ratio_den", config.RISK_REWARD_DEN)

        if side == "BUY":
            stop_loss = entry_price * (1 - sl_value)
            risk_amount = entry_price - stop_loss
            take_profit = entry_price + (risk_amount * rr_den / rr_num) if rr_num > 0 else entry_price * (1 + sl_value * 2)
        else:
            stop_loss = entry_price * (1 + sl_value)
            risk_amount = stop_loss - entry_price
            take_profit = entry_price - (risk_amount * rr_den / rr_num) if rr_num > 0 else entry_price * (1 - sl_value * 2)

        return round(stop_loss, 8), round(take_profit, 8)

    def check_sl_tp(self, position: Position, current_price: float) -> Optional[str]:
        if position.side == "BUY":
            if current_price <= position.stop_loss:
                return "SL_HIT"
            if current_price >= position.take_profit:
                return "TP_HIT"
        else:
            if current_price >= position.stop_loss:
                return "SL_HIT"
            if current_price <= position.take_profit:
                return "TP_HIT"
        return None

    def record_equity(self, balance: float, equity: float):
        timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
        save_equity_snapshot(timestamp, balance, equity, self.daily_pnl)
