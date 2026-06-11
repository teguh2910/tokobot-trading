#!/usr/bin/env python3
import argparse
import logging
import sys
import os

os.makedirs("logs", exist_ok=True)

fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

sh = logging.StreamHandler(sys.stdout)
sh.setLevel(logging.WARNING)
sh.setFormatter(fmt)

fh = logging.FileHandler("logs/bot.log")
fh.setLevel(logging.INFO)
fh.setFormatter(fmt)

root = logging.getLogger()
root.setLevel(logging.NOTSET)
root.addHandler(sh)
root.addHandler(fh)

for name in ("tokobot", "tokobot.engine", "tokobot.signal", "tokobot.ws", "tokobot.risk"):
    logging.getLogger(name).setLevel(logging.INFO)
    logging.getLogger(name).propagate = True


def parse_args():
    parser = argparse.ArgumentParser(description="Tokocrypto Trading Bot")
    parser.add_argument("--mode", choices=["paper", "live", "dashboard"], default=None,
                        help="Bot mode (default: from .env)")
    parser.add_argument("--strategy", choices=["ma_cross", "rsi", "grid"], default=None,
                        help="Trading strategy (default: from .env)")
    parser.add_argument("--strategies", type=str, default=None,
                        help="Comma-separated strategies (default: from .env)")
    parser.add_argument("--symbol", type=str, default=None,
                        help="Trading symbol, comma separated (default: from .env)")
    parser.add_argument("--dashboard", action="store_true",
                        help="Start dashboard server alongside bot")
    parser.add_argument("--dashboard-only", action="store_true",
                        help="Start only the dashboard server (no trading)")
    parser.add_argument("--port", type=int, default=None,
                        help="Dashboard port (default: 8000)")
    parser.add_argument("--init-db", action="store_true",
                        help="Initialize database and exit")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.mode:
        import config as cfg
        cfg.config.BOT_MODE = args.mode
    if args.strategies:
        import config as cfg
        cfg.config.BOT_STRATEGIES = [s.strip() for s in args.strategies.split(",")]
    if args.strategy:
        import config as cfg
        cfg.config.BOT_STRATEGIES = [args.strategy]
    if args.symbol:
        import config as cfg
        cfg.config.BOT_SYMBOLS = [s.strip() for s in args.symbol.split(",")]
    if args.port:
        import config as cfg
        cfg.config.DASHBOARD_PORT = args.port

    from db import init_db, init_risk_settings

    if args.init_db:
        init_db()
        init_risk_settings()
        logger.info("Database initialized successfully")
        return

    if args.dashboard_only:
        logger.info("Starting dashboard server only...")
        from web.server import start_dashboard
        start_dashboard()
        return

    from engine import TradingEngine

    engine = TradingEngine()

    if args.dashboard:
        import threading
        from web.server import start_dashboard

        dash_thread = threading.Thread(target=start_dashboard, daemon=True)
        dash_thread.start()
        logger.info(f"Dashboard started on http://localhost:{engine.client.config.DASHBOARD_PORT}")

    engine.start()


if __name__ == "__main__":
    main()
