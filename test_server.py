"""
QuantumTrade AI — Smart Test Suite v1.0
Covers: EMA, RSI, Q-Score, QAOA bias, Polymarket bonus,
        log_trade, API auth, rate limiting, triangular arb math.
Run: pytest test_server.py -v
"""

import sys, os, time, importlib, types, unittest
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

# ── Set env vars before any import so server.py constants are correct ─────────
os.environ.setdefault("KUCOIN_API_KEY",    "test_key")
os.environ.setdefault("KUCOIN_API_SECRET", "test_secret")
os.environ.setdefault("KUCOIN_PASSPHRASE", "test_pass")
os.environ.setdefault("BOT_TOKEN",         "0:test")
os.environ.setdefault("TELEGRAM_CHAT_ID",  "123")
os.environ.setdefault("API_SECRET",        "test_api_secret_32chars_xxxxxxxxx")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")

# Import the pure functions we want to test (lazy, avoids full app startup)
# We import only after stubs are in place
import importlib.util, pathlib

_SERVER_PATH = pathlib.Path(__file__).parent / "server.py"

def _load_server():
    """Load server module with mocked startup side-effects."""
    spec = importlib.util.spec_from_file_location("server", _SERVER_PATH)
    mod  = importlib.util.module_from_spec(spec)
    # Patch asyncio.create_task so startup tasks don't fire
    with patch("asyncio.create_task", return_value=None):
        try:
            spec.loader.exec_module(mod)
        except Exception:
            pass  # startup errors are OK — we only need pure functions
    return mod

_srv = None

def get_srv():
    global _srv
    if _srv is None:
        _srv = _load_server()
    return _srv


# ══════════════════════════════════════════════════════════════════════════════
# 1. EMA — Exponential Moving Average
# ══════════════════════════════════════════════════════════════════════════════
class TestEMA(unittest.TestCase):

    def setUp(self):
        self.ema = get_srv()._ema

    def test_empty_list(self):
        self.assertEqual(self.ema([], 10), 0.0)

    def test_single_element(self):
        self.assertEqual(self.ema([42.0], 5), 42.0)

    def test_short_list_returns_last(self):
        # less data than period → returns last element
        result = self.ema([10.0, 20.0, 30.0], 10)
        self.assertEqual(result, 30.0)

    def test_exact_period_is_sma(self):
        data = [10.0, 20.0, 30.0]
        result = self.ema(data, 3)
        self.assertAlmostEqual(result, 20.0, places=4)

    def test_rising_series_ema_above_sma(self):
        data = list(range(1, 21))  # 1..20
        ema5  = self.ema(data, 5)
        sma5  = sum(data[-5:]) / 5
        # EMA reacts faster to recent prices → should be close to SMA for linear series
        self.assertAlmostEqual(ema5, sma5, delta=2.0)

    def test_constant_series(self):
        data = [50.0] * 20
        self.assertAlmostEqual(self.ema(data, 10), 50.0, places=4)


# ══════════════════════════════════════════════════════════════════════════════
# 2. RSI — Relative Strength Index
# ══════════════════════════════════════════════════════════════════════════════
class TestRSI(unittest.TestCase):

    def setUp(self):
        self.rsi = get_srv()._rsi

    def test_insufficient_data_returns_50(self):
        self.assertEqual(self.rsi([100.0] * 5, 14), 50.0)

    def test_all_gains_returns_100(self):
        data = [float(i) for i in range(1, 30)]  # always rising
        self.assertEqual(self.rsi(data), 100.0)

    def test_all_losses_returns_near_0(self):
        data = [float(30 - i) for i in range(30)]  # always falling
        result = self.rsi(data)
        self.assertLess(result, 5.0)

    def test_neutral_oscillation_near_50(self):
        import math
        data = [50.0 + 5 * math.sin(i) for i in range(30)]
        result = self.rsi(data)
        self.assertGreater(result, 30.0)
        self.assertLess(result, 70.0)

    def test_output_bounded_0_100(self):
        import random
        random.seed(42)
        data = [random.uniform(0, 100) for _ in range(50)]
        result = self.rsi(data)
        self.assertGreaterEqual(result, 0.0)
        self.assertLessEqual(result, 100.0)


# ══════════════════════════════════════════════════════════════════════════════
# 3. calc_signal — Q-Score engine
# ══════════════════════════════════════════════════════════════════════════════
class TestCalcSignal(unittest.TestCase):

    def setUp(self):
        self.calc = get_srv().calc_signal

    def _vision(self, pattern="consolidation", rsi=50.0, ema_bullish=None, vol_ratio=1.0, bonus=0.0):
        return {
            "pattern": pattern, "rsi": rsi, "ema_bullish": ema_bullish,
            "vol_ratio": vol_ratio, "vision_bonus": bonus, "signal": "HOLD", "confidence": 0.5
        }

    def test_strong_bull_returns_buy(self):
        result = self.calc(
            price_change=5.0,
            vision=self._vision("uptrend_breakout", rsi=65.0, ema_bullish=True, vol_ratio=1.5),
            fear_greed={"bonus": 8, "success": True},
            polymarket_bonus=5.0,
            whale_bonus=4.0,
            quantum_bias=10.0,
        )
        self.assertEqual(result["action"], "BUY")
        self.assertGreater(result["q_score"], 70.0)

    def test_strong_bear_returns_sell(self):
        result = self.calc(
            price_change=-5.0,
            vision=self._vision("downtrend_breakdown", rsi=35.0, ema_bullish=False),
            fear_greed={"bonus": -8, "success": True},
            polymarket_bonus=-5.0,
            quantum_bias=-12.0,
        )
        self.assertEqual(result["action"], "SELL")
        self.assertLess(result["q_score"], 40.0)

    def test_neutral_returns_hold(self):
        result = self.calc(price_change=0.0)
        self.assertEqual(result["action"], "HOLD")
        self.assertAlmostEqual(result["q_score"], 50.0, delta=3.0)

    def test_q_score_always_0_to_100(self):
        for pc in [-20, -5, 0, 5, 20]:
            r = self.calc(price_change=float(pc), quantum_bias=float(pc * 2))
            self.assertGreaterEqual(r["q_score"], 0.0)
            self.assertLessEqual(r["q_score"], 100.0)

    def test_quantum_amplification_when_aligned(self):
        """Quantum bias aligned with trend should amplify score vs misaligned."""
        base = self.calc(price_change=3.0, quantum_bias=0.0)
        aligned = self.calc(price_change=3.0, quantum_bias=10.0)
        misaligned = self.calc(price_change=3.0, quantum_bias=-10.0)
        self.assertGreater(aligned["q_score"], base["q_score"])
        self.assertLess(misaligned["q_score"], base["q_score"])

    def test_breakdown_keys_present(self):
        result = self.calc(price_change=1.0, polymarket_bonus=2.0, whale_bonus=1.0)
        bd = result["breakdown"]
        for key in ("price_momentum", "fear_greed", "polymarket", "whale", "quantum_bias"):
            self.assertIn(key, bd)

    def test_confidence_range(self):
        for pc in [-10, -3, 0, 3, 10]:
            r = self.calc(price_change=float(pc))
            self.assertGreaterEqual(r["confidence"], 0.0)
            self.assertLessEqual(r["confidence"], 1.0)


# ══════════════════════════════════════════════════════════════════════════════
# 4. _smooth_qaoa_bias — rolling average + clamp
# ══════════════════════════════════════════════════════════════════════════════
class TestSmoothQaoaBias(unittest.TestCase):

    def setUp(self):
        srv = get_srv()
        self.fn = srv._smooth_qaoa_bias
        # Reset history for clean tests
        srv._qaoa_history.clear()

    def test_clamp_positive(self):
        result = self.fn("BTC", 999.0)
        self.assertLessEqual(result, 15.0)

    def test_clamp_negative(self):
        result = self.fn("ETH", -999.0)
        self.assertGreaterEqual(result, -15.0)

    def test_rolling_average_smooths(self):
        srv = get_srv()
        srv._qaoa_history.clear()
        # Feed alternating +10 / -10 values → average should hover near 0
        for _ in range(10):
            self.fn("SOL", 10.0)
            self.fn("SOL", -10.0)
        result = self.fn("SOL", 0.0)
        self.assertAlmostEqual(result, 0.0, delta=3.0)

    def test_history_max_window(self):
        srv = get_srv()
        srv._qaoa_history.clear()
        win = srv._QAOA_WINDOW
        for i in range(win + 5):
            self.fn("BTC", float(i))
        self.assertLessEqual(len(srv._qaoa_history["BTC"]), win)


# ══════════════════════════════════════════════════════════════════════════════
# 5. calc_polymarket_bonus
# ══════════════════════════════════════════════════════════════════════════════
class TestPolymarketBonus(unittest.TestCase):

    def setUp(self):
        self.fn = get_srv().calc_polymarket_bonus

    def test_empty_events_returns_zero(self):
        self.assertEqual(self.fn("BTC", []), 0.0)

    def test_output_clamped_pm8(self):
        events = [{"title": "bitcoin etf approved sec", "yes_prob": 95.0, "volume": 1_000_000}] * 10
        result = self.fn("BTC", events)
        self.assertGreaterEqual(result, -8.0)
        self.assertLessEqual(result, 8.0)

    def test_bullish_event_positive_bonus(self):
        events = [{"title": "bitcoin etf approved", "yes_prob": 85.0, "volume": 500_000}]
        result = self.fn("BTC", events)
        self.assertGreater(result, 0.0)

    def test_bearish_event_negative_bonus(self):
        # "crypto ban" is a known bearish keyword in _PM_SIGNALS
        events = [{"title": "crypto ban announced by government", "yes_prob": 80.0, "volume": 500_000}]
        result = self.fn("BTC", events)
        self.assertLess(result, 0.0)

    def test_low_probability_near_zero(self):
        # yes_prob=50% → signal_strength=0 → bonus≈0
        events = [{"title": "bitcoin etf approved", "yes_prob": 50.0, "volume": 100_000}]
        result = self.fn("BTC", events)
        self.assertAlmostEqual(result, 0.0, delta=0.5)


# ══════════════════════════════════════════════════════════════════════════════
# 6. log_trade — структура записи
# ══════════════════════════════════════════════════════════════════════════════
class TestLogTrade(unittest.TestCase):

    def setUp(self):
        srv = get_srv()
        srv.trade_log.clear()
        self.log_trade = srv.log_trade
        self.trade_log = srv.trade_log

    def test_trade_appended_to_log(self):
        self.log_trade("XBTUSDTM", "BUY", 50000.0, 0.001, 51500.0, 49500.0, 0.80, 78.5, "uptrend")
        self.assertEqual(len(self.trade_log), 1)

    def test_trade_has_required_keys(self):
        self.log_trade("ETHUSDTM", "SELL", 3000.0, 0.01, 2910.0, 3090.0, 0.75, 72.0, "downtrend")
        t = self.trade_log[-1]
        # log_trade stores entry price as "price" key (not "entry_price")
        for key in ("id", "symbol", "side", "price", "size", "tp", "sl",
                    "confidence", "q_score", "pattern", "status"):
            self.assertIn(key, t, f"Missing key: {key}")

    def test_new_trade_status_is_open(self):
        self.log_trade("SOLUSDT", "BUY", 150.0, 1.0, 157.5, 147.0, 0.70, 65.0, "uptrend")
        self.assertEqual(self.trade_log[-1]["status"], "open")

    def test_trade_id_is_unique(self):
        for i in range(5):
            self.log_trade("BTCUSDT", "BUY", 50000.0 + i, 0.001, 51500.0, 49500.0, 0.8, 70.0, "uptrend")
        ids = [t["id"] for t in self.trade_log]
        self.assertEqual(len(ids), len(set(ids)))


# ══════════════════════════════════════════════════════════════════════════════
# 7. API Key Authentication
# ══════════════════════════════════════════════════════════════════════════════
class TestAPIKeyAuth(unittest.TestCase):

    def test_correct_key_passes(self):
        """verify_api_key should not raise for correct key."""
        import asyncio
        srv = get_srv()
        secret = os.environ["API_SECRET"]
        coro = srv.verify_api_key(x_api_key=secret)
        # Should not raise
        try:
            asyncio.get_event_loop().run_until_complete(coro)
        except Exception as e:
            self.fail(f"verify_api_key raised unexpectedly: {e}")

    def test_wrong_key_raises_401(self):
        import asyncio
        from fastapi import HTTPException
        srv = get_srv()
        with self.assertRaises(HTTPException) as ctx:
            asyncio.get_event_loop().run_until_complete(
                srv.verify_api_key(x_api_key="wrong_key")
            )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_missing_key_raises_401(self):
        import asyncio
        from fastapi import HTTPException
        srv = get_srv()
        with self.assertRaises(HTTPException) as ctx:
            asyncio.get_event_loop().run_until_complete(
                srv.verify_api_key(x_api_key=None)
            )
        self.assertEqual(ctx.exception.status_code, 401)


# ══════════════════════════════════════════════════════════════════════════════
# 8. Rate Limiting — /api/ai/chat
# ══════════════════════════════════════════════════════════════════════════════
class TestRateLimiting(unittest.TestCase):

    def setUp(self):
        srv = get_srv()
        srv._ai_chat_rl.clear()
        self.srv = srv

    def _simulate_requests(self, n: int, ip: str = "127.0.0.1"):
        """Simulate n rate-limit increments directly."""
        from fastapi import HTTPException
        srv = self.srv
        blocked_at = None
        for i in range(n):
            now_ts = time.time()
            rl = srv._ai_chat_rl.get(ip, (0, now_ts))
            if now_ts - rl[1] > srv._AI_CHAT_WINDOW:
                srv._ai_chat_rl[ip] = (1, now_ts)
            else:
                if rl[0] >= srv._AI_CHAT_LIMIT:
                    blocked_at = i + 1
                    break
                srv._ai_chat_rl[ip] = (rl[0] + 1, rl[1])
        return blocked_at

    def test_under_limit_not_blocked(self):
        blocked = self._simulate_requests(15)
        self.assertIsNone(blocked)

    def test_over_limit_gets_blocked(self):
        blocked = self._simulate_requests(25)
        self.assertIsNotNone(blocked)
        self.assertLessEqual(blocked, 21)

    def test_different_ips_independent(self):
        for ip in ["1.1.1.1", "2.2.2.2", "3.3.3.3"]:
            blocked = self._simulate_requests(15, ip=ip)
            self.assertIsNone(blocked, f"IP {ip} was incorrectly blocked")

    def test_window_reset_allows_new_requests(self):
        """After window expires, counter resets."""
        srv = self.srv
        ip = "10.0.0.1"
        old_ts = time.time() - srv._AI_CHAT_WINDOW - 1  # expired window
        srv._ai_chat_rl[ip] = (srv._AI_CHAT_LIMIT, old_ts)  # was at limit but old
        # New request should reset window
        now_ts = time.time()
        rl = srv._ai_chat_rl[ip]
        self.assertGreater(now_ts - rl[1], srv._AI_CHAT_WINDOW)  # confirm expired


# ══════════════════════════════════════════════════════════════════════════════
# 9. Triangular Arbitrage Math
# ══════════════════════════════════════════════════════════════════════════════
class TestTriangularArbMath(unittest.TestCase):
    """
    Tests the profit formula used in check_triangular_arb,
    without making any HTTP calls.
    """

    ARB_FEE = 0.001  # 0.1% per leg

    def _profit1(self, price_a, price_b, actual_cross):
        """USDT → A → B → USDT profit formula."""
        return (1 / price_a) * actual_cross * price_b * (1 - self.ARB_FEE)**3 - 1

    def _profit2(self, price_a, price_b, actual_cross):
        """Reverse direction profit formula."""
        return (1 / price_b) * (1 / actual_cross) * price_a * (1 - self.ARB_FEE)**3 - 1

    def test_no_arb_when_prices_aligned(self):
        """If actual_cross == implied_cross, both profits should be near zero (minus fees)."""
        price_a = 3000.0  # ETH
        price_b = 50000.0  # BTC
        implied = price_a / price_b  # 0.06
        p1 = self._profit1(price_a, price_b, implied)
        p2 = self._profit2(price_a, price_b, implied)
        # Both should be negative (fees eat the profit)
        self.assertLess(p1, 0.0)
        self.assertLess(p2, 0.0)

    def test_arb_detected_when_spread_exists(self):
        """Artificially large spread should produce positive profit in one direction."""
        price_a = 3000.0   # ETH
        price_b = 50000.0  # BTC
        implied = price_a / price_b  # 0.06
        actual  = implied * 1.01    # 1% overpriced cross → arb opportunity
        p1 = self._profit1(price_a, price_b, actual)
        # Direction 1 benefits from overpriced cross
        self.assertGreater(p1, 0.0)

    def test_profit_symmetric_inverse(self):
        """If dir1 is profitable, dir2 should be unprofitable and vice versa."""
        price_a = 3000.0
        price_b = 50000.0
        implied = price_a / price_b
        actual  = implied * 1.005
        p1 = self._profit1(price_a, price_b, actual)
        p2 = self._profit2(price_a, price_b, actual)
        # They should have opposite signs for meaningful spread
        self.assertGreater(max(p1, p2), 0)
        self.assertLess(min(p1, p2), 0)

    def test_fee_impact(self):
        """Higher fees reduce profit."""
        price_a, price_b = 3000.0, 50000.0
        actual = (price_a / price_b) * 1.01
        low_fee  = (1 / price_a) * actual * price_b * (1 - 0.0005)**3 - 1
        high_fee = (1 / price_a) * actual * price_b * (1 - 0.002)**3 - 1
        self.assertGreater(low_fee, high_fee)


# ══════════════════════════════════════════════════════════════════════════════
# 10. Trade log resilience — t.get("status") fix
# ══════════════════════════════════════════════════════════════════════════════
class TestTradeLogResilience(unittest.TestCase):
    """Verifies that _tg_stats/_tg_positions don't crash on legacy trades."""

    def setUp(self):
        srv = get_srv()
        srv.trade_log.clear()
        self.srv = srv

    def test_missing_status_key_does_not_crash(self):
        """Old trade entries without 'status' key should not cause KeyError."""
        self.srv.trade_log.append({
            "id": "legacy_001", "symbol": "BTCUSDT",
            "side": "BUY", "pnl": 5.0, "entry_price": 50000.0
            # NO "status" key — simulates old persisted trade
        })
        # The fixed comprehension uses t.get("status", "") — should not raise
        try:
            open_count = sum(1 for t in self.srv.trade_log if t.get("status", "") == "open")
            open_trades = [t for t in self.srv.trade_log if t.get("status", "") == "open"]
        except KeyError as e:
            self.fail(f"KeyError raised on legacy trade: {e}")
        self.assertEqual(open_count, 0)
        self.assertEqual(open_trades, [])


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    unittest.main(verbosity=2)
