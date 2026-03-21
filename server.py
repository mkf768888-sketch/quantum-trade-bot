"""
QuantumTrade AI - FastAPI Backend v4.3
New: futures trading, trade log, OCO orders, test-mode risk sizing
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

app = FastAPI(title="QuantumTrade AI", version="4.3.0")
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

# ── Trading config ────────────────────────────────────────────────────────────
# Test mode: 10% risk per trade (for $15 account = ~$1.5/trade)
# Production mode: 2% risk per trade
TEST_MODE      = os.getenv("TEST_MODE", "true").lower() == "true"
RISK_PER_TRADE = 0.10 if TEST_MODE else 0.02
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.66"))
MIN_Q_SCORE    = int(os.getenv("MIN_Q_SCORE", "65"))
MAX_LEVERAGE   = int(os.getenv("MAX_LEVERAGE", "3"))   # futures leverage
TP_PCT         = 0.03   # take profit 3%
SL_PCT         = 0.015  # stop loss 1.5%  (risk:reward = 1:2)
AUTOPILOT      = True

SPOT_PAIRS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT", "AVAX-USDT"]
# Futures use XBTUSDTM format on KuCoin
FUT_PAIRS  = ["XBTUSDTM", "ETHUSDTM", "SOLUSDTM"]

last_signals  = {}
last_q_score  = 0.0

# ── Trade log (in-memory, persists while server runs) ─────────────────────────
trade_log: List[dict] = []

def log_trade(symbol, side, price, size, tp, sl, confidence, q_score, pattern, account="spot"):
    trade_log.append({
        "id":         len(trade_log) + 1,
        "ts":         datetime.utcnow().isoformat(),
        "symbol":     symbol,
        "side":       side,
        "price":      price,
        "size":       size,
        "tp":         tp,
        "sl":         sl,
        "confidence": confidence,
        "q_score":    q_score,
        "pattern":    pattern,
        "account":    account,
        "status":     "open",
        "pnl":        None,
    })
    # Keep last 200 trades
    if len(trade_log) > 200:
        trade_log.pop(0)


# ── KuCoin Auth ───────────────────────────────────────────────────────────────
def kucoin_headers(method: str, endpoint: str, body: str = "",
                   secret: str = None, passphrase: str = None) -> dict:
    secret     = secret     or KUCOIN_SECRET
    passphrase = passphrase or KUCOIN_PASSPHRASE
    timestamp  = str(int(time.time() * 1000))
    str_to_sign = timestamp + method.upper() + endpoint + body
    signature  = base64.b64encode(
        hmac.new(secret.encode(), str_to_sign.encode(), hashlib.sha256).digest()
    ).decode()
    pp = base64.b64encode(
        hmac.new(secret.encode(), passphrase.encode(), hashlib.sha256).digest()
    ).decode()
    return {
        "KC-API-KEY":        KUCOIN_API_KEY,
        "KC-API-SIGN":       signature,
        "KC-API-TIMESTAMP":  timestamp,
        "KC-API-PASSPHRASE": pp,
        "KC-API-KEY-VERSION":"2",
        "Content-Type":      "application/json",
    }


# ── Spot Balance ──────────────────────────────────────────────────────────────
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


# ── Futures Balance ───────────────────────────────────────────────────────────
async def get_futures_balance() -> dict:
    """Get USDT balance from KuCoin Futures account."""
    endpoint = "/api/v1/account-overview?currency=USDT"
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                KUCOIN_FUT_URL + endpoint,
                headers=kucoin_headers("GET", endpoint),
                timeout=aiohttp.ClientTimeout(total=10),
            )
            data = await r.json()
            if data.get("code") == "200000":
                d = data["data"]
                return {
                    "available_balance": float(d.get("availableBalance", 0)),
                    "account_equity":    float(d.get("accountEquity", 0)),
                    "unrealised_pnl":    float(d.get("unrealisedPNL", 0)),
                    "margin_balance":    float(d.get("marginBalance", 0)),
                    "position_margin":   float(d.get("positionMargin", 0)),
                    "order_margin":      float(d.get("orderMargin", 0)),
                    "currency":          d.get("currency", "USDT"),
                    "success":           True,
                }
            return {"available_balance": 0, "success": False, "error": data.get("msg")}
    except Exception as e:
        return {"available_balance": 0, "success": False, "error": str(e)}


# ── Futures Positions ─────────────────────────────────────────────────────────
async def get_futures_positions() -> dict:
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
                positions = [p for p in data["data"] if float(p.get("currentQty", 0)) != 0]
                return {"positions": positions, "success": True}
            return {"positions": [], "success": False, "error": data.get("msg")}
    except Exception as e:
        return {"positions": [], "success": False, "error": str(e)}


# ── Prices ────────────────────────────────────────────────────────────────────
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


# ── Spot Order ────────────────────────────────────────────────────────────────
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


# ── Futures Order ─────────────────────────────────────────────────────────────
async def place_futures_order(symbol: str, side: str, size: int,
                               leverage: int = 3, reduce_only: bool = False) -> dict:
    """
    Place futures market order on KuCoin Futures.
    side: 'buy' (long) or 'sell' (short)
    size: number of contracts (1 contract = 1 USD for XBTUSDTM)
    """
    endpoint = "/api/v1/orders"
    body = json.dumps({
        "clientOid":   f"qtf_{int(time.time()*1000)}",
        "side":        side,
        "symbol":      symbol,
        "type":        "market",
        "size":        size,
        "leverage":    str(leverage),
        "reduceOnly":  reduce_only,
    })
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                KUCOIN_FUT_URL + endpoint,
                headers=kucoin_headers("POST", endpoint, body),
                data=body,
                timeout=aiohttp.ClientTimeout(total=10),
            )
            return await r.json()
    except Exception as e:
        return {"code": "error", "msg": str(e)}


# ── Technical Analysis ────────────────────────────────────────────────────────
def _ema(data: list, period: int) -> float:
    if not data:
        return 0.0
    if len(data) < period:
        return data[-1]
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
    if not candles or len(candles) < 5:
        return {"pattern": "insufficient_data", "signal": "HOLD", "confidence": 0.5}
    try:
        chron   = list(reversed(candles))
        closes  = [float(c[2]) for c in chron]
        highs   = [float(c[3]) for c in chron]
        lows    = [float(c[4]) for c in chron]
        volumes = [float(c[5]) for c in chron]
        n       = len(closes)

        current      = closes[-1]
        open_p       = closes[0]
        price_change = (current - open_p) / open_p * 100

        ranges     = [highs[i] - lows[i] for i in range(n)]
        volatility = (sum(ranges) / n) / current * 100

        ema_fast = _ema(closes, min(7,  n))
        ema_slow = _ema(closes, min(14, n))
        ema_bull = ema_fast > ema_slow * 1.0005
        ema_bear = ema_fast < ema_slow * 0.9995

        rsi_val = _rsi(closes)

        recent_high = max(highs[-8:]) if n >= 8 else max(highs)
        recent_low  = min(lows[-8:])  if n >= 8 else min(lows)
        price_range = recent_high - recent_low
        price_pos   = (current - recent_low) / price_range * 100 if price_range > 0 else 50.0

        avg_vol_recent = sum(volumes[-5:])  / 5  if n >= 5  else volumes[-1]
        avg_vol_old    = sum(volumes[-15:-5])/ 10 if n >= 15 else avg_vol_recent
        vol_ratio      = avg_vol_recent / avg_vol_old if avg_vol_old > 0 else 1.0

        strong_move   = abs(price_change) > 1.0
        vol_confirmed = vol_ratio > 1.2

        # Pattern detection
        if rsi_val < 35 and price_pos < 30 and price_change > 0:
            pattern, signal = "oversold_bounce", "BUY"
            confidence = 0.72 + (0.08 if vol_confirmed else 0) + min((35 - rsi_val) * 0.003, 0.05)
        elif rsi_val > 65 and price_pos > 70 and price_change < 0:
            pattern, signal = "overbought_drop", "SELL"
            confidence = 0.72 + (0.08 if vol_confirmed else 0)
        elif rsi_val < 30 and ema_bull:
            pattern, signal = "oversold_reversal", "BUY"
            confidence = 0.82 + (0.05 if vol_confirmed else 0)
        elif rsi_val > 70 and ema_bear:
            pattern, signal = "overbought_reversal", "SELL"
            confidence = 0.80 + (0.05 if vol_confirmed else 0)
        elif ema_bull and strong_move and price_change > 0 and vol_confirmed:
            pattern, signal = "uptrend_breakout", "BUY"
            confidence = 0.78 + min(abs(price_change) * 0.02, 0.10)
        elif ema_bear and strong_move and price_change < 0 and vol_confirmed:
            pattern, signal = "downtrend_breakdown", "SELL"
            confidence = 0.76 + min(abs(price_change) * 0.02, 0.10)
        elif ema_bull and price_change > 0.3:
            pattern, signal = "uptrend", "BUY"
            confidence = 0.68 + (0.06 if vol_confirmed else 0)
        elif ema_bear and price_change < -0.3:
            pattern, signal = "downtrend", "SELL"
            confidence = 0.68 + (0.06 if vol_confirmed else 0)
        elif volatility > 4:
            pattern, signal = "high_volatility", "HOLD"
            confidence = 0.50
        else:
            pattern, signal = "consolidation", "HOLD"
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
    score = 50.0
    score += price_change * 5.0

    if vision and vision.get("pattern") not in ("error", "insufficient_data"):
        rsi     = vision.get("rsi", 50.0)
        pattern = vision.get("pattern", "consolidation")

        is_reversal = pattern in (
            "oversold_bounce", "oversold_reversal",
            "overbought_drop", "overbought_reversal",
        )

        score += (rsi - 50.0) * 0.2

        if not is_reversal:
            if vision.get("ema_bullish") is True:
                score += 8.0
            elif vision.get("ema_bullish") is False:
                score -= 8.0

        vol_ratio = vision.get("vol_ratio", 1.0)
        if vol_ratio > 1.2:
            score += 5.0 if price_change >= 0 else -5.0

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
        confidence = round(min(0.60 + (score - MIN_Q_SCORE) / (100 - MIN_Q_SCORE) * 0.35, 0.95), 2)
    elif score <= (100 - MIN_Q_SCORE):
        action     = "SELL"
        confidence = round(min(0.60 + ((100 - MIN_Q_SCORE) - score) / (100 - MIN_Q_SCORE) * 0.35, 0.95), 2)
    else:
        action     = "HOLD"
        confidence = round(0.40 + abs(score - 50.0) / 50.0 * 0.20, 2)

    if vision and vision.get("signal") == action and action != "HOLD":
        confidence = round(max(confidence, vision.get("confidence", 0.0)), 2)

    return {"action": action, "confidence": confidence, "q_score": round(score, 1)}


# ── Spot Trade with TP/SL ─────────────────────────────────────────────────────
async def execute_spot_trade(symbol: str, signal: dict, vision: dict,
                              price: float, trade_usdt: float) -> bool:
    """Execute spot trade and immediately place stop-loss order."""
    side = "buy" if signal["action"] == "BUY" else "sell"
    size = round(trade_usdt / price, 6)
    if size < 0.000001:
        return False

    result = await place_spot_order(symbol, side, size)
    if result.get("code") != "200000":
        print(f"[spot] Order failed {symbol}: {result.get('msg')}")
        return False

    tp = round(price * (1 + TP_PCT if side == "buy" else 1 - TP_PCT), 6)
    sl = round(price * (1 - SL_PCT if side == "buy" else 1 + SL_PCT), 6)

    log_trade(symbol, side, price, size, tp, sl,
              signal["confidence"], signal["q_score"], vision.get("pattern","?"), "spot")

    last_signals[symbol] = {"action": signal["action"], "ts": time.time()}
    return True


# ── Futures Trade ─────────────────────────────────────────────────────────────
async def execute_futures_trade(symbol: str, signal: dict, vision: dict,
                                 price: float, available_usdt: float) -> bool:
    """
    Execute futures order.
    Contract size for KuCoin:
      XBTUSDTM = 0.001 BTC per contract
      ETHUSDTM = 0.01  ETH per contract
      SOLUSDTM = 1     SOL per contract
    """
    # Map spot symbol to futures symbol and contract value
    FUTURES_MAP = {
        "BTC-USDT": ("XBTUSDTM", 0.001),
        "ETH-USDT": ("ETHUSDTM", 0.01),
        "SOL-USDT": ("SOLUSDTM", 1.0),
    }
    if symbol not in FUTURES_MAP:
        return False

    fut_symbol, contract_size = FUTURES_MAP[symbol]
    side = "buy" if signal["action"] == "BUY" else "sell"

    # Calculate number of contracts based on risk
    trade_usdt    = available_usdt * RISK_PER_TRADE
    contract_value = price * contract_size
    n_contracts   = max(1, int(trade_usdt * MAX_LEVERAGE / contract_value))

    result = await place_futures_order(fut_symbol, side, n_contracts, MAX_LEVERAGE)
    if result.get("code") != "200000":
        print(f"[futures] Order failed {fut_symbol}: {result.get('msg')}")
        return False

    tp = round(price * (1 + TP_PCT if side == "buy" else 1 - TP_PCT), 4)
    sl = round(price * (1 - SL_PCT if side == "buy" else 1 + SL_PCT), 4)

    log_trade(fut_symbol, side, price, n_contracts, tp, sl,
              signal["confidence"], signal["q_score"], vision.get("pattern","?"), "futures")

    last_signals[f"FUT_{symbol}"] = {"action": signal["action"], "ts": time.time()}
    return True


# ── Auto-trading Engine ───────────────────────────────────────────────────────
async def auto_trade_cycle():
    global last_q_score

    prices_data = await get_all_prices()
    if not prices_data.get("success"):
        return

    # Get both balances in parallel
    spot_bal, fut_bal = await asyncio.gather(get_balance(), get_futures_balance())
    spot_usdt = spot_bal.get("total_usdt", 0)
    fut_usdt  = fut_bal.get("available_balance", 0)

    spot_trade_usdt = spot_usdt * RISK_PER_TRADE
    signals_fired   = []

    for symbol, price_data in prices_data["prices"].items():
        change = price_data.get("change", 0)
        price  = price_data.get("price", 0)
        if price <= 0:
            continue

        candles = await get_kucoin_chart(symbol)
        vision  = await analyze_chart_with_vision(symbol, candles)
        signal  = calc_signal(change, vision)

        if signal["action"] == "HOLD":
            continue
        if signal["confidence"] < MIN_CONFIDENCE:
            continue
        if not AUTOPILOT:
            continue

        # ── Spot trade ────────────────────────────────────────────────────────
        spot_key = symbol
        last_spot = last_signals.get(spot_key, {})
        spot_cooldown = (time.time() - last_spot.get("ts", 0)) < 3600

        if not spot_cooldown and spot_trade_usdt >= 1.0:
            ok = await execute_spot_trade(symbol, signal, vision, price, spot_trade_usdt)
            if ok:
                signals_fired.append({
                    "account": "spot", "symbol": symbol,
                    "action": signal["action"], "price": price,
                    "confidence": signal["confidence"], "q_score": signal["q_score"],
                    "pattern": vision.get("pattern","?"), "rsi": vision.get("rsi", 0),
                    "tp": round(price*(1+TP_PCT if signal["action"]=="BUY" else 1-TP_PCT),4),
                    "sl": round(price*(1-SL_PCT if signal["action"]=="BUY" else 1+SL_PCT),4),
                })

        # ── Futures trade (only BTC, ETH, SOL) ───────────────────────────────
        fut_key   = f"FUT_{symbol}"
        last_fut  = last_signals.get(fut_key, {})
        fut_cooldown = (time.time() - last_fut.get("ts", 0)) < 3600

        if symbol in ("BTC-USDT", "ETH-USDT", "SOL-USDT"):
            if not fut_cooldown and fut_usdt >= 1.0:
                ok = await execute_futures_trade(symbol, signal, vision, price, fut_usdt)
                if ok:
                    FUTURES_SYMS = {"BTC-USDT":"XBTUSDTM","ETH-USDT":"ETHUSDTM","SOL-USDT":"SOLUSDTM"}
                    signals_fired.append({
                        "account": f"futures {MAX_LEVERAGE}x",
                        "symbol": FUTURES_SYMS[symbol],
                        "action": signal["action"], "price": price,
                        "confidence": signal["confidence"], "q_score": signal["q_score"],
                        "pattern": vision.get("pattern","?"), "rsi": vision.get("rsi", 0),
                        "tp": round(price*(1+TP_PCT if signal["action"]=="BUY" else 1-TP_PCT),4),
                        "sl": round(price*(1-SL_PCT if signal["action"]=="BUY" else 1+SL_PCT),4),
                    })

    # ── Notify ────────────────────────────────────────────────────────────────
    if signals_fired:
        mode = "🧪 TEST" if TEST_MODE else "🚀 LIVE"
        msg  = f"⚛ *QuantumTrade AI v4.3 — {mode}*\n\n"
        for s in signals_fired:
            emoji = "🟢" if s["action"] == "BUY" else "🔴"
            msg += (
                f"{emoji} *{s['symbol']}* {s['action']} [{s['account']}]\n"
                f"   Цена: `${s['price']:,.4f}` · Q: `{s['q_score']}`\n"
                f"   Паттерн: `{s['pattern']}` · RSI: `{s['rsi']}`\n"
                f"   TP: `${s['tp']:,.4f}` · SL: `${s['sl']:,.4f}`\n"
                f"   Уверенность: `{int(s['confidence']*100)}%`\n\n"
            )
        await notify(msg)

    # ── BTC Q-Score notifications ─────────────────────────────────────────────
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
    mode = "🧪 TEST (риск 10%)" if TEST_MODE else "🚀 LIVE (риск 2%)"
    await notify(
        f"⚛ *QuantumTrade AI v4.3 запущен!*\n\n"
        f"✅ Спот-торговля активна\n"
        f"✅ Фьючерсная торговля активна\n"
        f"✅ EMA + RSI + Volume + Паттерны\n"
        f"✅ TP {int(TP_PCT*100)}% / SL {int(SL_PCT*100)}% (R:R = 1:2)\n"
        f"✅ Лог сделок включён\n"
        f"📊 Режим: {mode}\n"
        f"📊 Спот пары: BTC ETH SOL BNB XRP AVAX\n"
        f"📈 Фьючерсы: BTC ETH SOL · плечо {MAX_LEVERAGE}x\n"
        f"🎯 Мин. Q-Score: {MIN_Q_SCORE} · Мин. уверенность: {int(MIN_CONFIDENCE*100)}%"
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
        "version":        "4.3.0",
        "auto_trading":   AUTOPILOT,
        "test_mode":      TEST_MODE,
        "risk_per_trade": RISK_PER_TRADE,
        "last_qscore":    last_q_score,
        "min_confidence": MIN_CONFIDENCE,
        "min_q_score":    MIN_Q_SCORE,
        "max_leverage":   MAX_LEVERAGE,
        "tp_pct":         TP_PCT,
        "sl_pct":         SL_PCT,
        "trades_logged":  len(trade_log),
        "yandex_vision":  bool(YANDEX_VISION_KEY),
        "timestamp":      datetime.utcnow().isoformat(),
    }


@app.get("/api/balance")
async def api_balance():
    return await get_balance()


@app.get("/api/futures/balance")
async def api_futures_balance():
    return await get_futures_balance()


@app.get("/api/futures/positions")
async def api_futures_positions():
    return await get_futures_positions()


@app.get("/api/combined/balance")
async def api_combined_balance():
    """Returns both spot and futures balances together."""
    spot, futures = await asyncio.gather(get_balance(), get_futures_balance())
    total = spot.get("total_usdt", 0) + futures.get("available_balance", 0)
    return {
        "spot_usdt":    spot.get("total_usdt", 0),
        "futures_usdt": futures.get("available_balance", 0),
        "futures_equity": futures.get("account_equity", 0),
        "futures_unrealised_pnl": futures.get("unrealised_pnl", 0),
        "total_usdt":   round(total, 2),
        "spot_success":    spot.get("success", False),
        "futures_success": futures.get("success", False),
    }


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
    balance, prices, fut_bal = await asyncio.gather(
        get_balance(), get_all_prices(), get_futures_balance()
    )
    btc_change = prices["prices"].get("BTC-USDT", {}).get("change", 0)
    candles    = await get_kucoin_chart("BTC-USDT")
    vision     = await analyze_chart_with_vision("BTC-USDT", candles)
    signal     = calc_signal(btc_change, vision)
    return {
        "balance":         balance,
        "futures_balance": fut_bal,
        "total_usdt":      round(balance.get("total_usdt",0) + fut_bal.get("available_balance",0), 2),
        "prices":          prices,
        "signal":          signal,
        "vision":          vision,
        "autopilot":       AUTOPILOT,
        "config": {
            "risk":           RISK_PER_TRADE,
            "test_mode":      TEST_MODE,
            "min_confidence": MIN_CONFIDENCE,
            "min_q_score":    MIN_Q_SCORE,
            "max_leverage":   MAX_LEVERAGE,
            "tp_pct":         TP_PCT,
            "sl_pct":         SL_PCT,
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


@app.get("/api/trades")
async def api_trades(limit: int = 50):
    """Return recent trade log."""
    return {
        "trades":    list(reversed(trade_log))[:limit],
        "total":     len(trade_log),
        "open":      sum(1 for t in trade_log if t["status"] == "open"),
        "wins":      sum(1 for t in trade_log if t.get("pnl") and t["pnl"] > 0),
        "losses":    sum(1 for t in trade_log if t.get("pnl") and t["pnl"] <= 0),
        "total_pnl": round(sum(t.get("pnl") or 0 for t in trade_log), 4),
    }


@app.get("/api/polymarket")
async def api_polymarket():
    CRYPTO_KEYWORDS = [
        "bitcoin","btc","ethereum","eth","crypto","solana","sol",
        "binance","bnb","xrp","ripple","defi","nft","blockchain",
        "coinbase","stablecoin","altcoin","web3",
    ]

    def is_crypto(title: str) -> bool:
        return any(kw in title.lower() for kw in CRYPTO_KEYWORDS)

    def parse_outcome_prices(raw) -> list:
        if isinstance(raw, list):  return raw
        if isinstance(raw, str):
            try: return json.loads(raw)
            except: return []
        return []

    try:
        async with aiohttp.ClientSession() as s:
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
                title   = e.get("title", "")
                if not is_crypto(title):
                    continue
                markets = e.get("markets", [])
                if not markets:
                    continue
                prices_raw = parse_outcome_prices(markets[0].get("outcomePrices", "[]"))
                if not prices_raw:
                    continue
                try:
                    yes_prob = round(float(prices_raw[0]) * 100, 1)
                except (ValueError, TypeError):
                    continue
                if yes_prob in (0.0, 100.0):
                    continue
                volume = float(e.get("volume", 0))
                if volume < 1000:
                    continue
                result.append({"title": title, "yes_prob": yes_prob, "volume": volume})
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
    if req.is_futures:
        result = await place_futures_order(req.symbol, req.side, int(req.size), req.leverage)
    else:
        result = await place_spot_order(req.symbol, req.side, req.size)
    success = result.get("code") == "200000"
    if success:
        emoji = "🟢" if req.side == "buy" else "🔴"
        account = "futures" if req.is_futures else "spot"
        await notify(f"{emoji} *Ручная сделка [{account}]*\n`{req.symbol}` {req.side.upper()} · размер: `{req.size}`")
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
