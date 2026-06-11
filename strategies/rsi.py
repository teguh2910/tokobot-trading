from typing import Optional, List
import numpy as np
from models import Kline, BotSignal
from strategies.base import Strategy
from config import config


class RSIStrategy(Strategy):
    def __init__(self, symbol: str, interval: str = "1m",
                 period: int = None, oversold: int = None, overbought: int = None):
        super().__init__("rsi", symbol, interval)
        self.period = period or config.RSI_PERIOD
        self.oversold = oversold or config.RSI_OVERSOLD
        self.overbought = overbought or config.RSI_OVERBOUGHT
        self.prev_rsi = 50.0
        self.last_signal = ""

    def _compute_rsi(self, closes: List[float]) -> float:
        if len(closes) < self.period + 1:
            return 50.0

        deltas = np.diff(closes[-self.period - 1:])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = float(np.mean(gains))
        avg_loss = float(np.mean(losses))

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return rsi

    def analyze(self) -> Optional[BotSignal]:
        if len(self.klines) < self.period + 1:
            return None

        closes = [k.close for k in self.klines]
        rsi = self._compute_rsi(closes)
        current_price = closes[-1]

        # Oversold: RSI below threshold then crosses back up
        if self.prev_rsi <= self.oversold and rsi > self.oversold and self.last_signal != "BUY":
            self.last_signal = "BUY"
            signal = BotSignal(
                symbol=self.symbol,
                action="BUY",
                price=current_price,
                quantity=0,
                strategy=self.name,
                timestamp=int(self.klines[-1].close_time),
                reason=f"RSI oversold bounce: {rsi:.1f} (threshold: {self.oversold})"
            )
            self.prev_rsi = rsi
            return signal

        # Overbought: RSI above threshold then crosses back down
        if self.prev_rsi >= self.overbought and rsi < self.overbought and self.last_signal != "SELL":
            self.last_signal = "SELL"
            signal = BotSignal(
                symbol=self.symbol,
                action="SELL",
                price=current_price,
                quantity=0,
                strategy=self.name,
                timestamp=int(self.klines[-1].close_time),
                reason=f"RSI overbought drop: {rsi:.1f} (threshold: {self.overbought})"
            )
            self.prev_rsi = rsi
            return signal

        self.prev_rsi = rsi
        return None

    def reset(self):
        super().reset()
        self.prev_rsi = 50.0
        self.last_signal = ""
