import asyncio
import json
import logging
import threading
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from config import config as bot_config
from db import (
    get_performance_metrics, get_trade_history, get_equity_history,
    get_active_positions, get_recent_logs, get_risk_settings, update_risk_settings,
    add_log
)

logger = logging.getLogger("tokobot.dashboard")

cfg = {
    "BOT_MODE": bot_config.BOT_MODE,
    "BOT_STRATEGY": bot_config.BOT_STRATEGY,
    "BOT_STRATEGIES": bot_config.BOT_STRATEGIES,
    "BOT_SYMBOLS": bot_config.BOT_SYMBOLS,
    "DASHBOARD_PORT": bot_config.DASHBOARD_PORT,
    "DASHBOARD_HOST": bot_config.DASHBOARD_HOST,
    "DASHBOARD_USER": bot_config.DASHBOARD_USER,
    "DASHBOARD_PASS": bot_config.DASHBOARD_PASS,
    "MA_FAST": bot_config.MA_FAST,
    "MA_SLOW": bot_config.MA_SLOW,
    "RSI_PERIOD": bot_config.RSI_PERIOD,
    "RSI_OVERSOLD": bot_config.RSI_OVERSOLD,
    "RSI_OVERBOUGHT": bot_config.RSI_OVERBOUGHT,
}

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Tokocrypto Trading Bot Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["cfg"] = cfg

connected_websockets = set()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"cfg": cfg})


@app.get("/trades", response_class=HTMLResponse)
async def trades_page(request: Request):
    return templates.TemplateResponse(request, "trades.html")


@app.get("/orders", response_class=HTMLResponse)
async def orders_page(request: Request):
    return templates.TemplateResponse(request, "orders.html")


@app.get("/performance", response_class=HTMLResponse)
async def performance_page(request: Request):
    return templates.TemplateResponse(request, "performance.html")


@app.get("/strategy", response_class=HTMLResponse)
async def strategy_page(request: Request):
    return templates.TemplateResponse(request, "strategy.html", {"strategies": ["ma_cross", "rsi", "grid"]})


@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    return templates.TemplateResponse(request, "logs.html")


@app.get("/portfolio", response_class=HTMLResponse)
async def portfolio_page(request: Request):
    return templates.TemplateResponse(request, "portfolio.html")


# ── API Routes ──

@app.get("/api/dashboard")
async def api_dashboard():
    metrics = get_performance_metrics()
    positions = get_active_positions()
    active_orders = []
    try:
        from client.rest import TokocryptoClient
        client = TokocryptoClient()
        balances, can_trade = client.get_account_info()
        balance_data = [{"asset": b.asset, "free": b.free, "locked": b.locked, "total": b.total} for b in balances]
    except Exception as e:
        balance_data = []
        logger.warning(f"Dashboard balance fetch failed: {e}")

    return {
        "metrics": {
            "total_trades": metrics.total_trades,
            "win_rate": f"{metrics.win_rate:.1f}",
            "total_pnl": round(metrics.total_pnl, 2),
            "profit_factor": metrics.profit_factor_str,
            "max_drawdown": round(metrics.max_drawdown, 2),
            "sharpe_ratio": round(metrics.sharpe_ratio, 2),
        },
        "balances": balance_data,
        "positions": [
            {
                "symbol": p.symbol, "side": p.side,
                "entry_price": p.entry_price, "quantity": p.quantity,
                "pnl": round(p.pnl, 2), "pnl_pct": round(p.pnl_pct, 2),
                "stop_loss": p.stop_loss, "take_profit": p.take_profit,
            }
            for p in positions
        ],
        "active_orders_count": len(active_orders),
        "bot_mode": bot_config.BOT_MODE,
        "bot_strategies": bot_config.BOT_STRATEGIES,
        "symbols": bot_config.BOT_SYMBOLS,
    }


@app.get("/api/trades")
async def api_trades(symbol: str = "", strategy: str = "", side: str = "", limit: int = 100):
    trades = get_trade_history(limit=limit, symbol=symbol, strategy=strategy, side=side)
    for t in trades:
        t["trade_time_str"] = datetime.fromtimestamp(t["trade_time"] / 1000).strftime("%Y-%m-%d %H:%M:%S")
    return {"trades": trades}


@app.get("/api/orders/active")
async def api_active_orders():
    positions = get_active_positions()
    return {
        "orders": [
            {
                "symbol": p.symbol, "side": p.side,
                "price": p.entry_price, "qty": p.quantity,
                "stop_loss": p.stop_loss, "take_profit": p.take_profit,
                "pnl": round(p.pnl, 2), "open_time": p.open_time,
                "strategy": p.strategy,
            }
            for p in positions
        ]
    }


@app.get("/api/performance")
async def api_performance():
    metrics = get_performance_metrics()
    equity = get_equity_history(500)
    return {
        "metrics": {
            "total_trades": metrics.total_trades,
            "wins": metrics.wins,
            "losses": metrics.losses,
            "win_rate": round(metrics.win_rate, 2),
            "gross_profit": round(metrics.gross_profit, 2),
            "gross_loss": round(metrics.gross_loss, 2),
            "total_pnl": round(metrics.total_pnl, 2),
            "profit_factor": round(metrics.profit_factor, 2),
            "max_drawdown": round(metrics.max_drawdown, 2),
            "sharpe_ratio": round(metrics.sharpe_ratio, 2),
            "avg_win": round(metrics.avg_win, 2),
            "avg_loss": round(metrics.avg_loss, 2),
            "best_trade": round(metrics.best_trade, 2),
            "worst_trade": round(metrics.worst_trade, 2),
        },
        "equity": [
            {"timestamp": e["timestamp"], "equity": e["equity"]}
            for e in equity
        ]
    }


@app.get("/api/strategy/{strategy_name}")
async def api_get_strategy(strategy_name: str):
    settings = get_risk_settings(strategy_name)
    return {"settings": settings}


@app.post("/api/strategy/{strategy_name}")
async def api_update_strategy(strategy_name: str, data: dict):
    update_risk_settings(strategy_name, data)
    add_log("INFO", f"Risk settings updated for {strategy_name}")
    return {"status": "ok"}


@app.get("/api/logs")
async def api_logs(limit: int = 100):
    logs = get_recent_logs(limit)
    for l in logs:
        l["time_str"] = datetime.fromtimestamp(l["timestamp"] / 1000).strftime("%H:%M:%S")
    return {"logs": logs}


@app.get("/api/portfolio")
async def api_portfolio():
    try:
        from client.rest import TokocryptoClient
        client = TokocryptoClient()
        balances, _ = client.get_account_info()
        prices = client.get_ticker()
    except Exception as e:
        logger.warning(f"Portfolio fetch failed: {e}")
        return {"portfolio": [], "total_idr": 0}

    btc_idr = prices.get("BTCIDR", 0)
    usdt_idr = prices.get("USDTIDR", 0)
    portfolio = []
    total_idr = 0.0

    for bal in balances:
        total_qty = bal.free + bal.locked
        if total_qty <= 0:
            continue

        asset = bal.asset
        price_idr = 0.0

        if asset == "IDR":
            price_idr = 1.0
        else:
            direct = f"{asset}IDR"
            if direct in prices:
                price_idr = prices[direct]
            else:
                via_btc = f"{asset}BTC"
                if via_btc in prices and btc_idr:
                    price_idr = prices[via_btc] * btc_idr
                else:
                    via_usdt = f"{asset}USDT"
                    if via_usdt in prices and usdt_idr:
                        price_idr = prices[via_usdt] * usdt_idr

        value_idr = total_qty * price_idr
        total_idr += value_idr

        portfolio.append({
            "asset": asset,
            "free": round(bal.free, 8),
            "locked": round(bal.locked, 8),
            "total": round(total_qty, 8),
            "price_idr": round(price_idr, 2),
            "value_idr": round(value_idr, 2),
        })

    portfolio.sort(key=lambda x: x["value_idr"], reverse=True)

    for item in portfolio:
        item["pct"] = round(item["value_idr"] / total_idr * 100, 2) if total_idr > 0 else 0

    equity = get_equity_history(500)
    return {
        "portfolio": portfolio,
        "total_idr": round(total_idr, 2),
        "btc_idr": round(btc_idr, 2) if btc_idr else 0,
        "usdt_idr": round(usdt_idr, 2) if usdt_idr else 0,
        "equity": [{"timestamp": e["timestamp"], "equity": e["equity"]} for e in equity],
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.add(websocket)
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        connected_websockets.discard(websocket)
    except Exception:
        connected_websockets.discard(websocket)


async def broadcast(data: dict):
    dead = set()
    for ws in connected_websockets:
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    connected_websockets.difference_update(dead)


def broadcast_sync(data: dict):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(broadcast(data))
        loop.close()
    except Exception:
        pass


def start_dashboard():
    uvicorn.run(app, host=bot_config.DASHBOARD_HOST, port=bot_config.DASHBOARD_PORT, log_level="warning")
