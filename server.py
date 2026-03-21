"""
QuantumTrade AI - FastAPI Backend v4.1
Fixed: calc_signal, Vision analysis, Polymarket, trading logic
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

app = FastAPI(title="QuantumTrade AI", version="4.1.0")
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
            r = await s.get(
                KUCOIN_BASE_URL + endpoint,
                headers=kucoin_headers("GET", endpoint),
                timeout=aiohttp.ClientTimeout(total=10)
            )
            data = await r.json()
            if data.get("code") == "200000":
                total_usdt = sum(
                    float(a.get("balance", 0))
                    for a in data["data"]
                    if a["currency"] == "USDT"
                )
                return {"total_usdt": round(total_usdt, 2), "accounts": data["data"], "success": True}
            return {"total_usdt": 0, "success": False, "error": data.get("msg")}
    except Exception as e:
        return {"total_usdt": 0, "success": False, "error": str(e)}


async def get_all_prices() -> dict:
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                f"{KUCOIN_BASE_URL}/api/v1/market/allTickers",
                timeout=aiohttp.ClientTimeout(total=10)
            )
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
            r = await s.get(
                f"{KUCOIN_BASE_URL}/api/v1/market/orderbook/level1?symbol={symbol}",
                timeout=aiohttp.ClientTimeout(total=5)
            )
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
                f"{KUCOIN_BASE_URL}/api/v1/market/candles"
                f"?type={interval}&symbol={symbol}&startAt={start}&endAt={end}",
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
            r = await s.post(
                KUCOIN_BASE_URL + endpoint,
                headers=kucoin_headers("POST", endpoint, body),
                data=body,
                timeout=aiohttp.ClientTimeout(total=10)
            )
            return await r.json()
    except Exception as e:
        return {"code": "error", "msg": str(e)}


# ── Chart Analysis (Technical Indicators) ────────────────────────────────────
async def analyze_chart_with_vision(symbol: str, candles: list) -> dict:
    """
    Full technical analysis on OHLCV candles.
    FIX v4.1:
      - Proper candle parsing (KuCoin format: [time, open, close, high, low, vol, turnover])
      - Real trend detection with EMA crossover logic
      - RSI calculation
      - Volume confirmation
      - Yandex Vision called only when image is available (skipped for text)
    """
    if not candles or len(candles) < 5:
        return {"pattern": "insufficient_data", "signal": "HOLD", "confidence": 0.5}

    try:
        # KuCoin candle format: [timestamp, open, close, high, low, volume, turnover]
        # candles are newest-first → reverse for chronological order
        candles_chron = list(reversed(candles))

        closes  = [float(c[2]) for c in candles_chron]
        highs   = [float(c[3]) for c in candles_chron]
        lows    = [float(c[4]) for c in candles_chron]
        volumes = [float(c[5]) for c in candles_chron]

        n = len(closes)
        current_price = closes[-1]
        open_price    = closes[0]

        # ── Price change ──────────────────────────────────────────────────────
        price_change = (current_price - open_price) / open_price * 100

        # ── Volatility (ATR-like) ─────────────────────────────────────────────
        ranges = [highs[i] - lows[i] for i in range(n)]
        avg_range = sum(ranges) / n
        volatility = avg_range / current_price * 100

        # ── EMA calculation ───────────────────────────────────────────────────
        def ema(data, period):
            if len(data) < period:
                return data[-1]
            k = 2 / (period + 1)
            val = sum(data[:period]) / period
            for price in data[period:]:
                val = price * k + val * (1 - k)
            return val

        ema_fast = ema(closes, min(7,  n))   # fast EMA
        ema_slow = ema(closes, min(14, n))   # slow EMA

        # ── RSI (14) ──────────────────────────────────────────────────────────
        def rsi(data, period=14):
            if len(data) < period + 1:
                return 50.0
            gains, losses = [], []
            for i in range(1, len(data)):
                diff = data[i] - data[i-1]
                gains.append(max(diff, 0))
                losses.append(max(-diff, 0))
            avg_gain = sum(gains[-period:]) / period
            avg_loss = sum(losses[-period:]) / period
            if avg_loss == 0:
                return 100.0
            rs = avg_gain / avg_loss
            return round(100 - 100 / (1 + rs), 1)

        rsi_val = rsi(closes)

        # ── Volume trend ──────────────────────────────────────────────────────
        avg_vol_recent = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else volumes[-1]
        avg_vol_old    = sum(volumes[-15:-5]) / 10 if len(volumes) >= 15 else avg_vol_recent
        vol_ratio      = avg_vol_recent / avg_vol_old if avg_vol_old > 0 else 1.0

        # ── Support / Resistance ──────────────────────────────────────────────
        recent_high = max(highs[-8:]) if len(highs) >= 8 else max(highs)
        recent_low  = min(lows[-8:])  if len(lows)  >= 8 else min(lows)
        price_in_range_pct = (current_price - recent_low) / (recent_high - recent_low) * 100 \
                             if recent_high != recent_low else 50

        # ── Pattern detection ─────────────────────────────────────────────────
        bullish_ema   = ema_fast > ema_slow * 1.001
        bearish_ema   = ema_fast < ema_slow * 0.999
        rsi_overbought = rsi_val > 70
        rsi_oversold   = rsi_val < 30
        vol_confirmed  = vol_ratio > 1.2   # volume surge confirms move
        strong_move    = abs(price_change) > 1.0

        if rsi_oversold and bullish_ema:
            pattern    = "oversold_reversal"
            signal     = "BUY"
            confidence = 0.82 + (0.05 if vol_confirmed else 0)
        elif rsi_overbought and bearish_ema:
            pattern    = "overbought_reversal"
            signal     = "SELL"
            confidence = 0.80 + (0.05 if vol_confirmed else 0)
        elif bullish_ema and strong_move and vol_confirmed:
            pattern    = "uptrend_breakout"
            signal     = "BUY"
            confidence = 0.78 + min(abs(price_change) * 0.02, 0.10)
        elif bearish_ema and strong_move and vol_confirmed:
            pattern    = "downtrend_breakdown"
            signal     = "SELL"
            confidence = 0.76 + min(abs(price_change) * 0.02, 0.10)
        elif bullish_ema and price_change > 0.5:
            pattern    = "uptrend"
            signal     = "BUY"
            confidence = 0.68 + (0.06 if vol_confirmed else 0)
        elif bearish_ema and price_change < -0.5:
            pattern    = "downtrend"
            signal     = "SELL"
            confidence = 0.68 + (0.06 if vol_confirmed else 0)
        elif volatility > 4:
            pattern    = "high_volatility"
            signal     = "HOLD"
            confidence = 0.5
        else:
            pattern    = "consolidation"
            signal     = "HOLD"
            confidence = 0.55

        confidence = round(min(confidence, 0.95), 2)

        return {
            "pattern":      pattern,
            "signal":       signal,
            "confidence":   confidence,
            "price_change": round(price_change, 2),
            "volatility":   round(volatility, 2),
            "rsi":          rsi_val,
            "ema_fast":     round(ema_fast, 4),
            "ema_slow":     round(ema_slow, 4),
            "ema_bullish":  bullish_ema,
            "vol_ratio":    round(vol_ratio, 2),
            "price_pos_pct": round(price_in_range_pct, 1),
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


# ── Signal Generator (FIXED v4.1) ─────────────────────────────────────────────
def calc_signal(price_change: float, vision: dict = None) -> dict:
    """
    FIX v4.1: Incorporate Vision technical analysis into Q-Score.
    
    Q-Score components:
      - Base 50 (neutral)
      - Price momentum: price_change * 5  (was *8, too sensitive to tiny moves)
      - RSI contribution: deviation from 50 → ±10 pts
      - EMA trend: ±8 pts
      - Volume confirmation: ±5 pts
      - Vision pattern bonus: ±7 pts
    """
    score = 50.0

    # 1. Price momentum (reduced sensitivity, more realistic)
    score += price_change * 5

    if vision and vision.get("pattern") != "error":
        # 2. RSI contribution
        rsi = vision.get("rsi", 50)
        score += (rsi - 50) * 0.2   # RSI 70 → +4, RSI 30 → -4

        # 3. EMA trend
        if vision.get("ema_bullish") is True:
            score += 8
        elif vision.get("ema_bullish") is False:
            score -= 8

        # 4. Volume confirmation
        vol_ratio = vision.get("vol_ratio", 1.0)
        if vol_ratio > 1.3:
            score += 5 if price_change > 0 else -5

        # 5. Vision pattern bonus
        pattern_scores = {
            "uptrend_breakout":    +7,
            "oversold_reversal":   +7,
            "uptrend":             +4,
            "consolidation":        0,
            "high_volatility":     -2,
            "downtrend":           -4,
            "downtrend_breakdown": -7,
            "overbought_reversal": -7,
        }
        score += pattern_scores.get(vision.get("pattern", "consolidation"), 0)

    score = max(0.0, min(100.0, score))

    # Determine action
    if score >= MIN_Q_SCORE:
        action     = "BUY"
        confidence = round(min(0.50 + (score - MIN_Q_SCORE) / 100, 0.95), 2)
    elif score <= (100 - MIN_Q_SCORE):   # ≤ 35
        action     = "SELL"
        confidence = round(min(0.50 + ((100 - MIN_Q_SCORE) - score) / 100, 0.95), 2)
    else:
        action     = "HOLD"
        confidence = round(0.40 + abs(score - 50) / 100, 2)

    # Use Vision confidence if it's a strong signal
    if vision and vision.get("signal") == action and action != "HOLD":
        confidence = round(max(confidence, vision.get("confidence", 0)), 2)

    return {
        "action":     action,
        "confidence": confidence,
        "q_score":    round(score, 1),
    }


# ── Auto-trading Engine ───────────────────────────────────────────────────────
async def auto_trade_cycle():
    global last_signals, last_q_score

    prices_data = await get_all_prices()
    if not prices_data.get("success"):
        return

    balance  = await get_balance()
    total_usdt      = balance.get("total_usdt", 0)
    trade_size_usdt = total_usdt * RISK_PER_TRADE
    signals_fired   = []

    for symbol, price_data in prices_data["prices"].items():
        change = price_data.get("change", 0)
        price  = price_data.get("price", 0)

        # Get chart data and technical analysis
        candles = await get_kucoin_chart(symbol)
        vision  = await analyze_chart_with_vision(symbol, candles)
        signal  = calc_signal(change, vision)

        # Skip if same signal within last hour
        last = last_signals.get(symbol, {})
        if last.get("action") == signal["action"] and (time.time() - last.get("ts", 0)) < 3600:
            continue

        if signal["action"] == "HOLD":
            continue

        if signal["confidence"] < MIN_CONFIDENCE:
            continue

        if not AUTOPILOT or trade_size_usdt < 1:
            continue

        if price > 0:
            size = round(trade_size_usdt / price, 6)
            if size < 0.000001:
                continue

            side   = "buy" if signal["action"] == "BUY" else "sell"
            result = await place_spot_order(symbol, side, size)

            if result.get("code") == "200000":
                last_signals[symbol] = {"action": signal["action"], "ts": time.time()}
                tp = price * 1.03 if side == "buy" else price * 0.97
                sl = price * 0.98 if side == "buy" else price * 1.02
                signals_fired.append({
                    "symbol":     symbol,
                    "action":     signal["action"],
                    "price":      price,
                    "confidence": signal["confidence"],
                    "q_score":    signal["q_score"],
                    "tp":         round(tp, 4),
                    "sl":         round(sl, 4),
                    "size":       size,
                    "pattern":    vision["pattern"],
                    "rsi":        vision.get("rsi", 50),
                })

    if signals_fired:
        msg = "⚛ *QuantumTrade AI — Автосделки*\n\n"
        for s in signals_fired:
            emoji = "🟢" if s["action"] == "BUY" else "🔴"
            msg += f"{emoji} *{s['symbol']}* {s['action']}\n"
            msg += f"   Цена: `${s['price']:,.4f}` · Q: `{s['q_score']}`\n"
            msg += f"   Паттерн: `{s['pattern']}` · RSI: `{s['rsi']}`\n"
            msg += f"   TP: `${s['tp']:,.4f}` · SL: `${s['sl']:,.4f}`\n\n"
        await notify(msg)

    # Q-Score notifications (BTC)
    btc_data = prices_data["prices"].get("BTC-USDT", {})
    if btc_data:
        candles_btc  = await get_kucoin_chart("BTC-USDT")
        vision_btc   = await analyze_chart_with_vision("BTC-USDT", candles_btc)
        btc_signal   = calc_signal(btc_data.get("change", 0), vision_btc)
        q    = btc_signal["q_score"]
        conf = btc_signal["confidence"]

        if q >= MIN_Q_SCORE and last_q_score < MIN_Q_SCORE:
            await notify(
                f"🚀 *Q-Score вырос до {q}!*\n\n"
                f"Сигнал: *{btc_signal['action']}* BTC-USDT\n"
                f"Цена: `${btc_data['price']:,.1f}`\n"
                f"Уверенность: `{int(conf*100)}%`\n"
                f"Паттерн: `{vision_btc.get('pattern', '?')}`\n"
                f"RSI: `{vision_btc.get('rsi', '?')}`\n\n"
                f"{'✅ Автопилот открывает сделку...' if conf >= MIN_CONFIDENCE else '⏳ Автопилот ждёт подтверждения...'}"
            )
        elif q <= 35 and last_q_score > 35:
            await notify(
                f"⚠️ *Q-Score упал до {q}!*\n\n"
                f"Рынок МЕДВЕЖИЙ — автопилот приостанавливает покупки.\n"
                f"BTC: `${btc_data['price']:,.1f}` ({btc_data['change']:+.2f}%)\n"
                f"Паттерн: `{vision_btc.get('pattern', '?')}`"
            )

        last_q_score = q


# ── Background task ───────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    asyncio.create_task(trading_loop())
    await notify(
        "⚛ *QuantumTrade AI v4.1 запущен!*\n\n"
        "✅ Автоторговля активна\n"
        "✅ Технический анализ (EMA + RSI + Volume)\n"
        "✅ Мультипарная стратегия\n"
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
        "status":         "ok",
        "version":        "4.1.0",
        "auto_trading":   AUTOPILOT,
        "last_qscore":    last_q_score,
        "min_confidence": MIN_CONFIDENCE,
        "min_q_score":    MIN_Q_SCORE,
        "yandex_vision":  bool(YANDEX_VISION_KEY),
        "timestamp":      datetime.utcnow().isoformat(),
    }


@app.get("/api/balance")
async def api_balance():
    return await get_balance()


@app.get("/api/prices")
async def api_prices():
    return await get_all_prices()


@app.get("/api/signal/{symbol}")
async def api_signal(symbol: str):
    price   = await get_ticker(symbol)
    prices  = await get_all_prices()
    change  = prices["prices"].get(symbol, {}).get("change", 0)
    candles = await get_kucoin_chart(symbol)
    vision  = await analyze_chart_with_vision(symbol, candles)
    signal  = calc_signal(change, vision)
    signal["symbol"] = symbol
    signal["price"]  = price
    signal["vision"] = vision
    return signal


@app.get("/api/dashboard")
async def api_dashboard():
    balance, prices = await asyncio.gather(get_balance(), get_all_prices())
    btc_change = prices["prices"].get("BTC-USDT", {}).get("change", 0)
    candles    = await get_kucoin_chart("BTC-USDT")
    vision     = await analyze_chart_with_vision("BTC-USDT", candles)
    signal     = calc_signal(btc_change, vision)
    return {
        "balance":   balance,
        "prices":    prices,
        "signal":    signal,
        "vision":    vision,
        "autopilot": AUTOPILOT,
        "config": {
            "risk":           RISK_PER_TRADE,
            "min_confidence": MIN_CONFIDENCE,
            "min_q_score":    MIN_Q_SCORE,
            "yandex_vision":  bool(YANDEX_VISION_KEY),
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/chart/{symbol}")
async def api_chart(symbol: str):
    candles = await get_kucoin_chart(symbol)
    vision  = await analyze_chart_with_vision(symbol, candles)
    return {
        "symbol":          symbol,
        "candles_count":   len(candles),
        "vision_analysis": vision,
        "timestamp":       datetime.utcnow().isoformat(),
    }


@app.get("/api/polymarket")
async def api_polymarket():
    """
    FIX v4.1: Polymarket gamma API returns outcomePrices as a JSON string,
    not a plain list. Must parse it properly.
    """
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                "https://gamma-api.polymarket.com/events?limit=10&active=true&tag=crypto",
                timeout=aiohttp.ClientTimeout(total=10)
            )
            events = await r.json()
            result = []
            for e in events[:8]:
                markets = e.get("markets", [])
                if not markets:
                    continue
                m = markets[0]
                # outcomePrices can be a JSON string "[\"0.72\",\"0.28\"]" or a list
                outcome_prices = m.get("outcomePrices", "[]")
                if isinstance(outcome_prices, str):
                    try:
                        outcome_prices = json.loads(outcome_prices)
                    except Exception:
                        outcome_prices = []
                if not outcome_prices:
                    continue
                yes_prob = float(outcome_prices[0])
                result.append({
                    "title":    e.get("title", ""),
                    "yes_prob": round(yes_prob * 100, 1),
                    "volume":   float(e.get("volume", 0)),
                })
            return {"events": result, "success": True}
    except Exception as e:
        return {"events": [], "success": False, "error": str(e)}


class ManualTrade(BaseModel):
    symbol:     str
    side:       str
    size:       float
    is_futures: bool = False
    leverage:   int  = 3


@app.post("/api/trade/manual")
async def manual_trade(req: ManualTrade):
    result  = await place_spot_order(req.symbol, req.side, req.size)
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
            prices     = await get_all_prices()
            btc_change = prices["prices"].get("BTC-USDT", {}).get("change", 0)
            candles    = await get_kucoin_chart("BTC-USDT")
            vision     = await analyze_chart_with_vision("BTC-USDT", candles)
            signal     = calc_signal(btc_change, vision)
            await websocket.send_json({
                "type":      "update",
                "prices":    prices,
                "signal":    signal,
                "vision":    vision,
                "timestamp": datetime.utcnow().isoformat(),
            })
            await asyncio.sleep(15)
    except:
        pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
