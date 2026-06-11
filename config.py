import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # API
    API_KEY = os.getenv("TOKO_API_KEY", "")
    SECRET_KEY = os.getenv("TOKO_SECRET_KEY", "")
    BASE_URL = "https://www.tokocrypto.com"
    BASE_URL_SITE = "https://www.tokocrypto.site"

    # Bot
    BOT_MODE = os.getenv("BOT_MODE", "paper")
    BOT_STRATEGY = "scalp"
    BOT_STRATEGIES = ["scalp"]
    BOT_SYMBOLS = [s.strip() for s in os.getenv("BOT_SYMBOLS", "BTC_IDR").split(",")]
    BOT_INTERVAL = "1m"

    # Risk
    RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "1.0"))
    RISK_REWARD_NUM = int(os.getenv("RISK_REWARD_NUM", "1"))
    RISK_REWARD_DEN = int(os.getenv("RISK_REWARD_DEN", "2"))
    SL_TYPE = os.getenv("SL_TYPE", "fixed")
    SL_VALUE = float(os.getenv("SL_VALUE", "1.0"))
    MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "5.0"))
    MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "3"))

    # Grid
    GRID_LEVELS = int(os.getenv("GRID_LEVELS", "10"))
    GRID_SPREAD_PCT = float(os.getenv("GRID_SPREAD_PCT", "0.5"))
    GRID_TOTAL_INVESTMENT = float(os.getenv("GRID_TOTAL_INVESTMENT", "100"))

    # MA Crossover
    MA_FAST = int(os.getenv("MA_FAST", "9"))
    MA_SLOW = int(os.getenv("MA_SLOW", "21"))

    # RSI
    RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))
    RSI_OVERSOLD = int(os.getenv("RSI_OVERSOLD", "30"))
    RSI_OVERBOUGHT = int(os.getenv("RSI_OVERBOUGHT", "70"))

    # Dashboard
    DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8000"))
    DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    DASHBOARD_USER = os.getenv("DASHBOARD_USER", "admin")
    DASHBOARD_PASS = os.getenv("DASHBOARD_PASS", "admin123")

    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    @property
    def risk_reward_ratio(self):
        return self.RISK_REWARD_NUM / self.RISK_REWARD_DEN


config = Config()
