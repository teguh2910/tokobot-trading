from abc import ABC, abstractmethod
from typing import List, Optional
from models import Kline, BotSignal


class Strategy(ABC):
    def __init__(self, name: str, symbol: str, interval: str = "1m"):
        self.name = name
        self.symbol = symbol
        self.interval = interval
        self.klines: List[Kline] = []

    @abstractmethod
    def analyze(self) -> Optional[BotSignal]:
        pass

    def update_klines(self, klines: List[Kline]):
        self.klines = klines

    def on_tick(self, price: float, volume: float = 0) -> Optional[BotSignal]:
        return None

    def on_kline(self, kline: Kline) -> Optional[BotSignal]:
        self.klines.append(kline)
        if len(self.klines) > 500:
            self.klines = self.klines[-500:]
        return self.analyze()

    def reset(self):
        self.klines = []
