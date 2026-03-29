"""
QuantumTrade AI — PostgreSQL Storage Layer v8.2.0
Persistent storage for trades, signals, Q-score history, and performance stats.
Uses asyncpg for async PostgreSQL access.
Falls back gracefully to in-memory if DATABASE_URL is not set.
"""

import os
import json
import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict

# Will be set after init
_pool = None
_ready = False

DATABASE_URL = os.getenv("DATABASE_URL", "")


async def init_db():
    """Initialize connection pool and create tables if needed."""
    global _pool, _ready
    if not DATABASE_URL:
        print("[db] DATABASE_URL not set → in-memory fallback")
        return False
    try:
        import asyncpg
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=15,
        )
        await _create_tables()
        _ready = True
        print("[db] PostgreSQL connected ✅")
        return True
    except Exception as e:
        print(f"[db] PostgreSQL connection failed: {e}")
        return False


async def _create_tables():
    """Create tables if they don't exist."""
    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id SERIAL PRIMARY KEY,
                ts TIMESTAMPTZ DEFAULT NOW(),
                open_ts DOUBLE PRECISION,
                close_ts DOUBLE PRECISION,
                symbol VARCHAR(32) NOT NULL,
                side VARCHAR(8) NOT NULL,
                price DOUBLE PRECISION,
                close_price DOUBLE PRECISION,
                size DOUBLE PRECISION,
                tp DOUBLE PRECISION,
                sl DOUBLE PRECISION,
                confidence DOUBLE PRECISION,
                q_score DOUBLE PRECISION,
                pattern VARCHAR(64),
                account VARCHAR(16) DEFAULT 'spot',
                strategy VARCHAR(8),
                status VARCHAR(16) DEFAULT 'open',
                pnl_usdt DOUBLE PRECISION,
                pnl_pct DOUBLE PRECISION,
                close_reason VARCHAR(32),
                duration_sec DOUBLE PRECISION,
                extra JSONB DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS signals (
                id SERIAL PRIMARY KEY,
                ts TIMESTAMPTZ DEFAULT NOW(),
                symbol VARCHAR(32) NOT NULL,
                side VARCHAR(8),
                q_score DOUBLE PRECISION,
                confidence DOUBLE PRECISION,
                pattern VARCHAR(64),
                fg_bonus DOUBLE PRECISION,
                poly_bonus DOUBLE PRECISION,
                whale_bonus DOUBLE PRECISION,
                vision_bonus DOUBLE PRECISION,
                quantum_bias DOUBLE PRECISION,
                executed BOOLEAN DEFAULT FALSE,
                extra JSONB DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS q_score_history (
                id SERIAL PRIMARY KEY,
                ts TIMESTAMPTZ DEFAULT NOW(),
                symbol VARCHAR(32) NOT NULL,
                q_score DOUBLE PRECISION,
                components JSONB DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS perf_stats (
                id SERIAL PRIMARY KEY,
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                stats JSONB NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
            CREATE INDEX IF NOT EXISTS idx_trades_ts ON trades(ts);
            CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
            CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(ts);
            CREATE INDEX IF NOT EXISTS idx_qscore_ts ON q_score_history(ts);
        """)
        print("[db] tables ready ✅")


def is_ready() -> bool:
    return _ready and _pool is not None


# ── Trade Operations ─────────────────────────────────────────────────────────

async def insert_trade(trade: dict) -> Optional[int]:
    """Insert a new trade, return its DB id."""
    if not is_ready():
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO trades (
                    ts, open_ts, symbol, side, price, size, tp, sl,
                    confidence, q_score, pattern, account, strategy, status
                ) VALUES (
                    NOW(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 'open'
                ) RETURNING id
            """,
                trade.get("open_ts", 0.0),
                trade["symbol"], trade["side"], trade["price"], trade["size"],
                trade["tp"], trade["sl"], trade["confidence"], trade["q_score"],
                trade.get("pattern", "?"), trade.get("account", "spot"),
                trade.get("strategy", "B"),
            )
            return row["id"] if row else None
    except Exception as e:
        print(f"[db] insert_trade error: {e}")
        return None


async def close_trade(symbol: str, pnl_usdt: float, pnl_pct: float,
                      close_price: float, close_reason: str = "monitor",
                      strategy: str = "B", duration_sec: float = 0.0):
    """Close the most recent open trade for symbol."""
    if not is_ready():
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute("""
                UPDATE trades SET
                    status = 'closed',
                    close_ts = EXTRACT(EPOCH FROM NOW()),
                    close_price = $1,
                    pnl_usdt = $2,
                    pnl_pct = $3,
                    close_reason = $4,
                    strategy = $5,
                    duration_sec = $6
                WHERE id = (
                    SELECT id FROM trades
                    WHERE symbol = $7 AND status = 'open'
                    ORDER BY ts DESC LIMIT 1
                )
            """, close_price, pnl_usdt, pnl_pct, close_reason, strategy,
                duration_sec, symbol)
    except Exception as e:
        print(f"[db] close_trade error: {e}")


async def get_trades(limit: int = 50, status: str = None) -> List[dict]:
    """Get recent trades, optionally filtered by status."""
    if not is_ready():
        return []
    try:
        async with _pool.acquire() as conn:
            if status:
                rows = await conn.fetch(
                    "SELECT * FROM trades WHERE status = $1 ORDER BY ts DESC LIMIT $2",
                    status, limit)
            else:
                rows = await conn.fetch(
                    "SELECT * FROM trades ORDER BY ts DESC LIMIT $1", limit)
            return [dict(r) for r in rows]
    except Exception as e:
        print(f"[db] get_trades error: {e}")
        return []


async def get_trade_count() -> int:
    """Total trade count."""
    if not is_ready():
        return 0
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow("SELECT COUNT(*) as cnt FROM trades")
            return row["cnt"] if row else 0
    except Exception as e:
        return 0


# ── Signal Operations ────────────────────────────────────────────────────────

async def insert_signal(signal: dict):
    """Log a trading signal for analytics."""
    if not is_ready():
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO signals (
                    symbol, side, q_score, confidence, pattern,
                    fg_bonus, poly_bonus, whale_bonus, vision_bonus,
                    quantum_bias, executed
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            """,
                signal.get("symbol"), signal.get("side"),
                signal.get("q_score", 0), signal.get("confidence", 0),
                signal.get("pattern", "?"),
                signal.get("fg_bonus", 0), signal.get("poly_bonus", 0),
                signal.get("whale_bonus", 0), signal.get("vision_bonus", 0),
                signal.get("quantum_bias", 0), signal.get("executed", False),
            )
    except Exception as e:
        print(f"[db] insert_signal error: {e}")


# ── Q-Score History ──────────────────────────────────────────────────────────

async def insert_q_score(symbol: str, q_score: float, components: dict):
    """Log Q-Score for historical analysis."""
    if not is_ready():
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO q_score_history (symbol, q_score, components)
                VALUES ($1, $2, $3)
            """, symbol, q_score, json.dumps(components))
    except Exception as e:
        print(f"[db] insert_q_score error: {e}")


# ── Performance Stats ────────────────────────────────────────────────────────

async def save_perf_stats(stats: dict):
    """Upsert aggregated performance stats."""
    if not is_ready():
        return
    try:
        async with _pool.acquire() as conn:
            # Keep only latest row, update it
            await conn.execute("""
                INSERT INTO perf_stats (id, updated_at, stats)
                VALUES (1, NOW(), $1)
                ON CONFLICT (id)
                DO UPDATE SET updated_at = NOW(), stats = $1
            """, json.dumps(stats))
    except Exception as e:
        print(f"[db] save_perf_stats error: {e}")


async def load_perf_stats() -> Optional[dict]:
    """Load aggregated performance stats."""
    if not is_ready():
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow("SELECT stats FROM perf_stats WHERE id = 1")
            if row:
                return json.loads(row["stats"]) if isinstance(row["stats"], str) else row["stats"]
    except Exception as e:
        print(f"[db] load_perf_stats error: {e}")
    return None


# ── Analytics Queries ────────────────────────────────────────────────────────

async def get_analytics() -> dict:
    """Rich analytics from trade history for AI self-learning."""
    if not is_ready():
        return {}
    try:
        async with _pool.acquire() as conn:
            # Win rate by strategy
            by_strategy = await conn.fetch("""
                SELECT strategy,
                       COUNT(*) as total,
                       SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END) as wins,
                       ROUND(SUM(pnl_usdt)::numeric, 4) as total_pnl,
                       ROUND(AVG(pnl_usdt)::numeric, 4) as avg_pnl
                FROM trades WHERE status = 'closed'
                GROUP BY strategy
            """)

            # Win rate by symbol
            by_symbol = await conn.fetch("""
                SELECT symbol,
                       COUNT(*) as total,
                       SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END) as wins,
                       ROUND(SUM(pnl_usdt)::numeric, 4) as total_pnl
                FROM trades WHERE status = 'closed'
                GROUP BY symbol
            """)

            # Win rate by hour (UTC)
            by_hour = await conn.fetch("""
                SELECT EXTRACT(HOUR FROM ts)::int as hour,
                       COUNT(*) as total,
                       SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END) as wins,
                       ROUND(SUM(pnl_usdt)::numeric, 4) as total_pnl
                FROM trades WHERE status = 'closed'
                GROUP BY hour ORDER BY hour
            """)

            # Average Q-Score for wins vs losses
            q_scores = await conn.fetchrow("""
                SELECT
                    ROUND(AVG(CASE WHEN pnl_usdt > 0 THEN q_score END)::numeric, 1) as avg_q_win,
                    ROUND(AVG(CASE WHEN pnl_usdt <= 0 THEN q_score END)::numeric, 1) as avg_q_loss
                FROM trades WHERE status = 'closed'
            """)

            # Daily PnL (last 30 days)
            daily_pnl = await conn.fetch("""
                SELECT DATE(ts) as day,
                       COUNT(*) as trades,
                       ROUND(SUM(pnl_usdt)::numeric, 4) as pnl
                FROM trades WHERE status = 'closed'
                GROUP BY day ORDER BY day DESC LIMIT 30
            """)

            return {
                "by_strategy": [dict(r) for r in by_strategy],
                "by_symbol": [dict(r) for r in by_symbol],
                "by_hour": [dict(r) for r in by_hour],
                "avg_q_win": float(q_scores["avg_q_win"] or 0) if q_scores else 0,
                "avg_q_loss": float(q_scores["avg_q_loss"] or 0) if q_scores else 0,
                "daily_pnl": [{"day": str(r["day"]), "trades": r["trades"], "pnl": float(r["pnl"] or 0)} for r in daily_pnl],
            }
    except Exception as e:
        print(f"[db] get_analytics error: {e}")
        return {}


# ── Migrate from JSON ────────────────────────────────────────────────────────

async def migrate_from_json(trade_log: list, perf_stats: dict):
    """One-time migration: import existing JSON trade_log into PostgreSQL."""
    if not is_ready() or not trade_log:
        return 0
    count = 0
    try:
        async with _pool.acquire() as conn:
            for t in trade_log:
                await conn.execute("""
                    INSERT INTO trades (
                        ts, open_ts, close_ts, symbol, side, price, close_price,
                        size, tp, sl, confidence, q_score, pattern, account,
                        strategy, status, pnl_usdt, pnl_pct, close_reason, duration_sec
                    ) VALUES (
                        $1::timestamptz, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                        $11, $12, $13, $14, $15, $16, $17, $18, $19, $20
                    )
                """,
                    t.get("ts", datetime.now(timezone.utc).isoformat()),
                    t.get("open_ts", 0.0),
                    t.get("close_ts"),
                    t["symbol"], t["side"], t.get("price", 0), t.get("close_price"),
                    t.get("size", 0), t.get("tp", 0), t.get("sl", 0),
                    t.get("confidence", 0), t.get("q_score", 0),
                    t.get("pattern", "?"), t.get("account", "spot"),
                    t.get("strategy", "B"), t.get("status", "open"),
                    t.get("pnl_usdt") or t.get("pnl"),
                    t.get("pnl_pct"),
                    t.get("close_reason"),
                    t.get("duration_sec"),
                )
                count += 1
        if perf_stats:
            await save_perf_stats(perf_stats)
        print(f"[db] migrated {count} trades from JSON → PostgreSQL")
    except Exception as e:
        print(f"[db] migration error: {e}")
    return count
