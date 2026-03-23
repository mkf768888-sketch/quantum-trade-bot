"""
QuantumTrade AI - FastAPI Backend v5.2
Phase1: Fear&Greed, Polymarket→Q-Score, Whale, TP/SL stop-orders, Position Monitor, Strategy A/B/C
"""

import asyncio
import hashlib
import hmac
import time
import base64
import json
import os
from datetime import datetime
from typing import Optional, List
import aiohttp
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="QuantumTrade AI", version="5.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

KUCOIN_API_KEY    = os.getenv("KUCOIN_API_KEY", "")
KUCOIN_SECRET     = os.getenv("KUCOIN_SECRET", "")
KUCOIN_PASSPHRASE = os.getenv("KUCOIN_PASSPHRASE", "")
KUCOIN_BASE_URL   = "https://api.kucoin.com"
KUCOIN_FUT_URL    = "https://api-futures.kucoin.com"
BOT_TOKEN         = os.getenv("BOT_TOKEN", "")
ALERT_CHAT_ID     = os.getenv("ALERT_CHAT_ID", "")
YANDEX_VISION_KEY = os.getenv("YANDEX_VISION_KEY", "")
YANDEX_FOLDER_ID  = os.getenv("YANDEX_FOLDER_ID", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

RISK_PER_TRADE = 0.02
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.66"))
MIN_Q_SCORE    = int(os.getenv("MIN_Q_SCORE", "65"))
MAX_LEVERAGE   = int(os.getenv("MAX_LEVERAGE", "3"))
# With $100 futures balance, risk 10% = $10/trade, leverage 3x = $30 position size
TP_PCT         = 0.03
SL_PCT         = 0.015
TEST_MODE      = os.getenv("TEST_MODE", "true").lower() == "true"
if TEST_MODE:
    RISK_PER_TRADE = 0.10

AUTOPILOT  = True
SPOT_PAIRS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT", "AVAX-USDT"]
FUT_PAIRS  = ["XBTUSDTM", "ETHUSDTM", "SOLUSDTM"]

last_signals  = {}
last_q_score  = 0.0
trade_log: List[dict] = []

def log_trade(symbol, side, price, size, tp, sl, confidence, q_score, pattern, account="spot"):
    trade_log.append({
        "id": len(trade_log) + 1, "ts": datetime.utcnow().isoformat(),
        "symbol": symbol, "side": side, "price": price, "size": size,
        "tp": tp, "sl": sl, "confidence": confidence, "q_score": q_score,
        "pattern": pattern, "account": account, "status": "open", "pnl": None,
    })
    if len(trade_log) > 200:
        trade_log.pop(0)


# ── KuCoin Auth ────────────────────────────────────────────────────────────────
def kucoin_headers(method: str, endpoint: str, body: str = "") -> dict:
    timestamp = str(int(time.time() * 1000))
    str_to_sign = timestamp + method.upper() + endpoint + body
    signature = base64.b64encode(
        hmac.new(KUCOIN_SECRET.encode(), str_to_sign.encode(), hashlib.sha256).digest()
    ).decode()
    pp = base64.b64encode(
        hmac.new(KUCOIN_SECRET.encode(), KUCOIN_PASSPHRASE.encode(), hashlib.sha256).digest()
    ).decode()
    return {
        "KC-API-KEY": KUCOIN_API_KEY, "KC-API-SIGN": signature,
        "KC-API-TIMESTAMP": timestamp, "KC-API-PASSPHRASE": pp,
        "KC-API-KEY-VERSION": "2", "Content-Type": "application/json",
    }


# ── KuCoin API ─────────────────────────────────────────────────────────────────
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

async def get_futures_balance() -> dict:
    endpoint = "/api/v1/account-overview?currency=USDT"
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(KUCOIN_FUT_URL + endpoint, headers=kucoin_headers("GET", endpoint), timeout=aiohttp.ClientTimeout(total=10))
            data = await r.json()
            if data.get("code") == "200000":
                d = data["data"]
                return {
                    "available_balance": float(d.get("availableBalance", 0)),
                    "account_equity":    float(d.get("accountEquity", 0)),
                    "unrealised_pnl":    float(d.get("unrealisedPNL", 0)),
                    "margin_balance":    float(d.get("marginBalance", 0)),
                    "currency": "USDT", "success": True,
                }
            return {"available_balance": 0, "success": False, "error": data.get("msg")}
    except Exception as e:
        return {"available_balance": 0, "success": False, "error": str(e)}

async def get_futures_positions() -> dict:
    endpoint = "/api/v1/positions"
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(KUCOIN_FUT_URL + endpoint, headers=kucoin_headers("GET", endpoint), timeout=aiohttp.ClientTimeout(total=10))
            data = await r.json()
            if data.get("code") == "200000":
                positions = [p for p in data["data"] if float(p.get("currentQty", 0)) != 0]
                return {"positions": positions, "success": True}
            return {"positions": [], "success": False}
    except Exception as e:
        return {"positions": [], "success": False, "error": str(e)}

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
                        result[sym] = {"price": float(t.get("last", 0)), "change": float(t.get("changeRate", 0)) * 100, "vol": float(t.get("vol", 0))}
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
    return 0.0

async def get_kucoin_chart(symbol: str, interval: str = "1hour") -> list:
    try:
        end = int(time.time()); start = end - 86400
        async with aiohttp.ClientSession() as s:
            r = await s.get(f"{KUCOIN_BASE_URL}/api/v1/market/candles?type={interval}&symbol={symbol}&startAt={start}&endAt={end}", timeout=aiohttp.ClientTimeout(total=10))
            data = await r.json()
            if data.get("code") == "200000":
                return data.get("data", [])
    except:
        pass
    return []

async def place_spot_order(symbol: str, side: str, size: float) -> dict:
    endpoint = "/api/v1/orders"
    body = json.dumps({"clientOid": f"qt_{int(time.time()*1000)}", "side": side, "symbol": symbol, "type": "market", "size": str(size)})
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(KUCOIN_BASE_URL + endpoint, headers=kucoin_headers("POST", endpoint, body), data=body, timeout=aiohttp.ClientTimeout(total=10))
            return await r.json()
    except Exception as e:
        return {"code": "error", "msg": str(e)}

async def place_futures_order(symbol: str, side: str, size: int, leverage: int = 3, reduce_only: bool = False) -> dict:
    endpoint = "/api/v1/orders"
    body = json.dumps({"clientOid": f"qtf_{int(time.time()*1000)}", "side": side, "symbol": symbol, "type": "market", "size": size, "leverage": str(leverage), "reduceOnly": reduce_only, "marginMode": "CROSS"})
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(KUCOIN_FUT_URL + endpoint, headers=kucoin_headers("POST", endpoint, body), data=body, timeout=aiohttp.ClientTimeout(total=10))
            return await r.json()
    except Exception as e:
        return {"code": "error", "msg": str(e)}


# ── Technical Analysis ─────────────────────────────────────────────────────────
def _ema(data: list, period: int) -> float:
    if not data: return 0.0
    if len(data) < period: return data[-1]
    k = 2.0 / (period + 1)
    val = sum(data[:period]) / period
    for price in data[period:]: val = price * k + val * (1 - k)
    return val

def _rsi(data: list, period: int = 14) -> float:
    if len(data) < period + 1: return 50.0
    gains, losses = [], []
    for i in range(1, len(data)):
        diff = data[i] - data[i-1]
        gains.append(max(diff, 0.0)); losses.append(max(-diff, 0.0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0: return 100.0
    return round(100.0 - 100.0 / (1.0 + avg_gain / avg_loss), 1)

async def analyze_chart_with_vision(symbol: str, candles: list) -> dict:
    if not candles or len(candles) < 5:
        return {"pattern": "insufficient_data", "signal": "HOLD", "confidence": 0.5}
    try:
        chron   = list(reversed(candles))
        closes  = [float(c[2]) for c in chron]
        highs   = [float(c[3]) for c in chron]
        lows    = [float(c[4]) for c in chron]
        volumes = [float(c[5]) for c in chron]
        n = len(closes)
        current = closes[-1]; open_p = closes[0]
        price_change = (current - open_p) / open_p * 100
        ranges = [highs[i] - lows[i] for i in range(n)]
        volatility = (sum(ranges) / n) / current * 100
        ema_fast = _ema(closes, min(7, n)); ema_slow = _ema(closes, min(14, n))
        ema_bull = ema_fast > ema_slow * 1.0005; ema_bear = ema_fast < ema_slow * 0.9995
        rsi_val = _rsi(closes)
        recent_high = max(highs[-8:]) if n >= 8 else max(highs)
        recent_low  = min(lows[-8:])  if n >= 8 else min(lows)
        price_range = recent_high - recent_low
        price_pos   = (current - recent_low) / price_range * 100 if price_range > 0 else 50.0
        avg_vol_recent = sum(volumes[-5:]) / 5  if n >= 5  else volumes[-1]
        avg_vol_old    = sum(volumes[-15:-5]) / 10 if n >= 15 else avg_vol_recent
        vol_ratio = avg_vol_recent / avg_vol_old if avg_vol_old > 0 else 1.0
        strong_move = abs(price_change) > 1.0; vol_confirmed = vol_ratio > 1.2

        if rsi_val < 35 and price_pos < 30 and price_change > 0:
            pattern, signal = "oversold_bounce", "BUY"; confidence = 0.72 + (0.08 if vol_confirmed else 0)
        elif rsi_val > 65 and price_pos > 70 and price_change < 0:
            pattern, signal = "overbought_drop", "SELL"; confidence = 0.72 + (0.08 if vol_confirmed else 0)
        elif rsi_val < 30 and ema_bull:
            pattern, signal = "oversold_reversal", "BUY"; confidence = 0.82 + (0.05 if vol_confirmed else 0)
        elif rsi_val > 70 and ema_bear:
            pattern, signal = "overbought_reversal", "SELL"; confidence = 0.80 + (0.05 if vol_confirmed else 0)
        elif ema_bull and strong_move and price_change > 0 and vol_confirmed:
            pattern, signal = "uptrend_breakout", "BUY"; confidence = 0.78 + min(abs(price_change)*0.02, 0.10)
        elif ema_bear and strong_move and price_change < 0 and vol_confirmed:
            pattern, signal = "downtrend_breakdown", "SELL"; confidence = 0.76 + min(abs(price_change)*0.02, 0.10)
        elif ema_bull and price_change > 0.3:
            pattern, signal = "uptrend", "BUY"; confidence = 0.68 + (0.06 if vol_confirmed else 0)
        elif ema_bear and price_change < -0.3:
            pattern, signal = "downtrend", "SELL"; confidence = 0.68 + (0.06 if vol_confirmed else 0)
        elif volatility > 4:
            pattern, signal = "high_volatility", "HOLD"; confidence = 0.50
        else:
            pattern, signal = "consolidation", "HOLD"; confidence = 0.55

        return {"pattern": pattern, "signal": signal, "confidence": round(min(confidence, 0.95), 2),
                "price_change": round(price_change, 2), "volatility": round(volatility, 2),
                "rsi": rsi_val, "ema_fast": round(ema_fast, 4), "ema_slow": round(ema_slow, 4),
                "ema_bullish": ema_bull, "vol_ratio": round(vol_ratio, 2), "price_pos_pct": round(price_pos, 1)}
    except Exception as e:
        return {"pattern": "error", "signal": "HOLD", "confidence": 0.5, "error": str(e)}


# ── Telegram ───────────────────────────────────────────────────────────────────
async def notify(text: str):
    if not BOT_TOKEN or not ALERT_CHAT_ID: return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": ALERT_CHAT_ID, "text": text, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=5))
    except: pass


# ── Signal Generator v5.0 ──────────────────────────────────────────────────────
def calc_signal(price_change: float, vision: dict = None,
                fear_greed: dict = None, polymarket_bonus: float = 0.0,
                whale_bonus: float = 0.0) -> dict:
    """Q-Score v5.0: технический анализ + мировые события + киты."""
    score = 50.0

    # ── Технический анализ (max ±35) ─────────────────────────────────────
    score += price_change * 2.0  # было × 5 — слишком доминировало
    if vision and vision.get("pattern") not in ("error", "insufficient_data"):
        rsi     = vision.get("rsi", 50.0)
        pattern = vision.get("pattern", "consolidation")
        is_reversal = pattern in ("oversold_bounce", "oversold_reversal", "overbought_drop", "overbought_reversal")
        score += (rsi - 50.0) * 0.2
        if not is_reversal:
            if vision.get("ema_bullish") is True:  score += 8.0
            elif vision.get("ema_bullish") is False: score -= 8.0
        vol_ratio = vision.get("vol_ratio", 1.0)
        if vol_ratio > 1.2: score += 5.0 if price_change >= 0 else -5.0
        pattern_bonus_map = {
            "oversold_bounce": +10, "oversold_reversal": +10, "uptrend_breakout": +7,
            "uptrend": +4, "consolidation": 0, "high_volatility": -3,
            "downtrend": -4, "downtrend_breakdown": -7, "overbought_reversal": -10, "overbought_drop": -10
        }
        score += pattern_bonus_map.get(pattern, 0)

    # ── Внешние сигналы (max ±23) ─────────────────────────────────────────
    fg_bonus = fear_greed.get("bonus", 0) if fear_greed else 0
    score += fg_bonus          # Fear&Greed контрарный: ±8
    score += polymarket_bonus  # Polymarket события: ±5
    score += whale_bonus       # Whale flow: ±5 (упрощённо)

    score = max(0.0, min(100.0, score))

    if score >= MIN_Q_SCORE:
        action = "BUY"
        confidence = round(min(0.60 + (score - MIN_Q_SCORE) / (100 - MIN_Q_SCORE) * 0.35, 0.95), 2)
    elif score <= (100 - MIN_Q_SCORE):
        action = "SELL"
        confidence = round(min(0.60 + ((100 - MIN_Q_SCORE) - score) / (100 - MIN_Q_SCORE) * 0.35, 0.95), 2)
    else:
        action = "HOLD"
        confidence = round(0.40 + abs(score - 50.0) / 50.0 * 0.20, 2)

    if vision and vision.get("signal") == action and action != "HOLD":
        confidence = round(max(confidence, vision.get("confidence", 0.0)), 2)

    return {
        "action": action, "confidence": confidence, "q_score": round(score, 1),
        "breakdown": {
            "price_momentum": round(price_change * 2.0, 1),
            "fear_greed": fg_bonus, "polymarket": round(polymarket_bonus, 1),
            "whale": round(whale_bonus, 1),
        }
    }


# ── Trading ────────────────────────────────────────────────────────────────────
async def execute_spot_trade(symbol, signal, vision, price, trade_usdt):
    side = "buy" if signal["action"] == "BUY" else "sell"
    size = round(trade_usdt / price, 6)
    print(f"[spot] {symbol}: {side.upper()} {size} @ ${price:.2f}")
    if size < 0.000001: return False
    result = await place_spot_order(symbol, side, size)
    if result.get("code") != "200000": return False
    tp = round(price * (1 + TP_PCT if side == "buy" else 1 - TP_PCT), 6)
    sl = round(price * (1 - SL_PCT if side == "buy" else 1 + SL_PCT), 6)
    log_trade(symbol, side, price, size, tp, sl, signal["confidence"], signal["q_score"], vision.get("pattern","?"), "spot")
    last_signals[symbol] = {"action": signal["action"], "ts": time.time()}
    return True

async def place_futures_stop_order(symbol: str, side: str, size: int,
                                   stop_price: float, stop_dir: str) -> dict:
    """Выставляет stop-market ордер на KuCoin Futures (для TP/SL)."""
    endpoint = "/api/v1/st-orders"
    body = json.dumps({
        "clientOid": f"qts_{int(time.time()*1000)}",
        "side": side, "symbol": symbol, "type": "market",
        "size": size, "stop": stop_dir,
        "stopPrice": str(stop_price), "stopPriceType": "TP",
        "reduceOnly": True, "marginMode": "CROSS",
    })
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(KUCOIN_FUT_URL + endpoint,
                             headers=kucoin_headers("POST", endpoint, body),
                             data=body, timeout=aiohttp.ClientTimeout(total=10))
            return await r.json()
    except Exception as e:
        return {"code": "error", "msg": str(e)}


async def execute_futures_trade(symbol, signal, vision, price, available_usdt):
    FUTURES_MAP = {"BTC-USDT": ("XBTUSDTM", 0.001), "ETH-USDT": ("ETHUSDTM", 0.01), "SOL-USDT": ("SOLUSDTM", 1.0)}
    if symbol not in FUTURES_MAP: return False
    fut_symbol, contract_size = FUTURES_MAP[symbol]
    side = "buy" if signal["action"] == "BUY" else "sell"
    trade_usdt = available_usdt * RISK_PER_TRADE
    contract_value = price * contract_size
    n_contracts = max(1, int(trade_usdt * MAX_LEVERAGE / contract_value))
    margin_needed = contract_value / MAX_LEVERAGE
    if margin_needed > available_usdt:
        log_activity(f"[futures] {symbol}: SKIP — need ${margin_needed:.2f}, have ${available_usdt:.2f}")
        return False
    print(f"[futures] {symbol} -> {fut_symbol}: {side.upper()} {n_contracts} @ ${price:.2f}")
    result = await place_futures_order(fut_symbol, side, n_contracts, MAX_LEVERAGE)
    if result.get("code") != "200000":
        err = result.get("msg", result.get("code", "?"))
        log_activity(f"[futures] {fut_symbol} FAILED: {err}")
        return False
    # ── Реальные TP/SL стоп-ордера на KuCoin ─────────────────────────────
    tp = round(price * (1 + TP_PCT if side == "buy" else 1 - TP_PCT), 4)
    sl = round(price * (1 - SL_PCT if side == "buy" else 1 + SL_PCT), 4)
    close_side = "sell" if side == "buy" else "buy"
    tp_dir = "up" if side == "buy" else "down"
    sl_dir = "down" if side == "buy" else "up"
    tp_res = await place_futures_stop_order(fut_symbol, close_side, n_contracts, tp, tp_dir)
    sl_res = await place_futures_stop_order(fut_symbol, close_side, n_contracts, sl, sl_dir)
    log_activity(f"[futures] {fut_symbol} TP={tp}({'ok' if tp_res.get('code')=='200000' else 'err'}) SL={sl}({'ok' if sl_res.get('code')=='200000' else 'err'})")
    log_trade(fut_symbol, side, price, n_contracts, tp, sl, signal["confidence"], signal["q_score"], vision.get("pattern","?"), "futures")
    last_signals[f"FUT_{symbol}"] = {"action": signal["action"], "ts": time.time()}
    return True


# ── Кеш ────────────────────────────────────────────────────────────────────────
_cache: dict = {}
def _cache_get(key: str, ttl: int):
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < ttl:
        return entry["val"]
    return None
def _cache_set(key: str, val):
    _cache[key] = {"val": val, "ts": time.time()}


# ── Fear & Greed Index ─────────────────────────────────────────────────────────
async def get_fear_greed() -> dict:
    cached = _cache_get("fear_greed", 3600)
    if cached: return cached
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get("https://api.alternative.me/fng/?limit=1",
                            timeout=aiohttp.ClientTimeout(total=5))
            data = await r.json()
            val = int(data["data"][0]["value"])
            cls = data["data"][0]["value_classification"]
        if val <= 25:   bonus = +8
        elif val <= 40: bonus = +4
        elif val <= 60: bonus = 0
        elif val <= 75: bonus = -4
        else:           bonus = -8
        result = {"value": val, "classification": cls, "bonus": bonus, "success": True}
        _cache_set("fear_greed", result)
        return result
    except Exception as e:
        return {"value": 50, "classification": "Neutral", "bonus": 0, "success": False, "error": str(e)}


# ── Whale Tracker ──────────────────────────────────────────────────────────────
async def get_whale_signal(symbol: str) -> dict:
    coin_map = {"BTC-USDT": "bitcoin", "ETH-USDT": "ethereum"}
    coin = coin_map.get(symbol)
    if not coin: return {"bonus": 0, "success": False}
    cache_key = f"whale_{coin}"
    cached = _cache_get(cache_key, 300)
    if cached: return cached
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                f"https://api.blockchair.com/{coin}/stats",
                timeout=aiohttp.ClientTimeout(total=6)
            )
            data = await r.json()
            stats = data.get("data", {})
            # Используем mempool_transactions_count как proxy активности
            txn_count = stats.get("mempool_transactions_count", 0)
            # Нормализуем: высокая активность мемпула = потенциальная продажа
            if txn_count > 50000:   bonus = -5
            elif txn_count > 20000: bonus = -2
            elif txn_count < 5000:  bonus = +3
            else:                   bonus = 0
        result = {"txn_count": txn_count, "bonus": bonus, "success": True}
        _cache_set(cache_key, result)
        return result
    except Exception as e:
        return {"bonus": 0, "success": False, "error": str(e)}


# ── Polymarket bonus ───────────────────────────────────────────────────────────
def calc_polymarket_bonus(symbol: str, events: list) -> float:
    sym_keywords = {
        "BTC-USDT": ["bitcoin", "btc"], "ETH-USDT": ["ethereum", "eth"],
        "SOL-USDT": ["solana", "sol"],  "BNB-USDT": ["binance", "bnb"],
        "XRP-USDT": ["xrp", "ripple"],  "AVAX-USDT": ["avalanche", "avax"],
    }
    keywords = sym_keywords.get(symbol, [])
    if not keywords or not events: return 0.0
    relevant = [e for e in events if any(k in e.get("title","").lower() for k in keywords)]
    if not relevant: return 0.0
    avg_yes = sum(e.get("yes_prob", 50) for e in relevant) / len(relevant)
    if avg_yes >= 65:   return +5.0
    elif avg_yes >= 55: return +2.0
    elif avg_yes <= 35: return -5.0
    elif avg_yes <= 45: return -2.0
    return 0.0


# ── Pending strategy choices ───────────────────────────────────────────────────
pending_strategies: dict = {}  # trade_id → {symbol, signal, vision, price, fut_usdt, expires_at}

# ── Стратегии A/B/C ────────────────────────────────────────────────────────────
STRATEGIES = {
    "A": {"name": "Консервативная", "risk": 0.05, "leverage": 2, "tp": 0.02, "sl": 0.01,  "emoji": "🛡",  "tag": "real"},
    "B": {"name": "Стандартная",    "risk": 0.10, "leverage": 3, "tp": 0.03, "sl": 0.015, "emoji": "⚖️", "tag": "real"},
    "C": {"name": "Бонусная",       "risk": 0.25, "leverage": 5, "tp": 0.05, "sl": 0.025, "emoji": "🚀",  "tag": "bonus"},
}
# DUAL: одновременно B (реальный) + C (бонусный агрессивный)
STRATEGY_TIMEOUT = 180  # 3 минуты


async def send_strategy_choice(trade_id, symbol, action, price, q, pattern, fg, poly_b, whale_b):
    fg_txt = f"F&G: {fg.get('value',50)} {fg.get('classification','—')} ({fg.get('bonus',0):+d})" if fg.get("success") else ""
    poly_txt = f"Poly: {poly_b:+.0f}" if poly_b != 0 else ""
    whale_txt = f"Whale: {whale_b:+.0f}" if whale_b != 0 else ""
    ctx = " · ".join(p for p in [fg_txt, poly_txt, whale_txt] if p)
    act_emoji = "🟢 BUY" if action == "BUY" else "🔴 SELL"
    text = (
        f"⚛ *QuantumTrade — {act_emoji}*\n\n"
        f"Пара: *{symbol}* · Цена: `${price:,.2f}`\n"
        f"Q-Score: `{q}` · Паттерн: `{pattern}`\n"
        f"{ctx}\n\n"
        f"*Выбери стратегию:*\n"
        f"🛡 *A* — Консерватив (5%, TP 2%, SL 1%)\n"
        f"⚖️ *B* — Стандарт (10%, TP 3%, SL 1.5%)\n"
        f"🚀 *C* — Бонусная (25%, TP 5%, SL 2.5%)\n"
        f"💥 *DUAL* — B + C одновременно\n\n"
        f"_Нет ответа 3 мин → авто стратегия B_"
    )
    keyboard = {"inline_keyboard": [
        [
            {"text": "🛡 A", "callback_data": f"strat_A_{trade_id}"},
            {"text": "⚖️ B", "callback_data": f"strat_B_{trade_id}"},
            {"text": "🚀 C", "callback_data": f"strat_C_{trade_id}"},
        ],
        [
            {"text": "💥 DUAL (B + C бонус)", "callback_data": f"strat_D_{trade_id}"},
        ]
    ]}
    if not BOT_TOKEN or not ALERT_CHAT_ID: return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": ALERT_CHAT_ID, "text": text,
                      "parse_mode": "Markdown", "reply_markup": keyboard},
                timeout=aiohttp.ClientTimeout(total=5)
            )
    except Exception as e:
        print(f"[telegram] strategy choice error: {e}")


async def execute_with_strategy(strategy: str, symbol: str, signal: dict,
                                 vision: dict, price: float, fut_usdt: float) -> bool:
    s = STRATEGIES.get(strategy, STRATEGIES["B"])
    log_activity(f"[strategy] {s['emoji']} {strategy} риск={int(s['risk']*100)}% lev={s['leverage']}x TP={int(s['tp']*100)}% SL={int(s['sl']*100)}%")
    FMAP = {"BTC-USDT": ("XBTUSDTM", 0.001), "ETH-USDT": ("ETHUSDTM", 0.01), "SOL-USDT": ("SOLUSDTM", 1.0)}
    if symbol not in FMAP: return False
    fut_symbol, contract_size = FMAP[symbol]
    side = "buy" if signal["action"] == "BUY" else "sell"
    trade_usdt = fut_usdt * s["risk"]
    contract_value = price * contract_size
    n_contracts = max(1, int(trade_usdt * s["leverage"] / contract_value))
    if (contract_value / s["leverage"]) > fut_usdt:
        log_activity(f"[strategy] {symbol} SKIP — маржи недостаточно")
        return False
    body = json.dumps({
        "clientOid": f"qts_{int(time.time()*1000)}", "side": side, "symbol": fut_symbol,
        "type": "market", "size": n_contracts, "leverage": str(s["leverage"]),
        "reduceOnly": False, "marginMode": "CROSS",
    })
    endpoint = "/api/v1/orders"
    try:
        async with aiohttp.ClientSession() as sess:
            r = await sess.post(KUCOIN_FUT_URL + endpoint,
                                headers=kucoin_headers("POST", endpoint, body),
                                data=body, timeout=aiohttp.ClientTimeout(total=10))
            result = await r.json()
    except Exception as e:
        log_activity(f"[strategy] ошибка запроса: {e}"); return False
    if result.get("code") != "200000":
        log_activity(f"[strategy] {fut_symbol} FAILED: {result.get('msg','?')}"); return False
    tp = round(price * (1 + s["tp"] if side == "buy" else 1 - s["tp"]), 4)
    sl = round(price * (1 - s["sl"] if side == "buy" else 1 + s["sl"]), 4)
    close_side = "sell" if side == "buy" else "buy"
    await place_futures_stop_order(fut_symbol, close_side, n_contracts, tp, "up" if side == "buy" else "down")
    await place_futures_stop_order(fut_symbol, close_side, n_contracts, sl, "down" if side == "buy" else "up")
    log_trade(fut_symbol, side, price, n_contracts, tp, sl,
              signal["confidence"], signal["q_score"], vision.get("pattern","?"), f"futures_{strategy}")
    last_signals[f"FUT_{symbol}"] = {"action": signal["action"], "ts": time.time()}
    log_activity(f"[strategy] {strategy} {fut_symbol} {side.upper()} OK TP={tp} SL={sl}")
    await notify(f"{s['emoji']} *Стратегия {strategy} — {s['name']}*\n{fut_symbol} {side.upper()} Q={signal['q_score']}")
    return True



async def execute_dual_strategy(symbol: str, signal: dict, vision: dict,
                                 price: float, fut_usdt: float) -> bool:
    """DUAL: открывает B (реальный) + C (бонусный) одновременно."""
    log_activity(f"[dual] {symbol}: B(реальный) + C(бонусный) одновременно")
    # Запускаем оба параллельно
    ok_b, ok_c = await asyncio.gather(
        execute_with_strategy("B", symbol, signal, vision, price, fut_usdt),
        execute_with_strategy("C", symbol, signal, vision, price, fut_usdt),
        return_exceptions=True
    )
    ok_b = ok_b is True; ok_c = ok_c is True
    log_activity(f"[dual] результат: B={'OK' if ok_b else 'FAIL'} C={'OK' if ok_c else 'FAIL'}")
    if ok_b or ok_c:
        await notify(
            f"💥 *DUAL стратегия*\n"
            f"{symbol} {('BUY' if signal['action']=='BUY' else 'SELL')} Q={signal['q_score']}\n"
            f"⚖️ B (реальный): {'✅' if ok_b else '❌'}\n"
            f"🚀 C (бонусный): {'✅' if ok_c else '❌'}"
        )
    return ok_b or ok_c

async def auto_execute_strategy_b(trade_id: str):
    await asyncio.sleep(STRATEGY_TIMEOUT)
    pending = pending_strategies.pop(trade_id, None)
    if not pending: return
    log_activity(f"[strategy] timeout {trade_id} → авто B")
    await notify("⏱ _Таймаут 3 мин — выполняю стратегию B_")
    await execute_with_strategy("B", pending["symbol"], pending["signal"],
                                 pending["vision"], pending["price"], pending["fut_usdt"])


async def auto_trade_cycle():
    global last_q_score
    log_activity(f"[cycle start] {datetime.utcnow().strftime('%H:%M:%S')}")

    # ── Все внешние данные параллельно ───────────────────────────────────────
    try:
        prices_data, fg_data, spot_bal, fut_bal = await asyncio.wait_for(
            asyncio.gather(get_all_prices(), get_fear_greed(), get_balance(), get_futures_balance()),
            timeout=12.0
        )
    except asyncio.TimeoutError:
        log_activity("[cycle] data fetch timeout — skipping"); return
    if not prices_data.get("success"):
        log_activity("[cycle] prices fetch FAILED"); return

    spot_usdt       = spot_bal.get("total_usdt", 0)
    fut_usdt        = fut_bal.get("available_balance", 0)
    spot_trade_usdt = spot_usdt * RISK_PER_TRADE
    fg_val = fg_data.get("value", 50)
    log_activity(f"[cycle] F&G={fg_val}({fg_data.get('bonus',0):+d}) spot=${spot_usdt:.1f} fut=${fut_usdt:.1f}")

    # ── Polymarket (кеш 15 мин) ───────────────────────────────────────────────
    poly_events = _cache_get("polymarket", 900) or []
    if not poly_events:
        try:
            async with aiohttp.ClientSession() as _s:
                _r = await _s.get("https://gamma-api.polymarket.com/events?limit=30&active=true&tag=crypto",
                                  timeout=aiohttp.ClientTimeout(total=6))
                _data = await _r.json()
            result = []
            for e in (_data if isinstance(_data, list) else []):
                markets = e.get("markets", [])
                if not markets: continue
                pr = markets[0].get("outcomePrices", "[]")
                if isinstance(pr, str):
                    try: pr = json.loads(pr)
                    except: continue
                if not pr: continue
                try: yp = round(float(pr[0]) * 100, 1)
                except: continue
                if yp in (0.0, 100.0): continue
                if float(e.get("volume", 0)) < 1000: continue
                result.append({"title": e.get("title",""), "yes_prob": yp})
            poly_events = result[:10]
            _cache_set("polymarket", poly_events)
        except Exception: poly_events = []

    signals_fired = []
    COOLDOWN = 100

    # ── Параллельный fetch: chart + vision + whale ────────────────────────────
    async def _get_sym_data(sym, pdata):
        try:
            candles = await asyncio.wait_for(get_kucoin_chart(sym), timeout=8.0)
        except asyncio.TimeoutError:
            candles = []
        vision  = await analyze_chart_with_vision(sym, candles)
        whale   = await get_whale_signal(sym)
        poly_b  = calc_polymarket_bonus(sym, poly_events)
        signal  = calc_signal(pdata.get("change", 0), vision, fg_data, poly_b, whale.get("bonus", 0))
        return sym, vision, signal, whale, poly_b

    cv_tasks = [_get_sym_data(sym, pdata)
                for sym, pdata in prices_data["prices"].items()
                if pdata.get("price", 0) > 0]
    cv_results = await asyncio.gather(*cv_tasks, return_exceptions=True)

    futures_candidates = []

    for res in cv_results:
        if isinstance(res, Exception):
            log_activity(f"[cycle] error: {res}"); continue
        symbol, vision, signal, whale, poly_b = res
        price = prices_data["prices"].get(symbol, {}).get("price", 0)
        if price <= 0: continue
        action = signal["action"]
        conf   = signal["confidence"]
        q      = signal["q_score"]
        bd     = signal.get("breakdown", {})
        log_activity(f"[cycle] {symbol}: {action} Q={q:.1f} "
                     f"fg={bd.get('fear_greed',0):+.0f} poly={bd.get('polymarket',0):+.0f} "
                     f"whale={bd.get('whale',0):+.0f} pattern={vision.get('pattern','?')}")

        if action == "HOLD": continue
        if conf < MIN_CONFIDENCE: continue
        if not AUTOPILOT: continue

        # ── Спот (только BUY) ─────────────────────────────────────────────────
        if action == "BUY":
            elapsed = time.time() - last_signals.get(symbol, {}).get("ts", 0)
            if elapsed >= COOLDOWN and spot_trade_usdt >= 1.0:
                log_activity(f"[cycle] {symbol}: PLACING spot BUY ${spot_trade_usdt:.2f}")
                ok = await execute_spot_trade(symbol, signal, vision, price, spot_trade_usdt)
                if ok:
                    signals_fired.append({"account": "spot", "symbol": symbol, "action": action,
                        "price": price, "confidence": conf, "q_score": q,
                        "pattern": vision.get("pattern","?"), "rsi": vision.get("rsi", 0),
                        "tp": round(price*(1+TP_PCT),4), "sl": round(price*(1-SL_PCT),4)})

        # ── Фьючерсы: собираем кандидатов ────────────────────────────────────
        if symbol in ("BTC-USDT", "ETH-USDT", "SOL-USDT"):
            FMAP = {"BTC-USDT":("XBTUSDTM",0.001),"ETH-USDT":("ETHUSDTM",0.01),"SOL-USDT":("SOLUSDTM",1.0)}
            _, cs = FMAP[symbol]
            margin = (price * cs) / MAX_LEVERAGE
            elapsed = time.time() - last_signals.get(f"FUT_{symbol}", {}).get("ts", 0)
            reason = None
            if elapsed < COOLDOWN:  reason = f"cooldown {int(COOLDOWN-elapsed)}s"
            elif fut_usdt < 1.0:    reason = f"bal ${fut_usdt:.2f}<$1"
            elif margin > fut_usdt: reason = f"margin ${margin:.2f}>${fut_usdt:.2f}"
            if reason:
                log_activity(f"[cycle] {symbol}: SKIP fut — {reason}")
            else:
                futures_candidates.append({
                    "symbol": symbol, "signal": signal, "vision": vision,
                    "price": price, "action": action, "conf": conf, "q": q,
                    "fg": fg_data, "poly": poly_b, "whale": whale.get("bonus", 0),
                    "pattern": vision.get("pattern","?")
                })

    # ── Лучший кандидат → Telegram A/B/C (3 мин таймаут) ────────────────────
    if futures_candidates:
        best = sorted(futures_candidates, key=lambda c: abs(c["q"] - 50), reverse=True)[0]
        others = [c["symbol"] for c in futures_candidates if c["symbol"] != best["symbol"]]
        skip_txt = f" (skip: {', '.join(others)})" if others else ""
        log_activity(f"[cycle] BEST: {best['symbol']} {best['action']} Q={best['q']:.1f}{skip_txt}")

        trade_id = f"{best['symbol']}_{int(time.time())}"
        pending_strategies[trade_id] = {
            "symbol": best["symbol"], "signal": best["signal"], "vision": best["vision"],
            "price": best["price"], "fut_usdt": fut_usdt,
            "expires_at": time.time() + STRATEGY_TIMEOUT + 60
        }
        # ВАЖНО: блокируем эту пару сразу, не ждём исполнения
        # иначе следующий цикл создаст новый pending для той же пары
        last_signals[f"FUT_{best['symbol']}"] = {"action": best["action"], "ts": time.time()}
        log_activity(f"[cycle] {best['symbol']}: reserved — cooldown {COOLDOWN}s")
        for k in [k for k, v in list(pending_strategies.items()) if time.time() > v["expires_at"]]:
            del pending_strategies[k]

        await send_strategy_choice(
            trade_id, best["symbol"], best["action"], best["price"],
            best["q"], best["pattern"], best["fg"], best["poly"], best["whale"]
        )
        asyncio.create_task(auto_execute_strategy_b(trade_id))

    # ── Уведомление спот ─────────────────────────────────────────────────────
    if signals_fired:
        mode = "TEST" if TEST_MODE else "LIVE"
        msg  = f"⚛ *QuantumTrade {mode}*\n\n"
        for s in signals_fired:
            emoji = "🟢" if s["action"] == "BUY" else "🔴"
            msg += f"{emoji} *{s['symbol']}* {s['action']} [spot]\n   Q:`{s['q_score']}` TP:`${s['tp']:,.2f}` SL:`${s['sl']:,.2f}`\n\n"
        await notify(msg)

    # ── BTC Q-Score алерты ────────────────────────────────────────────────────
    btc_res = next((r for r in cv_results if not isinstance(r, Exception) and r[0] == "BTC-USDT"), None)
    if btc_res:
        _, _, btc_signal, _, _ = btc_res
        q = btc_signal["q_score"]; conf = btc_signal["confidence"]
        btc_price = prices_data["prices"].get("BTC-USDT", {}).get("price", 0)
        if q >= MIN_Q_SCORE and last_q_score < MIN_Q_SCORE:
            await notify(f"🚀 *Q-Score {q}!* BTC `${btc_price:,.0f}` · {btc_signal['action']} `{int(conf*100)}%` · F&G={fg_val}")
        elif q <= 35 and last_q_score > 35:
            await notify(f"⚠️ *Q-Score упал до {q}!* BTC `${btc_price:,.0f}`")
        last_q_score = q


# ── Startup ────────────────────────────────────────────────────────────────────
# ── Position Monitor ────────────────────────────────────────────────────────────
async def position_monitor_loop():
    """Каждые 30 сек проверяет открытые позиции — закрылись ли по TP/SL."""
    await asyncio.sleep(30)
    SYM_REV = {"XBTUSDTM": "BTC-USDT", "ETHUSDTM": "ETH-USDT", "SOLUSDTM": "SOL-USDT"}
    while True:
        try:
            open_trades = [t for t in trade_log if t.get("status") == "open"]
            if open_trades:
                pos_data   = await get_futures_positions()
                open_syms  = {p.get("symbol") for p in pos_data.get("positions", [])}
                for trade in open_trades:
                    if trade["symbol"] not in open_syms:
                        base_sym  = SYM_REV.get(trade["symbol"], "BTC-USDT")
                        price_now = await get_ticker(base_sym)
                        entry     = trade["price"]
                        if trade["side"] == "sell":
                            pnl_pct = (entry - price_now) / entry
                        else:
                            pnl_pct = (price_now - entry) / entry
                        pnl_usdt = round(pnl_pct * entry * trade["size"] * MAX_LEVERAGE, 4)
                        trade["status"]      = "closed"
                        trade["pnl"]         = pnl_usdt
                        trade["close_price"] = price_now
                        emoji = "✅" if pnl_usdt >= 0 else "❌"
                        log_activity(f"[monitor] {trade['symbol']} closed PnL=${pnl_usdt:+.3f}")
                        await notify(
                            f"{emoji} *Позиция закрыта*\n"
                            f"`{trade['symbol']}` {trade['side'].upper()}\n"
                            f"Вход: `${entry:,.2f}` · Выход: `${price_now:,.2f}`\n"
                            f"PnL: `${pnl_usdt:+.3f}` ({pnl_pct*100:+.2f}%)"
                        )
        except Exception as e:
            print(f"[monitor] {e}")
        await asyncio.sleep(30)


# ── Telegram Webhook — callback для A/B/C ────────────────────────────────────
class TelegramUpdate(BaseModel):
    callback_query: Optional[dict] = None
    message:        Optional[dict] = None

@app.post("/api/telegram/callback")
async def telegram_callback(req: TelegramUpdate):
    cb = req.callback_query
    if not cb: return {"ok": True}
    data = cb.get("data", "")
    if not data.startswith("strat_"): return {"ok": True}
    parts = data.split("_", 2)  # strat_A_BTC-USDT_1234567890
    if len(parts) < 3: return {"ok": True}
    strategy = parts[1]
    trade_id = parts[2]

    pending = pending_strategies.pop(trade_id, None)
    if not pending:
        if BOT_TOKEN:
            async with aiohttp.ClientSession() as _s:
                await _s.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
                    json={"callback_query_id": cb["id"], "text": "Сигнал устарел или уже исполнен"},
                    timeout=aiohttp.ClientTimeout(total=3)
                )
        return {"ok": True}

    s = STRATEGIES.get(strategy, STRATEGIES["B"])
    if BOT_TOKEN:
        try:
            async with aiohttp.ClientSession() as _s:
                await _s.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
                    json={"callback_query_id": cb["id"], "text": f"{s['emoji']} Стратегия {strategy} принята!"},
                    timeout=aiohttp.ClientTimeout(total=3)
                )
        except: pass

    if strategy == "D":
        asyncio.create_task(execute_dual_strategy(
            pending["symbol"], pending["signal"], pending["vision"],
            pending["price"], pending["fut_usdt"]
        ))
    else:
        asyncio.create_task(execute_with_strategy(
            strategy, pending["symbol"], pending["signal"], pending["vision"],
            pending["price"], pending["fut_usdt"]
        ))
    return {"ok": True}


@app.on_event("startup")
async def startup():
    asyncio.create_task(trading_loop())
    asyncio.create_task(position_monitor_loop())
    mode = "TEST (риск 10%)" if TEST_MODE else "LIVE (риск 2%)"
    await notify(
        f"⚛ *QuantumTrade v5.2*\n"
        f"✅ Спот + Фьючерсы + реальные TP/SL\n"
        f"✅ Fear&Greed + Polymarket + Whale → Q-Score\n"
        f"✅ Стратегии A/B/C (3 мин таймаут)\n"
        f"✅ Position Monitor\n"
        f"📊 Режим: {mode}\n"
        f"🎯 Q-min: {MIN_Q_SCORE} · Conf-min: {int(MIN_CONFIDENCE*100)}%"
    )

async def trading_loop():
    while True:
        try: await auto_trade_cycle()
        except Exception as e: log_activity(f"[loop] error: {e}")
        await asyncio.sleep(60)


# ── Routes ─────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "version": "5.2.0", "auto_trading": AUTOPILOT, "test_mode": TEST_MODE,
            "risk_per_trade": RISK_PER_TRADE, "last_qscore": last_q_score, "min_confidence": MIN_CONFIDENCE,
            "min_q_score": MIN_Q_SCORE, "max_leverage": MAX_LEVERAGE, "tp_pct": TP_PCT, "sl_pct": SL_PCT,
            "trades_logged": len(trade_log), "yandex_vision": bool(YANDEX_VISION_KEY),
            "ai_chat": bool(ANTHROPIC_API_KEY), "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/balance")
async def api_balance(): return await get_balance()

@app.get("/api/futures/balance")
async def api_futures_balance(): return await get_futures_balance()

@app.get("/api/futures/positions")
async def api_futures_positions(): return await get_futures_positions()

@app.get("/api/combined/balance")
async def api_combined_balance():
    spot, futures = await asyncio.gather(get_balance(), get_futures_balance())
    total = spot.get("total_usdt", 0) + futures.get("available_balance", 0)
    return {"spot_usdt": spot.get("total_usdt", 0), "futures_usdt": futures.get("available_balance", 0),
            "futures_equity": futures.get("account_equity", 0), "futures_unrealised_pnl": futures.get("unrealised_pnl", 0),
            "total_usdt": round(total, 2), "spot_success": spot.get("success", False), "futures_success": futures.get("success", False)}

@app.get("/api/prices")
async def api_prices(): return await get_all_prices()

@app.get("/api/signal/{symbol}")
async def api_signal(symbol: str):
    price = await get_ticker(symbol)
    prices = await get_all_prices()
    change = prices["prices"].get(symbol, {}).get("change", 0)
    candles = await get_kucoin_chart(symbol)
    vision = await analyze_chart_with_vision(symbol, candles)
    signal = calc_signal(change, vision)
    signal["symbol"] = symbol; signal["price"] = price; signal["vision"] = vision
    return signal

@app.get("/api/dashboard")
async def api_dashboard():
    balance, prices, fut_bal = await asyncio.gather(get_balance(), get_all_prices(), get_futures_balance())
    btc_change = prices["prices"].get("BTC-USDT", {}).get("change", 0)
    candles = await get_kucoin_chart("BTC-USDT")
    vision = await analyze_chart_with_vision("BTC-USDT", candles)
    signal = calc_signal(btc_change, vision)
    return {"balance": balance, "futures_balance": fut_bal,
            "total_usdt": round(balance.get("total_usdt",0) + fut_bal.get("available_balance",0), 2),
            "prices": prices, "signal": signal, "vision": vision, "autopilot": AUTOPILOT,
            "config": {"risk": RISK_PER_TRADE, "test_mode": TEST_MODE, "min_confidence": MIN_CONFIDENCE,
                       "min_q_score": MIN_Q_SCORE, "max_leverage": MAX_LEVERAGE, "tp_pct": TP_PCT, "sl_pct": SL_PCT},
            "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/chart/{symbol}")
async def api_chart(symbol: str):
    candles = await get_kucoin_chart(symbol)
    vision = await analyze_chart_with_vision(symbol, candles)
    return {"symbol": symbol, "candles_count": len(candles), "vision_analysis": vision, "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/trades")
async def api_trades(limit: int = 50):
    # Статистика по трекам
    def track_stats(tag_filter):
        filtered = [t for t in trade_log if tag_filter in t.get("account","")]
        wins   = sum(1 for t in filtered if (t.get("pnl") or 0) > 0)
        losses = sum(1 for t in filtered if (t.get("pnl") or 0) <= 0 and t.get("pnl") is not None)
        pnl    = round(sum(t.get("pnl") or 0 for t in filtered), 4)
        return {"count": len(filtered), "wins": wins, "losses": losses,
                "pnl": pnl, "win_rate": round(wins/len(filtered)*100, 1) if filtered else 0}
    return {
        "trades":     list(reversed(trade_log))[:limit],
        "total":      len(trade_log),
        "open":       sum(1 for t in trade_log if t["status"] == "open"),
        "wins":       sum(1 for t in trade_log if (t.get("pnl") or 0) > 0),
        "losses":     sum(1 for t in trade_log if (t.get("pnl") or 0) <= 0 and t.get("pnl") is not None),
        "total_pnl":  round(sum(t.get("pnl") or 0 for t in trade_log), 4),
        "by_track": {
            "real":  track_stats("_A") if any("_A" in t.get("account","") for t in trade_log)
                     else track_stats("_B") | {"note": "includes B"},
            "bonus": track_stats("_C"),
            "dual":  track_stats("_D"),
            "all_real": {**track_stats("_A"), "plus_B": track_stats("_B")},
        }
    }

@app.get("/api/polymarket")
async def api_polymarket():
    CRYPTO_KEYWORDS = ["bitcoin","btc","ethereum","eth","crypto","solana","sol","binance","bnb","xrp","ripple","defi","nft","blockchain","coinbase","stablecoin","altcoin","web3"]
    def is_crypto(title): return any(kw in title.lower() for kw in CRYPTO_KEYWORDS)
    def parse_prices(raw):
        if isinstance(raw, list): return raw
        if isinstance(raw, str):
            try: return json.loads(raw)
            except: return []
        return []
    try:
        async with aiohttp.ClientSession() as s:
            events = []
            for url in ["https://gamma-api.polymarket.com/events?limit=30&active=true&tag=crypto",
                        "https://gamma-api.polymarket.com/events?limit=50&active=true"]:
                try:
                    r = await s.get(url, timeout=aiohttp.ClientTimeout(total=10))
                    data = await r.json()
                    if isinstance(data, list) and data: events = data; break
                except: continue
            result = []
            for e in events:
                title = e.get("title", "")
                if not is_crypto(title): continue
                markets = e.get("markets", [])
                if not markets: continue
                prices_raw = parse_prices(markets[0].get("outcomePrices", "[]"))
                if not prices_raw: continue
                try: yes_prob = round(float(prices_raw[0]) * 100, 1)
                except: continue
                if yes_prob in (0.0, 100.0): continue
                volume = float(e.get("volume", 0))
                if volume < 1000: continue
                result.append({"title": title, "yes_prob": yes_prob, "volume": volume})
                if len(result) >= 8: break
            return {"events": result, "success": True, "count": len(result)}
    except Exception as e:
        return {"events": [], "success": False, "error": str(e)}


# ── AI Chat Proxy ──────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    messages: list
    context:  str = ""

@app.post("/api/ai/chat")
async def api_ai_chat(req: ChatRequest):
    """Proxy for Claude API — solves CORS from browser."""
    if not ANTHROPIC_API_KEY:
        return {"error": "ANTHROPIC_API_KEY not configured on server", "success": False}
    system_lines = [
        "Ты QuantumTrade AI — торговый советник в трейдинг-боте на KuCoin.",
        "Помогаешь понять рынок, сигналы и стратегию. Объясняй простым языком — многие новички.",
        "СТИЛЬ: по-русски, кратко (2-4 абзаца), конкретные советы, объясняй термины, умеренные эмодзи.",
        "КОНТЕКСТ: EMA+RSI+Volume, Q-Score 65+=BUY 35-=SELL, тест: $24 USDT, риск 10%, TP 3%, SL 1.5%.",
    ]
    if req.context:
        system_lines.append("")
        system_lines.append(req.context)
    system_prompt = "\n".join(system_lines)
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json={"model": "claude-sonnet-4-20250514", "max_tokens": 1000, "system": system_prompt, "messages": req.messages[-10:]},
                timeout=aiohttp.ClientTimeout(total=30),
            )
            data = await r.json()
            if r.status == 200:
                text = data.get("content", [{}])[0].get("text", "")
                return {"reply": text, "success": True}
            return {"error": data.get("error", {}).get("message", "API error"), "success": False, "status": r.status}
    except Exception as e:
        return {"error": str(e), "success": False}


class ManualTrade(BaseModel):
    symbol: str; side: str; size: float; is_futures: bool = False; leverage: int = 3


# In-memory activity log
activity_log = []
def log_activity(msg: str):
    activity_log.append({"ts": datetime.utcnow().isoformat(), "msg": msg})
    if len(activity_log) > 100: activity_log.pop(0)

@app.get("/api/debug")
async def api_debug():
    """Returns last known state for debugging."""
    return {
        "last_signals":  last_signals,
        "last_qscore":   last_q_score,
        "trade_count":   len(trade_log),
        "autopilot":     AUTOPILOT,
        "risk":          RISK_PER_TRADE,
        "min_confidence":MIN_CONFIDENCE,
        "cooldown_sec":  100,
        "activity_log":  list(reversed(activity_log))[:20],
        "timestamp":     datetime.utcnow().isoformat(),
    }

@app.post("/api/trade/manual")
async def manual_trade(req: ManualTrade):
    result = await place_futures_order(req.symbol, req.side, int(req.size), req.leverage) if req.is_futures else await place_spot_order(req.symbol, req.side, req.size)
    success = result.get("code") == "200000"
    if success:
        emoji = "🟢" if req.side == "buy" else "🔴"
        await notify(f"{emoji} *Ручная сделка*\n`{req.symbol}` {req.side.upper()} · `{req.size}`")
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
            prices = await get_all_prices()
            btc_change = prices["prices"].get("BTC-USDT", {}).get("change", 0)
            candles = await get_kucoin_chart("BTC-USDT")
            vision = await analyze_chart_with_vision("BTC-USDT", candles)
            signal = calc_signal(btc_change, vision)
            await websocket.send_json({"type": "update", "prices": prices, "signal": signal, "vision": vision, "timestamp": datetime.utcnow().isoformat()})
            await asyncio.sleep(15)
    except: pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
