"""
QuantumTrade AI - FastAPI Backend v3.0
Auto-trading + Notifications + Multi-pair strategy
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
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="QuantumTrade AI", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

KUCOIN_API_KEY    = os.getenv("KUCOIN_API_KEY", "")
KUCOIN_SECRET     = os.getenv("KUCOIN_SECRET", "")
KUCOIN_PASSPHRASE = os.getenv("KUCOIN_PASSPHRASE", "")
KUCOIN_BASE_URL   = "https://api.kucoin.com"
KUCOIN_FUT_URL    = "https://api-futures.kucoin.com"
BOT_TOKEN         = os.getenv("BOT_TOKEN", "")
ALERT_CHAT_ID     = os.getenv("ALERT_CHAT_ID", "")

# Trading pairs for auto-trading
TRADING_PAIRS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT", "AVAX-USDT"]
RISK_PER_TRADE = 0.02   # 2% of balance per trade
MAX_LEVERAGE   = 3       # max 3x leverage
MIN_CONFIDENCE = 0.70    # min 70% confidence to trade
MIN_QSCORE     = 65      # min Q-Score to trade

# State
last_qscore = 0
auto_trading = True
open_positions = {}


# ── KuCoin Auth ───────────────────────────────────────────────────────────────
def kucoin_headers(method: str, endpoint: str, body: str = "") -> dict:
    ts = str(int(time.time() * 1000))
    sig = base64.b64encode(
        hmac.new(KUCOIN_SECRET.encode(), (ts + method.upper() + endpoint + body).encode(), hashlib.sha256).digest()
    ).decode()
    pp = base64.b64encode(
        hmac.new(KUCOIN_SECRET.encode(), KUCOIN_PASSPHRASE.encode(), hashlib.sha256).digest()
    ).decode()
    return {"KC-API-KEY": KUCOIN_API_KEY, "KC-API-SIGN": sig, "KC-API-TIMESTAMP": ts,
            "KC-API-PASSPHRASE": pp, "KC-API-KEY-VERSION": "2", "Content-Type": "application/json"}


# ── KuCoin API ────────────────────────────────────────────────────────────────
async def get_balance() -> dict:
    endpoint = "/api/v1/accounts"
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(KUCOIN_BASE_URL + endpoint, headers=kucoin_headers("GET", endpoint), timeout=aiohttp.ClientTimeout(total=10))
            data = await r.json()
            if data.get("code") == "200000":
                total = sum(float(a.get("balance", 0)) for a in data["data"] if a["currency"] == "USDT")
                return {"total_usdt": round(total, 2), "accounts": data["data"], "success": True}
            return {"total_usdt": 0, "accounts": [], "success": False, "error": data.get("msg")}
    except Exception as e:
        return {"total_usdt": 0, "accounts": [], "success": False, "error": str(e)}


async def get_prices() -> dict:
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(f"{KUCOIN_BASE_URL}/api/v1/market/allTickers", timeout=aiohttp.ClientTimeout(total=10))
            data = await r.json()
            if data.get("code") == "200000":
                tickers = {t["symbol"]: t for t in data["data"]["ticker"]}
                result = {}
                for sym in TRADING_PAIRS:
                    if sym in tickers:
                        t = tickers[sym]
                        result[sym] = {
                            "price": float(t.get("last", 0)),
                            "change": float(t.get("changeRate", 0)) * 100,
                            "vol": float(t.get("vol", 0)),
                        }
                return {"prices": result, "success": True, "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        return {"prices": {}, "success": False, "error": str(e)}


async def place_order(symbol: str, side: str, size: float, order_type: str = "market") -> dict:
    endpoint = "/api/v1/orders"
    body = json.dumps({
        "clientOid": f"qt_{int(time.time()*1000)}",
        "side": side, "symbol": symbol,
        "type": order_type, "size": str(size),
    })
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(KUCOIN_BASE_URL + endpoint, headers=kucoin_headers("POST", endpoint, body),
                             data=body, timeout=aiohttp.ClientTimeout(total=10))
            return await r.json()
    except Exception as e:
        return {"code": "error", "msg": str(e)}


async def get_ticker(symbol: str) -> dict:
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(f"{KUCOIN_BASE_URL}/api/v1/market/orderbook/level1?symbol={symbol}",
                            timeout=aiohttp.ClientTimeout(total=5))
            data = await r.json()
            if data.get("code") == "200000":
                return {"price": float(data["data"].get("price", 0)), "success": True}
    except Exception:
        pass
    return {"price": 0, "success": False}


# ── Telegram ──────────────────────────────────────────────────────────────────
async def send_alert(text: str):
    if not BOT_TOKEN or not ALERT_CHAT_ID:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": ALERT_CHAT_ID, "text": text, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=5)
            )
    except Exception:
        pass


# ── Signal Generator ──────────────────────────────────────────────────────────
def calculate_signal(price_change: float, symbol: str) -> dict:
    """Calculate trading signal based on price change and momentum."""
    # Base score from price change
    base = 50 + price_change * 8

    # Symbol-specific adjustments
    bonuses = {"BTC-USDT": 5, "ETH-USDT": 3, "SOL-USDT": 2, "BNB-USDT": 1, "XRP-USDT": 0, "AVAX-USDT": 2}
    score = base + bonuses.get(symbol, 0)
    score = max(0, min(100, score))

    if score > 65:
        action, confidence = "BUY", min(score / 100, 0.95)
    elif score < 35:
        action, confidence = "SELL", min((100 - score) / 100, 0.95)
    else:
        action, confidence = "HOLD", 0.5

    return {"action": action, "confidence": round(confidence, 3), "q_score": round(score, 1)}


# ── Auto Trading Engine ───────────────────────────────────────────────────────
async def run_auto_trading():
    """Main auto-trading loop — runs every 60 seconds."""
    global last_qscore, auto_trading

    while True:
        await asyncio.sleep(60)

        if not auto_trading:
            continue

        try:
            prices_data = await get_prices()
            if not prices_data.get("success"):
                continue

            balance_data = await get_balance()
            total_usdt = balance_data.get("total_usdt", 0)

            if total_usdt < 1:
                continue

            signals = []
            for symbol, price_info in prices_data["prices"].items():
                sig = calculate_signal(price_info["change"], symbol)
                sig["symbol"] = symbol
                sig["price"] = price_info["price"]
                signals.append(sig)

            # Find best signal
            best = max(signals, key=lambda x: x["q_score"])
            current_qscore = best["q_score"]

            # Alert when Q-Score crosses 65
            if current_qscore > MIN_QSCORE and last_qscore <= MIN_QSCORE:
                await send_alert(
                    f"⚛ *QuantumTrade AI Alert*\n\n"
                    f"Q-Score поднялся до *{current_qscore:.0f}*!\n"
                    f"Сигнал: *{best['action']}* {best['symbol']}\n"
                    f"Цена: `${best['price']:.4f}`\n"
                    f"Уверенность: *{int(best['confidence']*100)}%*\n\n"
                    f"🤖 Автопилот анализирует позицию..."
                )

            last_qscore = current_qscore

            # Execute trades if signal is strong enough
            if current_qscore >= MIN_QSCORE and best["confidence"] >= MIN_CONFIDENCE:
                symbol = best["symbol"]

                # Skip if already in position for this symbol
                if symbol in open_positions:
                    continue

                # Calculate position size (2% of balance)
                position_usdt = round(total_usdt * RISK_PER_TRADE, 2)
                if position_usdt < 1:
                    continue

                # Get current price for size calculation
                ticker = await get_ticker(symbol)
                if not ticker["success"] or ticker["price"] == 0:
                    continue

                price = ticker["price"]
                size = round(position_usdt / price, 6)

                if size <= 0:
                    continue

                # Place order
                side = "buy" if best["action"] == "BUY" else "sell"
                result = await place_order(symbol, side, size)

                if result.get("code") == "200000":
                    open_positions[symbol] = {
                        "side": side, "size": size, "entry_price": price,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    await send_alert(
                        f"✅ *Сделка открыта!*\n\n"
                        f"Пара: `{symbol}`\n"
                        f"Действие: *{side.upper()}*\n"
                        f"Размер: `{size}` (~${position_usdt})\n"
                        f"Цена входа: `${price:.4f}`\n"
                        f"Q-Score: *{current_qscore:.0f}*\n"
                        f"Уверенность: *{int(best['confidence']*100)}%*"
                    )
                else:
                    await send_alert(
                        f"⚠️ *Ошибка ордера*\n`{symbol}`: {result.get('msg', 'Unknown error')}"
                    )

        except Exception as e:
            print(f"Auto-trading error: {e}")


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    asyncio.create_task(run_auto_trading())
    await send_alert(
        "⚛ *QuantumTrade AI v3.0 запущен!*\n\n"
        "✅ Автоторговля активна\n"
        "✅ Мультипарная стратегия\n"
        "✅ Уведомления включены\n"
        f"📊 Пары: {', '.join(TRADING_PAIRS)}\n"
        f"⚡ Риск на сделку: {int(RISK_PER_TRADE*100)}%\n"
        f"🎯 Мин. Q-Score для входа: {MIN_QSCORE}"
    )


# ── API Routes ────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "version": "3.0.0", "auto_trading": auto_trading,
            "last_qscore": last_qscore, "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/balance")
async def api_balance():
    return await get_balance()

@app.get("/api/prices")
async def api_prices():
    return await get_prices()

@app.get("/api/signal/{symbol}")
async def api_signal(symbol: str):
    ticker = await get_ticker(symbol)
    prices = await get_prices()
    change = prices["prices"].get(symbol, {}).get("change", 0)
    sig = calculate_signal(change, symbol)
    sig["symbol"] = symbol
    sig["price"] = ticker.get("price", 0)
    return sig

@app.get("/api/positions")
async def api_positions():
    return {"positions": open_positions, "count": len(open_positions)}

@app.get("/api/dashboard")
async def api_dashboard():
    balance, prices = await asyncio.gather(get_balance(), get_prices())
    signals = []
    for sym, price_info in prices.get("prices", {}).items():
        sig = calculate_signal(price_info["change"], sym)
        sig["symbol"] = sym
        sig["price"] = price_info["price"]
        signals.append(sig)
    best = max(signals, key=lambda x: x["q_score"]) if signals else {}
    return {"balance": balance, "prices": prices, "signal": best,
            "positions": open_positions, "auto_trading": auto_trading,
            "timestamp": datetime.utcnow().isoformat()}

@app.post("/api/trading/toggle")
async def toggle_trading():
    global auto_trading
    auto_trading = not auto_trading
    status = "включена" if auto_trading else "выключена"
    await send_alert(f"🤖 Автоторговля *{status}*")
    return {"auto_trading": auto_trading}

@app.post("/api/alert/test")
async def test_alert():
    await send_alert("✅ *Тест уведомлений работает!*\nQuantumTrade AI готов к торговле.")
    return {"sent": True}

@app.get("/api/polymarket")
async def api_polymarket():
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get("https://gamma-api.polymarket.com/events?limit=10&active=true&tag=crypto",
                            timeout=aiohttp.ClientTimeout(total=10))
            events = await r.json()
            result = []
            for e in events[:8]:
                markets = e.get("markets", [])
                if markets:
                    yes = float(markets[0].get("outcomePrices", ["0.5"])[0])
                    result.append({"title": e.get("title",""), "yes_prob": round(yes*100,1),
                                   "volume": float(e.get("volume",0))})
            return {"events": result, "success": True}
    except Exception as e:
        return {"events": [], "success": False, "error": str(e)}

@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            prices = await get_prices()
            await websocket.send_json({"type": "prices", "data": prices,
                                       "timestamp": datetime.utcnow().isoformat()})
            await asyncio.sleep(15)
    except Exception:
        pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
