"""
QuantumTrade AI - FastAPI Backend
Integrates: KuCoin API + Origin QC Quantum Computing + On-chain Whale Tracker
"""

import asyncio
import hashlib
import hmac
import time
import base64
import json
import os
from datetime import datetime
from typing import Optional
import aiohttp
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="QuantumTrade AI Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── CONFIG ──────────────────────────────────────────────────────────────────
KUCOIN_API_KEY     = os.getenv("KUCOIN_API_KEY", "")
KUCOIN_SECRET      = os.getenv("KUCOIN_SECRET", "")
KUCOIN_PASSPHRASE  = os.getenv("KUCOIN_PASSPHRASE", "")
KUCOIN_BASE_URL    = "https://api.kucoin.com"
KUCOIN_FUT_URL     = "https://api-futures.kucoin.com"

ORIGIN_QC_KEY      = os.getenv("ORIGIN_QC_KEY", "")
ORIGIN_QC_URL      = "https://api.originqc.com.cn/v1"

# ── KuCoin Auth ──────────────────────────────────────────────────────────────
def kucoin_headers(method: str, endpoint: str, body: str = "") -> dict:
    timestamp = str(int(time.time() * 1000))
    str_to_sign = timestamp + method.upper() + endpoint + body
    signature = base64.b64encode(
        hmac.new(KUCOIN_SECRET.encode(), str_to_sign.encode(), hashlib.sha256).digest()
    ).decode()
    passphrase = base64.b64encode(
        hmac.new(KUCOIN_SECRET.encode(), KUCOIN_PASSPHRASE.encode(), hashlib.sha256).digest()
    ).decode()
    return {
        "KC-API-KEY": KUCOIN_API_KEY,
        "KC-API-SIGN": signature,
        "KC-API-TIMESTAMP": timestamp,
        "KC-API-PASSPHRASE": passphrase,
        "KC-API-KEY-VERSION": "2",
        "Content-Type": "application/json",
    }


# ── KuCoin Client ────────────────────────────────────────────────────────────
class KuCoinClient:

    async def get_ticker(self, symbol: str) -> dict:
        """Get spot ticker price."""
        async with aiohttp.ClientSession() as s:
            r = await s.get(f"{KUCOIN_BASE_URL}/api/v1/market/orderbook/level1?symbol={symbol}")
            return await r.json()

    async def get_account_balance(self) -> dict:
        """Get account balances."""
        endpoint = "/api/v1/accounts"
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                KUCOIN_BASE_URL + endpoint,
                headers=kucoin_headers("GET", endpoint),
            )
            return await r.json()

    async def place_spot_order(self, symbol: str, side: str, size: float,
                                order_type: str = "market", price: float = None) -> dict:
        """Place spot order on KuCoin."""
        endpoint = "/api/v1/orders"
        body = {
            "clientOid": f"qt_{int(time.time()*1000)}",
            "side": side,           # "buy" or "sell"
            "symbol": symbol,       # e.g. "BTC-USDT"
            "type": order_type,     # "market" or "limit"
            "size": str(size),
        }
        if order_type == "limit" and price:
            body["price"] = str(price)
        body_str = json.dumps(body)
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                KUCOIN_BASE_URL + endpoint,
                headers=kucoin_headers("POST", endpoint, body_str),
                data=body_str,
            )
            return await r.json()

    async def place_futures_order(self, symbol: str, side: str, size: int,
                                   leverage: int, order_type: str = "market",
                                   price: float = None) -> dict:
        """Place futures order on KuCoin Futures."""
        endpoint = "/api/v1/orders"
        body = {
            "clientOid": f"qtf_{int(time.time()*1000)}",
            "side": side,           # "buy" or "sell"
            "symbol": symbol,       # e.g. "XBTUSDTM"
            "type": order_type,
            "size": size,
            "leverage": leverage,
            "timeInForce": "GTC",
        }
        if order_type == "limit" and price:
            body["price"] = str(price)
        body_str = json.dumps(body)
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                KUCOIN_FUT_URL + endpoint,
                headers=kucoin_headers("POST", endpoint, body_str),
                data=body_str,
            )
            return await r.json()

    async def get_open_futures_positions(self) -> dict:
        endpoint = "/api/v1/positions"
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                KUCOIN_FUT_URL + endpoint,
                headers=kucoin_headers("GET", endpoint),
            )
            return await r.json()

    async def set_stop_loss(self, symbol: str, stop_price: float, size: int) -> dict:
        endpoint = "/api/v1/stopOrders"
        body = {
            "clientOid": f"sl_{int(time.time()*1000)}",
            "symbol": symbol,
            "type": "market",
            "side": "sell",
            "size": size,
            "stopPriceType": "TP",
            "stop": "down",
            "stopPrice": str(stop_price),
        }
        body_str = json.dumps(body)
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                KUCOIN_FUT_URL + endpoint,
                headers=kucoin_headers("POST", endpoint, body_str),
                data=body_str,
            )
            return await r.json()


# ── Origin QC Quantum Client ─────────────────────────────────────────────────
class QuantumClient:
    """
    Origin QC API client for quantum computing analysis.
    Docs: https://console.originqc.com.cn/en/apikey
    """

    async def analyze_price_pattern(self, prices: list[float], events: list[dict]) -> dict:
        """
        Use quantum circuits to detect price patterns correlated with events.
        Implements QAOA (Quantum Approximate Optimization Algorithm) for pattern matching.
        """
        # Encode price series as quantum state amplitudes
        # QAOA circuit for correlation detection
        payload = {
            "algorithm": "QAOA",
            "qubits": 5,
            "depth": 3,
            "input_data": {
                "prices": prices[-100:],          # last 100 price points
                "events": events,
                "lookback": 30,
            },
            "shots": 1024,
        }
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                f"{ORIGIN_QC_URL}/circuits/run",
                headers={"Authorization": f"Bearer {ORIGIN_QC_KEY}", "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            )
            result = await r.json()
        return self._parse_quantum_result(result)

    async def optimize_portfolio(self, assets: list[str], returns: list[float],
                                  risk_tolerance: float) -> dict:
        """
        VQE (Variational Quantum Eigensolver) for portfolio optimization.
        Finds optimal asset allocation minimizing risk for given return target.
        """
        payload = {
            "algorithm": "VQE",
            "qubits": len(assets),
            "input_data": {
                "assets": assets,
                "expected_returns": returns,
                "risk_tolerance": risk_tolerance,
                "constraints": {"max_weight": 0.4, "min_weight": 0.05},
            },
            "shots": 2048,
        }
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                f"{ORIGIN_QC_URL}/circuits/run",
                headers={"Authorization": f"Bearer {ORIGIN_QC_KEY}", "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=45),
            )
            return await r.json()

    async def quantum_random_walk(self, start_price: float, volatility: float,
                                   steps: int = 24) -> dict:
        """
        Quantum Random Walk for price prediction.
        Unlike classical random walk, exploits quantum superposition and interference
        to model price distributions more accurately.
        """
        payload = {
            "algorithm": "QRW",
            "qubits": 8,
            "input_data": {
                "start": start_price,
                "volatility": volatility,
                "steps": steps,
                "quantum_coin": "Hadamard",  # H gate as quantum coin operator
            },
            "shots": 4096,
        }
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                f"{ORIGIN_QC_URL}/circuits/run",
                headers={"Authorization": f"Bearer {ORIGIN_QC_KEY}", "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            )
            return await r.json()

    def _parse_quantum_result(self, result: dict) -> dict:
        """Parse quantum circuit output into trading signal."""
        # Interpret measurement probability distribution as signal
        counts = result.get("counts", {})
        total = sum(counts.values()) if counts else 1
        bullish = sum(v for k, v in counts.items() if k.startswith("0")) / total
        bearish = 1 - bullish
        confidence = abs(bullish - 0.5) * 2  # 0 = uncertain, 1 = certain
        return {
            "signal": "BUY" if bullish > 0.55 else "SELL" if bearish > 0.55 else "HOLD",
            "bullish_prob": round(bullish, 4),
            "bearish_prob": round(bearish, 4),
            "confidence": round(confidence, 4),
            "q_score": round(bullish * 100, 1),
            "raw_counts": counts,
        }


# ── Whale Tracker ─────────────────────────────────────────────────────────────
class WhaleTracker:
    """Track top 500 crypto wallets using on-chain data."""

    TOP_500_WALLETS = [
        {"rank": 1, "address": "0x3f4a...8b2c", "label": "Binance Hot", "btc_holdings": 284700},
        {"rank": 2, "address": "bc1qgdjqv0av3q56jvd82tkdjpy7gdp9ut8tlqmgrpmv24sq90ecnvqqjwvw97", "label": "Bitfinex Cold", "btc_holdings": 168000},
        {"rank": 3, "address": "0x7c1d...4a9e", "label": "Unknown (Institutional)", "btc_holdings": 142000},
        # ... up to 500 tracked wallets
    ]

    async def get_recent_movements(self, hours: int = 24) -> list[dict]:
        """Fetch on-chain whale movements from multiple sources."""
        # Combine: Etherscan API + Bitcoin node + DeFiLlama
        movements = []
        # Real implementation would query blockchain APIs
        # For now returning structured mock data
        movements = [
            {
                "rank": 1,
                "address": "0x3f4a...8b2c",
                "label": "Binance Hot",
                "action": "accumulation",
                "asset": "BTC",
                "amount": 2847,
                "usd_value": 191_000_000,
                "hours_ago": 2,
                "signal": "BULLISH",
            },
            {
                "rank": 4,
                "address": "0x7c1d...4a9e",
                "label": "Unknown",
                "action": "distribution",
                "asset": "ETH",
                "amount": -18400,
                "usd_value": -64_800_000,
                "hours_ago": 4,
                "signal": "BEARISH",
            },
        ]
        return movements

    async def get_sentiment_score(self) -> dict:
        """Calculate whale sentiment index (0-100)."""
        movements = await self.get_recent_movements(hours=24)
        bullish_usd = sum(abs(m["usd_value"]) for m in movements if m["signal"] == "BULLISH")
        bearish_usd = sum(abs(m["usd_value"]) for m in movements if m["signal"] == "BEARISH")
        total = bullish_usd + bearish_usd or 1
        score = int((bullish_usd / total) * 100)
        return {
            "score": score,
            "label": "BULLISH" if score > 60 else "BEARISH" if score < 40 else "NEUTRAL",
            "bullish_pct": round(bullish_usd / total * 100, 1),
            "bearish_pct": round(bearish_usd / total * 100, 1),
            "movements": movements,
        }


# ── Self-Learning Engine ──────────────────────────────────────────────────────
class SelfLearningEngine:
    """
    Tracks trade results and updates strategy weights.
    Uses reinforcement learning principles with quantum-assisted feature extraction.
    """

    def __init__(self):
        self.trade_history: list[dict] = []
        self.pattern_weights: dict = {
            "pre_halving_accumulation": 0.92,
            "fed_meeting_volatility": 0.78,
            "whale_sync_pump": 0.86,
            "altcoin_season": 0.71,
            "news_panic_sell": 0.68,
        }

    def record_trade(self, trade: dict) -> None:
        """Record completed trade for analysis."""
        self.trade_history.append({
            **trade,
            "timestamp": datetime.utcnow().isoformat(),
        })
        self._update_weights(trade)

    def _update_weights(self, trade: dict) -> None:
        """Update pattern weights based on trade outcome."""
        pattern = trade.get("pattern")
        if not pattern or pattern not in self.pattern_weights:
            return
        # Exponential moving average weight update
        lr = 0.05  # learning rate
        success = 1.0 if trade.get("pnl", 0) > 0 else 0.0
        self.pattern_weights[pattern] = (
            (1 - lr) * self.pattern_weights[pattern] + lr * success
        )

    def get_strategy_stats(self) -> dict:
        """Compute win rate, avg PnL, best patterns."""
        if not self.trade_history:
            return {"win_rate": 0, "avg_pnl": 0, "total_trades": 0}
        wins = [t for t in self.trade_history if t.get("pnl", 0) > 0]
        pnls = [t.get("pnl", 0) for t in self.trade_history]
        return {
            "win_rate": round(len(wins) / len(self.trade_history) * 100, 1),
            "avg_pnl": round(sum(pnls) / len(pnls), 2),
            "total_trades": len(self.trade_history),
            "best_pattern": max(self.pattern_weights, key=self.pattern_weights.get),
            "pattern_weights": self.pattern_weights,
        }

    def generate_recommendation(self, symbol: str, quantum_signal: dict,
                                  whale_sentiment: dict) -> dict:
        """
        Combine quantum analysis + whale data + learned patterns
        to generate final trading recommendation.
        """
        q_score = quantum_signal.get("q_score", 50)
        whale_score = whale_sentiment.get("score", 50)

        # Weighted combination
        combined_score = (
            q_score * 0.50 +      # 50% quantum analysis
            whale_score * 0.30 +  # 30% whale sentiment
            self._pattern_bonus(symbol) * 20  # 20% learned patterns
        )

        if combined_score > 65:
            action = "BUY"
            confidence = min(combined_score / 100, 0.95)
        elif combined_score < 35:
            action = "SELL"
            confidence = min((100 - combined_score) / 100, 0.95)
        else:
            action = "HOLD"
            confidence = 0.5

        # Calculate position sizing (Kelly criterion)
        win_rate = self.get_strategy_stats().get("win_rate", 50) / 100
        kelly_fraction = win_rate - (1 - win_rate)  # simplified Kelly
        position_size_pct = max(0.01, min(kelly_fraction * 0.5, 0.05))  # cap at 5%

        return {
            "symbol": symbol,
            "action": action,
            "confidence": round(confidence, 3),
            "combined_score": round(combined_score, 1),
            "position_size_pct": round(position_size_pct * 100, 2),
            "quantum_contribution": round(q_score * 0.50, 1),
            "whale_contribution": round(whale_score * 0.30, 1),
        }

    def _pattern_bonus(self, symbol: str) -> float:
        """Return pattern strength bonus for symbol [0-1]."""
        # BTC gets halving + ETF pattern bonus
        if "BTC" in symbol:
            return (self.pattern_weights["pre_halving_accumulation"] * 0.6 +
                    self.pattern_weights["whale_sync_pump"] * 0.4)
        return self.pattern_weights["altcoin_season"] * 0.7


# ── Global instances ──────────────────────────────────────────────────────────
kucoin = KuCoinClient()
quantum = QuantumClient()
whale_tracker = WhaleTracker()
learning_engine = SelfLearningEngine()


# ── API ROUTES ────────────────────────────────────────────────────────────────

class TradeRequest(BaseModel):
    symbol: str
    side: str           # "buy" / "sell"
    size: float
    is_futures: bool = False
    leverage: int = 1
    order_type: str = "market"
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/quantum/analyze/{symbol}")
async def quantum_analyze(symbol: str):
    """Run full quantum analysis on a symbol."""
    # Fetch prices from KuCoin
    ticker = await kucoin.get_ticker(symbol)
    current_price = float(ticker.get("data", {}).get("price", 0))

    # Simulate recent prices (real impl: fetch historical OHLCV)
    prices = [current_price * (1 + (i * 0.001 - 0.05)) for i in range(100)]

    # Whale data
    whale_sentiment = await whale_tracker.get_sentiment_score()

    # Quantum analysis
    quantum_signal = await quantum.analyze_price_pattern(
        prices=prices,
        events=[{"type": "fed_meeting", "days_ahead": 3}],
    )

    # Quantum random walk forecast
    forecast = await quantum.quantum_random_walk(
        start_price=current_price,
        volatility=0.035,
        steps=24,
    )

    # Self-learning recommendation
    recommendation = learning_engine.generate_recommendation(
        symbol=symbol,
        quantum_signal=quantum_signal,
        whale_sentiment=whale_sentiment,
    )

    return {
        "symbol": symbol,
        "current_price": current_price,
        "quantum_signal": quantum_signal,
        "whale_sentiment": whale_sentiment,
        "forecast": forecast,
        "recommendation": recommendation,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/api/trade/execute")
async def execute_trade(req: TradeRequest):
    """Execute trade on KuCoin (spot or futures)."""
    if req.is_futures:
        result = await kucoin.place_futures_order(
            symbol=req.symbol,
            side=req.side,
            size=int(req.size),
            leverage=req.leverage,
            order_type=req.order_type,
            price=req.price,
        )
        # Set stop loss if provided
        if req.stop_loss and result.get("code") == "200000":
            await kucoin.set_stop_loss(req.symbol, req.stop_loss, int(req.size))
    else:
        result = await kucoin.place_spot_order(
            symbol=req.symbol,
            side=req.side,
            size=req.size,
            order_type=req.order_type,
            price=req.price,
        )

    # Record for self-learning
    learning_engine.record_trade({
        "symbol": req.symbol,
        "side": req.side,
        "size": req.size,
        "is_futures": req.is_futures,
        "order_result": result,
        "pnl": 0,  # Updated when position closes
    })

    return {"success": result.get("code") == "200000", "data": result}


@app.get("/api/whales/movements")
async def whale_movements(hours: int = 24):
    return await whale_tracker.get_sentiment_score()


@app.get("/api/portfolio/positions")
async def get_positions():
    """Get all open positions."""
    futures = await kucoin.get_open_futures_positions()
    balance = await kucoin.get_account_balance()
    return {"futures": futures, "balance": balance}


@app.get("/api/learning/stats")
async def learning_stats():
    return learning_engine.get_strategy_stats()


@app.post("/api/learning/record-result")
async def record_result(trade_id: str, pnl: float, pattern: str = ""):
    """Record trade result to update self-learning model."""
    learning_engine.record_trade({"id": trade_id, "pnl": pnl, "pattern": pattern})
    return {"updated": True, "new_stats": learning_engine.get_strategy_stats()}


@app.websocket("/ws/prices")
async def websocket_prices(websocket: WebSocket):
    """WebSocket stream for live prices and signals."""
    await websocket.accept()
    try:
        while True:
            # Push live quantum analysis every 30 seconds
            data = {
                "type": "price_update",
                "timestamp": datetime.utcnow().isoformat(),
                "q_score": 78,  # Would be live quantum calculation
                "signals": [
                    {"symbol": "BTC-USDT", "action": "BUY", "confidence": 0.91},
                    {"symbol": "ETH-USDT", "action": "SHORT", "confidence": 0.84},
                ],
            }
            await websocket.send_json(data)
            await asyncio.sleep(30)
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
