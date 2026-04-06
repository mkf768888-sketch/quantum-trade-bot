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

            -- v9.2: Fear & Greed history tracking
            CREATE TABLE IF NOT EXISTS fg_history (
                id SERIAL PRIMARY KEY,
                ts TIMESTAMPTZ DEFAULT NOW(),
                value INT NOT NULL,
                classification VARCHAR(32)
            );
            CREATE INDEX IF NOT EXISTS idx_fg_ts ON fg_history(ts);

            -- v9.2: MiroFish memory persistence
            CREATE TABLE IF NOT EXISTS mirofish_memory (
                id SERIAL PRIMARY KEY,
                ts TIMESTAMPTZ DEFAULT NOW(),
                symbol VARCHAR(32) NOT NULL,
                score INT,
                direction VARCHAR(8),
                fg_value INT,
                rsi DOUBLE PRECISION,
                buy_count INT,
                sell_count INT,
                hold_count INT,
                agents_json JSONB DEFAULT '[]'
            );
            CREATE INDEX IF NOT EXISTS idx_mf_mem_symbol ON mirofish_memory(symbol);
            CREATE INDEX IF NOT EXISTS idx_mf_mem_ts ON mirofish_memory(ts);

            -- v9.2: Macro context snapshots (DXY, S&P500, BTC dominance)
            CREATE TABLE IF NOT EXISTS macro_snapshots (
                id SERIAL PRIMARY KEY,
                ts TIMESTAMPTZ DEFAULT NOW(),
                btc_dominance DOUBLE PRECISION,
                total_mcap DOUBLE PRECISION,
                eth_btc_ratio DOUBLE PRECISION,
                top_gainers JSONB DEFAULT '[]',
                top_losers JSONB DEFAULT '[]',
                extra JSONB DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_macro_ts ON macro_snapshots(ts);

            -- v9.2: Whale & large player movements
            CREATE TABLE IF NOT EXISTS whale_events (
                id SERIAL PRIMARY KEY,
                ts TIMESTAMPTZ DEFAULT NOW(),
                event_type VARCHAR(32),
                symbol VARCHAR(32),
                amount_usd DOUBLE PRECISION,
                from_entity VARCHAR(64),
                to_entity VARCHAR(64),
                direction VARCHAR(16),
                source VARCHAR(32),
                extra JSONB DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_whale_ts ON whale_events(ts);

            -- v10.12.7: Funding Rate Arbitrage open positions (survives server restart)
            CREATE TABLE IF NOT EXISTS funding_arb_positions (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(32) UNIQUE NOT NULL,
                perp_qty DOUBLE PRECISION NOT NULL,
                spot_qty DOUBLE PRECISION NOT NULL DEFAULT 0,
                entry_price DOUBLE PRECISION,
                usdt_deployed DOUBLE PRECISION,
                opened_at DOUBLE PRECISION,
                funding_collected DOUBLE PRECISION DEFAULT 0,
                last_funding_ts DOUBLE PRECISION DEFAULT 0
            );
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


# ── v9.2: Fear & Greed History ──────────────────────────────────────────────

async def save_fg_value(value: int, classification: str = ""):
    """Store F&G value for historical tracking."""
    if not is_ready():
        return
    try:
        async with _pool.acquire() as conn:
            # Avoid duplicates within same hour
            existing = await conn.fetchval(
                "SELECT id FROM fg_history WHERE ts > NOW() - INTERVAL '50 minutes' ORDER BY ts DESC LIMIT 1"
            )
            if not existing:
                await conn.execute(
                    "INSERT INTO fg_history (value, classification) VALUES ($1, $2)",
                    value, classification
                )
    except Exception as e:
        print(f"[db] save_fg_value error: {e}")


async def get_fg_history(days: int = 30) -> list:
    """Get F&G history for last N days."""
    if not is_ready():
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT ts, value, classification FROM fg_history
                WHERE ts > NOW() - INTERVAL '%s days'
                ORDER BY ts DESC
            """ % days)
            return [{"ts": str(r["ts"]), "value": r["value"], "class": r["classification"]} for r in rows]
    except Exception as e:
        print(f"[db] get_fg_history error: {e}")
        return []


async def get_fg_trade_correlation() -> list:
    """Correlate F&G ranges with trade outcomes — the money query."""
    if not is_ready():
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    CASE
                        WHEN (extra->>'fg_value')::int < 20 THEN 'Extreme Fear (0-19)'
                        WHEN (extra->>'fg_value')::int < 40 THEN 'Fear (20-39)'
                        WHEN (extra->>'fg_value')::int < 60 THEN 'Neutral (40-59)'
                        WHEN (extra->>'fg_value')::int < 80 THEN 'Greed (60-79)'
                        ELSE 'Extreme Greed (80-100)'
                    END as fg_zone,
                    COUNT(*) as total,
                    SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END) as wins,
                    ROUND(SUM(pnl_usdt)::numeric, 2) as pnl,
                    ROUND(AVG(pnl_usdt)::numeric, 2) as avg_pnl
                FROM trades
                WHERE status = 'closed' AND extra->>'fg_value' IS NOT NULL
                GROUP BY fg_zone ORDER BY fg_zone
            """)
            return [dict(r) for r in rows]
    except Exception as e:
        print(f"[db] get_fg_trade_correlation error: {e}")
        return []


# ── v9.2: MiroFish Memory Persistence ──────────────────────────────────────

async def save_mirofish_memory(symbol: str, score: int, direction: str,
                                fg_value: int, rsi: float,
                                buy_count: int, sell_count: int, hold_count: int,
                                agents_json: str = "[]"):
    """Persist MiroFish analysis to DB for cross-restart memory."""
    if not is_ready():
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO mirofish_memory (symbol, score, direction, fg_value, rsi,
                                              buy_count, sell_count, hold_count, agents_json)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """, symbol, score, direction, fg_value, rsi, buy_count, sell_count, hold_count, agents_json)
    except Exception as e:
        print(f"[db] save_mirofish_memory error: {e}")


async def load_mirofish_memory(symbol: str, limit: int = 10) -> list:
    """Load last N MiroFish analyses for a symbol."""
    if not is_ready():
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT ts, score, direction, fg_value, rsi, buy_count, sell_count, hold_count
                FROM mirofish_memory WHERE symbol = $1
                ORDER BY ts DESC LIMIT $2
            """, symbol, limit)
            return [dict(r) for r in reversed(rows)]  # oldest first
    except Exception as e:
        print(f"[db] load_mirofish_memory error: {e}")
        return []


async def load_all_mirofish_memory() -> dict:
    """Load latest MiroFish memory for all symbols (for startup restore)."""
    if not is_ready():
        return {}
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT ON (symbol) symbol, score, direction, fg_value, rsi,
                       buy_count, sell_count, ts
                FROM mirofish_memory ORDER BY symbol, ts DESC
            """)
            result = {}
            for r in rows:
                sym = r["symbol"]
                # Load last 10 for this symbol
                mem_rows = await conn.fetch("""
                    SELECT score, direction, fg_value, rsi, buy_count, sell_count,
                           EXTRACT(EPOCH FROM ts) as ts_epoch
                    FROM mirofish_memory WHERE symbol = $1
                    ORDER BY ts DESC LIMIT 10
                """, sym)
                result[sym] = [
                    {"ts": r2["ts_epoch"], "score": r2["score"], "direction": r2["direction"],
                     "fg": r2["fg_value"], "rsi": r2["rsi"],
                     "buy": r2["buy_count"], "sell": r2["sell_count"]}
                    for r2 in reversed(mem_rows)
                ]
            return result
    except Exception as e:
        print(f"[db] load_all_mirofish_memory error: {e}")
        return {}


# ── v9.2: Macro Snapshots ──────────────────────────────────────────────────

async def save_macro_snapshot(btc_dom: float, total_mcap: float, eth_btc: float,
                               gainers: list = None, losers: list = None, extra: dict = None):
    """Save macro market snapshot."""
    if not is_ready():
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO macro_snapshots (btc_dominance, total_mcap, eth_btc_ratio,
                                              top_gainers, top_losers, extra)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, btc_dom, total_mcap, eth_btc,
                json.dumps(gainers or []), json.dumps(losers or []),
                json.dumps(extra or {}))
    except Exception as e:
        print(f"[db] save_macro_snapshot error: {e}")


async def get_latest_macro() -> Optional[dict]:
    """Get latest macro snapshot."""
    if not is_ready():
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM macro_snapshots ORDER BY ts DESC LIMIT 1"
            )
            if row:
                r = dict(row)
                r["ts"] = str(r["ts"])
                return r
    except Exception as e:
        print(f"[db] get_latest_macro error: {e}")
    return None


# ── v9.2: Whale Events ─────────────────────────────────────────────────────

async def save_whale_event(event_type: str, symbol: str, amount_usd: float,
                            from_entity: str = "", to_entity: str = "",
                            direction: str = "", source: str = ""):
    """Store whale movement event."""
    if not is_ready():
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO whale_events (event_type, symbol, amount_usd,
                                           from_entity, to_entity, direction, source)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, event_type, symbol, amount_usd, from_entity, to_entity, direction, source)
    except Exception as e:
        print(f"[db] save_whale_event error: {e}")


async def get_recent_whale_events(hours: int = 24, min_usd: float = 1_000_000) -> list:
    """Get whale events from last N hours above minimum USD threshold."""
    if not is_ready():
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT ts, event_type, symbol, amount_usd, from_entity, to_entity, direction, source
                FROM whale_events
                WHERE ts > NOW() - INTERVAL '%s hours' AND amount_usd >= $1
                ORDER BY ts DESC LIMIT 50
            """ % hours, min_usd)
            return [dict(r) for r in rows]
    except Exception as e:
        print(f"[db] get_recent_whale_events error: {e}")
        return []


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


# ── Deep Analytics for Trade Pattern Analysis ────────────────────────────────

async def get_deep_analytics() -> dict:
    """v9.1: Deep trade pattern analysis — pairs, hours, F&G correlation, durations, streaks."""
    if not is_ready():
        return {}
    try:
        async with _pool.acquire() as conn:
            # 1. Per-symbol detailed stats
            by_symbol = await conn.fetch("""
                SELECT symbol,
                       COUNT(*) as total,
                       SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END) as wins,
                       ROUND(SUM(pnl_usdt)::numeric, 2) as total_pnl,
                       ROUND(AVG(pnl_usdt)::numeric, 2) as avg_pnl,
                       ROUND(MAX(pnl_usdt)::numeric, 2) as best_trade,
                       ROUND(MIN(pnl_usdt)::numeric, 2) as worst_trade,
                       ROUND(AVG(duration_sec)::numeric, 0) as avg_duration_sec,
                       ROUND(AVG(q_score)::numeric, 1) as avg_q
                FROM trades WHERE status = 'closed'
                GROUP BY symbol ORDER BY total_pnl DESC
            """)

            # 2. Win rate by hour (UTC)
            by_hour = await conn.fetch("""
                SELECT EXTRACT(HOUR FROM ts)::int as hour,
                       COUNT(*) as total,
                       SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END) as wins,
                       ROUND(SUM(pnl_usdt)::numeric, 2) as pnl,
                       ROUND(AVG(pnl_usdt)::numeric, 2) as avg_pnl
                FROM trades WHERE status = 'closed'
                GROUP BY hour ORDER BY pnl DESC
            """)

            # 3. Win rate by strategy
            by_strategy = await conn.fetch("""
                SELECT strategy,
                       COUNT(*) as total,
                       SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END) as wins,
                       ROUND(SUM(pnl_usdt)::numeric, 2) as pnl,
                       ROUND(AVG(q_score)::numeric, 1) as avg_q
                FROM trades WHERE status = 'closed'
                GROUP BY strategy ORDER BY pnl DESC
            """)

            # 4. Win rate by pattern (vision)
            by_pattern = await conn.fetch("""
                SELECT pattern,
                       COUNT(*) as total,
                       SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END) as wins,
                       ROUND(SUM(pnl_usdt)::numeric, 2) as pnl,
                       ROUND(AVG(pnl_usdt)::numeric, 2) as avg_pnl
                FROM trades WHERE status = 'closed' AND pattern IS NOT NULL
                GROUP BY pattern ORDER BY total DESC
            """)

            # 5. Q-Score ranges analysis
            q_ranges = await conn.fetch("""
                SELECT
                    CASE
                        WHEN q_score < 78 THEN '70-77'
                        WHEN q_score < 82 THEN '78-81'
                        WHEN q_score < 86 THEN '82-85'
                        WHEN q_score < 90 THEN '86-89'
                        ELSE '90+'
                    END as q_range,
                    COUNT(*) as total,
                    SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END) as wins,
                    ROUND(SUM(pnl_usdt)::numeric, 2) as pnl,
                    ROUND(AVG(pnl_usdt)::numeric, 2) as avg_pnl
                FROM trades WHERE status = 'closed'
                GROUP BY q_range ORDER BY q_range
            """)

            # 6. Win rate by day of week
            by_weekday = await conn.fetch("""
                SELECT EXTRACT(DOW FROM ts)::int as dow,
                       COUNT(*) as total,
                       SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END) as wins,
                       ROUND(SUM(pnl_usdt)::numeric, 2) as pnl
                FROM trades WHERE status = 'closed'
                GROUP BY dow ORDER BY dow
            """)

            # 7. Close reason analysis
            by_reason = await conn.fetch("""
                SELECT close_reason,
                       COUNT(*) as total,
                       SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END) as wins,
                       ROUND(SUM(pnl_usdt)::numeric, 2) as pnl
                FROM trades WHERE status = 'closed' AND close_reason IS NOT NULL
                GROUP BY close_reason ORDER BY total DESC
            """)

            # 8. Duration buckets analysis
            by_duration = await conn.fetch("""
                SELECT
                    CASE
                        WHEN duration_sec < 300 THEN '<5min'
                        WHEN duration_sec < 1800 THEN '5-30min'
                        WHEN duration_sec < 3600 THEN '30-60min'
                        WHEN duration_sec < 14400 THEN '1-4hr'
                        ELSE '4hr+'
                    END as duration_bucket,
                    COUNT(*) as total,
                    SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END) as wins,
                    ROUND(SUM(pnl_usdt)::numeric, 2) as pnl
                FROM trades WHERE status = 'closed' AND duration_sec IS NOT NULL
                GROUP BY duration_bucket ORDER BY total DESC
            """)

            # 9. Top 5 best and worst trades
            best5 = await conn.fetch("""
                SELECT symbol, pnl_usdt, pnl_pct, strategy, pattern,
                       EXTRACT(HOUR FROM ts)::int as hour, q_score
                FROM trades WHERE status = 'closed'
                ORDER BY pnl_usdt DESC LIMIT 5
            """)
            worst5 = await conn.fetch("""
                SELECT symbol, pnl_usdt, pnl_pct, strategy, pattern,
                       EXTRACT(HOUR FROM ts)::int as hour, q_score
                FROM trades WHERE status = 'closed'
                ORDER BY pnl_usdt ASC LIMIT 5
            """)

            # 10. Account type (spot vs futures)
            by_account = await conn.fetch("""
                SELECT account,
                       COUNT(*) as total,
                       SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END) as wins,
                       ROUND(SUM(pnl_usdt)::numeric, 2) as pnl
                FROM trades WHERE status = 'closed'
                GROUP BY account ORDER BY pnl DESC
            """)

            return {
                "by_symbol": [dict(r) for r in by_symbol],
                "by_hour": [dict(r) for r in by_hour],
                "by_strategy": [dict(r) for r in by_strategy],
                "by_pattern": [dict(r) for r in by_pattern],
                "q_ranges": [dict(r) for r in q_ranges],
                "by_weekday": [dict(r) for r in by_weekday],
                "by_reason": [dict(r) for r in by_reason],
                "by_duration": [dict(r) for r in by_duration],
                "best5": [dict(r) for r in best5],
                "worst5": [dict(r) for r in worst5],
                "by_account": [dict(r) for r in by_account],
            }
    except Exception as e:
        print(f"[db] get_deep_analytics error: {e}")
        return {}


# ── v10.10: Q-Score Threshold Auto-Tune Analytics ────────────────────────────

async def get_best_q_threshold() -> list:
    """Analyze last 30 days of closed trades, return win rates by Q-score range.
    Returns list of {q_range, q_min, total, wins, win_rate, avg_pnl}."""
    if not is_ready():
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    CASE
                        WHEN q_score >= 85 THEN '85+'
                        WHEN q_score >= 80 THEN '80-84'
                        WHEN q_score >= 77 THEN '77-79'
                        WHEN q_score >= 74 THEN '74-76'
                        WHEN q_score >= 70 THEN '70-73'
                        ELSE '<70'
                    END as q_range,
                    CASE
                        WHEN q_score >= 85 THEN 85
                        WHEN q_score >= 80 THEN 80
                        WHEN q_score >= 77 THEN 77
                        WHEN q_score >= 74 THEN 74
                        WHEN q_score >= 70 THEN 70
                        ELSE 65
                    END as q_min,
                    COUNT(*) as total,
                    SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END) as wins,
                    ROUND(AVG(pnl_usdt)::numeric, 4) as avg_pnl
                FROM trades
                WHERE status = 'closed'
                  AND pnl_usdt IS NOT NULL
                  AND close_ts > EXTRACT(EPOCH FROM (NOW() - INTERVAL '30 days'))
                  AND q_score IS NOT NULL
                GROUP BY q_range, q_min
                ORDER BY q_min DESC
            """)
            result = []
            for r in rows:
                total = int(r["total"])
                wins = int(r["wins"])
                result.append({
                    "q_range": r["q_range"],
                    "q_min": int(r["q_min"]),
                    "total": total,
                    "wins": wins,
                    "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
                    "avg_pnl": float(r["avg_pnl"]) if r["avg_pnl"] else 0,
                })
            return result
    except Exception as e:
        print(f"[db] get_best_q_threshold error: {e}")
        return []


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


# ── v10.9.5: Auto-cleanup — prevent volume growth ──────────────────────────

async def cleanup_old_data() -> dict:
    """v10.9.5: Delete old data from high-volume tables to prevent disk growth.
    Retention policy:
      - signals:         30 days  (logs every 15min × 9 pairs = ~26k rows/month)
      - q_score_history: 30 days  (same frequency)
      - mirofish_memory: 14 days  (AI memory, recent is enough)
      - whale_events:    14 days  (market context, recent is enough)
      - macro_snapshots: 14 days  (hourly snapshots)
      - fg_history:      90 days  (low frequency, keep longer for analytics)
      - trades (closed): 180 days (keep 6 months of trade history)
    Runs VACUUM ANALYZE after cleanup to actually reclaim disk space.
    """
    if not is_ready():
        return {}
    deleted = {}
    try:
        async with _pool.acquire() as conn:
            r = await conn.execute("DELETE FROM signals WHERE ts < NOW() - INTERVAL '30 days'")
            deleted["signals"] = int(r.split()[-1])

            r = await conn.execute("DELETE FROM q_score_history WHERE ts < NOW() - INTERVAL '30 days'")
            deleted["q_score_history"] = int(r.split()[-1])

            r = await conn.execute("DELETE FROM mirofish_memory WHERE ts < NOW() - INTERVAL '14 days'")
            deleted["mirofish_memory"] = int(r.split()[-1])

            r = await conn.execute("DELETE FROM whale_events WHERE ts < NOW() - INTERVAL '14 days'")
            deleted["whale_events"] = int(r.split()[-1])

            r = await conn.execute("DELETE FROM macro_snapshots WHERE ts < NOW() - INTERVAL '14 days'")
            deleted["macro_snapshots"] = int(r.split()[-1])

            r = await conn.execute("DELETE FROM fg_history WHERE ts < NOW() - INTERVAL '90 days'")
            deleted["fg_history"] = int(r.split()[-1])

            r = await conn.execute("DELETE FROM trades WHERE status = 'closed' AND ts < NOW() - INTERVAL '180 days'")
            deleted["trades_old"] = int(r.split()[-1])

            total = sum(deleted.values())
            print(f"[db] 🧹 cleanup: удалено {total} строк → {deleted}", flush=True)

            # VACUUM to actually reclaim disk space
            await conn.execute("VACUUM ANALYZE signals")
            await conn.execute("VACUUM ANALYZE q_score_history")
            await conn.execute("VACUUM ANALYZE mirofish_memory")
            await conn.execute("VACUUM ANALYZE whale_events")
            await conn.execute("VACUUM ANALYZE macro_snapshots")
            print(f"[db] 🧹 VACUUM ANALYZE завершён", flush=True)

    except Exception as e:
        print(f"[db] cleanup error: {e}", flush=True)
    return deleted


async def get_table_sizes() -> dict:
    """v10.9.5: Get row counts and estimated sizes for all tables."""
    if not is_ready():
        return {}
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    relname AS table_name,
                    n_live_tup AS row_count,
                    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
                FROM pg_stat_user_tables
                ORDER BY n_live_tup DESC
            """)
            return {r["table_name"]: {"rows": r["row_count"], "size": r["total_size"]} for r in rows}
    except Exception as e:
        print(f"[db] get_table_sizes error: {e}")
        return {}


# ── v10.12.7: Funding Rate Arbitrage position persistence ─────────────────────

async def save_funding_arb_position(pos: dict) -> bool:
    """Upsert a funding arb position by symbol."""
    if not is_ready():
        return False
    try:
        async with _pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO funding_arb_positions
                    (symbol, perp_qty, spot_qty, entry_price, usdt_deployed,
                     opened_at, funding_collected, last_funding_ts)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                ON CONFLICT (symbol) DO UPDATE SET
                    perp_qty         = EXCLUDED.perp_qty,
                    spot_qty         = EXCLUDED.spot_qty,
                    entry_price      = EXCLUDED.entry_price,
                    usdt_deployed    = EXCLUDED.usdt_deployed,
                    opened_at        = EXCLUDED.opened_at,
                    funding_collected= EXCLUDED.funding_collected,
                    last_funding_ts  = EXCLUDED.last_funding_ts
            """,
            pos["symbol"], pos["perp_qty"], pos.get("spot_qty", 0),
            pos.get("entry_price", 0), pos.get("usdt_deployed", 0),
            pos.get("opened_at", 0), pos.get("funding_collected", 0),
            pos.get("last_funding_ts", 0))
        return True
    except Exception as e:
        print(f"[db] save_funding_arb_position error: {e}")
        return False


async def load_funding_arb_positions() -> list:
    """Load all open funding arb positions on startup."""
    if not is_ready():
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM funding_arb_positions ORDER BY opened_at")
            return [dict(r) for r in rows]
    except Exception as e:
        print(f"[db] load_funding_arb_positions error: {e}")
        return []


async def delete_funding_arb_position(symbol: str) -> bool:
    """Remove closed position from DB."""
    if not is_ready():
        return False
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM funding_arb_positions WHERE symbol = $1", symbol)
        return True
    except Exception as e:
        print(f"[db] delete_funding_arb_position error: {e}")
        return False
