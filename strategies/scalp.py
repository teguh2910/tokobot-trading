import numpy as np
from typing import Optional
from strategies.base import Strategy
from models import BotSignal


class ScalpStrategy(Strategy):
    def __init__(self, symbol: str, interval: str = "1m"):
        super().__init__("scalp", symbol, interval)
        self.rsi_period = 7
        self.prev_rsi = 50.0
        self.last_signal = ""
        self.entry_price = 0
        self.entry_time = 0
        self.tp_pct = 0.5
        self.max_candles = 10

    def _compute_rsi(self, closes, period=7):
        if len(closes) < period + 1:
            return 50.0
        deltas = np.diff(closes[-period - 1:])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = float(np.mean(gains))
        avg_loss = float(np.mean(losses))
        if avg_loss == 0:
            return 100.0
        return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))

    def analyze(self) -> Optional[BotSignal]:
        if len(self.klines) < self.rsi_period + 1:
            return None

        closes = [k.close for k in self.klines]
        current_price = closes[-1]
        rsi = self._compute_rsi(closes)

        recent_vol = float(np.mean([k.volume for k in self.klines[-3:]]))
        avg_vol = float(np.mean([k.volume for k in self.klines]))
        vol_surge = recent_vol / avg_vol if avg_vol > 0 else 0

        signal = None

        if self.entry_price > 0:
            pnl_pct = (current_price / self.entry_price - 1) * 100
            candles_since_entry = len(self.klines) - self.entry_time

            if pnl_pct >= self.tp_pct:
                self.reset()
                signal = BotSignal(
                    symbol=self.symbol,
                    action="SELL",
                    price=current_price,
                    quantity=0,
                    strategy=self.name,
                    timestamp=int(self.klines[-1].close_time),
                    reason=f"TP {pnl_pct:.2f}%"
                )
                return signal

            if rsi > 70:
                self.reset()
                signal = BotSignal(
                    symbol=self.symbol,
                    action="SELL",
                    price=current_price,
                    quantity=0,
                    strategy=self.name,
                    timestamp=int(self.klines[-1].close_time),
                    reason=f"RSI overbought {rsi:.1f}"
                )
                return signal

            if candles_since_entry >= self.max_candles:
                self.reset()
                signal = BotSignal(
                    symbol=self.symbol,
                    action="SELL",
                    price=current_price,
                    quantity=0,
                    strategy=self.name,
                    timestamp=int(self.klines[-1].close_time),
                    reason=f"Time exit {candles_since_entry}c"
                )
                return signal

        elif vol_surge > 1.5 and rsi < 65 and self.prev_rsi <= rsi and self.last_signal != "BUY":
            self.last_signal = "BUY"
            self.entry_price = current_price
            self.entry_time = len(self.klines)
            signal = BotSignal(
                symbol=self.symbol,
                action="BUY",
                price=current_price,
                quantity=0,
                strategy=self.name,
                timestamp=int(self.klines[-1].close_time),
                reason=f"Vol spike {vol_surge:.1f}x RSI {rsi:.1f}"
            )

        self.prev_rsi = rsi
        return signal

    def on_kline(self, kline) -> Optional[BotSignal]:
        self.klines.append(kline)
        if len(self.klines) > 100:
            self.klines = self.klines[-100:]
        signal = self.analyze()
        return signal

    def reset(self):
        self.klines = []
        self.prev_rsi = 50.0
        self.last_signal = ""
        self.entry_price = 0
        self.entry_time = 0
