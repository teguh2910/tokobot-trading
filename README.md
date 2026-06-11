# Tokocrypto Trading Bot

Automated cryptocurrency trading bot for Tokocrypto exchange with multiple strategies, real-time WebSocket streaming, SQLite database, and a web dashboard.

## Features

- **Multiple Strategies**: RSI, Grid, MA Crossover — run simultaneously
- **Scalping Mode**: Tight SL (0.5%), 1:1.5 R:R, RSI period 7
- **Live & Paper Trading**: Switch via `BOT_MODE` config
- **Real-time Data**: WebSocket market data + user data streams
- **Risk Management**: Per-strategy SL/TP, daily loss limit, max positions
- **Quantity Validation**: LOT_SIZE rounding, min notional (20,000 IDR)
- **Web Dashboard**: FastAPI + Chart.js + Bootstrap 5 dark theme
  - Overview, Trades, Orders, Performance, Strategy config, Logs, Portfolio
- **SQLite Storage**: Orders, trades, positions, equity snapshots, logs
- **Systemd Service**: Runs as `tokobot` and `tokobot-dashboard` services

## Requirements

- Python 3.10+
- Tokocrypto API key with trading permissions (IP whitelisted)

## Quick Start

```bash
git clone https://github.com/teguh2910/tokobot-trading.git
cd tokobot-trading
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
python3 main.py --mode paper --symbol BTC_IDR --strategy rsi
```

## Configuration

Edit `.env` to configure:

| Variable | Description |
|---|---|
| `TOKO_API_KEY` | Tokocrypto API key |
| `TOKO_API_SECRET` | Tokocrypto API secret |
| `BOT_MODE` | `live` or `paper` |
| `BOT_STRATEGIES` | Comma-separated: `rsi,grid,ma_cross` |
| `BOT_SYMBOLS` | Comma-separated: `BTC_IDR,ETH_IDR,...` |
| `RSI_PERIOD` | RSI lookback period (default: 7) |
| `RSI_OVERSOLD` | Oversold threshold (default: 25) |
| `RSI_OVERBOUGHT` | Overbought threshold (default: 75) |
| `GRID_SPREAD` | Grid spacing percent (default: 0.3) |
| `DASHBOARD_PORT` | Dashboard port (default: 8080) |

## Directory Structure

```
tokobot-trading/
├── client/          # REST + WebSocket Tokocrypto API client
├── strategies/      # Trading strategies (ma_cross, rsi, grid)
├── web/             # FastAPI dashboard
│   ├── static/      # CSS, JS, assets
│   └── templates/   # Jinja2 HTML templates
├── config.py        # ENV-based configuration
├── engine.py        # Main trading engine
├── db.py            # SQLite database layer
├── models.py        # Data models
├── risk.py          # Risk management (SL/TP, position sizing)
├── signal_manager.py# Order execution + position tracking
├── main.py          # Entry point
└── requirements.txt
```

## Dashboard

Access at `http://<host>:8080`:

- **Overview**: Portfolio value, BTC price, active positions, balance pie chart, equity curve
- **Trades**: Trade history with PnL, filterable by symbol/strategy/side
- **Orders**: Active positions with current PnL, SL/TP levels
- **Performance**: Metrics (win rate, profit factor, Sharpe ratio, drawdown), equity curve
- **Strategy**: Per-strategy risk settings (risk per trade, R:R ratio, max positions)
- **Logs**: Real-time bot logs
- **Portfolio**: Asset allocation with donut chart, equity curve, asset breakdown table

## License

MIT
