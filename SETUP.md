[server.py](https://github.com/user-attachments/files/26231220/server.py)
"""
QuantumTrade AI - FastAPI Backend v6.8.0
Phase1: Fear&Greed, Polymarket→Q-Score, Whale, TP/SL stop-orders, Position Monitor, Strategy A/B/C
Phase3: Origin QC QAOA — квантовая оптимизация портфеля (CPU симулятор + Wukong 180 реальный чип)
Phase5: Claude Vision — AI-анализ графиков
Phase6: Origin QC Wukong 180 — реальный квантовый чип (авто-переключение по ORIGIN_QC_TOKEN)
"""

import asyncio
import hashlib
import hmac
import time
import base64
import json
import os
import math
import random
from datetime import datetime
from typing import Optional, List, Dict
import aiohttp
from fastapi import FastAPI, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="QuantumTrade AI", version="7.1.2")
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
ORIGIN_QC_TOKEN   = os.getenv("ORIGIN_QC_TOKEN", "")     # Phase 6: Origin QC Wukong 180

RISK_PER_TRADE = 0.25  # v6.9: Strategy C (25% of balance)
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.66"))
MIN_Q_SCORE    = int(os.getenv("MIN_Q_SCORE", "65"))  # v6.7: 78→65 (extreme fear market, F&G≈11)
# v7.1.2: per-pair Q thresholds (tune per volatility profile)
PAIR_Q_THRESHOLDS: dict = {"BTC-USDT": 64, "ETH-USDT": 66, "SOL-USDT": 65,
                            "BNB-USDT": 65, "XRP-USDT": 65, "AVAX-USDT": 65}
COOLDOWN       = int(os.getenv("COOLDOWN", "600"))   # v6.8: 300→600s (10 мин — меньше шума, лучше сигналы)
MAX_LEVERAGE   = int(os.getenv("MAX_LEVERAGE", "5"))   # v6.9: Strategy C default
# v6.9: Strategy C — risk 25%, leverage 5x, TP=5%, SL=2.5% (backtested optimal for bear market)
TP_PCT         = 0.05   # v6.9: Strategy C (5%)
SL_PCT         = 0.025  # v6.9: Strategy C (2.5%)
TEST_MODE      = os.getenv("TEST_MODE", "false").lower() == "true"  # v6.7: default LIVE mode
if TEST_MODE:
    RISK_PER_TRADE = 0.10

AUTOPILOT  = True
SPOT_PAIRS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT", "AVAX-USDT"]
FUT_PAIRS  = ["XBTUSDTM", "ETHUSDTM", "SOLUSDTM"]

last_signals  = {}
last_q_score  = 0.0
trade_log: List[dict] = []

# ── Персистентное хранилище сделок ─────────────────────────────────────────────
# Выживает при редеплое — пишем в /tmp/trades.json (Railway ephemeral storage)
_TRADES_FILE = "/tmp/qt_trades.json"

def _load_trades_from_disk():
    """Загружаем историю сделок при старте."""
    global trade_log
    try:
        if os.path.exists(_TRADES_FILE):
            with open(_TRADES_FILE, "r") as f:
                trade_log = json.load(f)
            print(f"[trades] загружено {len(trade_log)} сделок из {_TRADES_FILE}")
    except Exception as e:
        print(f"[trades] ошибка загрузки: {e}")

def _save_trades_to_disk():
    """Сохраняем trade_log на диск после каждой новой сделки."""
    try:
        with open(_TRADES_FILE, "w") as f:
            json.dump(trade_log[-500:], f)  # храним последние 500
    except Exception as e:
        print(f"[trades] ошибка записи: {e}")

# ── QAOA State ─────────────────────────────────────────────────────────────────
_quantum_bias: Dict[str, float] = {}   # symbol → bias [-15..+15]
_quantum_ts: float = 0.0               # timestamp последнего запуска

# ── Phase 6: Origin QC Wukong 180 ──────────────────────────────────────────────
_qcloud_ready: bool = False            # True после успешной инициализации чипа
_qvm_instance = None                   # глобальный инстанс QCloud (ленивая init)


def _init_qcloud() -> bool:
    """
    Пытается подключиться к Origin QC Wukong 180 через pyqpanda3.
    Вызывается при старте, если ORIGIN_QC_TOKEN задан.
    Возвращает True при успехе, False → CPU fallback.
    """
    global _qcloud_ready, _qvm_instance
    if not ORIGIN_QC_TOKEN:
        print("[qaoa] ORIGIN_QC_TOKEN не задан → CPU симулятор")
        return False
    try:
        from pyqpanda3 import QCloud, QMachineType  # type: ignore
        qvm = QCloud()
        qvm.init_qvm(ORIGIN_QC_TOKEN, QMachineType.Wukong)
        qvm.set_chip_id("72")  # Wukong-180: публичный чип #72
        _qvm_instance = qvm
        _qcloud_ready = True
        print("[qaoa] ✅ Origin QC Wukong 180 подключён (chip_id=72)")
        return True
    except ImportError:
        print("[qaoa] pyqpanda3 не установлен → CPU fallback")
    except Exception as e:
        print(f"[qaoa] Origin QC ошибка инициализации: {e} → CPU fallback")
    _qcloud_ready = False
    return False


# ── QAOA Module (Phase 3 + Phase 6: Origin QC) ─────────────────────────────────
# CPU-симулятор активен по умолчанию.
# При наличии ORIGIN_QC_TOKEN и pyqpanda3 — авто-переключение на Wukong 180.
#
# Корреляционная матрица (BTC ETH SOL BNB XRP AVAX)
PAIR_NAMES = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT", "AVAX-USDT"]
CORR_MATRIX = [
    # BTC    ETH    SOL    BNB    XRP    AVAX
    [1.00,  0.85,  0.78,  0.72,  0.60,  0.75],  # BTC
    [0.85,  1.00,  0.80,  0.70,  0.58,  0.77],  # ETH
    [0.78,  0.80,  1.00,  0.65,  0.55,  0.80],  # SOL
    [0.72,  0.70,  0.65,  1.00,  0.62,  0.68],  # BNB
    [0.60,  0.58,  0.55,  0.62,  1.00,  0.60],  # XRP
    [0.75,  0.77,  0.80,  0.68,  0.60,  1.00],  # AVAX
]
N_PAIRS = len(PAIR_NAMES)


def _qaoa_cpu_simulate(price_changes: List[float], p_layers: int = 2) -> List[float]:
    """
    QAOA CPU симулятор: оптимизирует портфельные веса с учётом корреляций.
    Возвращает bias [-15..+15] для каждой пары.
    p_layers: глубина схемы (1-3, больше = точнее, медленнее).
    """
    n = N_PAIRS

    # 1. Строим QUBO матрицу задачи максимизации Шарпа
    # Q_ij = corr[i][j] (штраф за коррелированные позиции)
    # Линейный член: -momentum[i] (награда за сильный тренд)
    momentum = [max(-1.0, min(1.0, pc / 5.0)) for pc in price_changes]

    # 2. Инициализируем углы QAOA (gamma, beta) случайно с seed
    random.seed(int(time.time()) // 900)  # меняется раз в 15 мин
    gamma = [random.uniform(0.1, math.pi) for _ in range(p_layers)]
    beta  = [random.uniform(0.1, math.pi / 2) for _ in range(p_layers)]

    # 3. Симулируем квантовое состояние (упрощённая vector sim)
    # |ψ⟩ = H^n|0⟩ → apply U_C(γ) → U_B(β) → measure
    # Начальное состояние: суперпозиция всех 2^n битовых строк
    state_size = 1 << n  # 64 состояния для 6 кубитов
    amplitudes = [complex(1.0 / math.sqrt(state_size))] * state_size

    for layer in range(p_layers):
        # U_C(γ): применяем cost unitary
        new_amp = [complex(0)] * state_size
        for s in range(state_size):
            bits = [(s >> i) & 1 for i in range(n)]
            # cost = -Σ momentum[i]*bits[i] + γ*Σ corr[i][j]*bits[i]*bits[j]
            cost = 0.0
            for i in range(n):
                cost -= momentum[i] * bits[i]
                for j in range(i + 1, n):
                    cost += gamma[layer] * CORR_MATRIX[i][j] * bits[i] * bits[j]
            phase = complex(math.cos(cost), -math.sin(cost))
            new_amp[s] = amplitudes[s] * phase
        amplitudes = new_amp

        # U_B(β): mixing unitary (X-rotation на каждом кубите)
        for q in range(n):
            new_amp = [complex(0)] * state_size
            cos_b = math.cos(beta[layer])
            sin_b = math.sin(beta[layer])
            for s in range(state_size):
                # flip бит q
                s_flip = s ^ (1 << q)
                new_amp[s] += amplitudes[s] * complex(cos_b, 0)
                new_amp[s] += amplitudes[s_flip] * complex(0, sin_b)
            amplitudes = new_amp

    # 4. Вычисляем ожидаемое значение <Z_i> для каждого кубита
    z_exp = [0.0] * n
    for s in range(state_size):
        prob = (amplitudes[s] * amplitudes[s].conjugate()).real
        bits = [(s >> i) & 1 for i in range(n)]
        for i in range(n):
            z_exp[i] += prob * (1 - 2 * bits[i])  # +1 если bit=0, -1 если bit=1

    # 5. Конвертируем в bias [-15..+15]
    # z_exp[i] ∈ [-1..+1] → bias = z_exp * 15 * momentum_sign
    bias = []
    for i in range(n):
        b = z_exp[i] * 15.0
        # Усиливаем сигнал в направлении momentum
        if momentum[i] > 0.1:
            b = abs(b)
        elif momentum[i] < -0.1:
            b = -abs(b)
        bias.append(round(b, 1))

    return bias


def _qaoa_wukong_run(price_changes: List[float], p_layers: int = 1) -> List[float]:
    """
    Phase 6: QAOA на реальном чипе Origin Wukong 180.
    Строит 6-кубитную QAOA схему, отправляет на аппаратный чип, парсит гистограмму.
    p_layers=1 (на реальном железе шум растёт с глубиной — используем p=1).
    Возвращает bias [-15..+15] для каждой пары.
    Требует: _qcloud_ready=True и _qvm_instance инициализирован.
    """
    from pyqpanda3 import QProg, H, Rz, Rx, CNOT, measure_all  # type: ignore

    n = N_PAIRS  # 6 кубитов
    momentum = [max(-1.0, min(1.0, pc / 5.0)) for pc in price_changes]

    # Оптимальные углы QAOA p=1 (предварительно откалиброваны на CPU)
    gamma = 0.8   # cost unitary angle
    beta  = 0.4   # mixing unitary angle

    # ── Строим квантовую схему QAOA ──────────────────────────────────────────
    qv  = _qvm_instance.allocate_qubit(n)    # 6 кубитов
    cv  = _qvm_instance.allocate_cbit(n)     # 6 классических бит для измерений
    prog = QProg()

    # Инициализация: суперпозиция H^⊗6|0⟩
    for i in range(n):
        prog << H(qv[i])

    # Cost unitary U_C(γ):
    # ZZ-взаимодействие для коррелированных пар (только сильные связи corr > 0.5)
    for i in range(n):
        for j in range(i + 1, n):
            if CORR_MATRIX[i][j] > 0.5:
                angle = 2.0 * gamma * CORR_MATRIX[i][j]
                prog << CNOT(qv[i], qv[j])
                prog << Rz(qv[j], angle)
                prog << CNOT(qv[i], qv[j])
    # Линейные члены: momentum bias
    for i in range(n):
        prog << Rz(qv[i], -2.0 * gamma * momentum[i])

    # Mixing unitary U_B(β): X-ротации
    for i in range(n):
        prog << Rx(qv[i], 2.0 * beta)

    # Измерения
    prog << measure_all(qv, cv)

    # ── Запуск на реальном чипе (1024 выборки) ───────────────────────────────
    result = _qvm_instance.run_with_configuration(prog, cv, 1024)
    # result: dict[str, int], ключ = битовая строка "010110", значение = кол-во

    # Вычисляем <Z_i> из гистограммы
    z_exp = [0.0] * n
    total_shots = sum(result.values()) if result else 0
    if total_shots > 0:
        for bitstring, count in result.items():
            # Wukong возвращает строку MSB-first: bitstring[0] = кубит 0
            for i in range(min(n, len(bitstring))):
                bit = int(bitstring[i])
                z_exp[i] += (count / total_shots) * (1 - 2 * bit)  # +1→0, -1→1
    else:
        print("[qaoa_wukong] пустой результат — возвращаем нули")
        return [0.0] * n

    # Конвертируем в bias [-15..+15], усиливаем в направлении momentum
    bias = []
    for i in range(n):
        b = z_exp[i] * 15.0
        if momentum[i] > 0.1:
            b = abs(b)
        elif momentum[i] < -0.1:
            b = -abs(b)
        bias.append(round(b, 1))

    return bias


async def run_qaoa_optimization(price_changes: Dict[str, float]) -> Dict[str, float]:
    """
    Phase 3 + Phase 6: QAOA оптимизация с авто-выбором бэкенда.
    - Если ORIGIN_QC_TOKEN задан и pyqpanda3 доступен → реальный чип Wukong 180
    - Иначе → CPU симулятор (6 кубитов, p=2)
    Обновляет глобальный _quantum_bias. Вызывается каждые 15 минут.
    """
    global _quantum_bias, _quantum_ts
    changes_list = [price_changes.get(p, 0.0) for p in PAIR_NAMES]
    chip_used = "CPU_simulator"
    try:
        if _qcloud_ready and _qvm_instance is not None:
            # ── Phase 6: реальный квантовый чип ──────────────────────────────
            bias_list = await asyncio.get_event_loop().run_in_executor(
                None, _qaoa_wukong_run, changes_list, 1  # p=1 на железе
            )
            chip_used = "Wukong_180"
        else:
            # ── Phase 3: CPU симулятор ────────────────────────────────────────
            bias_list = await asyncio.get_event_loop().run_in_executor(
                None, _qaoa_cpu_simulate, changes_list, 2  # p=2 на CPU
            )
        _quantum_bias = {PAIR_NAMES[i]: bias_list[i] for i in range(N_PAIRS)}
        _quantum_ts = time.time()
        log_str = " ".join(f"{p.split('-')[0]}={b:+.1f}" for p, b in _quantum_bias.items())
        print(f"[qaoa/{chip_used}] bias: {log_str}")
    except Exception as e:
        print(f"[qaoa] error ({chip_used}): {e}")
        _quantum_bias = {p: 0.0 for p in PAIR_NAMES}
    return _quantum_bias

def log_trade(symbol, side, price, size, tp, sl, confidence, q_score, pattern, account="spot"):
    trade_log.append({
        "id": len(trade_log) + 1, "ts": datetime.utcnow().isoformat(), "open_ts": time.time(),
        "symbol": symbol, "side": side, "price": price, "size": size,
        "tp": tp, "sl": sl, "confidence": confidence, "q_score": q_score,
        "pattern": pattern, "account": account, "status": "open", "pnl": None,
    })
    if len(trade_log) > 500:
        trade_log.pop(0)
    _save_trades_to_disk()


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


# ── Yandex Vision — свечной график + OCR паттернов ────────────────────────────
def _render_candles_png_b64(candles: list, width: int = 400, height: int = 280) -> str:
    """Рисует свечной график через PIL и возвращает base64 PNG."""
    try:
        from PIL import Image, ImageDraw
        import io, base64 as _b64

        if not candles or len(candles) < 5:
            return ""

        chron  = list(reversed(candles[:24]))  # oldest first
        opens  = [float(c[1]) for c in chron]
        closes = [float(c[2]) for c in chron]
        highs  = [float(c[3]) for c in chron]
        lows   = [float(c[4]) for c in chron]

        p_min  = min(lows);  p_max = max(highs)
        p_rng  = p_max - p_min or 1
        pad    = 24
        cw     = width - pad * 2
        ch     = height - pad * 2
        cand_w = max(3, cw // len(chron) - 2)

        img  = Image.new("RGB", (width, height), (15, 15, 25))
        draw = ImageDraw.Draw(img)

        def p2y(p):
            return int(pad + ch - (p - p_min) / p_rng * ch)

        # Сетка
        for pct in [0.25, 0.5, 0.75]:
            y = p2y(p_min + p_rng * pct)
            draw.line([(pad, y), (width - pad, y)], fill=(40, 40, 60), width=1)

        # Свечи
        for i, (o, c, h, l) in enumerate(zip(opens, closes, highs, lows)):
            xc   = pad + i * (cw // len(chron)) + cand_w // 2
            bull = c >= o
            col  = (0, 200, 100) if bull else (220, 50, 50)
            draw.line([(xc, p2y(h)), (xc, p2y(l))], fill=col, width=1)
            yt, yb = min(p2y(o), p2y(c)), max(p2y(o), p2y(c))
            yb = max(yb, yt + 2)
            draw.rectangle([(xc - cand_w//2, yt), (xc + cand_w//2, yb)], fill=col)

        # Ценовые метки для OCR
        for price, label in [
            (p_min,      f"LOW:{p_min:.0f}"),
            (p_max,      f"HIGH:{p_max:.0f}"),
            (closes[-1], f"CLOSE:{closes[-1]:.0f}"),
            (opens[0],   f"OPEN:{opens[0]:.0f}"),
        ]:
            y = p2y(price)
            draw.text((2, max(0, y - 7)), label, fill=(200, 200, 200))

        # Тренд-линия
        n = len(closes)
        x1 = pad + cand_w // 2
        x2 = pad + (n - 1) * (cw // n) + cand_w // 2
        draw.line([(x1, p2y(closes[0])), (x2, p2y(closes[-1]))],
                  fill=(100, 150, 255), width=1)

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        return _b64.b64encode(buf.read()).decode("utf-8")

    except Exception as e:
        print(f"[vision render] {e}")
        return ""


async def call_yandex_vision(img_b64: str) -> dict:
    """Отправляет PNG в Yandex Vision OCR и возвращает распознанный текст."""
    if not YANDEX_VISION_KEY or not YANDEX_FOLDER_ID or not img_b64:
        return {"text": "", "success": False}
    try:
        payload = {
            "folderId": YANDEX_FOLDER_ID,
            "analyzeSpecs": [{
                "content":  img_b64,
                "mimeType": "image/png",
                "features": [{
                    "type": "TEXT_DETECTION",
                    "textDetectionConfig": {"languageCodes": ["en"]}
                }]
            }]
        }
        headers = {
            "Authorization": f"Api-Key {YANDEX_VISION_KEY}",
            "Content-Type":  "application/json",
        }
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze",
                json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=8)
            )
            data = await r.json()

        # Собираем весь текст из результата
        words = []
        for res in data.get("results", []):
            for inner in res.get("results", []):
                for page in inner.get("textDetection", {}).get("pages", []):
                    for block in page.get("blocks", []):
                        for line in block.get("lines", []):
                            for word in line.get("words", []):
                                words.append(word.get("text", ""))
        text = " ".join(words)
        return {"text": text, "words": words, "success": True}
    except Exception as e:
        return {"text": "", "success": False, "error": str(e)}


def parse_vision_bonus(ocr_text: str, vision_dict: dict) -> float:
    """
    Анализирует OCR-текст с графика → ±8 к Q-Score.
    Vision рисует: HIGH:2065 LOW:2048 CLOSE:2051 OPEN:2060
    Но иногда OPEN не попадает в кадр — используем price_change из vision_dict.
    """
    if not ocr_text:
        return 0.0
    text = ocr_text.upper()
    bonus = 0.0
    try:
        import re as _re
        nums = {}
        # Ищем все числа после меток (включая десятичные)
        for label in ["HIGH", "LOW", "CLOSE", "OPEN"]:
            m = _re.search(rf"{label}[:\s]+(\d+\.?\d*)", text)
            if m:
                nums[label] = float(m.group(1))

        ema_bull     = vision_dict.get("ema_bullish", None)
        price_change = vision_dict.get("price_change", 0.0)  # уже посчитан

        # Используем price_change из технического анализа (надёжнее чем OCR OPEN)
        pct_move = price_change

        # Если OCR всё же дал CLOSE и OPEN — используем их (точнее)
        if "CLOSE" in nums and "OPEN" in nums and nums["OPEN"] > 0:
            pct_move = (nums["CLOSE"] - nums["OPEN"]) / nums["OPEN"] * 100

        # Vision подтверждает тренд → усиливаем сигнал
        if pct_move < -1.5 and ema_bull is False:
            bonus = -8.0   # сильный нисходящий + EMA медвежья
        elif pct_move < -0.5 and ema_bull is False:
            bonus = -5.0   # умеренный нисходящий
        elif pct_move < -0.3:
            bonus = -3.0   # слабый нисходящий
        elif pct_move > 1.5 and ema_bull is True:
            bonus = +8.0   # сильный восходящий + EMA бычья
        elif pct_move > 0.5 and ema_bull is True:
            bonus = +5.0   # умеренный восходящий
        elif pct_move > 0.3:
            bonus = +3.0   # слабый восходящий

        # Позиция цены в диапазоне HIGH/LOW → дополнительный сигнал
        if "HIGH" in nums and "LOW" in nums and "CLOSE" in nums:
            rng = nums["HIGH"] - nums["LOW"]
            if rng > 0:
                price_pos = (nums["CLOSE"] - nums["LOW"]) / rng * 100
                if price_pos < 20 and pct_move < 0:
                    bonus -= 2.0  # цена у дна + падение → усиливаем SELL
                elif price_pos > 80 and pct_move > 0:
                    bonus += 2.0  # цена у вершины + рост → усиливаем BUY

    except Exception:
        pass
    return round(max(-8.0, min(8.0, bonus)), 1)


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

        result = {"pattern": pattern, "signal": signal, "confidence": round(min(confidence, 0.95), 2),
                  "price_change": round(price_change, 2), "volatility": round(volatility, 2),
                  "rsi": rsi_val, "ema_fast": round(ema_fast, 4), "ema_slow": round(ema_slow, 4),
                  "ema_bullish": ema_bull, "vol_ratio": round(vol_ratio, 2), "price_pos_pct": round(price_pos, 1),
                  "vision_bonus": 0.0, "vision_ocr": ""}
        # ── Phase 5: Claude Vision (нативный AI-анализ графика) ─────────────────
        if ANTHROPIC_API_KEY:
            img_b64 = _render_candles_png_b64(candles)
            if img_b64:
                cv = _cache_get(f"claude_vision_{symbol}", 180)
                if not cv:
                    cv = await _analyze_chart_claude_vision(img_b64, symbol, result)
                    _cache_set(f"claude_vision_{symbol}", cv)
                if cv and cv.get("success"):
                    result["vision_bonus"] = cv.get("bonus", 0.0)
                    result["vision_ocr"]   = cv.get("summary", "")
        return result
    except Exception as e:
        return {"pattern": "error", "signal": "HOLD", "confidence": 0.5,
                "error": str(e), "vision_bonus": 0.0, "vision_ocr": ""}


# ── Phase 5: Claude Vision — нативный AI-анализ свечного графика ──────────────
async def _analyze_chart_claude_vision(img_b64: str, symbol: str, tech: dict) -> dict:
    """
    Отправляет PNG графика в Claude Haiku с просьбой проанализировать паттерн.
    Возвращает bonus ∈ [-10, +10] и текстовое резюме.
    Haiku выбран за скорость и низкую стоимость (~$0.0003/вызов).
    """
    if not ANTHROPIC_API_KEY or not img_b64:
        return {"success": False, "bonus": 0.0, "summary": ""}
    try:
        tech_ctx = (
            f"Технический контекст: RSI={tech.get('rsi', 50):.0f}, "
            f"EMA_fast={'выше' if tech.get('ema_bullish') else 'ниже'} EMA_slow, "
            f"price_change={tech.get('price_change', 0):+.2f}%, "
            f"volatility={tech.get('volatility', 0):.2f}%, "
            f"price_pos={tech.get('price_pos_pct', 50):.0f}% от диапазона"
        )
        prompt = (
            f"Ты — торговый аналитик. Смотришь на свечной график {symbol} (последние 24 свечи).\n"
            f"{tech_ctx}\n\n"
            f"Проанализируй ВИЗУАЛЬНО:\n"
            f"1. Какой паттерн видишь? (флаг, клин, голова-плечи, треугольник, пробой и т.д.)\n"
            f"2. Направление: BULLISH / BEARISH / NEUTRAL\n"
            f"3. Уверенность: 0–100%\n"
            f"4. Ключевые уровни поддержки/сопротивления\n\n"
            f"Ответь СТРОГО в формате JSON:\n"
            f'{{ "pattern": "название", "direction": "BULLISH|BEARISH|NEUTRAL", '
            f'"confidence": 0-100, "support": число, "resistance": число, '
            f'"summary": "1 предложение по-русски" }}'
        )
        payload = {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 256,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/png", "data": img_b64
                    }},
                    {"type": "text", "text": prompt}
                ]
            }]
        }
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json=payload,
                timeout=aiohttp.ClientTimeout(total=12)
            )
            data = await r.json()

        raw = data.get("content", [{}])[0].get("text", "{}")
        # Извлекаем JSON из ответа
        import re as _re
        m = _re.search(r'\{.*\}', raw, _re.DOTALL)
        parsed = json.loads(m.group()) if m else {}

        direction   = parsed.get("direction", "NEUTRAL").upper()
        confidence  = min(100, max(0, int(parsed.get("confidence", 50)))) / 100.0
        summary     = parsed.get("summary", parsed.get("pattern", ""))

        # Рассчитываем bonus: BULLISH → +, BEARISH → -, масштаб по уверенности
        if direction == "BULLISH":
            bonus = round(confidence * 10, 1)    # max +10
        elif direction == "BEARISH":
            bonus = round(-confidence * 10, 1)   # min -10
        else:
            bonus = 0.0

        print(f"[claude_vision] {symbol}: {direction} {confidence*100:.0f}% → bonus={bonus:+.1f} | {summary}")
        return {"success": True, "bonus": bonus, "summary": summary,
                "pattern": parsed.get("pattern", ""), "direction": direction}

    except Exception as e:
        print(f"[claude_vision] {symbol} error: {e}")
        return {"success": False, "bonus": 0.0, "summary": ""}


# ── Telegram ───────────────────────────────────────────────────────────────────
async def notify(text: str):
    if not BOT_TOKEN or not ALERT_CHAT_ID: return
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": ALERT_CHAT_ID, "text": text, "parse_mode": "Markdown",
                      "disable_web_page_preview": True},
                timeout=aiohttp.ClientTimeout(total=5))
            resp = await r.json()
            if not resp.get("ok"):
                print(f"[notify] Telegram error: {resp.get('description','?')} | text[:60]={text[:60]!r}")
    except Exception as e:
        print(f"[notify] network error: {e}")


# ── Signal Generator v5.0 ──────────────────────────────────────────────────────
def calc_signal(price_change: float, vision: dict = None,
                fear_greed: dict = None, polymarket_bonus: float = 0.0,
                whale_bonus: float = 0.0, quantum_bias: float = 0.0) -> dict:
    """Q-Score v5.6: технический анализ + мировые события + киты + QAOA quantum bias."""
    score = 50.0

    # ── Технический анализ (max ±35) ─────────────────────────────────────
    score += price_change * 2.0  # было × 5 — слишком доминировало
    if vision and vision.get("pattern") not in ("error", "insufficient_data"):
        rsi     = vision.get("rsi", 50.0)
        pattern = vision.get("pattern", "consolidation")
        is_reversal = pattern in ("oversold_bounce", "oversold_reversal", "overbought_drop", "overbought_reversal")
        score += (rsi - 50.0) * 0.2
        if not is_reversal:
            if vision.get("ema_bullish") is True:  score += 5.0   # v5.7: 8→5 (убираем перекос к BUY)
            elif vision.get("ema_bullish") is False: score -= 5.0  # v5.7: -8→-5
        vol_ratio = vision.get("vol_ratio", 1.0)
        if vol_ratio > 1.2: score += 5.0 if price_change >= 0 else -5.0
        pattern_bonus_map = {
            "oversold_bounce": +10, "oversold_reversal": +10, "uptrend_breakout": +7,
            "uptrend": +4, "consolidation": 0, "high_volatility": -3,
            "downtrend": -4, "downtrend_breakdown": -7, "overbought_reversal": -10, "overbought_drop": -10
        }
        score += pattern_bonus_map.get(pattern, 0)
        # ── Yandex Vision OCR бонус (max ±8) ─────────────────────────────
        score += vision.get("vision_bonus", 0.0)

    # ── Внешние сигналы (max ±23) ─────────────────────────────────────────
    fg_bonus = fear_greed.get("bonus", 0) if fear_greed else 0
    score += fg_bonus          # Fear&Greed контрарный: ±8
    score += polymarket_bonus  # Polymarket events v7.0: ±8 (multi-query smart scoring)
    score += whale_bonus       # Whale flow: ±5 (упрощённо)

    # ── QAOA Quantum Bias (max ±15) ───────────────────────────────────────
    q_b = max(-15.0, min(15.0, quantum_bias))  # clamp безопасности
    score += q_b

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
            "quantum_bias": round(q_b, 1),
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
        # Контрарная логика: Extreme Fear → ждём разворота вверх (+)
        # НО: слишком сильный бонус гасит SELL сигналы при медвежьем рынке
        # Поэтому при Extreme Fear даём умеренный бонус +3 (не +8)
        if val <= 15:   bonus = +3   # Extreme Fear — рынок явно перепродан
        elif val <= 25: bonus = +6   # Fear — умеренный контрарный
        elif val <= 40: bonus = +3
        elif val <= 60: bonus = 0
        elif val <= 75: bonus = -4
        else:           bonus = -7   # Extreme Greed → сильный SELL сигнал
        result = {"value": val, "classification": cls, "bonus": bonus, "success": True}
        _cache_set("fear_greed", result)
        return result
    except Exception as e:
        return {"value": 50, "classification": "Neutral", "bonus": 0, "success": False, "error": str(e)}


# ── Whale Tracker ──────────────────────────────────────────────────────────────
async def get_whale_signal(symbol: str) -> dict:
    # v7.1.2: expanded to SOL, XRP, BNB via Blockchair (AVAX not supported → skip)
    coin_map = {
        "BTC-USDT": "bitcoin",
        "ETH-USDT": "ethereum",
        "SOL-USDT": "solana",
        "XRP-USDT": "ripple",
        "BNB-USDT": "binance-smart-chain",
    }
    coin = coin_map.get(symbol)
    if not coin: return {"bonus": 0, "success": False, "note": "unsupported"}
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


# ── Polymarket bonus v7.0 ─────────────────────────────────────────────────────
# Маркеры: ключевые слова → (направление, вес)
# direction: +1 = bullish если YES prob высок, -1 = bearish если YES prob высок
_PM_SIGNALS = [
    # Крипто-специфичные bullish
    ("bitcoin etf",            +1, 3.0), ("btc etf",              +1, 3.0),
    ("eth etf",                +1, 2.5), ("ethereum etf",         +1, 2.5),
    ("crypto etf",             +1, 2.0), ("bitcoin above",        +1, 2.0),
    ("btc above",              +1, 2.0), ("eth above",            +1, 1.5),
    ("bitcoin $",              +1, 1.5), ("crypto regulation",    +1, 1.5),
    ("sec approve",            +1, 2.0), ("bitcoin strategic",    +1, 2.0),
    ("us bitcoin reserve",     +1, 3.0), ("bitcoin reserve",      +1, 2.5),
    # Крипто-специфичные bearish
    ("bitcoin below",          -1, 2.0), ("btc below",            -1, 2.0),
    ("bitcoin crash",          -1, 2.5), ("crypto ban",           -1, 2.0),
    ("sec reject",             -1, 2.0), ("exchange hack",        -1, 1.5),
    ("exchange collapse",      -1, 2.5), ("bitcoin bankrupt",     -1, 2.0),
    # Макро-события (влияют на весь крипто)
    ("recession",              -1, 2.0), ("financial crisis",     -1, 2.5),
    ("fed rate hike",          -1, 1.5), ("fed hike",             -1, 1.5),
    ("interest rate hike",     -1, 1.5), ("us debt",              -1, 1.0),
    ("fed cut",                +1, 1.5), ("rate cut",             +1, 1.5),
    ("ceasefire",              +1, 1.0), ("peace deal",           +1, 1.0),
    ("war escalation",         -1, 1.5), ("nuclear",              -1, 2.0),
]

def calc_polymarket_bonus(symbol: str, events: list) -> float:
    """v7.0: умная классификация рынков Polymarket → бонус Q-Score ±8."""
    if not events: return 0.0
    total_score = 0.0
    total_weight = 0.0
    for ev in events:
        title = ev.get("title", "").lower()
        yes_p = ev.get("yes_prob", 50.0) / 100.0  # 0..1
        vol   = ev.get("volume", 0)
        # Вес события пропорционален объёму торгов
        vol_weight = min(1.0 + (vol / 100_000), 3.0)
        for keyword, direction, base_weight in _PM_SIGNALS:
            if keyword in title:
                # YES > 0.5 → сигнал direction, сила = |yes_p - 0.5| * 2
                signal_strength = (yes_p - 0.5) * 2  # -1..+1
                contribution = direction * signal_strength * base_weight * vol_weight
                total_score  += contribution
                total_weight += base_weight * vol_weight
    if total_weight == 0: return 0.0
    # Нормализуем и ограничиваем до ±8
    raw = total_score / max(total_weight, 1.0) * 8.0
    return round(max(-8.0, min(8.0, raw)), 2)


# ── Pending strategy choices ───────────────────────────────────────────────────
pending_strategies: dict = {}  # trade_id → {symbol, signal, vision, price, fut_usdt, expires_at}

# ── Стратегии A/B/C ────────────────────────────────────────────────────────────
STRATEGIES = {
    "A": {"name": "Консервативная", "risk": 0.05, "leverage": 2, "tp": 0.02, "sl": 0.01,  "emoji": "🛡",  "tag": "real"},
    "B": {"name": "Стандартная",    "risk": 0.10, "leverage": 3, "tp": 0.03, "sl": 0.015, "emoji": "⚖️", "tag": "real"},
    "C": {"name": "Бонусная",       "risk": 0.25, "leverage": 5, "tp": 0.05, "sl": 0.025, "emoji": "🚀",  "tag": "bonus"},
}
# DUAL: одновременно B (реальный) + C (бонусный агрессивный)
STRATEGY_TIMEOUT = 60   # 1 минута


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
        f"_Нет ответа 1 мин → авто стратегия B_"
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
    FMAP = {
        "BTC-USDT":  ("XBTUSDTM",  0.001),  # 0.001 BTC/контракт  ~$85 → нужно $17+ маржи
        "ETH-USDT":  ("ETHUSDTM",  0.01),   # 0.01  ETH/контракт  ~$22 → нужно ~$4.4 маржи
        "SOL-USDT":  ("SOLUSDTM",  1.0),    # 1     SOL/контракт  ~$130 → нужно $26 маржи
        "AVAX-USDT": ("AVAXUSDTM", 1.0),    # 1     AVAX/контракт ~$25  → нужно ~$5 маржи ✅
        "XRP-USDT":  ("XRPUSDTM",  10.0),   # 10    XRP/контракт  ~$25  → нужно ~$5 маржи ✅
    }
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

async def auto_execute_dynamic(trade_id: str):
    """Динамический выбор стратегии по Q-Score при таймауте."""
    await asyncio.sleep(STRATEGY_TIMEOUT)
    pending = pending_strategies.pop(trade_id, None)
    if not pending: return
    q = pending["signal"]["q_score"]
    # v6.9 Dynamic strategy: Q≥85→DUAL(B+C), Q≥65→C (оптимально для медвежьего рынка), else→B
    if q >= 85:
        auto_strategy = "D"
        label = "DUAL (B+C)"
    elif q >= 65:
        auto_strategy = "C"
        label = "C (агрессивная 🚀)"
    else:
        auto_strategy = "B"
        label = "B (стандартная)"
    log_activity(f"[strategy] timeout {trade_id} Q={q:.1f} → авто {label}")
    await notify(f"⏱ _Таймаут — Q={q:.0f} → стратегия {label}_")
    if auto_strategy == "D":
        await execute_dual_strategy(
            pending["symbol"], pending["signal"], pending["vision"],
            pending["price"], pending["fut_usdt"])
    else:
        await execute_with_strategy(
            auto_strategy, pending["symbol"], pending["signal"],
            pending["vision"], pending["price"], pending["fut_usdt"])


async def auto_trade_cycle():
    global last_q_score, MIN_Q_SCORE, COOLDOWN, AUTOPILOT
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
    # Cache prices for arb monitor
    _cache_set("all_prices", prices_data)
    # Pre-initialize poly_events from cache so log line below is always safe
    poly_events = _cache_get("polymarket", 900) or []
    log_activity(f"[cycle] F&G={fg_val}({fg_data.get('bonus',0):+d}) spot=${spot_usdt:.1f} fut=${fut_usdt:.1f} poly={len(poly_events)}mkts")

    # ── Polymarket v7.0 (кеш 15 мин, multi-query) ──────────────────────────────
    poly_events = _cache_get("polymarket", 900) or []
    if not poly_events:
        try:
            # Запросы по ключевым темам: крипто + макро
            PM_QUERIES = [
                "bitcoin", "ethereum", "crypto ETF", "crypto regulation",
                "recession", "fed rate", "ceasefire",
            ]
            result = {}  # slug → event (дедупликация)
            async with aiohttp.ClientSession() as _s:
                for q in PM_QUERIES:
                    try:
                        url = (f"https://gamma-api.polymarket.com/markets"
                               f"?q={q}&active=true&closed=false&limit=8")
                        _r = await _s.get(url, timeout=aiohttp.ClientTimeout(total=5))
                        _data = await _r.json()
                        for m in (_data if isinstance(_data, list) else []):
                            slug = m.get("slug", "")
                            if slug in result: continue
                            pr = m.get("outcomePrices", "[]")
                            if isinstance(pr, str):
                                try: pr = json.loads(pr)
                                except: continue
                            if not pr: continue
                            try: yp = round(float(pr[0]) * 100, 1)
                            except: continue
                            if yp in (0.0, 100.0): continue  # resolved/degenerate
                            vol = float(m.get("volume", 0))
                            if vol < 1000: continue
                            result[slug] = {
                                "title": m.get("question", ""),
                                "yes_prob": yp, "volume": vol,
                            }
                    except Exception: continue
            poly_events = list(result.values())[:20]
            _cache_set("polymarket", poly_events)
            log_activity(f"[polymarket] v7.0 fetched {len(poly_events)} markets")
        except Exception as e:
            log_activity(f"[polymarket] fetch error: {e}")
            poly_events = []

    # ── QAOA: обновляем quantum bias раз в 15 минут ──────────────────────────
    global _quantum_ts
    if time.time() - _quantum_ts > 870:  # 870 сек ≈ 14.5 мин (чуть раньше цикла)
        price_changes_map = {
            sym: pdata.get("change", 0.0)
            for sym, pdata in prices_data["prices"].items()
            if sym in PAIR_NAMES
        }
        await run_qaoa_optimization(price_changes_map)

    signals_fired = []
    # COOLDOWN теперь глобальная переменная (изменяется через Telegram настройки)

    # ── Параллельный fetch: chart + vision + whale ────────────────────────────
    async def _get_sym_data(sym, pdata):
        try:
            candles = await asyncio.wait_for(get_kucoin_chart(sym), timeout=8.0)
        except asyncio.TimeoutError:
            candles = []
        vision   = await analyze_chart_with_vision(sym, candles)
        whale    = await get_whale_signal(sym)
        poly_b   = calc_polymarket_bonus(sym, poly_events)
        q_bias   = _quantum_bias.get(sym, 0.0)
        signal   = calc_signal(pdata.get("change", 0), vision, fg_data, poly_b,
                               whale.get("bonus", 0), q_bias)
        return sym, vision, signal, whale, poly_b

    cv_tasks = [_get_sym_data(sym, pdata)
                for sym, pdata in prices_data["prices"].items()
                if pdata.get("price", 0) > 0]
    cv_results = await asyncio.gather(*cv_tasks, return_exceptions=True)

    # v7.1.2: re-fetch live futures balance so margin check uses current available funds
    try:
        _fresh_fut = await get_futures_balance()
        if _fresh_fut.get("success"):
            fut_usdt = _fresh_fut.get("available_balance", fut_usdt)
            log_activity(f"[cycle] live fut=${fut_usdt:.2f} (refreshed before margin checks)")
    except Exception:
        pass  # keep stale value on error

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
        # v7.1.2: per-pair Q threshold (overrides global MIN_Q_SCORE per symbol)
        _pair_min_q = PAIR_Q_THRESHOLDS.get(symbol, MIN_Q_SCORE)
        if action == "BUY" and q < _pair_min_q:
            log_activity(f"[cycle] {symbol}: Q={q:.1f}<{_pair_min_q} (pair threshold) → SKIP")
            continue
        if action == "SELL" and (100.0 - q) < _pair_min_q:
            log_activity(f"[cycle] {symbol}: sellQ={(100.0-q):.1f}<{_pair_min_q} (pair threshold) → SKIP")
            continue
        v_bonus = vision.get("vision_bonus", 0.0)
        v_ocr   = vision.get("vision_ocr", "")[:20] if vision.get("vision_ocr") else ""
        log_activity(f"[cycle] {symbol}: {action} Q={q:.1f} "
                     f"fg={bd.get('fear_greed',0):+.0f} poly={bd.get('polymarket',0):+.0f} "
                     f"whale={bd.get('whale',0):+.0f} vision={v_bonus:+.1f} "
                     f"qbias={bd.get('quantum_bias',0.0):+.1f} pattern={vision.get('pattern','?')}")

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
        asyncio.create_task(auto_execute_dynamic(trade_id))

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

# ══════════════════════════════════════════════════════════════════════════════
# TRIANGULAR ARBITRAGE MONITOR v7.1
# Схема: USDT → A → B → USDT
# Проверяем отклонение реального кросс-курса A-B от имплицитного
# Если спред > 0.4% (>0.3% комиссий KuCoin) → алерт в Telegram
# ══════════════════════════════════════════════════════════════════════════════

# Треугольные пары: (coin_a, coin_b, cross_pair, description)
ARB_TRIANGLES = [
    ("ETH-USDT",  "BTC-USDT",  "ETH-BTC",  "USDT→ETH→BTC→USDT"),
    # SOL-BTC and SOL-ETH pairs don't exist on KuCoin spot — removed
    ("XRP-USDT",  "BTC-USDT",  "XRP-BTC",  "USDT→XRP→BTC→USDT"),
    # XRP-ETH doesn't exist on KuCoin spot — removed
    ("ADA-USDT",  "BTC-USDT",  "ADA-BTC",  "USDT→ADA→BTC→USDT"),
    ("LINK-USDT", "BTC-USDT",  "LINK-BTC", "USDT→LINK→BTC→USDT"),
    ("LTC-USDT",  "BTC-USDT",  "LTC-BTC",  "USDT→LTC→BTC→USDT"),
]
ARB_FEE       = 0.001   # 0.1% per trade, 0.3% for 3 trades
ARB_MIN_SPREAD = 0.004  # минимальный спред 0.4% после комиссий
ARB_COOLDOWNS: dict = {}  # path → last_alert_ts (cooldown 5 мин)
ARB_COOLDOWN_SEC = 300

async def get_cross_ticker(symbol: str) -> float:
    """Получить цену кросс-пары из KuCoin (напр. ETH-BTC)."""
    cached = _cache_get(f"ticker_{symbol}", 60)
    if cached: return cached
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={symbol}",
                timeout=aiohttp.ClientTimeout(total=5)
            )
            d = await r.json()
        data = d.get("data") if isinstance(d, dict) else None
        if not data or not data.get("price"):
            log_activity(f"[arb] cross ticker {symbol}: no data (pair may not exist)")
            return 0.0
        price = float(data["price"])
        _cache_set(f"ticker_{symbol}", price)
        return price
    except Exception as e:
        log_activity(f"[arb] cross ticker {symbol} error: {e}")
        return 0.0

async def check_triangular_arb(prices: dict) -> list:
    """
    Проверяет все треугольные связки.
    Возвращает список найденных возможностей [{path, spread_pct, direction, ...}].
    """
    opportunities = []
    now = time.time()

    for a_sym, b_sym, cross_sym, path in ARB_TRIANGLES:
        # Cooldown check
        if now - ARB_COOLDOWNS.get(path, 0) < ARB_COOLDOWN_SEC:
            continue

        price_a = prices.get(a_sym, {}).get("price", 0)
        price_b = prices.get(b_sym, {}).get("price", 0)
        if not price_a or not price_b:
            continue

        # Имплицитный кросс-курс (из USDT пар)
        implied_cross = price_a / price_b  # напр. ETH/BTC = ETH_USDT / BTC_USDT

        # Реальный кросс-курс с биржи
        actual_cross = await get_cross_ticker(cross_sym)
        if not actual_cross:
            continue

        # Спред: насколько реальный отличается от имплицитного
        spread = (actual_cross - implied_cross) / implied_cross

        # Проверяем оба направления
        fee3 = ARB_FEE * 3  # 0.3% суммарные комиссии

        # Направление 1: USDT → A → B → USDT (используем actual_cross для продажи A за B)
        # Прибыль = (1/price_a) * actual_cross * price_b * (1-fee)^3 - 1
        profit1 = (1 / price_a) * actual_cross * price_b * (1 - ARB_FEE)**3 - 1

        # Направление 2: USDT → B → A → USDT (обратный путь)
        # Прибыль = (1/price_b) * (1/actual_cross) * price_a * (1-fee)^3 - 1
        profit2 = (1 / price_b) * (1 / actual_cross) * price_a * (1 - ARB_FEE)**3 - 1

        best_profit = max(profit1, profit2)
        direction   = 1 if profit1 >= profit2 else 2

        if best_profit >= ARB_MIN_SPREAD:
            path_str = path if direction == 1 else path.replace("→", "←").split("←")[0] + "←".join(path.split("→")[1:])
            opp = {
                "path":        path,
                "cross_sym":   cross_sym,
                "implied":     round(implied_cross, 8),
                "actual":      round(actual_cross, 8),
                "spread_pct":  round(spread * 100, 3),
                "profit_pct":  round(best_profit * 100, 3),
                "direction":   direction,
                "price_a":     price_a,
                "price_b":     price_b,
                "a_sym":       a_sym,
                "b_sym":       b_sym,
            }
            opportunities.append(opp)
            ARB_COOLDOWNS[path] = now
            log_activity(f"[arb] ⚡ {path} profit={best_profit*100:.3f}% spread={spread*100:.3f}%")

    return opportunities

async def _notify_arb(opp: dict):
    """Telegram alert for triangular arbitrage opportunity."""
    d = opp["direction"]
    steps = opp["path"].split("→")
    arrow = "➡️"
    if d == 1:
        route = f"{steps[0]} {arrow} {steps[1]} {arrow} {steps[2]} {arrow} {steps[3]}"
    else:
        route = f"{steps[0]} {arrow} {steps[2]} {arrow} {steps[1]} {arrow} {steps[3]}"
    profit_100  = round(opp["profit_pct"] / 100 * 100, 3)
    profit_1000 = round(opp["profit_pct"] / 100 * 1000, 2)
    msg = (
        f"\u26a1 <b>\u0410\u0440\u0431\u0438\u0442\u0440\u0430\u0436 KuCoin!</b>\n"
        f"<code>{route}</code>\n\n"
        f"\U0001f4ca \u041a\u0440\u043e\u0441\u0441-\u043f\u0430\u0440\u0430: <code>{opp['cross_sym']}</code>\n"
        f"\u0418\u043c\u043f\u043b\u0438\u0446\u0438\u0442\u043d\u044b\u0439:  <code>{opp['implied']:.6f}</code>\n"
        f"\u0420\u044b\u043d\u043e\u0447\u043d\u044b\u0439:     <code>{opp['actual']:.6f}</code>\n"
        f"\u0421\u043f\u0440\u0435\u0434:        <code>{opp['spread_pct']:+.3f}%</code>\n\n"
        f"\U0001f4b0 \u041f\u0440\u0438\u0431\u044b\u043b\u044c (\u043f\u043e\u0441\u043b\u0435 \u043a\u043e\u043c\u0438\u0441\u0441\u0438\u0439 0.3%):\n"
        f"  $100  \u2192 <code>${profit_100:+.3f}</code>\n"
        f"  $1000 \u2192 <code>${profit_1000:+.2f}</code>\n\n"
        f"\u23f0 <i>\u0414\u0435\u0439\u0441\u0442\u0432\u0443\u0439 \u0431\u044b\u0441\u0442\u0440\u043e \u2014 \u0430\u0440\u0431\u0438\u0442\u0440\u0430\u0436 \u0436\u0438\u0432\u0451\u0442 \u0441\u0435\u043a\u0443\u043d\u0434\u044b!</i>"
    )
    await notify(msg)


async def position_monitor_loop():
    """Каждые 30 сек проверяет открытые позиции — закрылись ли по TP/SL."""
    await asyncio.sleep(30)
    SYM_REV = {"XBTUSDTM": "BTC-USDT", "ETHUSDTM": "ETH-USDT", "SOLUSDTM": "SOL-USDT"}
    # v6.8: правильные размеры контрактов для расчёта PnL
    CONTRACT_SIZES = {"XBTUSDTM": 0.001, "ETHUSDTM": 0.01, "SOLUSDTM": 1.0,
                      "AVAXUSDTM": 1.0, "XRPUSDTM": 10.0}
    while True:
        try:
            open_trades = [t for t in trade_log if t.get("status") == "open"]
            if open_trades:
                pos_data   = await get_futures_positions()
                open_syms  = {p.get("symbol") for p in pos_data.get("positions", [])}
                for trade in open_trades:
                    if trade["symbol"] not in open_syms:
                        base_sym      = SYM_REV.get(trade["symbol"], "BTC-USDT")
                        price_now     = await get_ticker(base_sym)
                        entry         = trade["price"]
                        contract_size = CONTRACT_SIZES.get(trade["symbol"], 0.01)
                        if trade["side"] == "sell":
                            pnl_pct = (entry - price_now) / entry
                        else:
                            pnl_pct = (price_now - entry) / entry
                        # v6.8 fix: PnL = price_change * n_contracts * contract_size_in_eth * entry
                        pnl_usdt = round(pnl_pct * entry * trade["size"] * contract_size, 4)
                        duration_min = round((time.time() - trade.get("open_ts", time.time())) / 60, 1)
                        # Определяем причину закрытия
                        tp  = trade.get("tp", entry * 1.03)
                        sl  = trade.get("sl", entry * 0.985)
                        if trade["side"] == "buy":
                            reason = "🎯 TP" if price_now >= tp * 0.995 else ("🛑 SL" if price_now <= sl * 1.005 else "📊 Монитор")
                        else:
                            reason = "🎯 TP" if price_now <= tp * 1.005 else ("🛑 SL" if price_now >= sl * 0.995 else "📊 Монитор")
                        trade["status"]      = "closed"
                        trade["pnl"]         = pnl_usdt
                        trade["close_price"] = price_now
                        emoji = "✅" if pnl_usdt >= 0 else "❌"
                        strat = trade.get("account", "B").replace("futures_", "")
                        log_activity(f"[monitor] {trade['symbol']} {reason} closed PnL=${pnl_usdt:+.4f}")
                        _save_trades_to_disk()
                        await notify(
                            f"{emoji} <b>Сделка закрыта — Стратегия {strat}</b>\n"
                            f"<code>{trade['symbol']}</code> {trade['side'].upper()} | {reason}\n"
                            f"Вход:  <code>${entry:,.2f}</code> → Выход: <code>${price_now:,.2f}</code>\n"
                            f"PnL:   <code>${pnl_usdt:+.4f}</code> ({pnl_pct*100:+.3f}%)\n"
                            f"Q={trade.get('q_score',0):.1f} | Длительность: {duration_min}м"
                        )
        except Exception as e:
            print(f"[monitor] {e}")

        # ── Арбитраж: проверяем каждые 2 цикла (60 сек) ──────────────────────
        try:
            if int(time.time()) % 60 < 32:  # примерно каждую минуту
                prices_snap = _cache_get("all_prices", 120) or {}
                if prices_snap:
                    arb_opps = await check_triangular_arb(prices_snap.get("prices", {}))
                    for opp in arb_opps:
                        await _notify_arb(opp)
        except Exception as e:
            log_activity(f"[arb] monitor error: {e}")

        await asyncio.sleep(30)


# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM BOT — команды, меню, настройки, статистика, airdrops
# ══════════════════════════════════════════════════════════════════════════════
class TelegramUpdate(BaseModel):
    callback_query: Optional[dict] = None
    message:        Optional[dict] = None

async def _tg_send(chat_id: int, text: str, keyboard: dict = None, parse_mode: str = "HTML"):
    """Универсальная отправка сообщения в Telegram (parse_mode=HTML для надёжности)."""
    if not BOT_TOKEN: return
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode,
               "disable_web_page_preview": True}
    if keyboard: payload["reply_markup"] = keyboard
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                             json=payload, timeout=aiohttp.ClientTimeout(total=8))
            resp = await r.json()
            if not resp.get("ok"):
                # Логируем реальную ошибку от Telegram API
                print(f"[tg_send] Telegram error: {resp.get('description','?')} | "
                      f"chat={chat_id} | text[:60]={text[:60]!r}")
    except Exception as e:
        print(f"[tg_send] network error: {e}")

async def _tg_answer(cb_id: str, text: str = ""):
    """Ответ на callback query (убирает часики у кнопки)."""
    if not BOT_TOKEN: return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
                         json={"callback_query_id": cb_id, "text": text},
                         timeout=aiohttp.ClientTimeout(total=3))
    except: pass

async def _tg_main_menu(chat_id: int):
    """Главное меню бота."""
    ap = "🟢 ВКЛ" if AUTOPILOT else "🔴 ВЫКЛ"
    kb = {"inline_keyboard": [
        [{"text": "📊 Статистика", "callback_data": "menu_stats"},
         {"text": "🪂 Airdrops",   "callback_data": "menu_airdrops"}],
        [{"text": "⚙️ Настройки",  "callback_data": "menu_settings"},
         {"text": f"🤖 Автопилот: {ap}", "callback_data": "menu_autopilot"}],
        [{"text": "💰 Баланс",     "callback_data": "menu_balance"},
         {"text": "📈 Позиции",    "callback_data": "menu_positions"}],
        [{"text": "⚡ Арбитраж",   "callback_data": "menu_arb"}],
    ]}
    await _tg_send(chat_id,
        "⚛ <b>QuantumTrade AI v6.8.0</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Выбери раздел:", kb)

async def _tg_stats(chat_id: int):
    """Отправляет карточку статистики трейдинга."""
    total = len(trade_log)
    wins  = sum(1 for t in trade_log if (t.get("pnl") or 0) > 0)
    losses= sum(1 for t in trade_log if (t.get("pnl") or 0) <= 0 and t.get("pnl") is not None)
    pnl   = round(sum(t.get("pnl") or 0 for t in trade_log), 4)
    wr    = round(wins / total * 100, 1) if total else 0
    open_ = sum(1 for t in trade_log if t["status"] == "open")
    last_q = round(last_q_score, 1) if last_q_score else "—"
    pnl_emoji = "✅" if pnl >= 0 else "❌"
    chip  = "Wukong 180 ⚛️" if _qcloud_ready else "CPU симулятор"
    kb = {"inline_keyboard": [[{"text": "◀️ Меню", "callback_data": "menu_main"}]]}
    await _tg_send(chat_id,
        f"📊 <b>Статистика трейдинга</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Всего сделок: <code>{total}</code> (открыто: <code>{open_}</code>)\n"
        f"Побед: <code>{wins}</code> / Потерь: <code>{losses}</code>\n"
        f"Win Rate: <code>{wr}%</code>\n"
        f"Итог PnL: {pnl_emoji} <code>${pnl:+.4f}</code>\n"
        f"Последний Q-Score: <code>{last_q}</code>\n"
        f"Автопилот: <code>{'ВКЛ' if AUTOPILOT else 'ВЫКЛ'}</code>\n"
        f"Min Q: <code>{MIN_Q_SCORE}</code> · Cooldown: <code>{COOLDOWN}s</code>\n"
        f"Квантовый чип: {chip}", kb)

def _html_esc(s: str) -> str:
    """Экранирует спецсимволы HTML для Telegram (& < >)."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

async def _tg_airdrops(chat_id: int):
    """Отправляет топ-5 airdrop возможностей (HTML-форматирование, без Markdown-крашей)."""
    airdrops = await get_airdrops()
    top = airdrops[:5]
    lines = ["🪂 <b>Топ Airdrop возможности</b>", "━━━━━━━━━━━━━━━━━━━━━━"]
    for a in top:
        stars = _stars(a.get("potential", 3))
        tge   = _html_esc(str(a.get("tge_estimate") or "TBD"))
        name  = _html_esc(a.get("name", "?"))
        eco   = _html_esc(a.get("ecosystem", "?"))
        desc  = _html_esc((a.get("description") or "")[:90])
        url   = a.get("url", "")
        # Ссылка через HTML-тег — не ломает парсер
        link  = f'<a href="{url}">{url[:45]}...</a>' if len(url) > 45 else f'<a href="{url}">{url}</a>'
        lines.append(
            f"\n<b>{name}</b> {stars}\n"
            f"📅 TGE: <code>{tge}</code> · {eco}\n"
            f"<i>{desc}</i>\n"
            f"🔗 {link}"
        )
    kb = {"inline_keyboard": [
        [{"text": "🔄 Обновить", "callback_data": "airdrops_refresh"},
         {"text": "◀️ Меню",    "callback_data": "menu_main"}]
    ]}
    await _tg_send(chat_id, "\n".join(lines), kb)

async def _tg_settings(chat_id: int):
    """Карточка настроек с рабочими кнопками."""
    kb = {"inline_keyboard": [
        [{"text": "🟢 Min Q: 62 (страх рынка)", "callback_data": "set_minq_62"},
         {"text": "📉 Min Q: 65 (мягкий)",      "callback_data": "set_minq_65"}],
        [{"text": "📊 Min Q: 70 (умеренный)",   "callback_data": "set_minq_70"},
         {"text": "📊 Min Q: 78 (стандарт)",    "callback_data": "set_minq_78"}],
        [{"text": "📈 Min Q: 82 (строгий)",     "callback_data": "set_minq_82"},
         {"text": f"✅ Текущий: {MIN_Q_SCORE}", "callback_data": "set_minq_cur"}],
        [{"text": "⏱ Cooldown: 180s", "callback_data": "set_cd_180"},
         {"text": "⏱ Cooldown: 300s", "callback_data": "set_cd_300"}],
        [{"text": "⏱ Cooldown: 600s", "callback_data": "set_cd_600"},
         {"text": f"✅ Текущий: {COOLDOWN}s", "callback_data": "set_cd_cur"}],
        [{"text": "💾 Сохранить (текущие)", "callback_data": "save_settings"}],
        [{"text": "◀️ Меню", "callback_data": "menu_main"}],
    ]}
    await _tg_send(chat_id,
        f"⚙️ <b>Настройки QuantumTrade</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 Min Q-Score: <code>{MIN_Q_SCORE}</code>\n"
        f"⏱ Cooldown: <code>{COOLDOWN}s</code>\n"
        f"🤖 Автопилот: <code>{'ВКЛ' if AUTOPILOT else 'ВЫКЛ'}</code>\n\n"
        f"<i>Выбери параметр для изменения, затем нажми Сохранить</i>", kb)


async def _tg_arb(chat_id: int):
    """Telegram: arbitrage monitor status."""
    now = time.time()
    lines = []
    for _, _, _, path in ARB_TRIANGLES:
        last    = ARB_COOLDOWNS.get(path, 0)
        elapsed = now - last
        status  = "\U0001f50d \u041c\u043e\u043d\u0438\u0442\u043e\u0440\u0438\u043d\u0433" if elapsed > ARB_COOLDOWN_SEC else f"\u23f3 CD {int(ARB_COOLDOWN_SEC - elapsed)}s"
        lines.append(f"  {path}: {status}")
    ap_status = "\u0412\u041a\u041b" if AUTOPILOT else "\u0412\u042b\u041a\u041b (\u0432\u043a\u043b\u044e\u0447\u0438 \u0430\u0432\u0442\u043e\u043f\u0438\u043b\u043e\u0442)"
    body = "\n".join(lines)
    text = (
        f"\u26a1 <b>\u0410\u0440\u0431\u0438\u0442\u0440\u0430\u0436 KuCoin \u2014 \u0421\u0442\u0430\u0442\u0443\u0441</b>\n\n"
        f"\U0001f504 \u041c\u043e\u043d\u0438\u0442\u043e\u0440\u0438\u043d\u0433: <b>{ap_status}</b>\n"
        f"\U0001f4d0 \u041c\u0438\u043d. \u0441\u043f\u0440\u0435\u0434: <code>{ARB_MIN_SPREAD*100:.1f}%</code> (\u043f\u043e\u0441\u043b\u0435 0.3% \u043a\u043e\u043c\u0438\u0441\u0441\u0438\u0439)\n"
        f"\u23f1 Cooldown: <code>{ARB_COOLDOWN_SEC}s</code>\n\n"
        f"<b>\u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0435 \u0441\u0432\u044f\u0437\u043a\u0438:</b>\n{body}\n\n"
        f"\U0001f4a1 \u0410\u043b\u0435\u0440\u0442 \u043f\u0440\u0438\u0445\u043e\u0434\u0438\u0442 \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438 \u043f\u0440\u0438 \u043e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d\u0438\u0438 \u0432\u043e\u0437\u043c\u043e\u0436\u043d\u043e\u0441\u0442\u0438."
    )
    kb = {"inline_keyboard": [[{"text": "\u25c0\ufe0f \u041c\u0435\u043d\u044e", "callback_data": "menu_main"}]]}
    await _tg_send(chat_id, text, kb)


async def _tg_balance(chat_id: int):
    """Текущие балансы спот + фьючерсы."""
    try:
        spot, fut = await asyncio.gather(get_balance(), get_futures_balance())
        spot_usdt = spot.get("USDT", 0)
        fut_eq    = fut.get("account_equity", 0)
        fut_pnl   = fut.get("unrealised_pnl", 0)
        kb = {"inline_keyboard": [[{"text": "◀️ Меню", "callback_data": "menu_main"}]]}
        await _tg_send(chat_id,
            f"💰 <b>Баланс</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Спот USDT: <code>${spot_usdt:.2f}</code>\n"
            f"Фьюч. equity: <code>${fut_eq:.2f}</code>\n"
            f"Нереализ. PnL: <code>${fut_pnl:+.4f}</code>", kb)
    except Exception as e:
        await _tg_send(chat_id, f"❌ Ошибка получения баланса: {e}")

async def _tg_positions(chat_id: int):
    """Открытые позиции."""
    open_trades = [t for t in trade_log if t["status"] == "open"]
    kb = {"inline_keyboard": [[{"text": "◀️ Меню", "callback_data": "menu_main"}]]}
    if not open_trades:
        await _tg_send(chat_id, "📈 <b>Позиции</b>\n\nОткрытых позиций нет.", kb)
        return
    lines = ["📈 <b>Открытые позиции</b>", "━━━━━━━━━━━━━━━━━━━━━━"]
    for t in open_trades[:8]:
        lines.append(
            f"`{t['symbol']}` {t['side'].upper()} | "
            f"entry: `${t.get('entry_price', 0):.2f}` | "
            f"TP: `${t.get('tp', 0):.2f}` SL: `${t.get('sl', 0):.2f}`"
        )
    await _tg_send(chat_id, "\n".join(lines), kb)

@app.post("/api/telegram/callback")
async def telegram_callback(req: TelegramUpdate):
    global MIN_Q_SCORE, COOLDOWN, AUTOPILOT

    # ── Обработка текстовых команд ─────────────────────────────────────────
    if req.message:
        msg  = req.message
        raw  = msg.get("text", "").strip()
        # Убираем @BotName суффикс: /menu@MyBot → /menu
        cmd  = raw.split("@")[0].lower() if raw.startswith("/") else raw
        chat_id = msg.get("chat", {}).get("id")
        if not chat_id: return {"ok": True}
        if cmd in ["/start", "/menu"]:     await _tg_main_menu(chat_id)
        elif cmd == "/stats":               await _tg_stats(chat_id)
        elif cmd in ["/airdrops", "/air"]: await _tg_airdrops(chat_id)
        elif cmd == "/settings":            await _tg_settings(chat_id)
        elif cmd == "/balance":             await _tg_balance(chat_id)
        elif cmd == "/positions":           await _tg_positions(chat_id)
        elif cmd == "/arb":                 await _tg_arb(chat_id)
        return {"ok": True}

    # ── Обработка callback (нажатия кнопок) ────────────────────────────────
    cb = req.callback_query
    if not cb: return {"ok": True}
    data    = cb.get("data", "")
    chat_id = cb.get("message", {}).get("chat", {}).get("id")
    cb_id   = cb["id"]

    # ── Главное меню ───────────────────────────────────────────────────────
    if data == "menu_main":
        await _tg_answer(cb_id)
        if chat_id: await _tg_main_menu(chat_id)

    elif data == "menu_stats":
        await _tg_answer(cb_id, "📊 Загружаю...")
        if chat_id: await _tg_stats(chat_id)

    elif data == "menu_airdrops":
        await _tg_answer(cb_id, "🪂 Загружаю...")
        if chat_id: await _tg_airdrops(chat_id)

    elif data == "airdrops_refresh":
        global _airdrop_cache_ts
        _airdrop_cache_ts = 0.0
        await _tg_answer(cb_id, "🔄 Обновляю...")
        if chat_id: await _tg_airdrops(chat_id)

    elif data == "menu_settings":
        await _tg_answer(cb_id)
        if chat_id: await _tg_settings(chat_id)

    elif data == "menu_balance":
        await _tg_answer(cb_id, "💰 Загружаю...")
        if chat_id: await _tg_balance(chat_id)

    elif data == "menu_positions":
        await _tg_answer(cb_id, "📈 Загружаю...")
        if chat_id: await _tg_positions(chat_id)

    elif data == "menu_arb":
        await _tg_answer(cb_id, "⚡ Загружаю арбитраж...")
        if chat_id: await _tg_arb(chat_id)

    elif data == "menu_autopilot":
        AUTOPILOT = not AUTOPILOT
        state = "ВКЛ 🟢" if AUTOPILOT else "ВЫКЛ 🔴"
        await _tg_answer(cb_id, f"Автопилот {state}")
        log_activity(f"[settings] Автопилот → {state} (via Telegram)")
        if chat_id: await _tg_main_menu(chat_id)

    # ── Настройки Min Q ────────────────────────────────────────────────────
    elif data in ("set_minq_62", "set_minq_65", "set_minq_70", "set_minq_78", "set_minq_82", "set_minq_cur"):
        if data == "set_minq_62":   MIN_Q_SCORE = 62
        elif data == "set_minq_65": MIN_Q_SCORE = 65
        elif data == "set_minq_70": MIN_Q_SCORE = 70
        elif data == "set_minq_78": MIN_Q_SCORE = 78
        elif data == "set_minq_82": MIN_Q_SCORE = 82
        await _tg_answer(cb_id, f"Min Q → {MIN_Q_SCORE}")
        if chat_id: await _tg_settings(chat_id)

    # ── Настройки Cooldown ─────────────────────────────────────────────────
    elif data in ("set_cd_180", "set_cd_300", "set_cd_600", "set_cd_cur"):
        if data == "set_cd_180":   COOLDOWN = 180
        elif data == "set_cd_300": COOLDOWN = 300
        elif data == "set_cd_600": COOLDOWN = 600
        await _tg_answer(cb_id, f"Cooldown → {COOLDOWN}s")
        if chat_id: await _tg_settings(chat_id)

    # ── Сохранить настройки ────────────────────────────────────────────────
    elif data == "save_settings":
        await _tg_answer(cb_id, "✅ Настройки сохранены!")
        log_activity(f"[settings] SAVED: MIN_Q={MIN_Q_SCORE} COOLDOWN={COOLDOWN}s AUTOPILOT={AUTOPILOT}")
        await notify(
            f"💾 *Настройки сохранены*\n"
            f"Min Q-Score: `{MIN_Q_SCORE}`\n"
            f"Cooldown: `{COOLDOWN}s`\n"
            f"Автопилот: `{'ВКЛ' if AUTOPILOT else 'ВЫКЛ'}`"
        )
        if chat_id: await _tg_settings(chat_id)

    # ── Стратегии A/B/C/D (торговые сигналы) ──────────────────────────────
    elif data.startswith("strat_"):
        parts = data.split("_", 2)
        if len(parts) < 3: return {"ok": True}
        strategy = parts[1]
        trade_id = parts[2]
        pending  = pending_strategies.pop(trade_id, None)
        if not pending:
            await _tg_answer(cb_id, "⏱ Сигнал устарел или уже исполнен")
            return {"ok": True}
        s = STRATEGIES.get(strategy, STRATEGIES["B"])
        await _tg_answer(cb_id, f"{s['emoji']} Стратегия {strategy} принята!")
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
    _load_trades_from_disk()          # загружаем историю сделок при старте

    # Phase 6: пробуем подключить Origin QC Wukong 180
    qc_ok = await asyncio.get_event_loop().run_in_executor(None, _init_qcloud)

    asyncio.create_task(trading_loop())
    asyncio.create_task(position_monitor_loop())
    asyncio.create_task(airdrop_digest_loop())
    await get_airdrops()  # прогреваем кеш при старте
    mode     = "TEST (риск 10%)" if TEST_MODE else "LIVE (риск 2%)"
    qc_label = "⚛️ Wukong 180 реальный чип ✅" if qc_ok else "⚛️ QAOA CPU симулятор"
    await notify(
        f"⚛ *QuantumTrade v6.8.0*\n"
        f"✅ 5 торгуемых пар: ETH·BTC·SOL·AVAX·XRP\n"
        f"✅ Telegram: /menu /stats /airdrops /settings\n"
        f"✅ Динамический выбор стратегии B/C/DUAL по Q\n"
        f"⚛️ Phase 5: Claude Vision — нативный AI-анализ графиков\n"
        f"{qc_label} (Phase 3+6)\n"
        f"🪂 Airdrop Tracker активен (Phase 4)\n"
        f"📊 Режим: {mode} · История: {len(trade_log)} сделок\n"
        f"🎯 Q-min: {MIN_Q_SCORE} · Cooldown: {COOLDOWN}s"
    )

async def trading_loop():
    while True:
        try: await auto_trade_cycle()
        except Exception as e: log_activity(f"[loop] error: {e}")
        await asyncio.sleep(60)


# ══════════════════════════════════════════════════════════════════════════════
# ФАЗА 4 — AIRDROP TRACKER
# ══════════════════════════════════════════════════════════════════════════════

# ── State ──────────────────────────────────────────────────────────────────────
_airdrop_cache: List[dict] = []
_airdrop_cache_ts: float = 0.0
_AIRDROP_TTL = 21600  # 6 часов

# ── Hardcoded fallback список (топ проекты 2026) ───────────────────────────────
_AIRDROP_FALLBACK = [
    {
        "id": "backpack-exchange", "name": "Backpack Exchange", "ecosystem": "EVM",
        "status": "active", "potential": 5, "effort": "low",
        "description": "Торгуй на споте/фьючерсах → фармишь очки к TGE. Команда с известными VC-бэкингом.",
        "tasks": ["Торгуй на споте", "Торгуй на фьючерсах", "Пополни депозит"],
        "deadline": None, "tge_estimate": "Q2 2026",
        "url": "https://backpack.exchange", "volume_usd": 5e9,
    },
    {
        "id": "monad-testnet", "name": "Monad Testnet", "ecosystem": "EVM",
        "status": "active", "potential": 4, "effort": "low",
        "description": "1 транзакция каждые 48ч достаточно. Консистентность важнее объёма.",
        "tasks": ["Сделай транзакцию раз в 48ч", "Используй dApps на тестнете"],
        "deadline": None, "tge_estimate": "Q3 2026",
        "url": "https://testnet.monad.xyz", "volume_usd": 1e9,
    },
    {
        "id": "base-ecosystem", "name": "Base Ecosystem", "ecosystem": "EVM",
        "status": "active", "potential": 4, "effort": "medium",
        "description": "L2 от Coinbase. Swap на Aerodrome/Uniswap, бридж ETH через official bridge.",
        "tasks": ["Бридж ETH → Base", "Swap на Aerodrome или Uniswap", "Используй Basename"],
        "deadline": None, "tge_estimate": "TBD",
        "url": "https://base.org", "volume_usd": 8e9,
    },
    {
        "id": "layerzero-s2", "name": "LayerZero Season 2", "ecosystem": "Multi",
        "status": "active", "potential": 4, "effort": "medium",
        "description": "Кросс-чейн протокол. Сделай транзакции через их бриджи между разными сетями.",
        "tasks": ["Кросс-чейн бридж через LZ", "Используй Stargate Finance"],
        "deadline": None, "tge_estimate": "Q2 2026",
        "url": "https://layerzero.network", "volume_usd": 2e9,
    },
    {
        "id": "tonkeeper-points", "name": "Tonkeeper Points", "ecosystem": "TON",
        "status": "active", "potential": 3, "effort": "low",
        "description": "Ежедневный check-in в приложении. Используй TON кошелёк активно.",
        "tasks": ["Ежедневный check-in", "Своп в TON Space", "Стейкинг TON"],
        "deadline": None, "tge_estimate": "TBD",
        "url": "https://tonkeeper.com", "volume_usd": 5e8,
    },
    {
        "id": "scroll-mainnet", "name": "Scroll", "ecosystem": "EVM",
        "status": "active", "potential": 4, "effort": "medium",
        "description": "ZK-rollup на Ethereum. Бридж ETH, используй dApps на Scroll.",
        "tasks": ["Бридж ETH → Scroll", "Swap на Uniswap v3 на Scroll", "Минт NFT на Scroll"],
        "deadline": None, "tge_estimate": "Q2 2026",
        "url": "https://scroll.io", "volume_usd": 1.5e9,
    },
    {
        "id": "hyperliquid-points", "name": "Hyperliquid Points", "ecosystem": "EVM",
        "status": "active", "potential": 5, "effort": "medium",
        "description": "DEX с перпами. Очки начисляются за объём торгов. Уже крупный airdrop был — ждут второй.",
        "tasks": ["Торгуй перпами на HyperLiquid", "Обеспечь ликвидность в HLP"],
        "deadline": None, "tge_estimate": "TBD",
        "url": "https://hyperliquid.xyz", "volume_usd": 10e9,
    },
    {
        "id": "zksync-s2", "name": "zkSync Era Season 2", "ecosystem": "EVM",
        "status": "active", "potential": 3, "effort": "low",
        "description": "ZK-rollup от Matter Labs. После первого airdrop ждут второй сезон.",
        "tasks": ["Бридж ETH → zkSync Era", "Swap на SyncSwap", "Используй ZK native dApps"],
        "deadline": None, "tge_estimate": "H2 2026",
        "url": "https://zksync.io", "volume_usd": 3e9,
    },
]

def _stars(n: int) -> str:
    """Конвертирует 1-5 в строку звёзд."""
    return "★" * n + "☆" * (5 - n)

def _effort_ru(e: str) -> str:
    return {"low": "низкие", "medium": "средние", "high": "высокие"}.get(e, e)

async def _fetch_defillama_airdrops() -> List[dict]:
    """Пробуем получить данные из DeFiLlama. Fallback → пустой список."""
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                "https://api.llama.fi/airdrops",
                timeout=aiohttp.ClientTimeout(total=6)
            )
            data = await r.json()
            result = []
            for item in (data if isinstance(data, list) else [])[:5]:
                name = item.get("name") or item.get("project", "")
                if not name:
                    continue
                result.append({
                    "id": name.lower().replace(" ", "-"),
                    "name": name,
                    "ecosystem": "EVM",
                    "status": "active",
                    "potential": 3,
                    "effort": "medium",
                    "description": item.get("description", "Из DeFiLlama"),
                    "tasks": ["Проверь официальный сайт"],
                    "deadline": None,
                    "tge_estimate": None,
                    "url": item.get("url", "https://defillama.com/airdrops"),
                    "volume_usd": float(item.get("totalLocked", 0) or 0),
                })
            return result
    except Exception:
        return []

async def get_airdrops() -> List[dict]:
    """Возвращает список airdrops (кеш 6ч + fallback)."""
    global _airdrop_cache, _airdrop_cache_ts
    if _airdrop_cache and time.time() - _airdrop_cache_ts < _AIRDROP_TTL:
        return _airdrop_cache
    # Пробуем DeFiLlama
    live = await _fetch_defillama_airdrops()
    # Мержим с fallback (fallback в конце, live в начале)
    seen = {a["id"] for a in live}
    merged = live + [a for a in _AIRDROP_FALLBACK if a["id"] not in seen]
    # Сортировка: potential DESC, volume DESC
    merged.sort(key=lambda x: (x["potential"], x["volume_usd"]), reverse=True)
    _airdrop_cache = merged
    _airdrop_cache_ts = time.time()
    print(f"[airdrops] кеш обновлён: {len(merged)} проектов ({len(live)} из DeFiLlama)")
    return _airdrop_cache

async def send_airdrop_digest():
    """Отправляет ежедневный дайджест в Telegram."""
    if not BOT_TOKEN or not ALERT_CHAT_ID:
        return
    airdrops = await get_airdrops()
    top5 = airdrops[:5]
    today = datetime.utcnow().strftime("%d.%m.%Y")
    lines = [f"⚛ *QuantumTrade · 🪂 Airdrop Digest {today}*", "━━━━━━━━━━━━━━━━━━━━━━"]
    emoji_map = {"EVM": "🔷", "TON": "💎", "Solana": "🟣", "Multi": "🌐"}
    for a in top5:
        eco_emoji = emoji_map.get(a["ecosystem"], "🔹")
        lines.append(
            f"\n{eco_emoji} *{a['name']}* `[{a['ecosystem']}]`\n"
            f"   {_stars(a['potential'])} · Усилия: {_effort_ru(a['effort'])}\n"
            f"   {a['description'][:80]}\n"
            f"   👉 {a['url']}"
        )
    # Дедлайны
    deadlines = [a for a in airdrops if a.get("deadline")]
    if deadlines:
        lines.append("\n⏰ *Дедлайны:*")
        for a in deadlines[:3]:
            lines.append(f"   • {a['name']}: {a['deadline']}")
    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("_/airdrops — полный список_")
    text = "\n".join(lines)
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": ALERT_CHAT_ID, "text": text,
                      "parse_mode": "Markdown", "disable_web_page_preview": True},
                timeout=aiohttp.ClientTimeout(total=5)
            )
        print("[airdrops] дайджест отправлен в Telegram")
    except Exception as e:
        print(f"[airdrops] ошибка отправки дайджеста: {e}")

async def airdrop_digest_loop():
    """Отправляет дайджест раз в 24ч (в 09:00 UTC)."""
    while True:
        now = datetime.utcnow()
        # Считаем секунды до следующего 09:00 UTC
        target_hour = 9
        secs_until = ((target_hour - now.hour) % 24) * 3600 - now.minute * 60 - now.second
        if secs_until <= 0:
            secs_until += 86400
        await asyncio.sleep(secs_until)
        try:
            await send_airdrop_digest()
        except Exception as e:
            print(f"[airdrops] digest loop error: {e}")


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/api/airdrops")
async def airdrops_list():
    """Phase 4: список активных airdrop возможностей."""
    data = await get_airdrops()
    ecosystems = list(dict.fromkeys(a["ecosystem"] for a in data))
    return {
        "airdrops": data,
        "total": len(data),
        "last_updated": datetime.utcfromtimestamp(_airdrop_cache_ts).isoformat() if _airdrop_cache_ts else None,
        "ecosystems": ecosystems,
    }

@app.get("/api/airdrops/digest")
async def airdrops_digest():
    """Топ-5 для дайджеста + дедлайны."""
    data = await get_airdrops()
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    tomorrow_str = datetime.utcnow().replace(day=datetime.utcnow().day + 1).strftime("%Y-%m-%d") if datetime.utcnow().day < 28 else None
    return {
        "top5": data[:5],
        "deadlines_today": [a for a in data if a.get("deadline") == today_str],
        "deadlines_tomorrow": [a for a in data if tomorrow_str and a.get("deadline") == tomorrow_str],
    }

@app.post("/api/airdrops/refresh")
async def airdrops_refresh():
    """Принудительный сброс кеша airdrops."""
    global _airdrop_cache_ts
    _airdrop_cache_ts = 0.0
    data = await get_airdrops()
    return {"status": "ok", "count": len(data)}

@app.post("/api/airdrops/digest/send")
async def airdrops_send_digest():
    """Отправить дайджест в Telegram прямо сейчас (для тестирования)."""
    await send_airdrop_digest()
    return {"status": "sent"}

@app.get("/api/quantum")
async def quantum_status():
    """Phase 3+6: текущий QAOA quantum bias, режим чипа и статус Origin QC."""
    age_sec = int(time.time() - _quantum_ts) if _quantum_ts else None
    if _qcloud_ready:
        chip      = "Wukong_180"
        p_layers  = 1
        note      = "⚛️ Реальный квантовый чип Origin Wukong 180 активен (chip_id=72)"
    else:
        chip      = "CPU_simulator"
        p_layers  = 2
        note      = ("Установи ORIGIN_QC_TOKEN в Railway для активации Wukong 180"
                     if not ORIGIN_QC_TOKEN else
                     "ORIGIN_QC_TOKEN задан, но pyqpanda3 недоступен → CPU fallback")
    return {
        "quantum_bias":    _quantum_bias,
        "last_run_ago_sec": age_sec,
        "chip":            chip,
        "chip_ready":      _qcloud_ready,
        "p_layers":        p_layers,
        "pairs":           PAIR_NAMES,
        "note":            note,
    }

@app.post("/api/settings")
async def update_settings(body: dict):
    """v6.7: runtime settings update without restart."""
    global MIN_Q_SCORE, COOLDOWN, AUTOPILOT, TEST_MODE, RISK_PER_TRADE, MAX_LEVERAGE
    changed = {}
    if "min_q_score" in body:
        MIN_Q_SCORE = int(body["min_q_score"])
        changed["min_q_score"] = MIN_Q_SCORE
    if "cooldown" in body:
        COOLDOWN = int(body["cooldown"])
        changed["cooldown"] = COOLDOWN
    if "autopilot" in body:
        AUTOPILOT = bool(body["autopilot"])
        changed["autopilot"] = AUTOPILOT
    if "test_mode" in body:
        TEST_MODE = bool(body["test_mode"])
        RISK_PER_TRADE = 0.10 if TEST_MODE else 0.25  # v6.9: Strategy C default in live mode
        changed["test_mode"] = TEST_MODE
        changed["risk_per_trade"] = RISK_PER_TRADE
    if "max_leverage" in body:
        MAX_LEVERAGE = int(body["max_leverage"])
        changed["max_leverage"] = MAX_LEVERAGE
    log_activity(f"[settings/api] changed: {changed}")
    return {"ok": True, "changed": changed,
            "current": {"min_q_score": MIN_Q_SCORE, "cooldown": COOLDOWN,
                        "autopilot": AUTOPILOT, "test_mode": TEST_MODE,
                        "risk_per_trade": RISK_PER_TRADE, "max_leverage": MAX_LEVERAGE}}

@app.get("/health")
async def health():
    return {"status": "ok", "version": "7.1.2", "auto_trading": AUTOPILOT, "test_mode": TEST_MODE,
            "risk_per_trade": RISK_PER_TRADE, "last_qscore": last_q_score, "min_confidence": MIN_CONFIDENCE,
            "min_q_score": MIN_Q_SCORE, "max_leverage": MAX_LEVERAGE, "tp_pct": TP_PCT, "sl_pct": SL_PCT,
            "trades_logged": len(trade_log), "yandex_vision": bool(YANDEX_VISION_KEY),
            "claude_vision": bool(ANTHROPIC_API_KEY), "ai_chat": bool(ANTHROPIC_API_KEY),
            "quantum_chip": "Wukong_180" if _qcloud_ready else "CPU_simulator",
            "origin_qc_token": bool(ORIGIN_QC_TOKEN),
            "timestamp": datetime.utcnow().isoformat()}

@app.post("/api/setup-webhook")
async def setup_webhook(request: Request):
    """Регистрирует Telegram Webhook + команды в меню бота."""
    if not BOT_TOKEN:
        return {"ok": False, "error": "BOT_TOKEN не задан"}
    base_url = str(request.base_url).rstrip("/").replace("http://", "https://")
    webhook_url = f"{base_url}/api/telegram/callback"
    results = {}
    try:
        async with aiohttp.ClientSession() as s:
            # 1. Регистрируем webhook
            r = await s.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
                json={"url": webhook_url, "allowed_updates": ["message", "callback_query"]},
                timeout=aiohttp.ClientTimeout(total=10)
            )
            results["webhook"] = await r.json()

            # 2. Регистрируем команды — появятся в меню "/" у пользователя
            r2 = await s.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setMyCommands",
                json={"commands": [
                    {"command": "menu",      "description": "🏠 Главное меню"},
                    {"command": "stats",     "description": "📊 Статистика торговли"},
                    {"command": "airdrops",  "description": "🪂 Топ Airdrop возможности"},
                    {"command": "settings",  "description": "⚙️ Настройки (Q-Score, Cooldown)"},
                    {"command": "balance",   "description": "💰 Баланс счёта"},
                    {"command": "positions", "description": "📈 Открытые позиции"},
                ]},
                timeout=aiohttp.ClientTimeout(total=10)
            )
            results["commands"] = await r2.json()

        return {"ok": True, "webhook_url": webhook_url, "results": results}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/setup-webhook")
async def get_webhook_info():
    """Проверяет текущий статус Telegram Webhook."""
    if not BOT_TOKEN:
        return {"ok": False, "error": "BOT_TOKEN не задан"}
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo",
                            timeout=aiohttp.ClientTimeout(total=5))
            return await r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

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
        "cooldown_sec":  COOLDOWN,
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
