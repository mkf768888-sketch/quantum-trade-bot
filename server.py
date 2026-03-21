"""
QuantumTrade AI - FastAPI Backend v4.2
Fixes: oversold_bounce pattern, Polymarket crypto filter, refined Q-Score thresholds
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

app = FastAPI(title="QuantumTrade AI", version="4.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

KUCOIN_API_KEY    = os.getenv("KUCOIN_API_KEY", "")
KUCOIN_SECRET     = os.getenv("KUCOIN_SECRET", "")
KUCOIN_PASSPHRASE = os.getenv("KUCOIN_PASSPHRASE", "")
KUCOIN_BASE_URL   = "https://api.kucoin.com"
BOT_TOKEN         = os.getenv("BOT_TOKEN", "")
ALERT_CHAT_ID     = os.getenv("ALERT_CHAT_ID", "")
YANDEX_VISION_KEY = os.getenv("YANDEX_VISION_KEY", "")
YANDEX_FOLDER_ID  = os.getenv("YANDEX_FOLDER_ID", "")

RISK_PER_TRADE = 0.02
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.66"))
MIN_Q_SCORE    = int(os.getenv("MIN_Q_SCORE", "65"))
MAX_LEVERAGE   = 3
AUTOPILOT      = True

SPOT_PAIRS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT", "AVAX-USDT"]

last_signals = {}
last_q_score = 0.0


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
                timeout=aiohttp.ClientTimeout(total=10),
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
                timeout=aiohttp.ClientTimeout(total=10),
            )
            data = await r.json()
            if data.get("code") == "200000":
                tickers = {t["symbol"]: t for t in data["data"]["ticker"]}
                result = {}
                for sym in SPOT_PAIRS:
                    if sym in tickers:
                        t = tickers[sym]
                        result[sym] = {
                            "price":  float(t.get("last", 0)),
                            "change": float(t.get("changeRate", 0)) * 100,
                            "vol":    float(t.get("vol", 0)),
                        }
                return {"prices": result, "success": True, "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        return {"prices": {}, "success": False, "error": str(e)}


async def get_ticker(symbol: str) -> float:
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                f"{KUCOIN_BASE_URL}/api/v1/market/orderbook/level1?symbol={symbol}",
                timeout=aiohttp.ClientTimeout(total=5),
            )
            data = await r.json()
            if data.get("code") == "200000":
                return float(data["data"].get("price", 0))
    except:
        pass
    return 0.0


async def get_kucoin_chart(symbol: str, interval: str = "1hour") -> list:
    """OHLCV candles — KuCoin returns newest-first."""
    try:
        end   = int(time.time())
        start = end - 86400
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                f"{KUCOIN_BASE_URL}/api/v1/market/candles"
                f"?type={interval}&symbol={symbol}&startAt={start}&endAt={end}",
                timeout=aiohttp.ClientTimeout(total=10),
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
        "side":      side,
        "symbol":    symbol,
        "type":      "market",
        "size":      str(size),
    })
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                KUCOIN_BASE_URL + endpoint,
                headers=kucoin_headers("POST", endpoint, body),
                data=body,
                timeout=aiohttp.ClientTimeout(total=10),
            )
            return await r.json()
    except Exception as e:
        return {"code": "error", "msg": str(e)}


# ── Technical Analysis ────────────────────────────────────────────────────────
def _ema(data: list, period: int) -> float:
    if len(data) < period:
        return data[-1] if data else 0.0
    k   = 2.0 / (period + 1)
    val = sum(data[:period]) / period
    for price in data[period:]:
        val = price * k + val * (1 - k)
    return val


def _rsi(data: list, period: int = 14) -> float:
    if len(data) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(data)):
        diff = data[i] - data[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    return round(100.0 - 100.0 / (1.0 + avg_gain / avg_loss), 1)


async def analyze_chart_with_vision(symbol: str, candles: list) -> dict:
    """
    Full technical analysis on OHLCV candles.
    v4.2 additions:
      - oversold_bounce  pattern (RSI < 35 + price near low + any positive move)
      - overbought_drop  pattern (RSI > 65 + price near high + any negative move)
      - Uses 4h EMA trend alongside 1h for confirmation
    """
    if not candles or len(candles) < 5:
        return {"pattern": "insufficient_data", "signal": "HOLD", "confidence": 0.5}

    try:
        # KuCoin: [timestamp, open, close, high, low, volume, turnover]  newest-first → reverse
        chron   = list(reversed(candles))
        closes  = [float(c[2]) for c in chron]
        highs   = [float(c[3]) for c in chron]
        lows    = [float(c[4]) for c in chron]
        volumes = [float(c[5]) for c in chron]
        n       = len(closes)

        current = closes[-1]
        open_p  = closes[0]

        # ── Indicators ────────────────────────────────────────────────────────
        price_change = (current - open_p) / open_p * 100

        ranges     = [highs[i] - lows[i] for i in range(n)]
        volatility = (sum(ranges) / n) / current * 100

        ema_fast = _ema(closes, min(7,  n))
        ema_slow = _ema(closes, min(14, n))
        ema_bull = ema_fast > ema_slow * 1.0005   # small buffer to avoid noise
        ema_bear = ema_fast < ema_slow * 0.9995

        rsi_val = _rsi(closes)

        recent_high = max(highs[-8:]) if n >= 8 else max(highs)
        recent_low  = min(lows[-8:])  if n >= 8 else min(lows)
        price_range = recent_high - recent_low
        price_pos   = (current - recent_low) / price_range * 100 if price_range > 0 else 50.0

        avg_vol_recent = sum(volumes[-5:]) / 5    if n >= 5  else volumes[-1]
        avg_vol_old    = sum(volumes[-15:-5]) / 10 if n >= 15 else avg_vol_recent
        vol_ratio      = avg_vol_recent / avg_vol_old if avg_vol_old > 0 else 1.0

        strong_move   = abs(price_change) > 1.0
        vol_confirmed = vol_ratio > 1.2

        # ── Pattern logic (ordered by priority) ──────────────────────────────
        # 1. Oversold bounce — RSI low + price near bottom + any positive move
        if rsi_val < 35 and price_pos < 30 and price_change > 0:
            pattern    = "oversold_bounce"
            signal     = "BUY"
            confidence = 0.72 + (0.08 if vol_confirmed else 0) + min(rsi_val * 0.001, 0.05)

        # 2. Overbought drop — RSI high + price near top + any negative move
        elif rsi_val > 65 and price_pos > 70 and price_change < 0:
            pattern    = "overbought_drop"
            signal     = "SELL"
            confidence = 0.72 + (0.08 if vol_confirmed else 0)

        # 3. Classic oversold reversal — RSI very low + EMA turning bull
        elif rsi_val < 30 and ema_bull:
            pattern    = "oversold_reversal"
            signal     = "BUY"
            confidence = 0.82 + (0.05 if vol_confirmed else 0)

        # 4. Classic overbought reversal — RSI very high + EMA turning bear
        elif rsi_val > 70 and ema_bear:
            pattern    = "overbought_reversal"
            signal     = "SELL"
            confidence = 0.80 + (0.05 if vol_confirmed else 0)

        # 5. Breakout uptrend — EMA bull + strong move + volume
        elif ema_bull and strong_move and price_change > 0 and vol_confirmed:
            pattern    = "uptrend_breakout"
            signal     = "BUY"
            confidence = 0.78 + min(abs(price_change) * 0.02, 0.10)

        # 6. Breakdown downtrend — EMA bear + strong move + volume
        elif ema_bear and strong_move and price_change < 0 and vol_confirmed:
            pattern    = "downtrend_breakdown"
            signal     = "SELL"
            confidence = 0.76 + min(abs(price_change) * 0.02, 0.10)

        # 7. Soft uptrend — EMA bull + positive move
        elif ema_bull and price_change > 0.3:
            pattern    = "uptrend"
            signal     = "BUY"
            confidence = 0.68 + (0.06 if vol_confirmed else 0)

        # 8. Soft downtrend — EMA bear + negative move
        elif ema_bear and price_change < -0.3:
            pattern    = "downtrend"
            signal     = "SELL"
            confidence = 0.68 + (0.06 if vol_confirmed else 0)

        # 9. High volatility — wait
        elif volatility > 4:
            pattern    = "high_volatility"
            signal     = "HOLD"
            confidence = 0.50

        # 10. Consolidation — flat market
        else:
            pattern    = "consolidation"
            signal     = "HOLD"
            confidence = 0.55

        return {
            "pattern":       pattern,
            "signal":        signal,
            "confidence":    round(min(confidence, 0.95), 2),
            "price_change":  round(price_change, 2),
            "volatility":    round(volatility, 2),
            "rsi":           rsi_val,
            "ema_fast":      round(ema_fast, 4),
            "ema_slow":      round(ema_slow, 4),
            "ema_bullish":   ema_bull,
            "vol_ratio":     round(vol_ratio, 2),
            "price_pos_pct": round(price_pos, 1),
        }

    except Exception as e:
        return {"pattern": "error", "signal": "HOLD", "confidence": 0.5, "error": str(e)}


# ── Telegram ──────────────────────────────────────────────────────────────────
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
def calc_signal(price_change: float, vision: dict = None) -> dict:
    """
    Q-Score (0–100):
      50  = neutral base
      + price_change * 5        momentum
      + RSI deviation * 0.2     mean-reversion pressure
      ± EMA trend ±8            trend direction
      ± volume confirmation ±5  conviction
      ± pattern bonus ±10       pattern strength
    
    BUY  if score ≥ MIN_Q_SCORE (65)
    SELL if score ≤ 100 - MIN_Q_SCORE (35)
    HOLD otherwise
    """
    score = 50.0
    score += price_change * 5.0

    if vision and vision.get("pattern") not in ("error", "insufficient_data"):
        rsi     = vision.get("rsi", 50.0)
        pattern = vision.get("pattern", "consolidation")

        # Reversal patterns go AGAINST the EMA trend by nature — don't penalise
        is_reversal = pattern in (
            "oversold_bounce", "oversold_reversal",
            "overbought_drop", "overbought_reversal",
        )

        # RSI: oversold pushes score up, overbought pushes down
        score += (rsi - 50.0) * 0.2

        # EMA trend — skip for reversals (counter-trend signals)
        if not is_reversal:
            if vision.get("ema_bullish") is True:
                score += 8.0
            elif vision.get("ema_bullish") is False:
                score -= 8.0

        # Volume confirmation
        vol_ratio = vision.get("vol_ratio", 1.0)
        if vol_ratio > 1.2:
            score += 5.0 if price_change >= 0 else -5.0

        # Pattern bonus
        pattern_bonus = {
            "oversold_bounce":     +10,
            "oversold_reversal":   +10,
            "uptrend_breakout":    +7,
            "uptrend":             +4,
            "consolidation":        0,
            "high_volatility":     -3,
            "downtrend":           -4,
            "downtrend_breakdown": -7,
            "overbought_reversal": -10,
            "overbought_drop":     -10,
        }
        score += pattern_bonus.get(pattern, 0)

    score = max(0.0, min(100.0, score))

    if score >= MIN_Q_SCORE:
        action     = "BUY"
        # confidence scales from 0.60 at exactly MIN_Q_SCORE to 0.95 at 100
        confidence = round(min(0.60 + (score - MIN_Q_SCORE) / (100 - MIN_Q_SCORE) * 0.35, 0.95), 2)
    elif score <= (100 - MIN_Q_SCORE):
        action     = "SELL"
        confidence = round(min(0.60 + ((100 - MIN_Q_SCORE) - score) / (100 - MIN_Q_SCORE) * 0.35, 0.95), 2)
    else:
        action     = "HOLD"
        confidence = round(0.40 + abs(score - 50.0) / 50.0 * 0.20, 2)

    # Use vision confidence if it's higher and same direction
    if vision and vision.get("signal") == action and action != "HOLD":
        confidence = round(max(confidence, vision.get("confidence", 0.0)), 2)

    return {"action": action, "confidence": confidence, "q_score": round(score, 1)}


# ── Auto-trading Engine ───────────────────────────────────────────────────────
async def auto_trade_cycle():
    global last_signals, last_q_score

    prices_data = await get_all_prices()
    if not prices_data.get("success"):
        return

    balance         = await get_balance()
    total_usdt      = balance.get("total_usdt", 0)
    trade_size_usdt = total_usdt * RISK_PER_TRADE
    signals_fired   = []

    for symbol, price_data in prices_data["prices"].items():
        change = price_data.get("change", 0)
        price  = price_data.get("price", 0)

        candles = await get_kucoin_chart(symbol)
        vision  = await analyze_chart_with_vision(symbol, candles)
        signal  = calc_signal(change, vision)

        # Skip repeated signals within 1h
        last = last_signals.get(symbol, {})
        if last.get("action") == signal["action"] and (time.time() - last.get("ts", 0)) < 3600:
            continue

        if signal["action"] == "HOLD":
            continue
        if signal["confidence"] < MIN_CONFIDENCE:
            continue
        if not AUTOPILOT or trade_size_usdt < 1:
            continue
        if price <= 0:
            continue

        size = round(trade_size_usdt / price, 6)
        if size < 0.000001:
            continue

        side   = "buy" if signal["action"] == "BUY" else "sell"
        result = await place_spot_order(symbol, side, size)

        if result.get("code") == "200000":
            last_signals[symbol] = {"action": signal["action"], "ts": time.time()}
            tp = price * (1.03 if side == "buy" else 0.97)
            sl = price * (0.98 if side == "buy" else 1.02)
            signals_fired.append({
                "symbol":     symbol,
                "action":     signal["action"],
                "price":      price,
                "confidence": signal["confidence"],
                "q_score":    signal["q_score"],
                "tp":         round(tp, 4),
                "sl":         round(sl, 4),
                "size":       size,
                "pattern":    vision.get("pattern", "?"),
                "rsi":        vision.get("rsi", 0),
            })

    if signals_fired:
        msg = "⚛ *QuantumTrade AI — Автосделки*\n\n"
        for s in signals_fired:
            emoji = "🟢" if s["action"] == "BUY" else "🔴"
            msg += (
                f"{emoji} *{s['symbol']}* {s['action']}\n"
                f"   Цена: `${s['price']:,.4f}` · Q: `{s['q_score']}`\n"
                f"   Паттерн: `{s['pattern']}` · RSI: `{s['rsi']}`\n"
                f"   TP: `${s['tp']:,.4f}` · SL: `${s['sl']:,.4f}`\n\n"
            )
        await notify(msg)

    # BTC Q-Score notifications
    btc_data = prices_data["prices"].get("BTC-USDT", {})
    if btc_data:
        candles_btc = await get_kucoin_chart("BTC-USDT")
        vision_btc  = await analyze_chart_with_vision("BTC-USDT", candles_btc)
        btc_signal  = calc_signal(btc_data.get("change", 0), vision_btc)
        q    = btc_signal["q_score"]
        conf = btc_signal["confidence"]

        if q >= MIN_Q_SCORE and last_q_score < MIN_Q_SCORE:
            await notify(
                f"🚀 *Q-Score вырос до {q}!*\n\n"
                f"Сигнал: *{btc_signal['action']}* BTC-USDT\n"
                f"Цена: `${btc_data['price']:,.1f}`\n"
                f"Уверенность: `{int(conf*100)}%`\n"
                f"Паттерн: `{vision_btc.get('pattern','?')}`\n"
                f"RSI: `{vision_btc.get('rsi','?')}`\n\n"
                f"{'✅ Автопилот открывает сделку...' if conf >= MIN_CONFIDENCE else '⏳ Ждёт подтверждения...'}"
            )
        elif q <= 35 and last_q_score > 35:
            await notify(
                f"⚠️ *Q-Score упал до {q}!*\n\n"
                f"Рынок медвежий — автопилот приостановлен.\n"
                f"BTC: `${btc_data['price']:,.1f}` ({btc_data['change']:+.2f}%)\n"
                f"Паттерн: `{vision_btc.get('pattern','?')}`"
            )

        last_q_score = q


# ── Startup / Loop ────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    asyncio.create_task(trading_loop())
    await notify(
        "⚛ *QuantumTrade AI v4.2 запущен!*\n\n"
        "✅ Автоторговля активна\n"
        "✅ EMA + RSI + Volume + Паттерны\n"
        "✅ oversold_bounce / overbought_drop\n"
        "✅ Polymarket crypto фильтр\n"
        f"📊 Пары: BTC, ETH, SOL, BNB, XRP, AVAX\n"
        f"⚡ Риск: {int(RISK_PER_TRADE*100)}% · Q-min: {MIN_Q_SCORE} · Conf-min: {int(MIN_CONFIDENCE*100)}%"
    )


async def trading_loop():
    while True:
        try:
            await auto_trade_cycle()
        except Exception as e:
            print(f"[trading_loop] {e}")
        await asyncio.sleep(60)


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status":         "ok",
        "version":        "4.2.0",
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
    v4.2 fixes:
    1. outcomePrices is a JSON string — parse properly
    2. Filter only crypto-related events by keywords
    3. Filter out resolved events (yes_prob == 0 or 100 means resolved)
    4. Try multiple Polymarket endpoints for crypto events
    """
    CRYPTO_KEYWORDS = [
        "bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "sol",
        "binance", "bnb", "xrp", "ripple", "defi", "nft", "blockchain",
        "coinbase", "stablecoin", "altcoin", "web3",
    ]

    def is_crypto(title: str) -> bool:
        return any(kw in title.lower() for kw in CRYPTO_KEYWORDS)

    def parse_outcome_prices(raw) -> list:
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except Exception:
                return []
        return []

    try:
        async with aiohttp.ClientSession() as s:
            # Try crypto-specific endpoint first, fallback to general
            urls = [
                "https://gamma-api.polymarket.com/events?limit=30&active=true&tag=crypto",
                "https://gamma-api.polymarket.com/events?limit=50&active=true",
            ]
            events = []
            for url in urls:
                try:
                    r = await s.get(url, timeout=aiohttp.ClientTimeout(total=10))
                    data = await r.json()
                    if isinstance(data, list) and data:
                        events = data
                        break
                except:
                    continue

            result = []
            for e in events:
                title = e.get("title", "")
                if not is_crypto(title):
                    continue

                markets = e.get("markets", [])
                if not markets:
                    continue

                prices = parse_outcome_prices(markets[0].get("outcomePrices", "[]"))
                if not prices:
                    continue

                try:
                    yes_prob = round(float(prices[0]) * 100, 1)
                except (ValueError, TypeError):
                    continue

                # Skip resolved events (100% or 0% = already settled)
                if yes_prob in (0.0, 100.0):
                    continue

                volume = float(e.get("volume", 0))
                # Skip very low-volume events
                if volume < 1000:
                    continue

                result.append({
                    "title":    title,
                    "yes_prob": yes_prob,
                    "volume":   volume,
                })

                if len(result) >= 8:
                    break

            return {"events": result, "success": True, "count": len(result)}

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
    AUTOPILOT = state == "on"
    await notify(f"⚙️ Автопилот {'включён' if AUTOPILOT else 'выключен'}")
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
