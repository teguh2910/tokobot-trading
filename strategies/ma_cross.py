from typing import Optional, List
import numpy as np
from models import Kline, BotSignal
from strategies.base import Strategy
from config import config


class MACrossoverStrategy(Strategy):
    def __init__(self, symbol: str, interval: str = "1m",
                 fast_period: int = None, slow_period: int = None):
        super().__init__("ma_cross", symbol, interval)
        self.fast_period = fast_period or config.MA_FAST
        self.slow_period = slow_period or config.MA_SLOW
        self.prev_fast_ma = 0.0
        self.prev_slow_ma = 0.0

    def _sma(self, data: List[float], period: int) -> float:
        if len(data) < period:
            return 0.0
        return float(np.mean(data[-period:]))

    def analyze(self) -> Optional[BotSignal]:
        if len(self.klines) < self.slow_period + 1:
            return None

        closes = [k.close for k in self.klines]
        fast_ma = self._sma(closes, self.fast_period)
        slow_ma = self._sma(closes, self.slow_period)

        if fast_ma == 0 or slow_ma == 0:
            return None

        # Golden cross: fast MA crosses above slow MA
        if self.prev_fast_ma <= self.prev_slow_ma and fast_ma > slow_ma:
            signal = BotSignal(
                symbol=self.symbol,
                action="BUY",
                price=closes[-1],
                quantity=0,
                strategy=self.name,
                timestamp=int(self.klines[-1].close_time),
                reason=f"Golden cross: fast MA({fast_ma:.2f}) crossed above slow MA({slow_ma:.2f})"
            )
            self.prev_fast_ma = fast_ma
            self.prev_slow_ma = slow_ma
            return signal

        # Death cross: fast MA crosses below slow MA
        if self.prev_fast_ma >= self.prev_slow_ma and fast_ma < slow_ma:
            signal = BotSignal(
                symbol=self.symbol,
                action="SELL",
                price=closes[-1],
                quantity=0,
                strategy=self.name,
                timestamp=int(self.klines[-1].close_time),
                reason=f"Death cross: fast MA({fast_ma:.2f}) crossed below slow MA({slow_ma:.2f})"
            )
            self.prev_fast_ma = fast_ma
            self.prev_slow_ma = slow_ma
            return signal

        self.prev_fast_ma = fast_ma
        self.prev_slow_ma = slow_ma
        return None

    def reset(self):
        super().reset()
        self.prev_fast_ma = 0.0
        self.prev_slow_ma = 0.0
