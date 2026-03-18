"""
QuantumTrade AI - FastAPI Backend v2.0
Real KuCoin data + Polymarket + Origin QC
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

app = FastAPI(title="QuantumTrade AI Backend", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

KUCOIN_API_KEY    = os.getenv("KUCOIN_API_KEY", "")
KUCOIN_SECRET     = os.getenv("KUCOIN_SECRET", "")
KUCOIN_PASSPHRASE = os.getenv("KUCOIN_PASSPHRASE", "")
KUCOIN_BASE_URL   = "https://api.kucoin.com"
KUCOIN_FUT_URL    = "https://api-futures.kucoin.com"
ORIGIN_QC_KEY     = os.getenv("ORIGIN_QC_KEY", "")
BOT_TOKEN         = os.getenv("BOT_TOKEN", "")
ALERT_CHAT_ID     = os.getenv("ALERT_CHAT_ID", "")


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


# ── KuCoin Real Data ─────────────────────────────────────────────────────────
async def get_kucoin_balance() -> dict:
    """Get real account balance from KuCoin."""
    endpoint = "/api/v1/accounts"
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                KUCOIN_BASE_URL + endpoint,
                headers=kucoin_headers("GET", endpoint),
                timeout=aiohttp.ClientTimeout(total=10),
            )
            data = await r.json()
            if data.get("code") == "200000":
                accounts = data.get("data", [])
                total_usdt = 0
                balances = []
                for acc in accounts:
                    if float(acc.get("balance", 0)) > 0:
                        balances.append({
                            "currency": acc["currency"],
                            "balance": float(acc["balance"]),
                            "available": float(acc["available"]),
                            "type": acc["type"],
                        })
                    if acc["currency"] == "USDT":
                        total_usdt += float(acc.get("balance", 0))
                return {"total_usdt": round(total_usdt, 2), "accounts": balances, "success": True}
            return {"total_usdt": 0, "accounts": [], "success": False, "error": data.get("msg")}
    except Exception as e:
        return {"total_usdt": 0, "accounts": [], "success": False, "error": str(e)}


async def get_kucoin_ticker(symbol: str) -> dict:
    """Get real ticker price from KuCoin."""
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                f"{KUCOIN_BASE_URL}/api/v1/market/orderbook/level1?symbol={symbol}",
                timeout=aiohttp.ClientTimeout(total=5),
            )
            data = await r.json()
            if data.get("code") == "200000":
                d = data["data"]
                return {
                    "symbol": symbol,
                    "price": float(d.get("price", 0)),
                    "bestBid": float(d.get("bestBid", 0)),
                    "bestAsk": float(d.get("bestAsk", 0)),
                    "success": True,
                }
            return {"symbol": symbol, "price": 0, "success": False}
    except Exception as e:
        return {"symbol": symbol, "price": 0, "success": False, "error": str(e)}


async def get_kucoin_prices() -> dict:
    """Get multiple real prices at once."""
    symbols = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT", "AVAX-USDT"]
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                f"{KUCOIN_BASE_URL}/api/v1/market/allTickers",
                timeout=aiohttp.ClientTimeout(total=10),
            )
            data = await r.json()
            if data.get("code") == "200000":
                tickers = {t["symbol"]: t for t in data["data"]["ticker"]}
                result = {}
                for sym in symbols:
                    if sym in tickers:
                        t = tickers[sym]
                        result[sym] = {
                            "price": float(t.get("last", 0)),
                            "change": float(t.get("changeRate", 0)) * 100,
                            "vol": float(t.get("vol", 0)),
                        }
                return {"prices": result, "success": True, "timestamp": datetime.utcnow().isoformat()}
            return {"prices": {}, "success": False}
    except Exception as e:
        return {"prices": {}, "success": False, "error": str(e)}


async def get_kucoin_orders() -> dict:
    """Get recent orders from KuCoin."""
    endpoint = "/api/v1/orders?status=done&pageSize=20"
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                KUCOIN_BASE_URL + endpoint,
                headers=kucoin_headers("GET", endpoint),
                timeout=aiohttp.ClientTimeout(total=10),
            )
            data = await r.json()
            if data.get("code") == "200000":
                orders = data["data"].get("items", [])
                total_pnl = 0
                wins = 0
                for o in orders:
                    fee = float(o.get("fee", 0))
                    total_pnl -= fee
                return {
                    "orders": orders[:10],
                    "total": data["data"].get("totalNum", 0),
                    "success": True,
                }
            return {"orders": [], "total": 0, "success": False}
    except Exception as e:
        return {"orders": [], "total": 0, "success": False, "error": str(e)}


async def get_futures_positions() -> dict:
    """Get open futures positions."""
    endpoint = "/api/v1/positions"
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                KUCOIN_FUT_URL + endpoint,
                headers=kucoin_headers("GET", endpoint),
                timeout=aiohttp.ClientTimeout(total=10),
            )
            data = await r.json()
            if data.get("code") == "200000":
                positions = data.get("data", [])
                open_pos = [p for p in positions if p.get("currentQty", 0) != 0]
                total_unrealized = sum(float(p.get("unrealisedPnl", 0)) for p in open_pos)
                return {
                    "positions": open_pos,
                    "count": len(open_pos),
                    "total_unrealized_pnl": round(total_unrealized, 4),
                    "success": True,
                }
            return {"positions": [], "count": 0, "total_unrealized_pnl": 0, "success": False}
    except Exception as e:
        return {"positions": [], "count": 0, "total_unrealized_pnl": 0, "success": False, "error": str(e)}


# ── Polymarket Public API ─────────────────────────────────────────────────────
async def get_polymarket_events() -> dict:
    """Get top crypto-related events from Polymarket public API."""
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                "https://gamma-api.polymarket.com/events?limit=20&active=true&tag=crypto",
                timeout=aiohttp.ClientTimeout(total=10),
            )
            events = await r.json()
            result = []
            for e in events[:10]:
                markets = e.get("markets", [])
                if markets:
                    m = markets[0]
                    yes_price = float(m.get("outcomePrices", ["0.5"])[0])
                    result.append({
                        "title": e.get("title", ""),
                        "yes_prob": round(yes_price * 100, 1),
                        "volume": float(e.get("volume", 0)),
                        "end_date": e.get("endDate", ""),
                        "slug": e.get("slug", ""),
                    })
            return {"events": result, "success": True}
    except Exception as e:
        return {"events": [], "success": False, "error": str(e)}


# ── Quantum Signal Generator ─────────────────────────────────────────────────
def generate_signal(price_change: float, whale_score: float, poly_bull: float) -> dict:
    """Generate trading signal from multiple data sources."""
    score = (
        (50 + price_change * 10) * 0.4 +
        whale_score * 0.35 +
        poly_bull * 0.25
    )
    score = max(0, min(100, score))
    if score > 65:
        action = "BUY"
        confidence = round(score / 100, 2)
    elif score < 35:
        action = "SELL"
        confidence = round((100 - score) / 100, 2)
    else:
        action = "HOLD"
        confidence = 0.5
    return {
        "action": action,
        "confidence": confidence,
        "q_score": round(score, 1),
    }


# ── Telegram Notifications ────────────────────────────────────────────────────
async def send_telegram_alert(text: str):
    if not BOT_TOKEN or not ALERT_CHAT_ID:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": ALERT_CHAT_ID, "text": text, "parse_mode": "Markdown"},
            )
    except Exception:
        pass


# ── Place Order ───────────────────────────────────────────────────────────────
async def place_spot_order(symbol: str, side: str, size: float,
                            order_type: str = "market", price: float = None) -> dict:
    endpoint = "/api/v1/orders"
    body = {
        "clientOid": f"qt_{int(time.time()*1000)}",
        "side": side,
        "symbol": symbol,
        "type": order_type,
        "size": str(size),
    }
    if order_type == "limit" and price:
        body["price"] = str(price)
    body_str = json.dumps(body)
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                KUCOIN_BASE_URL + endpoint,
                headers=kucoin_headers("POST", endpoint, body_str),
                data=body_str,
                timeout=aiohttp.ClientTimeout(total=10),
            )
            return await r.json()
    except Exception as e:
        return {"code": "error", "msg": str(e)}


# ── API ROUTES ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0", "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/dashboard")
async def dashboard():
    """Main dashboard — real data from KuCoin + Polymarket."""
    balance, prices, positions, poly = await asyncio.gather(
        get_kucoin_balance(),
        get_kucoin_prices(),
        get_futures_positions(),
        get_polymarket_events(),
    )

    btc_change = prices["prices"].get("BTC-USDT", {}).get("change", 0)
    poly_bull = 65.0
    if poly["events"]:
        btc_events = [e for e in poly["events"] if "bitcoin" in e["title"].lower() or "btc" in e["title"].lower()]
        if btc_events:
            poly_bull = btc_events[0]["yes_prob"]

    signal = generate_signal(btc_change, 62, poly_bull)

    return {
        "balance": balance,
        "prices": prices,
        "positions": positions,
        "polymarket": poly,
        "signal": signal,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/prices")
async def get_prices():
    return await get_kucoin_prices()


@app.get("/api/balance")
async def get_balance():
    return await get_kucoin_balance()


@app.get("/api/positions")
async def get_positions():
    return await get_futures_positions()


@app.get("/api/orders")
async def get_orders():
    return await get_kucoin_orders()


@app.get("/api/polymarket")
async def get_polymarket():
    return await get_polymarket_events()


@app.get("/api/signal/{symbol}")
async def get_signal(symbol: str):
    ticker = await get_kucoin_ticker(symbol)
    price_change = ticker.get("change", 0) if ticker.get("success") else 0
    signal = generate_signal(price_change, 62, 65)
    signal["symbol"] = symbol
    signal["price"] = ticker.get("price", 0)
    return signal


class TradeRequest(BaseModel):
    symbol: str
    side: str
    size: float
    order_type: str = "market"
    price: Optional[float] = None


@app.post("/api/trade")
async def execute_trade(req: TradeRequest):
    result = await place_spot_order(
        req.symbol, req.side, req.size, req.order_type, req.price
    )
    if result.get("code") == "200000":
        emoji = "🟢" if req.side == "buy" else "🔴"
        await send_telegram_alert(
            f"{emoji} *Сделка исполнена*\n"
            f"Пара: `{req.symbol}`\n"
            f"Сторона: *{req.side.upper()}*\n"
            f"Размер: `{req.size}`"
        )
    return {"success": result.get("code") == "200000", "data": result}


@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            prices = await get_kucoin_prices()
            await websocket.send_json({
                "type": "prices",
                "data": prices,
                "timestamp": datetime.utcnow().isoformat(),
            })
            await asyncio.sleep(15)
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
