import sqlite3
import os
from datetime import datetime
from typing import Optional, List
from models import Order, Trade, Position, PerformanceMetrics


DB_PATH = os.path.join(os.path.dirname(__file__), "trading_bot.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT UNIQUE,
            symbol TEXT NOT NULL,
            side INTEGER NOT NULL,
            type INTEGER NOT NULL,
            price REAL,
            orig_qty REAL,
            executed_qty REAL DEFAULT 0,
            status INTEGER,
            client_id TEXT,
            stop_price REAL DEFAULT 0,
            strategy TEXT DEFAULT '',
            create_time INTEGER,
            update_time INTEGER DEFAULT 0,
            cum_quote_qty REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT UNIQUE,
            order_id TEXT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            price REAL,
            qty REAL,
            quote_qty REAL,
            commission REAL DEFAULT 0,
            commission_asset TEXT DEFAULT '',
            pnl REAL DEFAULT 0,
            strategy TEXT DEFAULT '',
            trade_time INTEGER
        );

        CREATE TABLE IF NOT EXISTS equity_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            balance REAL NOT NULL,
            equity REAL NOT NULL,
            pnl_daily REAL DEFAULT 0,
            symbol TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS risk_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy TEXT UNIQUE NOT NULL,
            risk_per_trade REAL DEFAULT 1.0,
            reward_ratio_num INTEGER DEFAULT 1,
            reward_ratio_den INTEGER DEFAULT 2,
            sl_type TEXT DEFAULT 'fixed',
            sl_value REAL DEFAULT 1.0,
            tp_value REAL DEFAULT 2.0,
            max_daily_loss REAL DEFAULT 5.0,
            max_open_positions INTEGER DEFAULT 3,
            enabled INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS bot_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            level TEXT NOT NULL,
            message TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS active_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL,
            quantity REAL,
            stop_loss REAL,
            take_profit REAL,
            open_time INTEGER,
            strategy TEXT DEFAULT '',
            order_id TEXT DEFAULT ''
        );
    """)

    try:
        cur.execute("ALTER TABLE orders ADD COLUMN cum_quote_qty REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


def init_risk_settings():
    conn = get_conn()
    cur = conn.cursor()
    for strategy in ["ma_cross", "rsi", "grid"]:
        cur.execute(
            "INSERT OR IGNORE INTO risk_settings (strategy, risk_per_trade, reward_ratio_num, reward_ratio_den, sl_type, sl_value, tp_value, max_daily_loss, max_open_positions) "
            "VALUES (?, 1.0, 1, 2, 'fixed', 1.0, 2.0, 5.0, 3)",
            (strategy,)
        )
    conn.commit()
    conn.close()


def save_order(order: Order):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO orders (order_id, symbol, side, type, price, orig_qty, executed_qty, status, client_id, stop_price, strategy, create_time, update_time, cum_quote_qty) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (order.order_id, order.symbol, order.side, order.type, order.price,
         order.orig_qty, order.executed_qty, order.status, order.client_id,
         order.stop_price, "", order.create_time, int(datetime.now().timestamp() * 1000),
         order.cum_quote_qty)
    )
    conn.commit()
    conn.close()


def save_trade(trade: Trade, pnl: float = 0, strategy: str = ""):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO trades (trade_id, order_id, symbol, side, price, qty, quote_qty, commission, commission_asset, pnl, strategy, trade_time) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (trade.trade_id, trade.order_id, trade.symbol, trade.side_str,
         trade.price, trade.qty, trade.quote_qty, trade.commission,
         trade.commission_asset, pnl, strategy, trade.time)
    )
    conn.commit()
    conn.close()


def save_equity_snapshot(timestamp: int, balance: float, equity: float, pnl_daily: float, symbol: str = ""):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO equity_snapshot (timestamp, balance, equity, pnl_daily, symbol) VALUES (?, ?, ?, ?, ?)",
        (timestamp, balance, equity, pnl_daily, symbol)
    )
    conn.commit()
    conn.close()


def add_log(level: str, message: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO bot_logs (timestamp, level, message) VALUES (?, ?, ?)",
        (int(datetime.now().timestamp() * 1000), level, message)
    )
    conn.commit()
    conn.close()


def save_position(pos: Position):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO active_positions (symbol, side, entry_price, quantity, stop_loss, take_profit, open_time, strategy, order_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (pos.symbol, pos.side, pos.entry_price, pos.quantity, pos.stop_loss,
         pos.take_profit, pos.open_time, pos.strategy, pos.order_id)
    )
    conn.commit()
    conn.close()


def remove_position(symbol: str, side: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM active_positions WHERE symbol = ? AND side = ?", (symbol, side))
    conn.commit()
    conn.close()


def get_active_positions() -> List[Position]:
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute("SELECT * FROM active_positions").fetchall()
    conn.close()
    return [
        Position(
            symbol=r["symbol"], side=r["side"], entry_price=r["entry_price"],
            quantity=r["quantity"], stop_loss=r["stop_loss"],
            take_profit=r["take_profit"], open_time=r["open_time"],
            strategy=r["strategy"], order_id=r["order_id"],
            current_price=r["entry_price"]
        )
        for r in rows
    ]


def get_risk_settings(strategy: str) -> Optional[dict]:
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute("SELECT * FROM risk_settings WHERE strategy = ?", (strategy,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_risk_settings(strategy: str, settings: dict):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE risk_settings SET risk_per_trade=?, reward_ratio_num=?, reward_ratio_den=?, sl_type=?, sl_value=?, tp_value=?, max_daily_loss=?, max_open_positions=?, enabled=? WHERE strategy=?",
        (settings["risk_per_trade"], settings["reward_ratio_num"], settings["reward_ratio_den"],
         settings["sl_type"], settings["sl_value"], settings["tp_value"],
         settings["max_daily_loss"], settings["max_open_positions"],
         1 if settings.get("enabled", True) else 0, strategy)
    )
    conn.commit()
    conn.close()


def get_performance_metrics() -> PerformanceMetrics:
    conn = get_conn()
    cur = conn.cursor()

    total = cur.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    wins = cur.execute("SELECT COUNT(*) FROM trades WHERE pnl > 0").fetchone()[0]
    losses = cur.execute("SELECT COUNT(*) FROM trades WHERE pnl < 0").fetchone()[0]
    gross_profit = cur.execute("SELECT COALESCE(SUM(pnl),0) FROM trades WHERE pnl > 0").fetchone()[0]
    gross_loss = cur.execute("SELECT COALESCE(SUM(pnl),0) FROM trades WHERE pnl < 0").fetchone()[0]
    total_pnl = cur.execute("SELECT COALESCE(SUM(pnl),0) FROM trades").fetchone()[0]
    best = cur.execute("SELECT COALESCE(MAX(pnl),0) FROM trades").fetchone()[0]
    worst = cur.execute("SELECT COALESCE(MIN(pnl),0) FROM trades").fetchone()[0]

    conn.close()

    metrics = PerformanceMetrics(
        total_trades=total,
        wins=wins,
        losses=losses,
        gross_profit=gross_profit,
        gross_loss=abs(gross_loss),
        total_pnl=total_pnl,
        best_trade=best,
        worst_trade=worst,
    )

    if total > 0:
        metrics.win_rate = (wins / total) * 100
    if wins > 0:
        metrics.avg_win = gross_profit / wins
    if losses > 0:
        metrics.avg_loss = abs(gross_loss) / losses
    if gross_loss < 0:
        metrics.profit_factor = gross_profit / abs(gross_loss)
    else:
        metrics.profit_factor = gross_profit if gross_profit > 0 else 0

    equity_returns = []
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute("SELECT equity FROM equity_snapshot ORDER BY timestamp").fetchall()
    if len(rows) > 1:
        for i in range(1, len(rows)):
            prev = rows[i - 1]["equity"]
            if prev > 0:
                equity_returns.append((rows[i]["equity"] - prev) / prev)
    conn.close()

    if equity_returns:
        import numpy as np
        mean_r = np.mean(equity_returns)
        std_r = np.std(equity_returns)
        if std_r > 0:
            metrics.sharpe_ratio = (mean_r / std_r) * (252 ** 0.5)

        peak = 0
        dd_max = 0
        conn = get_conn()
        cur = conn.cursor()
        rows = cur.execute("SELECT equity FROM equity_snapshot ORDER BY timestamp").fetchall()
        for r in rows:
            eq = r["equity"]
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100 if peak > 0 else 0
            if dd > dd_max:
                dd_max = dd
        conn.close()
        metrics.max_drawdown = dd_max

    return metrics


def get_recent_logs(limit: int = 100) -> List[dict]:
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT timestamp, level, message FROM bot_logs ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_trade_history(limit: int = 100, symbol: str = "", strategy: str = "", side: str = "") -> List[dict]:
    conn = get_conn()
    cur = conn.cursor()
    query = "SELECT * FROM trades WHERE 1=1"
    params = []
    if symbol:
        query += " AND symbol = ?"
        params.append(symbol)
    if strategy:
        query += " AND strategy = ?"
        params.append(strategy)
    if side:
        query += " AND side = ?"
        params.append(side)
    query += " ORDER BY trade_time DESC LIMIT ?"
    params.append(limit)
    rows = cur.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def sync_trades_db():
    conn = get_conn()
    cur = conn.cursor()
    from client.rest import TokocryptoClient
    from config import config
    client = TokocryptoClient()
    symbols = config.BOT_SYMBOLS
    all_trades = []
    for sym in symbols:
        try:
            all_trades.extend(client.get_trade_history(sym, limit=500))
        except Exception as e:
            logger.warning(f"sync_trades_db {sym}: {e}")
    cur.execute("DELETE FROM trades")
    for t in all_trades:
        cur.execute(
            "INSERT INTO trades (trade_id, order_id, symbol, side, price, qty, quote_qty, commission, commission_asset, pnl, strategy, trade_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (t.trade_id, t.order_id, t.symbol, t.side_str,
             t.price, t.qty, t.quote_qty, t.commission,
             t.commission_asset, 0, "exchange", int(t.time))
        )
    conn.commit()
    conn.close()
    logger.info(f"sync_trades_db: {len(all_trades)} trades synced from exchange")


def get_equity_history(limit: int = 500) -> List[dict]:
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT timestamp, balance, equity, pnl_daily FROM equity_snapshot ORDER BY timestamp DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return list(reversed([dict(r) for r in rows]))
