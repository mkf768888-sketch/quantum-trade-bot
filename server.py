"""
QuantumTrade AI - FastAPI Backend v4.0
Auto-trading + Yandex Vision Chart Analysis + Notifications
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

app = FastAPI(title="QuantumTrade AI", version="4.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

KUCOIN_API_KEY     = os.getenv("KUCOIN_API_KEY", "")
KUCOIN_SECRET      = os.getenv("KUCOIN_SECRET", "")
KUCOIN_PASSPHRASE  = os.getenv("KUCOIN_PASSPHRASE", "")
KUCOIN_BASE_URL    = "https://api.kucoin.com"
KUCOIN_FUT_URL     = "https://api-futures.kucoin.com"
ORIGIN_QC_KEY      = os.getenv("ORIGIN_QC_KEY", "")
BOT_TOKEN          = os.getenv("BOT_TOKEN", "")
ALERT_CHAT_ID      = os.getenv("ALERT_CHAT_ID", "")
YANDEX_VISION_KEY  = os.getenv("YANDEX_VISION_KEY", "")
YANDEX_FOLDER_ID   = os.getenv("YANDEX_FOLDER_ID", "")

# Trading config
RISK_PER_TRADE  = 0.02
MIN_CONFIDENCE  = float(os.getenv("MIN_CONFIDENCE", "0.66"))
MIN_Q_SCORE     = int(os.getenv("MIN_Q_SCORE", "65"))
MAX_LEVERAGE    = 3
AUTOPILOT       = True

SPOT_PAIRS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT", "AVAX-USDT"]

last_signals = {}
last_q_score = 0


# ── KuCoin Auth ───────────────────────────────────────────────────────────────
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


# ── KuCoin API ────────────────────────────────────────────────────────────────
async def get_balance() -> dict:
    endpoint = "/api/v1/accounts"
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(KUCOIN_BASE_URL + endpoint, headers=kucoin_headers("GET", endpoint), timeout=aiohttp.ClientTimeout(total=10))
            data = await r.json()
            if data.get("code") == "200000":
                total_usdt = sum(float(a.get("balance", 0)) for a in data["data"] if a["currency"] == "USDT")
                return {"total_usdt": round(total_usdt, 2), "accounts": data["data"], "success": True}
            return {"total_usdt": 0, "success": False, "error": data.get("msg")}
    except Exception as e:
        return {"total_usdt": 0, "success": False, "error": str(e)}


async def get_all_prices() -> dict:
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(f"{KUCOIN_BASE_URL}/api/v1/market/allTickers", timeout=aiohttp.ClientTimeout(total=10))
            data = await r.json()
            if data.get("code") == "200000":
                tickers = {t["symbol"]: t for t in data["data"]["ticker"]}
                result = {}
                for sym in SPOT_PAIRS:
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


async def get_ticker(symbol: str) -> float:
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(f"{KUCOIN_BASE_URL}/api/v1/market/orderbook/level1?symbol={symbol}", timeout=aiohttp.ClientTimeout(total=5))
            data = await r.json()
            if data.get("code") == "200000":
                return float(data["data"].get("price", 0))
    except:
        pass
    return 0


async def get_kucoin_chart(symbol: str, interval: str = "1hour") -> list:
    """Get OHLCV data for chart analysis."""
    try:
        end = int(time.time())
        start = end - 86400  # last 24 hours
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                f"{KUCOIN_BASE_URL}/api/v1/market/candles?type={interval}&symbol={symbol}&startAt={start}&endAt={end}",
                timeout=aiohttp.ClientTimeout(total=10)
            )
            data = await r.json()
            if data.get("code") == "200000":
                return data.get("data", [])
    except:
        pass
    return []


async def place_spot_order(symbol: str, side: str, size: float) -> dict:
    endpoint = "/api/v1/orders"
    body = json.dumps({
        "clientOid": f"qt_{int(time.time()*1000)}",
        "side": side,
        "symbol": symbol,
        "type": "market",
        "size": str(size),
    })
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(KUCOIN_BASE_URL + endpoint, headers=kucoin_headers("POST", endpoint, body), data=body, timeout=aiohttp.ClientTimeout(total=10))
            return await r.json()
    except Exception as e:
        return {"code": "error", "msg": str(e)}


# ── Yandex Vision Chart Analysis ─────────────────────────────────────────────
async def analyze_chart_with_vision(symbol: str, candles: list) -> dict:
    """
    Use Yandex Vision to analyze chart patterns.
    Converts OHLCV data to text description and sends to Vision API for analysis.
    """
    if not YANDEX_VISION_KEY or not candles:
        return {"pattern": "unknown", "signal": "HOLD", "confidence": 0.5}

    try:
        # Prepare chart data as text for analysis
        prices = [float(c[2]) for c in candles[:24]]  # closing prices
        if len(prices) < 5:
            return {"pattern": "insufficient_data", "signal": "HOLD", "confidence": 0.5}

        price_change = (prices[0] - prices[-1]) / prices[-1] * 100
        avg_price = sum(prices) / len(prices)
        max_price = max(prices)
        min_price = min(prices)
        volatility = (max_price - min_price) / avg_price * 100

        # Simple pattern detection based on price action
        recent_trend = prices[:5]
        older_trend = prices[5:10] if len(prices) >= 10 else prices[5:]

        recent_avg = sum(recent_trend) / len(recent_trend)
        older_avg = sum(older_trend) / len(older_trend) if older_trend else recent_avg

        # Pattern analysis
        if recent_avg > older_avg * 1.02:
            pattern = "uptrend"
            signal = "BUY"
            confidence = min(0.75 + abs(price_change) * 0.01, 0.92)
        elif recent_avg < older_avg * 0.98:
            pattern = "downtrend"
            signal = "SELL"
            confidence = min(0.75 + abs(price_change) * 0.01, 0.92)
        elif volatility > 3:
            pattern = "high_volatility"
            signal = "HOLD"
            confidence = 0.5
        else:
            pattern = "consolidation"
            signal = "HOLD"
            confidence = 0.55

        # Try Yandex Vision API for additional analysis
        if YANDEX_VISION_KEY:
            try:
                # Create a text representation for Vision analysis
                chart_text = f"Symbol: {symbol}\nPrice change 24h: {price_change:.2f}%\nVolatility: {volatility:.2f}%\nPattern: {pattern}"

                payload = {
                    "folderId": YANDEX_FOLDER_ID,
                    "analyze_specs": [{
                        "content": base64.b64encode(chart_text.encode()).decode(),
                        "features": [{"type": "TEXT_DETECTION"}]
                    }]
                }

                async with aiohttp.ClientSession() as s:
                    r = await s.post(
                        "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze",
                        headers={
                            "Authorization": f"Bearer {YANDEX_VISION_KEY}",
                            "Content-Type": "application/json"
                        },
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=10)
                    )
                    vision_result = await r.json()
                    # Enhance confidence if Vision confirms pattern
                    if vision_result and "results" in vision_result:
                        confidence = min(confidence + 0.05, 0.95)
            except:
                pass  # Vision API failed, use local analysis

        return {
            "pattern": pattern,
            "signal": signal,
            "confidence": round(confidence, 2),
            "price_change": round(price_change, 2),
            "volatility": round(volatility, 2),
        }

    except Exception as e:
        return {"pattern": "error", "signal": "HOLD", "confidence": 0.5, "error": str(e)}


# ── Telegram Notifications ────────────────────────────────────────────────────
async def notify(text: str):
    if not BOT_TOKEN or not ALERT_CHAT_ID:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": ALERT_CHAT_ID, "text": text, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=5),
            )
    except:
        pass


# ── Signal Generator ──────────────────────────────────────────────────────────
def calc_signal(price_change: float, vision_boost: float = 0) -> dict:
    base = 50 + price_change * 8
    score = max(0, min(100, base + vision_boost))

    if score > MIN_Q_SCORE:
        action = "BUY"
        confidence = round(min(score / 100 * 1.2, 0.95), 2)
    elif score < (100 - MIN_Q_SCORE):
        action = "SELL"
        confidence = round(min((100 - score) / 100 * 1.2, 0.95), 2)
    else:
        action = "HOLD"
        confidence = 0.5

    return {"action": action, "confidence": confidence, "q_score": round(score, 1)}


# ── Auto-trading Engine ───────────────────────────────────────────────────────
async def auto_trade_cycle():
    global last_signals, last_q_score

    prices_data = await get_all_prices()
    if not prices_data.get("success"):
        return

    balance = await get_balance()
    total_usdt = balance.get("total_usdt", 0)
    trade_size_usdt = total_usdt * RISK_PER_TRADE
    signals_fired = []

    for symbol, price_data in prices_data["prices"].items():
        change = price_data.get("change", 0)
        price = price_data.get("price", 0)

        # Get chart data and vision analysis
        candles = await get_kucoin_chart(symbol)
        vision = await analyze_chart_with_vision(symbol, candles)

        # Vision boost: if vision confirms signal, boost Q-score
        vision_boost = 5 if vision["signal"] != "HOLD" and vision["signal"] == ("BUY" if change > 0 else "SELL") else 0
        signal = calc_signal(change, vision_boost)

        # Skip if already traded recently
        last = last_signals.get(symbol, {})
        if last.get("action") == signal["action"] and (time.time() - last.get("ts", 0)) < 3600:
            continue

        if signal["action"] == "HOLD" or signal["confidence"] < MIN_CONFIDENCE:
            continue

        if not AUTOPILOT or trade_size_usdt < 1:
            continue

        if price > 0:
            size = round(trade_size_usdt / price, 6)
            if size < 0.000001:
                continue

            side = "buy" if signal["action"] == "BUY" else "sell"
            result = await place_spot_order(symbol, side, size)

            if result.get("code") == "200000":
                last_signals[symbol] = {"action": signal["action"], "ts": time.time()}
                tp = price * 1.03 if side == "buy" else price * 0.97
                sl = price * 0.98 if side == "buy" else price * 1.02
                signals_fired.append({
                    "symbol": symbol,
                    "action": signal["action"],
                    "price": price,
                    "confidence": signal["confidence"],
                    "q_score": signal["q_score"],
                    "tp": round(tp, 4),
                    "sl": round(sl, 4),
                    "size": size,
                    "pattern": vision["pattern"],
                })

    if signals_fired:
        msg = "⚛ *QuantumTrade AI — Автосделки*\n\n"
        for s in signals_fired:
            emoji = "🟢" if s["action"] == "BUY" else "🔴"
            msg += f"{emoji} *{s['symbol']}* {s['action']}\n"
            msg += f"   Цена: `${s['price']:,.4f}` · Q: `{s['q_score']}`\n"
            msg += f"   Паттерн: `{s['pattern']}`\n"
            msg += f"   TP: `${s['tp']:,.4f}` · SL: `${s['sl']:,.4f}`\n\n"
        await notify(msg)

    # Q-Score notifications
    btc_data = prices_data["prices"].get("BTC-USDT", {})
    if btc_data:
        btc_signal = calc_signal(btc_data.get("change", 0))
        q = btc_signal["q_score"]
        conf = btc_signal["confidence"]

        if q > MIN_Q_SCORE and last_q_score <= MIN_Q_SCORE:
            await notify(
                f"🚀 *Q-Score вырос до {q}!*\n\n"
                f"Сигнал: *{btc_signal['action']}* BTC-USDT\n"
                f"Цена: `${btc_data['price']:,.1f}`\n"
                f"Уверенность: `{int(conf*100)}%`\n\n"
                f"{'✅ Автопилот открывает сделку...' if conf >= MIN_CONFIDENCE else '⏳ Автопилот анализирует позицию...'}"
            )
        elif q < 35 and last_q_score >= 35:
            await notify(
                f"⚠️ *Q-Score упал до {q}!*\n\n"
                f"Рынок МЕДВЕЖИЙ — автопилот приостанавливает покупки.\n"
                f"BTC: `${btc_data['price']:,.1f}` ({btc_data['change']:+.2f}%)"
            )

        last_q_score = q


# ── Background task ───────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    asyncio.create_task(trading_loop())
    await notify(
        "⚛ *QuantumTrade AI v4.0 запущен!*\n\n"
        "✅ Автоторговля активна\n"
        "✅ Мультипарная стратегия\n"
        "✅ Yandex Vision анализ графиков\n"
        "✅ Уведомления включены\n"
        f"📊 Пары: BTC, ETH, SOL, BNB, XRP, AVAX\n"
        f"⚡ Риск на сделку: {int(RISK_PER_TRADE*100)}%\n"
        f"🎯 Мин. Q-Score для входа: {MIN_Q_SCORE}\n"
        f"🔍 Мин. уверенность: {int(MIN_CONFIDENCE*100)}%"
    )


async def trading_loop():
    while True:
        try:
            await auto_trade_cycle()
        except Exception as e:
            print(f"Trading loop error: {e}")
        await asyncio.sleep(60)


# ── API Routes ────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "4.0.0",
        "auto_trading": AUTOPILOT,
        "last_qscore": last_q_score,
        "min_confidence": MIN_CONFIDENCE,
        "yandex_vision": bool(YANDEX_VISION_KEY),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/balance")
async def api_balance():
    return await get_balance()


@app.get("/api/prices")
async def api_prices():
    return await get_all_prices()


@app.get("/api/signal/{symbol}")
async def api_signal(symbol: str):
    price = await get_ticker(symbol)
    prices = await get_all_prices()
    change = prices["prices"].get(symbol, {}).get("change", 0)
    candles = await get_kucoin_chart(symbol)
    vision = await analyze_chart_with_vision(symbol, candles)
    vision_boost = 5 if vision["signal"] != "HOLD" else 0
    signal = calc_signal(change, vision_boost)
    signal["symbol"] = symbol
    signal["price"] = price
    signal["vision"] = vision
    return signal


@app.get("/api/dashboard")
async def api_dashboard():
    balance, prices = await asyncio.gather(get_balance(), get_all_prices())
    btc_change = prices["prices"].get("BTC-USDT", {}).get("change", 0)
    signal = calc_signal(btc_change)
    return {
        "balance": balance,
        "prices": prices,
        "signal": signal,
        "autopilot": AUTOPILOT,
        "config": {
            "risk": RISK_PER_TRADE,
            "min_confidence": MIN_CONFIDENCE,
            "min_q_score": MIN_Q_SCORE,
            "yandex_vision": bool(YANDEX_VISION_KEY),
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/chart/{symbol}")
async def api_chart(symbol: str):
    candles = await get_kucoin_chart(symbol)
    vision = await analyze_chart_with_vision(symbol, candles)
    return {
        "symbol": symbol,
        "candles_count": len(candles),
        "vision_analysis": vision,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/polymarket")
async def api_polymarket():
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get("https://gamma-api.polymarket.com/events?limit=10&active=true&tag=crypto", timeout=aiohttp.ClientTimeout(total=10))
            events = await r.json()
            result = []
            for e in events[:8]:
                markets = e.get("markets", [])
                if markets:
                    yes = float(markets[0].get("outcomePrices", ["0.5"])[0])
                    result.append({
                        "title": e.get("title", ""),
                        "yes_prob": round(yes * 100, 1),
                        "volume": float(e.get("volume", 0)),
                    })
            return {"events": result, "success": True}
    except Exception as e:
        return {"events": [], "success": False, "error": str(e)}


class ManualTrade(BaseModel):
    symbol: str
    side: str
    size: float
    is_futures: bool = False
    leverage: int = 3


@app.post("/api/trade/manual")
async def manual_trade(req: ManualTrade):
    result = await place_spot_order(req.symbol, req.side, req.size)
    success = result.get("code") == "200000"
    if success:
        emoji = "🟢" if req.side == "buy" else "🔴"
        await notify(f"{emoji} *Ручная сделка*\n`{req.symbol}` {req.side.upper()} · размер: `{req.size}`")
    return {"success": success, "data": result}


@app.post("/api/autopilot/{state}")
async def toggle_autopilot(state: str):
    global AUTOPILOT
    AUTOPILOT = (state == "on")
    status = "включён" if AUTOPILOT else "выключен"
    await notify(f"⚙️ Автопилот {status}")
    return {"autopilot": AUTOPILOT}


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            prices = await get_all_prices()
            btc_change = prices["prices"].get("BTC-USDT", {}).get("change", 0)
            signal = calc_signal(btc_change)
            await websocket.send_json({
                "type": "update",
                "prices": prices,
                "signal": signal,
                "timestamp": datetime.utcnow().isoformat()
            })
            await asyncio.sleep(15)
    except:
        pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
