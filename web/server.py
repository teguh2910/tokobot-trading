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

from fastapi.responses import RedirectResponse
@app.get("/favicon.ico")
async def favicon():
    return RedirectResponse(url="/static/favicon.svg")

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


@app.get("/trending", response_class=HTMLResponse)
async def trending_page(request: Request):
    return templates.TemplateResponse(request, "trending.html")


# ── API Routes ──

@app.get("/api/dashboard")
async def api_dashboard():
    metrics = get_performance_metrics()
    positions = get_active_positions()
    try:
        from client.rest import TokocryptoClient
        client = TokocryptoClient()
        balances, can_trade = client.get_account_info()
        balance_data = [{"asset": b.asset, "free": b.free, "locked": b.locked, "total": b.total} for b in balances]
        prices = client.get_ticker()
    except Exception as e:
        balance_data = []
        prices = {}
        logger.warning(f"Dashboard balance fetch failed: {e}")

    unrealized_pnl = 0.0
    pos_list = []
    for p in positions:
        sym = p.symbol.replace("_", "")
        current_price = prices.get(sym, 0) or p.current_price
        p.current_price = current_price
        pos_pnl = p.pnl
        pos_pnl_pct = p.pnl_pct
        unrealized_pnl += pos_pnl
        pos_list.append({
            "symbol": p.symbol, "side": p.side,
            "entry_price": p.entry_price, "quantity": p.quantity,
            "current_price": current_price,
            "pnl": round(pos_pnl, 2), "pnl_pct": round(pos_pnl_pct, 2),
            "stop_loss": p.stop_loss, "take_profit": p.take_profit,
        })

    total_pnl = round(metrics.total_pnl + unrealized_pnl, 2)
    profit_factor = metrics.profit_factor_str
    if metrics.total_trades == 0 and unrealized_pnl != 0:
        profit_factor = "—"

    return {
        "metrics": {
            "total_trades": metrics.total_trades,
            "win_rate": f"{metrics.win_rate:.1f}",
            "total_pnl": total_pnl,
            "profit_factor": profit_factor,
            "max_drawdown": round(metrics.max_drawdown, 2),
            "sharpe_ratio": round(metrics.sharpe_ratio, 2),
        },
        "balances": balance_data,
        "positions": pos_list,
        "active_orders_count": len(positions),
        "bot_mode": bot_config.BOT_MODE,
        "bot_strategies": bot_config.BOT_STRATEGIES,
        "symbols": bot_config.BOT_SYMBOLS,
    }


@app.get("/api/trades")
async def api_trades(symbol: str = "", strategy: str = "", side: str = "", limit: int = 100, sync: int = 0):
    if sync:
        try:
            from client.rest import TokocryptoClient
            client = TokocryptoClient()

            symbols = symbol.split(",") if symbol else cfg.get("BOT_SYMBOLS", ["BTC_IDR"])
            result = []
            for sym in symbols:
                sym = sym.strip()
                if not sym:
                    continue
                try:
                    api_trades = client.get_trade_history(sym, limit=500)
                    for t in api_trades:
                        result.append({
                            "trade_id": t.trade_id,
                            "order_id": t.order_id,
                            "symbol": t.symbol,
                            "side": t.side_str,
                            "price": t.price,
                            "qty": t.qty,
                            "quote_qty": t.quote_qty,
                            "commission": t.commission,
                            "commission_asset": t.commission_asset,
                            "trade_time": int(t.time),
                            "trade_time_str": datetime.fromtimestamp(int(t.time) / 1000).strftime("%Y-%m-%d %H:%M:%S"),
                        })
                except Exception as e:
                    logger.warning(f"Sync trades {sym}: {e}")
            result.sort(key=lambda x: x["trade_time"], reverse=True)
            return {"trades": result[:limit]}
        except Exception as e:
            logger.warning(f"Sync failed: {e}")

    trades = get_trade_history(limit=limit, symbol=symbol, strategy=strategy, side=side)
    for t in trades:
        t["trade_time_str"] = datetime.fromtimestamp(t["trade_time"] / 1000).strftime("%Y-%m-%d %H:%M:%S")
    return {"trades": trades}


@app.get("/api/orders/active")
async def api_active_orders():
    positions = get_active_positions()
    try:
        from client.rest import TokocryptoClient
        prices = TokocryptoClient().get_ticker()
    except Exception:
        prices = {}
    result = []
    for p in positions:
        sym = p.symbol.replace("_", "")
        cp = prices.get(sym, 0) or p.entry_price
        p.current_price = cp
        result.append({
            "symbol": p.symbol, "side": p.side,
            "price": p.entry_price, "qty": p.quantity,
            "current_price": cp,
            "stop_loss": p.stop_loss, "take_profit": p.take_profit,
            "pnl": round(p.pnl, 2), "open_time": p.open_time,
            "strategy": p.strategy,
        })
    return {"orders": result}


@app.get("/api/performance")
async def api_performance():
    metrics = get_performance_metrics()
    equity = get_equity_history(500)
    positions = get_active_positions()
    try:
        from client.rest import TokocryptoClient
        prices = TokocryptoClient().get_ticker()
    except Exception:
        prices = {}
    unrealized = 0.0
    for p in positions:
        cp = prices.get(p.symbol.replace("_", ""), 0)
        if cp:
            p.current_price = cp
        unrealized += p.pnl
    total_pnl = round(metrics.total_pnl + unrealized, 2)
    return {
        "metrics": {
            "total_trades": metrics.total_trades,
            "wins": metrics.wins,
            "losses": metrics.losses,
            "win_rate": round(metrics.win_rate, 2),
            "gross_profit": round(metrics.gross_profit, 2),
            "gross_loss": round(metrics.gross_loss, 2),
            "total_pnl": total_pnl,
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


@app.get("/api/trending")
async def api_trending():
    try:
        from client.rest import TokocryptoClient
        client = TokocryptoClient()
        tickers = client.get_ticker_24hr()
    except Exception as e:
        logger.warning(f"Trending fetch failed: {e}")
        return {"trending": []}

    coins = []
    for t in tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("IDR"):
            continue
        price = float(t.get("lastPrice", 0))
        change_pct = float(t.get("priceChangePercent", 0))
        high = float(t.get("highPrice", 0))
        low = float(t.get("lowPrice", 0))
        volume = float(t.get("volume", 0))
        quote_vol = float(t.get("quoteVolume", 0))
        if price <= 0:
            continue
        coins.append({
            "symbol": sym,
            "price": round(price, 2),
            "change_pct": round(change_pct, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "volume": round(volume, 2),
            "quote_volume": round(quote_vol, 2),
        })

    coins.sort(key=lambda x: x["change_pct"], reverse=True)
    return {"trending": coins}


@app.get("/api/screen")
async def api_screen(limit: int = 10, sort: str = "gainers"):
    try:
        from client.rest import TokocryptoClient
        client = TokocryptoClient()
        tickers = client.get_ticker_24hr()
    except Exception as e:
        logger.warning(f"Screen fetch failed: {e}")
        return {"screen": []}

    coins = []
    for t in tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("IDR"):
            continue
        price = float(t.get("lastPrice", 0))
        change_pct = float(t.get("priceChangePercent", 0))
        volume = float(t.get("volume", 0))
        if price <= 0:
            continue
        toko_sym = sym[:-3] + "_" + sym[-3:]
        coins.append({"symbol": sym, "toko_symbol": toko_sym, "price": price, "change_pct": change_pct, "volume": volume})

    coins.sort(key=lambda x: x["change_pct"], reverse=(sort == "gainers"))
    coins = coins[:limit]

    import numpy as np

    def compute_rsi(closes, period=14):
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

    results = []
    interval = "1m"
    for c in coins:
        try:
            klines = client.get_klines(c["toko_symbol"], interval=interval, limit=100)
            if len(klines) < 14:
                continue
            closes = [k.close for k in klines]
            rsi = round(compute_rsi(closes, period=7), 1)
            current_price = closes[-1]
            recent_vol = float(np.mean([k.volume for k in klines[-3:]]))
            avg_vol = float(np.mean([k.volume for k in klines]))
            vol_surge = round(recent_vol / avg_vol, 1) if avg_vol > 0 else 0
            price_chg_1m = round((current_price / closes[-2] - 1) * 100, 2) if len(closes) >= 2 else 0
            signals = []
            if rsi < 30:
                signals.append("Oversold")
            elif rsi > 70:
                signals.append("Overbought")
            if vol_surge > 1.5:
                signals.append("Vol spike")
            if abs(price_chg_1m) > 0.5:
                signals.append("Move " + ("▲" if price_chg_1m > 0 else "▼"))
            results.append({
                "symbol": c["symbol"],
                "price": round(current_price, 2),
                "change_pct": round(c["change_pct"], 2),
                "rsi": rsi,
                "vol_surge": vol_surge,
                "price_chg_1m": price_chg_1m,
                "interval": interval,
                "signals": signals,
            })
        except Exception as e:
            logger.warning(f"Screen {c['symbol']} failed: {e}")
            continue

    return {"screen": results}


SELECTED_SYMBOLS_FILE = Path("/tmp/tokobot_selected_symbols.json")

@app.get("/api/screen/selected")
async def get_selected_symbols():
    if SELECTED_SYMBOLS_FILE.exists():
        data = json.loads(SELECTED_SYMBOLS_FILE.read_text())
        return {"symbols": data.get("symbols", [])}
    return {"symbols": []}

@app.post("/api/screen/selected")
async def set_selected_symbols(data: dict):
    symbols = data.get("symbols", [])
    SELECTED_SYMBOLS_FILE.write_text(json.dumps({"symbols": symbols}))
    return {"ok": True, "symbols": symbols}


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
