"""
QuantumTrade AI - FastAPI Backend v10.1.0
Full-stack AI trading platform with multi-exchange support, 15-agent MiroFish v3,
advanced technical analysis (pandas-ta), social sentiment (LunarCrush + Reddit),
whale tracking, copy-trading intelligence, and continuous self-learning.

Changelog:
v10.0: pandas-ta indicators, LunarCrush Galaxy Score, Reddit sentiment,
       MiroFish v3 (role-based), security hardening, /sentiment command,
       continuous self-learning v2, advanced TA (MACD/BB/Stochastic/ADX)
v9.2:  Macro context, whale alerts, copy-trading, F&G history, persistent memory
v9.1:  Deep trade analytics, MiroFish v2 (12 agents, memory, arb specialists)
v9.0:  ByBit multi-exchange, cross-exchange arbitrage, MiroFish Lite
"""

import asyncio
import hashlib
import hmac
import html as html_mod
import time
import base64
import json
import os
import math
import random
from datetime import datetime
from typing import Optional, List, Dict
from collections import defaultdict
import aiohttp
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import db  # v8.2: PostgreSQL persistent storage

# v10.0: Advanced TA — pandas-ta for MACD, Bollinger, Stochastic, ADX, etc.
try:
    import pandas as pd
    import pandas_ta as ta
    _TA_AVAILABLE = True
    print("[ta] pandas-ta loaded ✅")
except ImportError:
    _TA_AVAILABLE = False
    print("[ta] pandas-ta not available — using built-in indicators")

app = FastAPI(title="QuantumTrade AI", version="10.0.0")

# v10.0: CORS — open for Telegram WebApp (origin varies)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def serve_mini_app():
    """v7.4.3: Serve the Telegram Mini App — no-cache headers to avoid stale version."""
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(
            content=content,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
        )
    except FileNotFoundError:
        return HTMLResponse(content="<h1>QuantumTrade AI</h1><p>index.html not found</p>", status_code=404)

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
# v8.3: 3-tier AI architecture
DEEPSEEK_API_KEY  = os.getenv("DEEPSEEK_API_KEY", "")   # DeepSeek V3 — text/strategy (free tier)
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")  # OpenAI-compatible
AI_TIER_VISION    = os.getenv("AI_TIER_VISION", "haiku")     # haiku (default) | opus
AI_TIER_CHAT      = os.getenv("AI_TIER_CHAT", "deepseek")    # deepseek (default) | haiku | sonnet
AI_TIER_CRITICAL  = os.getenv("AI_TIER_CRITICAL", "opus")    # opus (default) | sonnet
ORIGIN_QC_TOKEN   = os.getenv("ORIGIN_QC_TOKEN", "")     # Phase 6: Origin QC Wukong 180
AWS_ACCESS_KEY_ID  = os.getenv("AWS_ACCESS_KEY_ID",  "")   # v7.3.1: Amazon Braket
AWS_SECRET_KEY     = os.getenv("AWS_SECRET_ACCESS_KEY", "") # v7.3.1: Amazon Braket
AWS_REGION         = os.getenv("AWS_REGION", "us-east-1")  # v7.3.1: Braket region
BRAKET_S3_BUCKET   = os.getenv("BRAKET_S3_BUCKET",   "")   # v7.3.1: S3 бакет для результатов
BRAKET_DEVICE_ARN  = os.getenv("BRAKET_DEVICE_ARN",  "arn:aws:braket:us-east-1::device/qpu/ionq/Harmony")  # v7.3.1
RAILWAY_TOKEN        = os.getenv("RAILWAY_TOKEN", "")       # v7.2.1: Railway API — persist variable changes
RAILWAY_PUBLIC_DOMAIN= os.getenv("RAILWAY_PUBLIC_DOMAIN", "")  # v7.4.0: авто-URL Railway сервиса
WEBAPP_URL           = os.getenv("WEBAPP_URL", "")          # v7.4.0: если не задан — берётся из Railway URL
API_SECRET           = os.getenv("API_SECRET", "")          # v7.3.3: защита приватных эндпоинтов
TG_WEBHOOK_SECRET    = os.getenv("TG_WEBHOOK_SECRET", "")   # v10.0: Telegram webhook secret_token verification

# ── v9.0: ByBit Multi-Exchange ─────────────────────────────────────────────
BYBIT_API_KEY     = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET  = os.getenv("BYBIT_API_SECRET", "")
BYBIT_BASE_URL    = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")
BYBIT_ENABLED     = bool(BYBIT_API_KEY and BYBIT_API_SECRET)

# ── v7.3.3: API-аутентификация ──────────────────────────────────────────────
async def verify_api_key(x_api_key: str = Header(None, alias="X-API-Key")):
    """Проверяет X-API-Key заголовок на всех приватных эндпоинтах.
    Если API_SECRET задан в Railway env — требуем совпадения.
    Если API_SECRET не задан — выкидываем ошибку (секрет обязателен для приватных маршрутов).
    """
    if not API_SECRET:
        raise HTTPException(status_code=503, detail="API_SECRET not configured on server")
    if x_api_key != API_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")

# ── v7.3.3: Rate Limiting для AI Chat (защита бюджета Claude API) ────────────
_ai_chat_rl: dict = {}   # ip → (count, window_start_ts)
_AI_CHAT_LIMIT = 20      # макс 20 запросов
_AI_CHAT_WINDOW = 60     # в минуту с одного IP

RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.08"))  # v8.3.2: 8% (was 25%) — safe default per trading.md
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.66"))
MIN_Q_SCORE    = int(os.getenv("MIN_Q_SCORE", "77"))  # v8.3.2: 77 (was 55) — per trading.md
# v7.2.2: per-pair Q thresholds = MIN_Q_SCORE - 1
PAIR_Q_THRESHOLDS: dict = {"BTC-USDT": 76, "ETH-USDT": 76, "SOL-USDT": 76,
                            "BNB-USDT": 76, "XRP-USDT": 76, "AVAX-USDT": 76}
COOLDOWN       = int(os.getenv("COOLDOWN_STD", os.getenv("COOLDOWN", "600")))  # v8.3.2: 600s (was 450)
MAX_LEVERAGE   = min(int(os.getenv("MAX_LEVERAGE", "3")), 5)  # v8.3.3: cap at 5x even if env says higher
# v10.0: Lowered thresholds for small accounts ($30-50 range)
ARB_RESERVE_USDT = float(os.getenv("ARB_RESERVE_USDT", "3"))     # v10.0: $3 (was $15) — small account mode
SPOT_BUY_MIN_USDT = float(os.getenv("SPOT_BUY_MIN_USDT", "5"))   # v10.0: $5 (was $20) — allow small trades
# v10.0: Max simultaneous open positions — prevents draining all USDT in 1 cycle
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "2"))     # v10.0: max 2 at a time (was unlimited)
# v7.2.3: TP/SL ratio улучшен до 3:1 (было 2:1) — исправляет асимметрию убытков
TP_PCT         = 0.04   # v10.0: 4% (was 6%) — faster profit taking for small account
SL_PCT         = 0.02   # v7.2.3: 2% (было 2.5%) → ratio 2:1
TRAIL_TRIGGER  = 0.02   # v10.0: trailing stop при +2% прибыли (was 2.5%)
TRAIL_PCT      = 0.01   # v10.0: закрывать при откате 1% от пика (was 1.5%)
TEST_MODE      = os.getenv("TEST_MODE", "false").lower() == "true"  # v6.7: default LIVE mode
if TEST_MODE:
    RISK_PER_TRADE = min(RISK_PER_TRADE, 0.05)  # v8.3.2: test mode even more conservative

AUTOPILOT  = True
SPOT_PAIRS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT", "AVAX-USDT"]
FUT_PAIRS  = ["XBTUSDTM", "ETHUSDTM", "SOLUSDTM"]

last_signals  = {}
last_q_score  = 0.0
_q_alert_last: dict = {}   # v7.2.2: антиспам для Q-алертов {"sell": ts, "buy": ts}
trade_log: List[dict] = []

# ── Персистентное хранилище сделок (v7.5.0: увеличено до 2000, /data/) ────────
_TRADES_DIR = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "/tmp")
_TRADES_FILE = os.path.join(_TRADES_DIR, "qt_trades.json")
_TRADES_STATS_FILE = os.path.join(_TRADES_DIR, "qt_performance.json")

# v7.5.0: Агрегированная статистика для самообучения бота
_perf_stats = {
    "total_trades": 0, "wins": 0, "losses": 0, "total_pnl": 0.0,
    "by_strategy": {"B": {"trades": 0, "wins": 0, "pnl": 0.0}, "C": {"trades": 0, "wins": 0, "pnl": 0.0}, "DUAL": {"trades": 0, "wins": 0, "pnl": 0.0}},
    "by_symbol": {},
    "avg_q_score_win": 0.0, "avg_q_score_loss": 0.0,
    "best_hour_utc": None, "worst_hour_utc": None,
    "streak": 0, "max_streak": 0, "max_drawdown": 0.0,
    "updated": None,
}

def _load_trades_from_disk():
    """Загружаем историю сделок при старте."""
    global trade_log, _perf_stats
    try:
        if os.path.exists(_TRADES_FILE):
            with open(_TRADES_FILE, "r") as f:
                trade_log = json.load(f)
            print(f"[trades] загружено {len(trade_log)} сделок из {_TRADES_FILE}")
        if os.path.exists(_TRADES_STATS_FILE):
            with open(_TRADES_STATS_FILE, "r") as f:
                loaded = json.load(f)
                _perf_stats.update(loaded)
            print(f"[perf] статистика загружена: {_perf_stats['total_trades']} сделок, PnL: {_perf_stats['total_pnl']}")
    except Exception as e:
        print(f"[trades] ошибка загрузки: {e}")

def _save_trades_to_disk():
    """Сохраняем trade_log на диск после каждой новой сделки. v7.5.0: 2000 записей."""
    try:
        with open(_TRADES_FILE, "w") as f:
            json.dump(trade_log[-2000:], f)  # v7.5.0: 500→2000
    except Exception as e:
        print(f"[trades] ошибка записи: {e}")

def _save_perf_stats():
    """v7.5.0: Сохраняем агрегированную статистику производительности."""
    try:
        _perf_stats["updated"] = datetime.utcnow().isoformat()
        with open(_TRADES_STATS_FILE, "w") as f:
            json.dump(_perf_stats, f)
    except Exception as e:
        print(f"[perf] ошибка записи: {e}")

def _update_perf_on_trade(trade: dict):
    """v7.5.0: Обновляем статистику после каждой закрытой сделки для самообучения."""
    pnl = trade.get("pnl_usdt", 0.0)
    strat = trade.get("strategy", "B")
    symbol = trade.get("symbol", "?")
    q = trade.get("q_score", 0)
    is_win = pnl > 0

    _perf_stats["total_trades"] += 1
    _perf_stats["total_pnl"] = round(_perf_stats["total_pnl"] + pnl, 4)
    if is_win:
        _perf_stats["wins"] += 1
        _perf_stats["streak"] = max(0, _perf_stats["streak"]) + 1
    else:
        _perf_stats["losses"] += 1
        _perf_stats["streak"] = min(0, _perf_stats["streak"]) - 1
    _perf_stats["max_streak"] = max(_perf_stats["max_streak"], abs(_perf_stats["streak"]))

    # По стратегиям
    if strat not in _perf_stats["by_strategy"]:
        _perf_stats["by_strategy"][strat] = {"trades": 0, "wins": 0, "pnl": 0.0}
    s = _perf_stats["by_strategy"][strat]
    s["trades"] += 1
    if is_win: s["wins"] += 1
    s["pnl"] = round(s["pnl"] + pnl, 4)

    # По символам
    if symbol not in _perf_stats["by_symbol"]:
        _perf_stats["by_symbol"][symbol] = {"trades": 0, "wins": 0, "pnl": 0.0}
    sym = _perf_stats["by_symbol"][symbol]
    sym["trades"] += 1
    if is_win: sym["wins"] += 1
    sym["pnl"] = round(sym["pnl"] + pnl, 4)

    # Средний Q-Score для побед/поражений
    total = _perf_stats["total_trades"]
    if is_win and _perf_stats["wins"] > 0:
        prev = _perf_stats["avg_q_score_win"] * (_perf_stats["wins"] - 1)
        _perf_stats["avg_q_score_win"] = round((prev + q) / _perf_stats["wins"], 1)
    elif not is_win and _perf_stats["losses"] > 0:
        prev = _perf_stats["avg_q_score_loss"] * (_perf_stats["losses"] - 1)
        _perf_stats["avg_q_score_loss"] = round((prev + q) / _perf_stats["losses"], 1)

    # Max drawdown
    if _perf_stats["total_pnl"] < _perf_stats["max_drawdown"]:
        _perf_stats["max_drawdown"] = round(_perf_stats["total_pnl"], 4)

    _save_perf_stats()

# ── QAOA State ─────────────────────────────────────────────────────────────────
_quantum_bias: Dict[str, float] = {}   # symbol → bias [-15..+15]
_quantum_ts: float = 0.0               # timestamp последнего запуска
_qaoa_best_angles: dict  = {"gamma": [], "beta": [], "score": -999.0}  # v7.3.0: память лучших углов
_corr_cache: dict        = {}   # v7.3.0: кэш живых корреляций
_corr_cache_ts: float    = 0.0  # v7.3.0: время последнего обновления
_braket_ts: float    = 0.0   # v7.3.1: timestamp последнего запуска Braket
_braket_bias: dict   = {}    # v7.3.1: последний bias от Braket
_braket_ready: bool  = bool(os.getenv("AWS_ACCESS_KEY_ID","") and os.getenv("AWS_SECRET_ACCESS_KEY",""))  # v7.3.1

# v7.2.0: QAOA rolling average smoother (окно=3, clamp=±5 на CPU, ±15 на чипе)
_qaoa_history: Dict[str, list] = {}    # symbol → последние N значений
_QAOA_WINDOW = 3

def _smooth_qaoa_bias(symbol: str, raw_bias: float, clamp: float = 15.0) -> float:
    """Rolling average + clamp для QAOA bias. Убирает шум CPU симулятора."""
    hist = _qaoa_history.setdefault(symbol, [])
    hist.append(max(-clamp, min(clamp, raw_bias)))
    if len(hist) > _QAOA_WINDOW:
        hist.pop(0)
    return round(sum(hist) / len(hist), 2)

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


def _qaoa_cpu_simulate(price_changes: List[float], p_layers: int = 2, corr_matrix: list = None) -> List[float]:
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
    # v7.3.0: Angle Memory — стартуем от лучших известных углов, а не случайных
    random.seed(int(time.time()) // 300)
    if len(_qaoa_best_angles.get("gamma", [])) == p_layers:
        gamma = [max(0.05, min(math.pi,    _qaoa_best_angles["gamma"][j] + random.uniform(-0.2, 0.2))) for j in range(p_layers)]
        beta  = [max(0.05, min(math.pi/2,  _qaoa_best_angles["beta"][j]  + random.uniform(-0.1, 0.1))) for j in range(p_layers)]
    else:
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
                    _cm = corr_matrix if corr_matrix else CORR_MATRIX  # v7.3.0: live corr
                    cost += gamma[layer] * _cm[i][j] * bits[i] * bits[j]
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

    # v7.3.0: Сохраняем лучшие углы если сигнал сильнее предыдущего
    _total_signal = sum(abs(b) for b in bias)
    if _total_signal > _qaoa_best_angles.get("score", -999.0):
        _qaoa_best_angles["gamma"] = list(gamma)
        _qaoa_best_angles["beta"]  = list(beta)
        _qaoa_best_angles["score"] = _total_signal
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
    global _quantum_bias, _quantum_ts, _corr_cache, _corr_cache_ts, _braket_ts, _braket_bias
    # v7.3.0: Мультитаймфреймовый вход QAOA — 50%×1h + 30%×4h + 20%×24h
    prices_snap = _cache_get("all_prices", 300) or {}
    all_p = prices_snap.get("prices", {})
    changes_list = []
    for _p in PAIR_NAMES:
        ch_1h  = price_changes.get(_p, 0.0)
        _pd    = all_p.get(_p, {})
        ch_4h  = _pd.get("change_4h",  ch_1h * 0.5)
        ch_24h = _pd.get("change_24h", ch_1h * 0.25)
        changes_list.append(round(ch_1h * 0.5 + ch_4h * 0.3 + ch_24h * 0.2, 4))
    # v7.3.0: Живая матрица корреляций из реальных данных
    _now_c = time.time()
    if _now_c - _corr_cache_ts > 3600 and len(all_p) >= len(PAIR_NAMES):
        try:
            _vecs = [[all_p.get(_p2,{}).get("change_1h",0), all_p.get(_p2,{}).get("change_4h",0), all_p.get(_p2,{}).get("change_24h",0)] for _p2 in PAIR_NAMES]
            _mat = [[1.0]*len(PAIR_NAMES) for _ in range(len(PAIR_NAMES))]
            for _i in range(len(PAIR_NAMES)):
                for _j in range(_i+1, len(PAIR_NAMES)):
                    _same = sum(1 for _a,_b in zip(_vecs[_i],_vecs[_j]) if (_a>=0)==(_b>=0))
                    _c = round(0.4 + _same / (len(_vecs[_i]) * 1.5), 2)
                    _mat[_i][_j] = _mat[_j][_i] = min(1.0, _c)
            _corr_cache["matrix"] = _mat
            _corr_cache_ts = _now_c
            print(f"[qaoa] живая корреляционная матрица обновлена")
        except Exception as _ce:
            print(f"[qaoa] corr error: {_ce}")
    live_corr = _corr_cache.get("matrix", CORR_MATRIX)
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
                None, _qaoa_cpu_simulate, changes_list, 2, live_corr  # v7.3.0: live corr
            )
        raw_bias = {PAIR_NAMES[i]: bias_list[i] for i in range(N_PAIRS)}

        # v7.6: Amazon Braket энсембль — ЭКОНОМ: 4×/день (каждые 6 часов)
        braket_interval = int(os.getenv("BRAKET_INTERVAL", "21600"))  # 6ч = 4 запуска/день
        if _braket_ready and (time.time() - _braket_ts) >= braket_interval:
            try:
                braket_list = await _braket_qaoa_run(changes_list, live_corr)
                _braket_bias.update({PAIR_NAMES[i]: braket_list[i] for i in range(N_PAIRS)})
                _braket_ts = time.time()
                chip_used  = chip_used + "+Braket"
                # Энсембль: CPU 30% + Braket 70% — реальное железо важнее
                for i, p in enumerate(PAIR_NAMES):
                    raw_bias[p] = round(raw_bias[p] * 0.30 + braket_list[i] * 0.70, 2)
                log_b = " ".join(f"{p.split('-')[0]}={_braket_bias[p]:+.1f}" for p in PAIR_NAMES)
                print(f"[braket] энсембль обновлён: {log_b}", flush=True)
            except Exception as be:
                print(f"[braket] ошибка энсембля: {be}", flush=True)
        elif _braket_bias and _braket_ready:
            # Между запусками Braket: смешиваем со старым Braket-результатом (50/50)
            for p in PAIR_NAMES:
                if p in _braket_bias:
                    raw_bias[p] = round(raw_bias[p] * 0.50 + _braket_bias[p] * 0.50, 2)

        clamp_val = 15.0 if "Wukong" in chip_used else (12.0 if "Braket" in chip_used else 5.0)
        _quantum_bias = {sym: _smooth_qaoa_bias(sym, b, clamp_val) for sym, b in raw_bias.items()}
        _quantum_ts = time.time()
        log_str = " ".join(f"{p.split('-')[0]}={b:+.1f}" for p, b in _quantum_bias.items())
        print(f"[qaoa/{chip_used}] bias(smoothed): {log_str}")
    except Exception as e:
        print(f"[qaoa] error ({chip_used}): {e}")
        _quantum_bias = {p: 0.0 for p in PAIR_NAMES}
    return _quantum_bias


# ══════════════════════════════════════════════════════════════════════════════
# v7.3.1: Amazon Braket QAOA — квантовый энсембль (12×/день, каждые 2 часа)
# ══════════════════════════════════════════════════════════════════════════════

def _braket_run_sync(changes_list: list, live_corr: list) -> list:
    """v7.3.1: Синхронный QAOA на Amazon Braket QPU — для run_in_executor."""
    try:
        import os, boto3
        os.environ["AWS_ACCESS_KEY_ID"]     = AWS_ACCESS_KEY_ID
        os.environ["AWS_SECRET_ACCESS_KEY"] = AWS_SECRET_KEY
        os.environ["AWS_DEFAULT_REGION"]    = AWS_REGION
        from braket.circuits import Circuit
        from braket.aws import AwsDevice

        n  = N_PAIRS
        cm = live_corr if live_corr else CORR_MATRIX
        mom = [max(-1.0, min(1.0, pc / 5.0)) for pc in changes_list]

        # Берём лучшие углы из памяти (уже оптимизированы CPU-циклами)
        g = _qaoa_best_angles["gamma"][0] if _qaoa_best_angles.get("gamma") else 0.6
        b = _qaoa_best_angles["beta"][0]  if _qaoa_best_angles.get("beta")  else 0.35

        # Строим QAOA схему (p=1)
        circ = Circuit()
        for i in range(n):                             # суперпозиция |+⟩^n
            circ.h(i)
        for i in range(n):                             # Cost unitary U_C(γ)
            for j in range(i + 1, n):
                angle = 2 * g * cm[i][j]
                circ.cnot(i, j)
                circ.rz(j, angle)
                circ.cnot(i, j)
        for i in range(n):                             # Momentum bias RZ
            circ.rz(i, mom[i] * g * 0.5)
        for i in range(n):                             # Mixer U_B(β)
            circ.rx(i, 2 * b)

        # Запуск на QPU
        device = AwsDevice(BRAKET_DEVICE_ARN)
        n_shots = int(os.getenv("BRAKET_SHOTS", "256"))  # v7.6: эконом 256 (было 1024)
        task   = device.run(circ, s3_destination_folder=(BRAKET_S3_BUCKET, "qaoa"), shots=n_shots)
        result = task.result()

        # Вычисляем <Z_i> из измерений
        meas  = result.measurements
        z_exp = [0.0] * n
        for shot in meas:
            for i in range(min(n, len(shot))):
                z_exp[i] += (1 - 2 * int(shot[i])) / len(meas)

        # bias [-15..+15] с учётом momentum
        bias = []
        for i in range(n):
            bv = z_exp[i] * 15.0
            if   mom[i] >  0.1: bv =  abs(bv)
            elif mom[i] < -0.1: bv = -abs(bv)
            bias.append(round(bv, 1))

        log_str = " ".join(f"{PAIR_NAMES[i].split('-')[0]}={bias[i]:+.1f}" for i in range(n))
        print(f"[braket] QPU result: {log_str}", flush=True)
        return bias

    except ImportError:
        print("[braket] amazon-braket-sdk не установлен — pip install amazon-braket-sdk", flush=True)
        return [0.0] * N_PAIRS
    except Exception as e:
        print(f"[braket] error: {e}", flush=True)
        return [0.0] * N_PAIRS


async def _braket_qaoa_run(changes_list: list, live_corr: list) -> list:
    """v7.3.1: Асинхронная обёртка для Braket QPU."""
    import functools
    return await asyncio.get_event_loop().run_in_executor(
        None, functools.partial(_braket_run_sync, changes_list, live_corr)
    )


def log_trade(symbol, side, price, size, tp, sl, confidence, q_score, pattern, account="spot", strategy="B"):
    # v9.2: capture F&G and macro context at trade time for correlation analysis
    fg_now = _cache_get("fear_greed", 7200)  # use cached F&G if available
    fg_val = fg_now.get("value", 0) if fg_now else 0
    extra = {"fg_value": fg_val}
    if _macro_cache.get("btc_dominance"):
        extra["btc_dom"] = _macro_cache["btc_dominance"]
    if _whale_alert_cache.get("signal"):
        extra["whale_signal"] = _whale_alert_cache["signal"]
    trade = {
        "id": len(trade_log) + 1, "ts": datetime.utcnow().isoformat(), "open_ts": time.time(),
        "symbol": symbol, "side": side, "price": price, "size": size,
        "tp": tp, "sl": sl, "confidence": confidence, "q_score": q_score,
        "pattern": pattern, "account": account, "strategy": strategy, "status": "open", "pnl": None,
        "extra": extra,
    }
    trade_log.append(trade)
    if len(trade_log) > 2000:
        trade_log.pop(0)
    _save_trades_to_disk()
    # v8.2: PostgreSQL persistent storage
    if db.is_ready():
        asyncio.ensure_future(db.insert_trade(trade))


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


# ── v9.0: ByBit V5 API ─────────────────────────────────────────────────────────
_bybit_stats = {"calls": 0, "errors": 0, "last_call": 0}

def bybit_headers(method: str, endpoint: str, body: str = "") -> dict:
    """ByBit V5 HMAC-SHA256 auth headers."""
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"
    if method.upper() == "GET":
        # For GET: timestamp + api_key + recv_window + query_string
        param_str = timestamp + BYBIT_API_KEY + recv_window + body  # body = query string for GET
    else:
        param_str = timestamp + BYBIT_API_KEY + recv_window + body
    signature = hmac.new(
        BYBIT_API_SECRET.encode(), param_str.encode(), hashlib.sha256
    ).hexdigest()
    return {
        "X-BAPI-API-KEY": BYBIT_API_KEY,
        "X-BAPI-SIGN": signature,
        "X-BAPI-SIGN-TYPE": "2",
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": recv_window,
        "Content-Type": "application/json",
    }


async def bybit_request(method: str, endpoint: str, params: dict = None) -> dict:
    """Universal ByBit V5 API request handler."""
    if not BYBIT_ENABLED:
        return {"success": False, "error": "ByBit not configured"}
    _bybit_stats["calls"] += 1
    _bybit_stats["last_call"] = time.time()
    url = BYBIT_BASE_URL + endpoint
    try:
        async with aiohttp.ClientSession() as s:
            if method.upper() == "GET":
                qs = "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
                headers = bybit_headers("GET", endpoint, qs)
                r = await s.get(url + ("?" + qs if qs else ""),
                                headers=headers,
                                timeout=aiohttp.ClientTimeout(total=10))
            else:
                body = json.dumps(params or {})
                headers = bybit_headers("POST", endpoint, body)
                r = await s.post(url, headers=headers, data=body,
                                 timeout=aiohttp.ClientTimeout(total=10))
            data = await r.json()
            if data.get("retCode") == 0:
                return {"success": True, "data": data.get("result", {}), "raw": data}
            else:
                _bybit_stats["errors"] += 1
                return {"success": False, "error": data.get("retMsg", "unknown"),
                        "code": data.get("retCode")}
    except Exception as e:
        _bybit_stats["errors"] += 1
        log_activity(f"[bybit] API error: {e}")
        return {"success": False, "error": str(e)}


async def bybit_get_balance() -> dict:
    """Get ByBit unified account balance."""
    result = await bybit_request("GET", "/v5/account/wallet-balance",
                                  {"accountType": "UNIFIED"})
    if not result["success"]:
        return {"total_usdt": 0, "success": False, "error": result.get("error")}
    coins = result["data"].get("list", [{}])[0].get("coin", [])
    total_usdt = 0
    balances = {}
    for c in coins:
        cur = c.get("coin", "")
        eq = float(c.get("equity") or 0)
        usd_val = float(c.get("usdValue") or 0)
        if eq > 0:
            balances[cur] = {"equity": eq, "usd_value": round(usd_val, 2),
                             "available": float(c.get("availableToWithdraw") or 0)}
        if cur == "USDT":
            total_usdt = eq
    return {"total_usdt": round(total_usdt, 2), "balances": balances,
            "success": True}


async def bybit_get_ticker(symbol: str) -> float:
    """Get last price for symbol on ByBit. Symbol format: BTCUSDT (no dash)."""
    bb_symbol = symbol.replace("-", "")
    result = await bybit_request("GET", "/v5/market/tickers",
                                  {"category": "spot", "symbol": bb_symbol})
    if result["success"]:
        tickers = result["data"].get("list", [])
        if tickers:
            return float(tickers[0].get("lastPrice", 0))
    return 0.0


async def bybit_get_funding_rate(symbol: str) -> dict:
    """Get current funding rate for a perpetual contract."""
    bb_symbol = symbol.replace("-", "").replace("USDT", "USDT")
    result = await bybit_request("GET", "/v5/market/funding/history",
                                  {"category": "linear", "symbol": bb_symbol, "limit": "1"})
    if result["success"]:
        items = result["data"].get("list", [])
        if items:
            return {"rate": float(items[0].get("fundingRate", 0)),
                    "time": items[0].get("fundingRateTimestamp", ""),
                    "success": True}
    return {"rate": 0, "success": False}


async def bybit_spot_prices(symbols: list) -> dict:
    """Get prices for multiple symbols from ByBit. Returns {symbol: price}."""
    prices = {}
    for sym in symbols:
        p = await bybit_get_ticker(sym)
        if p > 0:
            prices[sym] = p
    return prices


# ── v10.0: ByBit Spot Trading ────────────────────────────────────────────────

async def bybit_place_spot_order(symbol: str, side: str, qty: float, order_type: str = "Market") -> dict:
    """Place a ByBit V5 spot order. symbol='BTC-USDT', side='Buy'/'Sell', qty in base coin."""
    if not BYBIT_ENABLED:
        return {"success": False, "error": "ByBit not configured"}
    bb_symbol = symbol.replace("-", "")  # BTC-USDT → BTCUSDT
    params = {
        "category": "spot",
        "symbol": bb_symbol,
        "side": side.capitalize(),  # Buy / Sell
        "orderType": order_type,
        "qty": str(qty),
    }
    # For market buy, use USDT amount via marketUnit=quoteCoin
    if side.lower() == "buy" and order_type == "Market":
        params["marketUnit"] = "quoteCoin"  # qty is in USDT, not base coin
    log_activity(f"[bybit] Placing {side} {symbol} qty={qty} type={order_type}")
    result = await bybit_request("POST", "/v5/order/create", params)
    if result["success"]:
        order_id = result["data"].get("orderId", "?")
        log_activity(f"[bybit] Order OK: {order_id}")
        return {"success": True, "orderId": order_id, "data": result["data"]}
    else:
        log_activity(f"[bybit] Order FAILED: {result.get('error')}")
        return {"success": False, "error": result.get("error", "unknown")}


async def bybit_sell_spot(symbol: str, qty: float = 0) -> dict:
    """Sell spot coin on ByBit. If qty=0, sell all available."""
    if not BYBIT_ENABLED:
        return {"success": False, "error": "ByBit not configured"}
    if qty <= 0:
        # Get available balance of the coin
        bal = await bybit_get_balance()
        if not bal["success"]:
            return {"success": False, "error": "Could not fetch ByBit balance"}
        coin = symbol.replace("-USDT", "")
        coin_bal = bal.get("balances", {}).get(coin, {})
        qty = coin_bal.get("available", 0)
        if qty <= 0:
            return {"success": False, "error": f"No {coin} balance on ByBit"}
    return await bybit_place_spot_order(symbol, "Sell", qty)


async def bybit_get_spot_balances() -> dict:
    """Get all non-zero spot balances with prices for ByBit. Similar to KuCoin get_spot_balances()."""
    bal = await bybit_get_balance()
    if not bal["success"]:
        return {}
    result = {}
    for coin, info in bal.get("balances", {}).items():
        if coin == "USDT" or info.get("available", 0) <= 0:
            continue
        symbol = f"{coin}-USDT"
        price = await bybit_get_ticker(symbol)
        if price > 0:
            result[symbol] = {
                "available": info["available"],
                "price": price,
                "usd_value": round(info["available"] * price, 2),
            }
    return result


# ══════════════════════════════════════════════════════════════════════════════
# v10.1: EARN ENGINE — Passive Income via Flexible Savings
# KuCoin Earn API + ByBit Earn API (Flexible Savings only — instant redeem)
# ══════════════════════════════════════════════════════════════════════════════

EARN_ENABLED = os.getenv("EARN_ENABLED", "true").lower() == "true"
EARN_MIN_IDLE_USDT = float(os.getenv("EARN_MIN_IDLE_USDT", "5.0"))   # don't earn below $5
EARN_RESERVE_USDT = float(os.getenv("EARN_RESERVE_USDT", "3.0"))     # always keep $3 liquid
_earn_stats = {
    "total_subscribed": 0.0, "total_redeemed": 0.0,
    "total_earned_interest": 0.0, "subscriptions": 0, "redemptions": 0,
    "last_action": 0, "errors": 0,
    "kucoin_subscribed": 0.0, "bybit_subscribed": 0.0,
    "best_apr": 0.0, "best_apr_exchange": "",
}
_earn_positions: list = []   # [{exchange, product_id, coin, amount, apr, subscribed_at}]
_earn_rates_cache = {"ts": 0, "data": {}}  # cache APR data for 10 min


async def kucoin_earn_get_savings_products(coin: str = "USDT") -> list:
    """KuCoin: GET /api/v1/earn/saving/products — Flexible Savings products."""
    endpoint = f"/api/v1/earn/saving/products?currency={coin}"
    try:
        headers = kucoin_headers("GET", endpoint)
        async with aiohttp.ClientSession() as s:
            r = await s.get(f"https://api.kucoin.com{endpoint}",
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=10))
            data = await r.json()
            if data.get("code") == "200000":
                items = data.get("data", {}).get("items", data.get("data", []))
                if isinstance(items, dict):
                    items = [items]
                return items if isinstance(items, list) else []
            else:
                log_activity(f"[earn/kc] get products error: {data.get('msg', data.get('code','?'))}")
                return []
    except Exception as e:
        log_activity(f"[earn/kc] get products exception: {e}")
        return []


async def kucoin_earn_subscribe(product_id: str, amount: float) -> dict:
    """KuCoin: POST /api/v1/earn/orders — Subscribe to Flexible Savings."""
    endpoint = "/api/v1/earn/orders"
    body = json.dumps({"productId": product_id, "amount": str(amount), "accountType": "MAIN"})
    try:
        headers = kucoin_headers("POST", endpoint, body)
        async with aiohttp.ClientSession() as s:
            r = await s.post(f"https://api.kucoin.com{endpoint}",
                             headers=headers, data=body,
                             timeout=aiohttp.ClientTimeout(total=10))
            data = await r.json()
            if data.get("code") == "200000":
                log_activity(f"[earn/kc] subscribed ${amount:.2f} USDT to product {product_id}")
                return {"success": True, "order_id": data.get("data", {}).get("orderId", ""),
                        "exchange": "kucoin"}
            else:
                log_activity(f"[earn/kc] subscribe error: {data.get('msg', '?')}")
                return {"success": False, "error": data.get("msg", "unknown")}
    except Exception as e:
        log_activity(f"[earn/kc] subscribe exception: {e}")
        return {"success": False, "error": str(e)}


async def kucoin_earn_redeem(order_id: str, amount: float) -> dict:
    """KuCoin: DELETE /api/v1/earn/orders — Redeem from Flexible Savings."""
    endpoint = "/api/v1/earn/orders"
    body = json.dumps({"orderId": order_id, "amount": str(amount)})
    try:
        headers = kucoin_headers("DELETE", endpoint, body)
        async with aiohttp.ClientSession() as s:
            r = await s.delete(f"https://api.kucoin.com{endpoint}",
                               headers=headers, data=body,
                               timeout=aiohttp.ClientTimeout(total=10))
            data = await r.json()
            if data.get("code") == "200000":
                log_activity(f"[earn/kc] redeemed ${amount:.2f} from order {order_id}")
                return {"success": True, "exchange": "kucoin"}
            else:
                log_activity(f"[earn/kc] redeem error: {data.get('msg', '?')}")
                return {"success": False, "error": data.get("msg", "unknown")}
    except Exception as e:
        log_activity(f"[earn/kc] redeem exception: {e}")
        return {"success": False, "error": str(e)}


async def kucoin_earn_get_hold_assets(coin: str = "USDT") -> list:
    """KuCoin: GET /api/v1/earn/hold-assets — Current Earn positions."""
    endpoint = f"/api/v1/earn/hold-assets?currency={coin}&productCategory=SAVING"
    try:
        headers = kucoin_headers("GET", endpoint)
        async with aiohttp.ClientSession() as s:
            r = await s.get(f"https://api.kucoin.com{endpoint}",
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=10))
            data = await r.json()
            if data.get("code") == "200000":
                return data.get("data", {}).get("items", [])
            return []
    except Exception as e:
        log_activity(f"[earn/kc] hold assets error: {e}")
        return []


async def bybit_earn_get_products(coin: str = "USDT") -> list:
    """ByBit: GET /v5/earn/product — Flexible Savings products."""
    res = await bybit_request("GET", "/v5/earn/product", {
        "category": "FlexibleSaving", "coin": coin
    })
    if res["success"]:
        return res["data"].get("list", [])
    else:
        log_activity(f"[earn/bb] get products error: {res.get('error','?')}")
        return []


async def bybit_earn_subscribe(product_id: str, amount: float, coin: str = "USDT") -> dict:
    """ByBit: POST /v5/earn/place-order — Subscribe to Flexible Savings."""
    res = await bybit_request("POST", "/v5/earn/place-order", {
        "category": "FlexibleSaving",
        "productId": product_id,
        "coin": coin,
        "amount": str(amount),
        "orderType": "Stake",
        "accountType": "FUND",
    })
    if res["success"]:
        order_id = res["data"].get("orderId", "")
        log_activity(f"[earn/bb] subscribed ${amount:.2f} {coin} to product {product_id}")
        return {"success": True, "order_id": order_id, "exchange": "bybit"}
    else:
        log_activity(f"[earn/bb] subscribe error: {res.get('error','?')}")
        return {"success": False, "error": res.get("error", "unknown")}


async def bybit_earn_redeem(product_id: str, amount: float, coin: str = "USDT") -> dict:
    """ByBit: POST /v5/earn/place-order — Redeem from Flexible Savings."""
    res = await bybit_request("POST", "/v5/earn/place-order", {
        "category": "FlexibleSaving",
        "productId": product_id,
        "coin": coin,
        "amount": str(amount),
        "orderType": "Redeem",
        "accountType": "FUND",
    })
    if res["success"]:
        log_activity(f"[earn/bb] redeemed ${amount:.2f} {coin} from product {product_id}")
        return {"success": True, "exchange": "bybit"}
    else:
        log_activity(f"[earn/bb] redeem error: {res.get('error','?')}")
        return {"success": False, "error": res.get("error", "unknown")}


async def bybit_earn_get_positions(coin: str = "USDT") -> list:
    """ByBit: GET /v5/earn/position — Current Earn positions."""
    res = await bybit_request("GET", "/v5/earn/position", {
        "category": "FlexibleSaving", "coin": coin
    })
    if res["success"]:
        return res["data"].get("list", [])
    return []


async def earn_get_best_rate(coin: str = "USDT") -> dict:
    """Compare APR across all exchanges, return the best option.
    Returns: {exchange, product_id, apr, min_amount, product_name}"""
    now = time.time()
    # Cache for 10 minutes
    if now - _earn_rates_cache["ts"] < 600 and coin in _earn_rates_cache["data"]:
        return _earn_rates_cache["data"][coin]

    best = {"exchange": "none", "product_id": "", "apr": 0.0, "min_amount": 0.0, "product_name": ""}

    # KuCoin rates
    try:
        kc_products = await kucoin_earn_get_savings_products(coin)
        for p in kc_products:
            apr = float(p.get("recentAnnualInterestRate", p.get("annualInterestRate", 0)))
            if apr > best["apr"]:
                best = {
                    "exchange": "kucoin",
                    "product_id": p.get("id", p.get("productId", "")),
                    "apr": round(apr * 100, 2) if apr < 1 else round(apr, 2),  # normalize to %
                    "min_amount": float(p.get("minInvestAmount", p.get("minPurchaseAmount", 0))),
                    "product_name": p.get("productName", f"KuCoin {coin} Flex"),
                }
    except Exception as e:
        log_activity(f"[earn] kucoin rate check error: {e}")

    # ByBit rates
    try:
        bb_products = await bybit_earn_get_products(coin)
        for p in bb_products:
            apr_str = p.get("estimateAnnualYield", p.get("annualYield", "0"))
            apr = float(apr_str) if apr_str else 0.0
            apr_pct = round(apr * 100, 2) if apr < 1 else round(apr, 2)
            if apr_pct > best["apr"]:
                best = {
                    "exchange": "bybit",
                    "product_id": p.get("productId", ""),
                    "apr": apr_pct,
                    "min_amount": float(p.get("minStakeAmount", p.get("minPurchaseAmount", 0))),
                    "product_name": p.get("productName", f"ByBit {coin} Flex"),
                }
    except Exception as e:
        log_activity(f"[earn] bybit rate check error: {e}")

    if best["apr"] > _earn_stats["best_apr"]:
        _earn_stats["best_apr"] = best["apr"]
        _earn_stats["best_apr_exchange"] = best["exchange"]

    _earn_rates_cache["ts"] = now
    _earn_rates_cache["data"][coin] = best
    return best


async def earn_auto_place_idle(exchange: str = "auto") -> dict:
    """Auto-place idle USDT into the best Flexible Savings product.
    Called after SELL or periodically. Respects EARN_RESERVE_USDT."""
    if not EARN_ENABLED:
        return {"success": False, "reason": "earn disabled"}

    result = {"placed": [], "errors": []}

    # Get available USDT on each exchange
    idle = {}
    try:
        if exchange in ("auto", "kucoin"):
            kc_bal = await get_balance()
            kc_usdt = kc_bal.get("available_usdt", 0) if isinstance(kc_bal, dict) else 0
            idle["kucoin"] = max(0, kc_usdt - EARN_RESERVE_USDT)
        if exchange in ("auto", "bybit") and BYBIT_ENABLED:
            bb_bal = await bybit_get_balance()
            bb_usdt = bb_bal.get("usdt", 0) if bb_bal.get("success") else 0
            idle["bybit"] = max(0, bb_usdt - EARN_RESERVE_USDT)
    except Exception as e:
        log_activity(f"[earn] balance check error: {e}")
        return {"success": False, "reason": str(e)}

    # Place idle USDT into best product per exchange
    for exch, amount in idle.items():
        if amount < EARN_MIN_IDLE_USDT:
            continue  # not enough to earn

        best = await earn_get_best_rate("USDT")

        # Prefer the exchange where the money already sits (avoid transfer fees)
        if exch == "kucoin":
            kc_products = await kucoin_earn_get_savings_products("USDT")
            if kc_products:
                p = kc_products[0]
                pid = p.get("id", p.get("productId", ""))
                min_amt = float(p.get("minInvestAmount", p.get("minPurchaseAmount", 1)))
                if amount >= min_amt and pid:
                    sub = await kucoin_earn_subscribe(pid, round(amount, 2))
                    if sub["success"]:
                        _earn_stats["subscriptions"] += 1
                        _earn_stats["total_subscribed"] += amount
                        _earn_stats["kucoin_subscribed"] += amount
                        _earn_stats["last_action"] = time.time()
                        _earn_positions.append({
                            "exchange": "kucoin", "product_id": pid,
                            "coin": "USDT", "amount": round(amount, 2),
                            "apr": best["apr"] if best["exchange"] == "kucoin" else 0,
                            "subscribed_at": time.time(),
                            "order_id": sub.get("order_id", ""),
                        })
                        result["placed"].append({"exchange": "kucoin", "amount": round(amount, 2)})
                        continue
                    else:
                        result["errors"].append(f"kucoin: {sub.get('error','?')}")
                        _earn_stats["errors"] += 1

        elif exch == "bybit":
            bb_products = await bybit_earn_get_products("USDT")
            if bb_products:
                p = bb_products[0]
                pid = p.get("productId", "")
                min_amt = float(p.get("minStakeAmount", p.get("minPurchaseAmount", 1)))
                if amount >= min_amt and pid:
                    sub = await bybit_earn_subscribe(pid, round(amount, 2))
                    if sub["success"]:
                        _earn_stats["subscriptions"] += 1
                        _earn_stats["total_subscribed"] += amount
                        _earn_stats["bybit_subscribed"] += amount
                        _earn_stats["last_action"] = time.time()
                        _earn_positions.append({
                            "exchange": "bybit", "product_id": pid,
                            "coin": "USDT", "amount": round(amount, 2),
                            "apr": best["apr"] if best["exchange"] == "bybit" else 0,
                            "subscribed_at": time.time(),
                            "order_id": sub.get("order_id", ""),
                        })
                        result["placed"].append({"exchange": "bybit", "amount": round(amount, 2)})
                        continue
                    else:
                        result["errors"].append(f"bybit: {sub.get('error','?')}")
                        _earn_stats["errors"] += 1

    result["success"] = len(result["placed"]) > 0
    return result


async def earn_redeem_for_trading(exchange: str, amount: float) -> dict:
    """Redeem USDT from Earn before a BUY trade. Returns dict with success status."""
    if not EARN_ENABLED or not _earn_positions:
        return {"success": True, "redeemed": 0, "reason": "no earn positions"}

    redeemed_total = 0.0
    for pos in list(_earn_positions):
        if pos["exchange"] != exchange or pos["coin"] != "USDT":
            continue
        if redeemed_total >= amount:
            break
        redeem_amount = min(pos["amount"], amount - redeemed_total)

        if exchange == "kucoin":
            res = await kucoin_earn_redeem(pos.get("order_id", ""), redeem_amount)
        elif exchange == "bybit":
            res = await bybit_earn_redeem(pos["product_id"], redeem_amount)
        else:
            continue

        if res.get("success"):
            redeemed_total += redeem_amount
            pos["amount"] -= redeem_amount
            _earn_stats["redemptions"] += 1
            _earn_stats["total_redeemed"] += redeem_amount
            _earn_stats["last_action"] = time.time()
            if pos["amount"] <= 0.01:
                _earn_positions.remove(pos)
        else:
            log_activity(f"[earn] redeem failed on {exchange}: {res.get('error','?')}")

    return {"success": True, "redeemed": round(redeemed_total, 2)}


async def earn_monitor_loop():
    """Background loop: periodically check idle USDT and place into Earn.
    Runs every 15 minutes. Also syncs positions with exchange data."""
    await asyncio.sleep(120)  # wait 2 min after startup
    while True:
        try:
            if EARN_ENABLED:
                # Auto-place idle USDT
                result = await earn_auto_place_idle("auto")
                if result.get("placed"):
                    placed_str = ", ".join(f"{p['exchange']}=${p['amount']:.2f}" for p in result["placed"])
                    log_activity(f"[earn_mon] auto-placed: {placed_str}")

                # Sync positions with actual exchange data
                try:
                    kc_holds = await kucoin_earn_get_hold_assets("USDT")
                    bb_holds = await bybit_earn_get_positions("USDT")
                    total_kc = sum(float(h.get("holdAmount", h.get("amount", 0))) for h in kc_holds)
                    total_bb = sum(float(h.get("amount", h.get("holdAmount", 0))) for h in bb_holds)
                    _earn_stats["kucoin_subscribed"] = round(total_kc, 2)
                    _earn_stats["bybit_subscribed"] = round(total_bb, 2)
                except Exception:
                    pass

                # Check best rates (refresh cache)
                best = await earn_get_best_rate("USDT")
                if best["apr"] > 0:
                    log_activity(f"[earn_mon] best rate: {best['exchange']} {best['apr']}% APR")

        except Exception as e:
            log_activity(f"[earn_mon] error: {e}")

        await asyncio.sleep(900)  # every 15 min


# ── v9.0: Cross-Exchange Arbitrage Monitor ─────────────────────────────────────
_xarb_stats = {"checks": 0, "opportunities": 0, "executions": 0,
               "total_pnl": 0.0, "best_spread": 0.0, "last_check": 0}
_xarb_history: list = []  # last 50 opportunities

XARB_MIN_SPREAD = float(os.getenv("XARB_MIN_SPREAD", "0.003"))   # 0.3% min spread
XARB_SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]              # monitored pairs
XARB_ENABLED = os.getenv("XARB_ENABLED", "true").lower() == "true"

async def check_cross_exchange_arb() -> list:
    """v9.0: Compare prices between KuCoin and ByBit for arb opportunities.
    Returns list of opportunities with spread > XARB_MIN_SPREAD."""
    if not BYBIT_ENABLED or not XARB_ENABLED:
        return []

    opportunities = []
    _xarb_stats["checks"] += 1
    _xarb_stats["last_check"] = time.time()

    for symbol in XARB_SYMBOLS:
        try:
            # Get prices from both exchanges
            kc_price = await get_ticker(symbol)
            bb_price = await bybit_get_ticker(symbol)

            if kc_price <= 0 or bb_price <= 0:
                continue

            # Calculate spread
            spread = abs(kc_price - bb_price) / min(kc_price, bb_price)

            # Which direction?
            if kc_price < bb_price:
                direction = "BUY_KC_SELL_BB"
                buy_ex, sell_ex = "KuCoin", "ByBit"
                buy_price, sell_price = kc_price, bb_price
            else:
                direction = "BUY_BB_SELL_KC"
                buy_ex, sell_ex = "ByBit", "KuCoin"
                buy_price, sell_price = bb_price, kc_price

            opp = {
                "symbol": symbol, "spread": round(spread, 6),
                "spread_pct": round(spread * 100, 3),
                "kc_price": kc_price, "bb_price": bb_price,
                "direction": direction, "buy_ex": buy_ex, "sell_ex": sell_ex,
                "buy_price": buy_price, "sell_price": sell_price,
                "ts": time.time(),
            }

            if spread > _xarb_stats["best_spread"]:
                _xarb_stats["best_spread"] = round(spread, 6)

            if spread >= XARB_MIN_SPREAD:
                _xarb_stats["opportunities"] += 1
                opportunities.append(opp)
                log_activity(f"[xarb] {symbol}: {spread*100:.3f}% spread! "
                             f"KC=${kc_price:,.2f} BB=${bb_price:,.2f} → {direction}")

                # Keep history
                _xarb_history.append(opp)
                if len(_xarb_history) > 50:
                    _xarb_history.pop(0)

        except Exception as e:
            log_activity(f"[xarb] {symbol} error: {e}")

    return opportunities


async def bybit_get_funding_rates_all() -> dict:
    """Get funding rates for monitored symbols — useful for funding rate arb."""
    rates = {}
    for sym in XARB_SYMBOLS:
        fr = await bybit_get_funding_rate(sym)
        if fr["success"]:
            rates[sym] = fr["rate"]
    return rates


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


async def get_spot_balances() -> dict:
    """v8.3: Get all non-zero spot balances for position monitoring.
    Returns {symbol: {available, balance, currency, usdt_value}} for coins with balance > 0."""
    endpoint = "/api/v1/accounts?type=trade"
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(KUCOIN_BASE_URL + endpoint,
                            headers=kucoin_headers("GET", endpoint),
                            timeout=aiohttp.ClientTimeout(total=10))
            data = await r.json()
            if data.get("code") != "200000":
                return {}
            result = {}
            for acc in data.get("data", []):
                bal = float(acc.get("balance", 0))
                avail = float(acc.get("available", 0))
                cur = acc.get("currency", "")
                if bal > 0 and cur not in ("USDT", "KCS"):
                    pair = f"{cur}-USDT"
                    price = await get_ticker(pair)
                    if price > 0:
                        result[pair] = {
                            "currency": cur,
                            "available": avail,
                            "balance": bal,
                            "price": price,
                            "usdt_value": round(bal * price, 4),
                        }
            return result
    except Exception as e:
        log_activity(f"[spot_bal] error: {e}")
        return {}


async def sell_spot_to_usdt(symbol: str, size: float = 0) -> dict:
    """v8.3: Sell spot coin back to USDT. If size=0, sell all available."""
    if size <= 0:
        balances = await get_spot_balances()
        info = balances.get(symbol)
        if not info or info["available"] <= 0:
            return {"success": False, "msg": f"no {symbol} balance"}
        size = info["available"]
    # KuCoin spot baseIncrement (precision) per pair
    PRECISION = {"BTC-USDT": 8, "ETH-USDT": 4, "SOL-USDT": 2,
                 "XRP-USDT": 1, "BNB-USDT": 4, "AVAX-USDT": 2,
                 "ADA-USDT": 1, "LINK-USDT": 2, "LTC-USDT": 3,
                 "DOGE-USDT": 0}
    MIN_SIZES = {"BTC-USDT": 0.00001, "ETH-USDT": 0.0001, "SOL-USDT": 0.01,
                 "XRP-USDT": 1.0, "BNB-USDT": 0.01, "AVAX-USDT": 0.01,
                 "ADA-USDT": 1.0, "LINK-USDT": 0.01, "LTC-USDT": 0.001}
    prec = PRECISION.get(symbol, 6)
    size = math.floor(size * 10**prec) / 10**prec  # floor to correct precision
    min_size = MIN_SIZES.get(symbol, 0.001)
    if size < min_size:
        return {"success": False, "msg": f"size {size} < minSize {min_size}"}
    result = await place_spot_order(symbol, "sell", size)
    ok = result.get("code") == "200000"
    # KuCoin error can be in 'msg' or nested in 'data'
    err_msg = result.get("msg") or result.get("data", {}).get("msg") if isinstance(result.get("data"), dict) else result.get("msg", "?")
    if ok:
        log_activity(f"[spot_sell] {symbol} SELL {size} OK orderId={result.get('data',{}).get('orderId','?')}")
    else:
        log_activity(f"[spot_sell] {symbol} SELL {size} FAILED: {err_msg} | raw: {json.dumps(result)[:200]}")
    return {"success": ok, "result": result, "size": size, "msg": err_msg if not ok else "ok"}

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

async def get_recent_futures_fills(symbol: str, since_ts: float, trade_side: str = "buy") -> Optional[float]:
    """v7.3.2: Возвращает цену ЗАКРЫТИЯ позиции из fills KuCoin Futures.
    Фильтрует только fills противоположной стороны (closing fills), исключая fills открытия."""
    endpoint = f"/api/v1/fills?symbol={symbol}&type=trade&pageSize=20"
    close_side = "sell" if trade_side == "buy" else "buy"  # для BUY-позиции закрытие = sell
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                KUCOIN_FUT_URL + endpoint,
                headers=kucoin_headers("GET", endpoint),
                timeout=aiohttp.ClientTimeout(total=8)
            )
            data = await r.json()
            if data.get("code") == "200000":
                items = data["data"].get("items", [])
                # v7.3.2: берём только closing fills (противоположная сторона) ПОСЛЕ открытия позиции
                close_fills = [
                    f for f in items
                    if float(f.get("createdAt", 0)) / 1000 > since_ts
                    and f.get("side") == close_side
                ]
                if close_fills:
                    total_qty = sum(float(f.get("size", 1)) for f in close_fills)
                    if total_qty > 0:
                        avg_price = sum(
                            float(f["price"]) * float(f.get("size", 1))
                            for f in close_fills
                        ) / total_qty
                        print(f"[fills] {symbol}: цена закрытия ${avg_price:,.4f} ({len(close_fills)} closing fills)", flush=True)
                        return avg_price
    except Exception as e:
        print(f"[fills] {symbol}: ошибка получения fills — {e}", flush=True)
    return None

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
    # v8.3: include all arb triangle USDT pairs in addition to SPOT_PAIRS
    _arb_usdt_pairs = set()
    for a, b, _, _ in ARB_TRIANGLES:
        _arb_usdt_pairs.add(a)
        _arb_usdt_pairs.add(b)
    all_pairs = set(SPOT_PAIRS) | _arb_usdt_pairs
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(f"{KUCOIN_BASE_URL}/api/v1/market/allTickers", timeout=aiohttp.ClientTimeout(total=10))
            data = await r.json()
            if data.get("code") == "200000":
                tickers = {t["symbol"]: t for t in data["data"]["ticker"]}
                result = {}
                for sym in all_pairs:
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
    except Exception as e:
        log_activity(f"[get_ticker] {symbol} error: {e}")
    return 0.0

async def get_kucoin_chart(symbol: str, interval: str = "1hour") -> list:
    try:
        end = int(time.time()); start = end - 86400
        async with aiohttp.ClientSession() as s:
            r = await s.get(f"{KUCOIN_BASE_URL}/api/v1/market/candles?type={interval}&symbol={symbol}&startAt={start}&endAt={end}", timeout=aiohttp.ClientTimeout(total=10))
            data = await r.json()
            if data.get("code") == "200000":
                return data.get("data", [])
    except Exception as e:
        log_activity(f"[get_kucoin_chart] {symbol} error: {e}")
    return []

async def place_spot_order(symbol: str, side: str, size: float) -> dict:
    endpoint = "/api/v1/orders"
    body = json.dumps({"clientOid": f"qt_{int(time.time()*1000)}", "side": side, "symbol": symbol, "type": "market", "size": str(size)})
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(KUCOIN_BASE_URL + endpoint, headers=kucoin_headers("POST", endpoint, body), data=body, timeout=aiohttp.ClientTimeout(total=10))
            resp = await r.json()
            if resp.get("code") != "200000":
                log_activity(f"[spot_order] {symbol} {side} size={size} ERR: {json.dumps(resp)[:300]}")
            return resp
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


def calc_advanced_ta(candles: list) -> dict:
    """v10.0: Advanced TA via pandas-ta — MACD, Bollinger Bands, Stochastic, ADX, VWAP, OBV.
    Falls back to basic indicators if pandas-ta not installed."""
    result = {"macd_signal": "neutral", "bb_position": "mid", "stoch_signal": "neutral",
              "adx_strength": 0, "adx_trend": "none", "obv_trend": "neutral",
              "macd_hist": 0, "bb_pct": 0.5, "stoch_k": 50, "stoch_d": 50, "available": False}
    if not _TA_AVAILABLE or not candles or len(candles) < 20:
        return result
    try:
        chron = list(reversed(candles))
        df = pd.DataFrame(chron, columns=["time", "open", "close", "high", "low", "volume", "turnover"])
        for col in ["open", "close", "high", "low", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.dropna(inplace=True)
        if len(df) < 14:
            return result

        # MACD (12, 26, 9)
        macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
        if macd is not None and len(macd.columns) >= 3:
            macd_val = macd.iloc[-1, 0]  # MACD line
            signal_val = macd.iloc[-1, 2]  # Signal line
            hist = macd.iloc[-1, 1]  # Histogram
            result["macd_hist"] = round(float(hist) if pd.notna(hist) else 0, 4)
            if pd.notna(macd_val) and pd.notna(signal_val):
                result["macd_signal"] = "bullish" if macd_val > signal_val else "bearish"

        # Bollinger Bands (20, 2)
        bb = ta.bbands(df["close"], length=20, std=2)
        if bb is not None and len(bb.columns) >= 3:
            lower = float(bb.iloc[-1, 0]) if pd.notna(bb.iloc[-1, 0]) else 0
            mid = float(bb.iloc[-1, 1]) if pd.notna(bb.iloc[-1, 1]) else 0
            upper = float(bb.iloc[-1, 2]) if pd.notna(bb.iloc[-1, 2]) else 0
            price = float(df["close"].iloc[-1])
            if upper > lower:
                bb_pct = (price - lower) / (upper - lower)
                result["bb_pct"] = round(bb_pct, 3)
                result["bb_position"] = "oversold" if bb_pct < 0.15 else "overbought" if bb_pct > 0.85 else "mid"

        # Stochastic (14, 3, 3)
        stoch = ta.stoch(df["high"], df["low"], df["close"], k=14, d=3, smooth_k=3)
        if stoch is not None and len(stoch.columns) >= 2:
            k_val = float(stoch.iloc[-1, 0]) if pd.notna(stoch.iloc[-1, 0]) else 50
            d_val = float(stoch.iloc[-1, 1]) if pd.notna(stoch.iloc[-1, 1]) else 50
            result["stoch_k"] = round(k_val, 1)
            result["stoch_d"] = round(d_val, 1)
            result["stoch_signal"] = "oversold" if k_val < 20 else "overbought" if k_val > 80 else "neutral"

        # ADX (14) — trend strength
        adx = ta.adx(df["high"], df["low"], df["close"], length=14)
        if adx is not None and len(adx.columns) >= 3:
            adx_val = float(adx.iloc[-1, 0]) if pd.notna(adx.iloc[-1, 0]) else 0
            dmp = float(adx.iloc[-1, 1]) if pd.notna(adx.iloc[-1, 1]) else 0
            dmn = float(adx.iloc[-1, 2]) if pd.notna(adx.iloc[-1, 2]) else 0
            result["adx_strength"] = round(adx_val, 1)
            if adx_val > 25:
                result["adx_trend"] = "strong_up" if dmp > dmn else "strong_down"
            elif adx_val > 15:
                result["adx_trend"] = "weak_up" if dmp > dmn else "weak_down"
            else:
                result["adx_trend"] = "range"

        # OBV trend (last 5 bars)
        obv = ta.obv(df["close"], df["volume"])
        if obv is not None and len(obv) >= 5:
            obv_now = float(obv.iloc[-1])
            obv_5ago = float(obv.iloc[-5])
            result["obv_trend"] = "accumulation" if obv_now > obv_5ago * 1.02 else "distribution" if obv_now < obv_5ago * 0.98 else "flat"

        result["available"] = True
        return result
    except Exception as e:
        log_activity(f"[ta] calc_advanced_ta error: {e}")
        return result


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

        # v10.0: Advanced TA indicators (MACD, BB, Stochastic, ADX, OBV)
        adv_ta = calc_advanced_ta(candles)
        result["adv_ta"] = adv_ta
        if adv_ta.get("available"):
            # Confidence boost from confirming signals
            confirmations = 0
            if signal == "BUY":
                if adv_ta["macd_signal"] == "bullish": confirmations += 1
                if adv_ta["bb_position"] == "oversold": confirmations += 1
                if adv_ta["stoch_signal"] == "oversold": confirmations += 1
                if adv_ta["adx_trend"] in ("strong_up", "weak_up"): confirmations += 1
                if adv_ta["obv_trend"] == "accumulation": confirmations += 1
            elif signal == "SELL":
                if adv_ta["macd_signal"] == "bearish": confirmations += 1
                if adv_ta["bb_position"] == "overbought": confirmations += 1
                if adv_ta["stoch_signal"] == "overbought": confirmations += 1
                if adv_ta["adx_trend"] in ("strong_down", "weak_down"): confirmations += 1
                if adv_ta["obv_trend"] == "distribution": confirmations += 1
            result["ta_confirmations"] = confirmations
            # Boost confidence: each confirmation adds +0.02 (max +0.10)
            confidence_boost = min(confirmations * 0.02, 0.10)
            result["confidence"] = round(min(result["confidence"] + confidence_boost, 0.95), 2)

        # ── Phase 5: Claude Vision — ULTRA-SNIPER pre-filter (v10.0) ─────────
        # Only call Vision API if free indicators show strong signal:
        # - Signal is BUY or SELL (not HOLD)
        # - Confidence >= 0.65 from free indicators alone
        # - At least 2 TA confirmations (MACD, BB, Stoch, ADX, OBV)
        # This reduces Vision calls by ~80-90%, saving API costs.
        _ta_confs = result.get("ta_confirmations", 0)
        _pre_filter_pass = (
            signal in ("BUY", "SELL")
            and result["confidence"] >= 0.65
            and _ta_confs >= 2
        )
        if ANTHROPIC_API_KEY and _pre_filter_pass:
            img_b64 = _render_candles_png_b64(candles)
            if img_b64:
                cv = _cache_get(f"claude_vision_{symbol}", 900)  # v10.0: 600→900s (15 min cache)
                if not cv:
                    cv = await _analyze_chart_claude_vision(img_b64, symbol, result)
                    _cache_set(f"claude_vision_{symbol}", cv)
                if cv and cv.get("success"):
                    result["vision_bonus"] = cv.get("bonus", 0.0)
                    result["vision_ocr"]   = cv.get("summary", "")
        elif ANTHROPIC_API_KEY and not _pre_filter_pass:
            result["vision_bonus"] = 0.0
            result["vision_ocr"] = "skipped:pre-filter"
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

        # v7.2.0: логируем HTTP статус для диагностики
        if r.status != 200:
            err_body = await r.text()
            print(f"[claude_vision] {symbol}: HTTP {r.status} — {err_body[:120]}")
            if r.status == 401:
                print(f"[claude_vision] ❌ AUTHENTICATION ERROR — проверь ANTHROPIC_API_KEY в Railway Variables")
            return {"success": False, "bonus": 0.0, "summary": ""}

        raw = data.get("content", [{}])[0].get("text", "{}")
        # Извлекаем JSON из ответа
        import re as _re
        m = _re.search(r'\{.*\}', raw, _re.DOTALL)
        parsed = json.loads(m.group()) if m else {}

        direction   = parsed.get("direction", "NEUTRAL").upper()
        confidence_pct = min(100, max(0, int(parsed.get("confidence", 50))))
        confidence  = confidence_pct / 100.0
        summary     = parsed.get("summary", parsed.get("pattern", ""))

        # v7.2.0: уверенность < 60% → принудительно NEUTRAL (слабый сигнал)
        if confidence_pct < 60:
            print(f"[claude_vision] {symbol}: ➖ NEUTRAL (confidence {confidence_pct}% < 60%) → bonus=+0.0")
            return {"success": True, "bonus": 0.0, "summary": summary,
                    "pattern": parsed.get("pattern", ""), "direction": "NEUTRAL"}

        # Рассчитываем bonus: BULLISH → +, BEARISH → -, масштаб по уверенности
        if direction == "BULLISH":
            bonus = round((confidence_pct - 50) / 50 * 10, 1)   # 60%→+2, 80%→+6, 100%→+10
        elif direction == "BEARISH":
            bonus = round(-(confidence_pct - 50) / 50 * 10, 1)  # 60%→-2, 80%→-6, 100%→-10
        else:
            bonus = 0.0

        icon = "📈" if direction == "BULLISH" else "📉" if direction == "BEARISH" else "➖"
        print(f"[claude_vision] {symbol}: {icon} {direction} {confidence_pct}% → bonus={bonus:+.1f} | {summary}")
        return {"success": True, "bonus": bonus, "summary": summary,
                "pattern": parsed.get("pattern", ""), "direction": direction}

    except Exception as e:
        print(f"[claude_vision] {symbol} error: {type(e).__name__}: {e}")
        return {"success": False, "bonus": 0.0, "summary": ""}


# ── v8.3: 3-Tier AI Architecture ──────────────────────────────────────────────
# Tier 1: DeepSeek V3 — text/strategy/chat (~free, OpenAI-compatible API)
# Tier 2: Claude Haiku — routine vision analysis (~$0.0003/call)
# Tier 3: Claude Opus — critical decisions, anomalies (~$0.015/call)
# ──────────────────────────────────────────────────────────────────────────────

_ai_call_stats: dict = {"deepseek": 0, "haiku": 0, "sonnet": 0, "opus": 0, "errors": 0}
_deepseek_disabled_until: float = 0.0  # v8.3.5: skip DeepSeek for 1h after 402/401

async def ai_call_deepseek(messages: list, max_tokens: int = 500, system: str = "") -> dict:
    """Call DeepSeek V3 API (OpenAI-compatible). Falls back to Claude Haiku if no key or billing issue."""
    global _deepseek_disabled_until
    if not DEEPSEEK_API_KEY:
        return await ai_call_claude(messages, max_tokens, system, model="haiku")
    # v8.3.5: Skip DeepSeek if recently got 402 (no balance) — don't waste time on dead API
    if time.time() < _deepseek_disabled_until:
        return await ai_call_claude(messages, max_tokens, system, model="haiku")
    try:
        payload = {
            "model": "deepseek-chat",
            "messages": ([{"role": "system", "content": system}] if system else []) + messages,
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=25)
            )
            data = await r.json()
        if r.status != 200:
            log_activity(f"[deepseek] HTTP {r.status}: {json.dumps(data)[:200]}")
            _ai_call_stats["errors"] += 1
            # v8.3.5: If billing error (402/401), disable DeepSeek for 1 hour to save latency
            if r.status in (401, 402, 429):
                _deepseek_disabled_until = time.time() + 3600
                log_activity(f"[deepseek] disabled for 1h (HTTP {r.status}), using Haiku")
            return await ai_call_claude(messages, max_tokens, system, model="haiku")
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        _ai_call_stats["deepseek"] += 1
        # v8.3.5: DeepSeek worked! Reset disable timer
        _deepseek_disabled_until = 0.0
        return {"success": True, "text": text, "model": "deepseek-v3", "tokens": data.get("usage", {}).get("total_tokens", 0)}
    except Exception as e:
        log_activity(f"[deepseek] error: {e}")
        _ai_call_stats["errors"] += 1
        return await ai_call_claude(messages, max_tokens, system, model="haiku")


async def ai_call_claude(messages: list, max_tokens: int = 500, system: str = "", model: str = "haiku") -> dict:
    """Call Claude API. Model: haiku | sonnet | opus."""
    if not ANTHROPIC_API_KEY:
        return {"success": False, "text": "", "model": "none", "error": "no ANTHROPIC_API_KEY"}
    model_map = {
        "haiku":  "claude-haiku-4-5-20251001",
        "sonnet": "claude-sonnet-4-20250514",
        "opus":   "claude-opus-4-6-20250610",
    }
    model_id = model_map.get(model, model_map["haiku"])
    try:
        payload = {
            "model": model_id,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            payload["system"] = system
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=20)
            )
            data = await r.json()
        if r.status != 200:
            log_activity(f"[claude_{model}] HTTP {r.status}: {json.dumps(data)[:200]}")
            _ai_call_stats["errors"] += 1
            return {"success": False, "text": "", "model": model_id, "error": f"HTTP {r.status}"}
        text = data.get("content", [{}])[0].get("text", "")
        _ai_call_stats[model] += 1
        return {"success": True, "text": text, "model": model_id,
                "tokens": data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0)}
    except Exception as e:
        log_activity(f"[claude_{model}] error: {e}")
        _ai_call_stats["errors"] += 1
        return {"success": False, "text": "", "model": model_id, "error": str(e)}


# ── v9.0: MiroFish Lite — Multi-Agent Sentiment Simulation ─────────────────────
# Inspired by MiroFish (OASIS/CAMEL-AI). Instead of deploying full MiroFish infra
# (Neo4j + Ollama + 16GB RAM), we simulate diverse "trader personas" via existing LLM.
# Each persona has a unique personality, risk appetite, and analysis style.
# Collective vote → sentiment score for trade decisions.
# ──────────────────────────────────────────────────────────────────────────────────

MIROFISH_ENABLED  = os.getenv("MIROFISH_ENABLED", "true").lower() == "true"
MIROFISH_CACHE_TTL = int(os.getenv("MIROFISH_CACHE_TTL", "1800"))  # 30 min cache

_mirofish_cache: dict = {}  # symbol → {ts, score, agents, detail}
_mirofish_stats: dict = {"calls": 0, "cache_hits": 0, "avg_score": 0.0, "last_call": 0}
# v9.1: Historical memory — stores last 5 results per symbol for trend awareness
_mirofish_memory: dict = {}  # symbol → [{ts, score, direction, fg}] max 5 entries

# v10.0: MiroFish v3 — 15 role-based agents (inspired by TradingAgents framework)
# Organized into: ANALYSTS (data), RESEARCHERS (context), TRADERS (decisions), RISK (vetoes)
MIROFISH_PERSONAS = [
    {"id": "whale", "name": "Кит-институционал", "style": "Крупный фонд. Покупает только фундаментально сильные активы. Очень осторожен. Смотрит на макро и ликвидность."},
    {"id": "scalper", "name": "Скальпер", "style": "Дейтрейдер. Ловит быстрые движения. Смотрит только на моментум, объёмы и RSI. Не держит позиции дольше часа."},
    {"id": "contrarian", "name": "Контрариан", "style": "Идёт против толпы. Когда все покупают — продаёт. Когда паника — покупает. Любит экстремальные значения Fear & Greed."},
    {"id": "quant", "name": "Квант-аналитик", "style": "Математик. Анализирует паттерны, EMA кроссы, RSI дивергенции. Игнорирует эмоции. Торгует только по статистике."},
    {"id": "macro", "name": "Макро-стратег", "style": "Смотрит на глобальную картину: ставки ФРС, DXY, корреляция с S&P500. Fear & Greed для него ключевой индикатор."},
    {"id": "degen", "name": "Дегенерат", "style": "Агрессивный трейдер. Высокий риск, высокая награда. Любит волатильность. Покупает на хайпе и новостях."},
    {"id": "conservative", "name": "Консерватор", "style": "Пенсионный фонд. Покупает только BTC/ETH. Только при сильных сигналах. Предпочитает HOLD если не уверен."},
    {"id": "news_trader", "name": "Новостной трейдер", "style": "Торгует на новостях и настроениях. Polymarket, Twitter тренды, регуляции. Быстро реагирует на события."},
    # v9.1: New specialized personas
    {"id": "arb_hunter", "name": "Арбитражёр", "style": "Ищет ценовые расхождения между биржами и парами. Если спред маленький — HOLD. Если цена выше на одной бирже — сигнал на продажу здесь. Нейтрален к направлению рынка, смотрит только на неэффективности."},
    {"id": "funding_arb", "name": "Фандинг-арбитражёр", "style": "Специалист по funding rate perpetual контрактов. Положительный funding → шорт, отрицательный → лонг. Зарабатывает на ставках финансирования, а не на движении цены. Если funding нейтральный — HOLD."},
    {"id": "volume_prof", "name": "Профиль объёмов", "style": "Анализирует объёмы торгов. Растущие объёмы при росте цены — BUY. Падающие объёмы при росте — дивергенция, SELL. Низкие объёмы — HOLD, ждёт прорыва."},
    {"id": "onchain", "name": "On-Chain аналитик", "style": "Смотрит на ончейн метрики: приток на биржи (медвежий сигнал), отток (бычий), активные адреса, whale movements. Если нет ончейн данных — решение по Fear & Greed как proxy."},
    # v10.0: TradingAgents-inspired role-based specialists
    {"id": "risk_mgr", "name": "Риск-менеджер", "style": "Его задача — НЕ заработать, а НЕ потерять. Оценивает downside: ADX слабый + BB overbought = HOLD. Волатильность > 4% = HOLD. Серия проигрышей = HOLD. Голосует SELL/HOLD, крайне редко BUY. Последнее слово в оценке риска."},
    {"id": "social_analyst", "name": "Соц.аналитик", "style": "Анализирует social sentiment: Reddit bullish/bearish, LunarCrush Galaxy Score, trending коины. Если social volume растёт при позитиве — BUY. Если хайп затихает — HOLD. Негативный sentiment — SELL."},
    {"id": "copytrade_watcher", "name": "Copy-Trade наблюдатель", "style": "Смотрит на то, что делают топ-10 трейдеров ByBit. Если 70%+ Long — BUY. Если 70%+ Short — SELL. Если паритет — HOLD. Доверяет деньгам больших игроков больше, чем теории."},
]

async def mirofish_simulate(symbol: str, price: float, q_score: float,
                             fg_value: int, pattern: str, rsi: float = 50,
                             context: str = "") -> dict:
    """v9.0: MiroFish Lite — run multi-agent sentiment simulation.
    Returns: {score: -100..+100, direction: BUY/SELL/HOLD, confidence: 0-100,
              agents: [{id, vote, reason}], cached: bool}
    """
    # Check cache first
    cache_key = f"{symbol}_{int(time.time() // MIROFISH_CACHE_TTL)}"
    cached = _mirofish_cache.get(cache_key)
    if cached:
        _mirofish_stats["cache_hits"] += 1
        return {**cached, "cached": True}

    # Build market context for all agents
    fg_label = "Extreme Fear" if fg_value < 15 else "Fear" if fg_value < 40 else "Neutral" if fg_value < 60 else "Greed" if fg_value < 80 else "Extreme Greed"
    market_ctx = (
        f"Symbol: {symbol}, Price: ${price:,.2f}, Q-Score: {q_score:.1f}/100, "
        f"Pattern: {pattern}, RSI: {rsi:.0f}, Fear&Greed: {fg_value} ({fg_label})"
    )
    if context:
        market_ctx += f"\nAdditional: {context}"

    # v9.1: Historical memory — add trend context from last 5 analyses
    mem = _mirofish_memory.get(symbol, [])
    if mem:
        prev_scores = [m["score"] for m in mem[-5:]]
        prev_dirs = [m["direction"] for m in mem[-5:]]
        trend = "bullish" if sum(prev_scores) > 50 else "bearish" if sum(prev_scores) < -50 else "mixed"
        market_ctx += (
            f"\nHistorical MiroFish (last {len(mem)} analyses): "
            f"scores={prev_scores}, directions={prev_dirs}, trend={trend}"
        )

    # v9.2: Enriched context — macro data, whale activity, copy-trading consensus
    if _macro_cache.get("success"):
        mc = _macro_cache
        market_ctx += (
            f"\nMacro: BTC dominance={mc.get('btc_dominance',0)}%, "
            f"Total MCap=${mc.get('total_mcap',0)}B ({mc.get('mcap_change_24h',0):+.1f}% 24h), "
            f"ETH/BTC={mc.get('eth_btc_ratio',0)}"
        )
        trending = mc.get("trending", [])
        if trending:
            market_ctx += f", Trending: {', '.join(t['symbol'] for t in trending[:5])}"

    if _whale_alert_cache.get("success"):
        wc = _whale_alert_cache
        market_ctx += (
            f"\nWhale Activity: {wc.get('whale_txs',0)} large txs, "
            f"${wc.get('total_whale_usd',0):,.0f} total, signal={wc.get('signal','?')}"
        )

    if _copytrade_cache.get("success"):
        cons = _copytrade_cache.get("consensus", {})
        coin_key = symbol.replace("-USDT", "")
        if coin_key in cons:
            cc = cons[coin_key]
            market_ctx += (
                f"\nByBit Copy-Trading: {coin_key} Long={cc['long_pct']}% Short={cc['short_pct']}% "
                f"Bias={cc['bias']}"
            )
        # Top traders summary
        traders = _copytrade_cache.get("traders", [])
        if traders:
            avg_wr = round(sum(t.get("win_rate", 0) for t in traders) / len(traders), 1) if traders else 0
            market_ctx += f", Top 10 traders avg WR={avg_wr}%"

    # v9.2: F&G trend context
    fg_hist = await db.get_fg_history(3)
    if len(fg_hist) >= 2:
        fg_vals = [h["value"] for h in fg_hist[:5]]
        fg_change = fg_vals[0] - fg_vals[-1]
        fg_trend = "rising" if fg_change > 5 else "falling" if fg_change < -5 else "stable"
        market_ctx += f"\nF&G Trend (3d): {fg_vals} ({fg_trend}, change={fg_change:+d})"

    # v10.0: LunarCrush social sentiment
    coin_key = symbol.replace("-USDT", "")
    lc = _lunarcrush_cache.get("coins", {}).get(coin_key)
    if lc:
        market_ctx += (
            f"\nSocial (LunarCrush): Galaxy={lc.get('galaxy_score',0)}/100, "
            f"Sentiment={lc.get('sentiment',0)}, SocialVol={lc.get('social_volume',0)}"
        )

    # v10.0: Reddit sentiment
    if _reddit_cache.get("success"):
        market_ctx += f"\nReddit: sentiment={_reddit_cache.get('sentiment_score',0):+.1f} (bull={_reddit_cache.get('bullish',0)} bear={_reddit_cache.get('bearish',0)})"

    # v10.0: Self-learning insights
    li = _learning_insights
    if li.get("avoid_symbols"):
        market_ctx += f"\nSelf-Learning: AVOID symbols={li['avoid_symbols']}, best_fg={li.get('best_fg_range','?')}, best_hour={li.get('best_hour','?')}"

    # Run all agents in parallel (single LLM call with all personas for efficiency)
    all_personas = "\n".join([f"- {p['name']}: {p['style']}" for p in MIROFISH_PERSONAS])

    system = f"""Ты — MiroFish движок мульти-агентной симуляции.
Тебе даны 8 различных трейдерских персон. Каждая должна проголосовать BUY, SELL или HOLD.
Отвечай СТРОГО в формате JSON массива (без markdown):
[{{"id":"whale","vote":"BUY","reason":"краткая причина"}},{{"id":"scalper","vote":"SELL","reason":"причина"}}...]

Персоны:
{all_personas}"""

    user_msg = f"Рыночные данные:\n{market_ctx}\n\nКаждая персона голосует BUY/SELL/HOLD с кратким обоснованием (1 предложение). Только JSON массив, ничего больше."

    try:
        result = await ai_call_claude(
            [{"role": "user", "content": user_msg}],
            max_tokens=600, system=system, model="haiku"
        )
        raw = result.get("text", "").strip()

        # Parse JSON response
        # Clean potential markdown wrapping
        if raw.startswith("```"): raw = raw.split("```")[1].strip()
        if raw.startswith("json"): raw = raw[4:].strip()
        agents = json.loads(raw)

        # Calculate collective score
        buy_count = sum(1 for a in agents if a.get("vote", "").upper() == "BUY")
        sell_count = sum(1 for a in agents if a.get("vote", "").upper() == "SELL")
        hold_count = sum(1 for a in agents if a.get("vote", "").upper() == "HOLD")
        total = len(agents) or 1

        # Score: -100 (all sell) to +100 (all buy)
        score = round((buy_count - sell_count) / total * 100)
        confidence = round(max(buy_count, sell_count) / total * 100)
        direction = "BUY" if score > 20 else "SELL" if score < -20 else "HOLD"

        result_data = {
            "score": score, "direction": direction, "confidence": confidence,
            "buy": buy_count, "sell": sell_count, "hold": hold_count,
            "agents": agents, "model": result.get("model", "?"),
        }

        # Cache result
        _mirofish_cache[cache_key] = result_data
        _mirofish_stats["calls"] += 1
        _mirofish_stats["last_call"] = time.time()
        # Running average
        n = _mirofish_stats["calls"]
        _mirofish_stats["avg_score"] = round((_mirofish_stats["avg_score"] * (n-1) + score) / n, 1)

        # v9.1: Save to historical memory (max 10 per symbol) + v9.2: persist to DB
        if symbol not in _mirofish_memory:
            _mirofish_memory[symbol] = []
        _mirofish_memory[symbol].append({
            "ts": time.time(), "score": score, "direction": direction,
            "fg": fg_value, "rsi": rsi, "buy": buy_count, "sell": sell_count
        })
        if len(_mirofish_memory[symbol]) > 10:
            _mirofish_memory[symbol] = _mirofish_memory[symbol][-10:]
        # Persist to PostgreSQL (non-blocking)
        if db.is_ready():
            asyncio.create_task(db.save_mirofish_memory(
                symbol, score, direction, fg_value, rsi,
                buy_count, sell_count, hold_count,
                json.dumps(agents)
            ))

        log_activity(f"[mirofish] {symbol}: score={score:+d} ({direction}) buy={buy_count} sell={sell_count} hold={hold_count} agents={total}")
        return {**result_data, "cached": False}

    except json.JSONDecodeError as e:
        log_activity(f"[mirofish] JSON parse error: {e} | raw: {raw[:200]}")
        return {"score": 0, "direction": "HOLD", "confidence": 0, "error": "parse_error",
                "buy": 0, "sell": 0, "hold": 0, "agents": [], "cached": False}
    except Exception as e:
        log_activity(f"[mirofish] error: {e}")
        return {"score": 0, "direction": "HOLD", "confidence": 0, "error": str(e),
                "buy": 0, "sell": 0, "hold": 0, "agents": [], "cached": False}


async def ai_dispatch(tier: str, messages: list, max_tokens: int = 500, system: str = "") -> dict:
    """v8.3: Unified AI dispatcher. Routes to the right model based on tier config.
    tier: 'chat' | 'vision' | 'critical'
    """
    tier_config = {
        "chat": AI_TIER_CHAT,        # deepseek | haiku | sonnet
        "vision": AI_TIER_VISION,     # haiku | opus
        "critical": AI_TIER_CRITICAL, # opus | sonnet
    }
    target = tier_config.get(tier, "haiku")
    if target == "deepseek":
        return await ai_call_deepseek(messages, max_tokens, system)
    else:
        return await ai_call_claude(messages, max_tokens, system, model=target)


# ── Telegram ───────────────────────────────────────────────────────────────────
async def notify(text: str):
    if not BOT_TOKEN or not ALERT_CHAT_ID: return
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": ALERT_CHAT_ID, "text": text, "parse_mode": "HTML",
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
    # v7.3.0: Квантовое усиление: +50% когда квант согласен с трендом
    q_b = max(-15.0, min(15.0, quantum_bias))  # clamp безопасности
    _p_dir = 1 if price_change > 0.3 else (-1 if price_change < -0.3 else 0)
    _q_dir = 1 if q_b > 1.5 else (-1 if q_b < -1.5 else 0)
    if _p_dir != 0 and _q_dir == _p_dir:
        q_b = min(15.0, q_b * 1.5)   # квант + тренд согласны: +50% усиление
    elif _p_dir != 0 and _q_dir == -_p_dir:
        q_b = q_b * 0.3              # квант противоречит тренду: ослабляем
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
    # v8.3.2: Reserve check — keep funds for arbitrage
    tradeable_usdt = max(0, available_usdt - ARB_RESERVE_USDT)
    if tradeable_usdt < 5:
        log_activity(f"[futures] {symbol}: SKIP — ${available_usdt:.2f} available, ${ARB_RESERVE_USDT:.0f} reserved for arb")
        return False
    fut_symbol, contract_size = FUTURES_MAP[symbol]
    side = "buy" if signal["action"] == "BUY" else "sell"
    trade_usdt = tradeable_usdt * RISK_PER_TRADE
    contract_value = price * contract_size
    n_contracts = max(1, int(trade_usdt * MAX_LEVERAGE / contract_value))
    margin_needed = contract_value / MAX_LEVERAGE
    if margin_needed > tradeable_usdt:
        log_activity(f"[futures] {symbol}: SKIP — need ${margin_needed:.2f}, have ${tradeable_usdt:.2f} (after reserve)")
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
    print(f"[TRADE] {fut_symbol} {side.upper()} Q={signal['q_score']:.1f} conf={signal['confidence']:.0%} n={n_contracts} @ ${price:,.2f} TP={tp} SL={sl}", flush=True)
    return True


# ── v8.3.3: Opus Gate — AI confirmation for significant trades ─────────────────
OPUS_GATE_MIN_USDT = float(os.getenv("OPUS_GATE_MIN_USDT", "15"))  # trades above $15 ask Opus
_opus_gate_stats = {"asked": 0, "approved": 0, "rejected": 0}

async def opus_gate_check(symbol: str, side: str, amount_usdt: float, q_score: float,
                          fg_val: int, pattern: str, context: str = "") -> dict:
    """v8.3.3: Ask Claude Opus whether to proceed with a trade.
    Returns {"approved": bool, "reason": str, "model": str}
    Only triggers for trades above OPUS_GATE_MIN_USDT.
    Falls back to auto-approve if AI unavailable."""
    if amount_usdt < OPUS_GATE_MIN_USDT:
        return {"approved": True, "reason": "below gate threshold", "model": "auto"}
    if not ANTHROPIC_API_KEY:
        return {"approved": True, "reason": "no API key — auto-approve", "model": "auto"}

    _opus_gate_stats["asked"] += 1
    prompt = (
        f"Trade review request:\n"
        f"- Pair: {symbol}, Side: {side}, Amount: ${amount_usdt:.2f}\n"
        f"- Q-Score: {q_score:.1f}, Pattern: {pattern}\n"
        f"- Fear&Greed: {fg_val}\n"
        f"{f'- Context: {context}' if context else ''}\n\n"
        f"Rules: RISK_PER_TRADE max 8%, MAX_LEVERAGE 3x, MIN_Q_SCORE 77.\n"
        f"Should this trade proceed? Answer ONLY 'APPROVE' or 'REJECT: <reason>' (1 line max)."
    )
    try:
        result = await ai_dispatch("critical", [{"role": "user", "content": prompt}],
                                   max_tokens=60, system="You are a risk manager. Be concise.")
        text = result.get("text", "").strip()
        model = result.get("model", "?")
        if text.upper().startswith("APPROVE"):
            _opus_gate_stats["approved"] += 1
            log_activity(f"[opus_gate] {symbol} {side} ${amount_usdt:.0f} → APPROVED ({model})")
            return {"approved": True, "reason": text, "model": model}
        else:
            _opus_gate_stats["rejected"] += 1
            reason = text.replace("REJECT:", "").replace("REJECT", "").strip() or "rejected by AI"
            log_activity(f"[opus_gate] {symbol} {side} ${amount_usdt:.0f} → REJECTED: {reason} ({model})")
            await notify(f"🛡️ <b>Opus отклонил сделку</b>\n{symbol} {side} ${amount_usdt:.0f}\n<i>{reason}</i>")
            return {"approved": False, "reason": reason, "model": model}
    except Exception as e:
        log_activity(f"[opus_gate] error: {e} — auto-approving")
        return {"approved": True, "reason": f"AI error: {e}", "model": "fallback"}


# ── v8.3.3: KuCoin WebSocket real-time price feed for arbitrage ────────────────
_ws_prices: dict = {}       # symbol → {"price": float, "ts": float} — real-time
_ws_connected: bool = False
_ws_reconnects: int = 0

async def _ws_price_feed():
    """Connect to KuCoin WebSocket and stream real-time ticker prices.
    Used by arb scanner for near-instant price updates instead of REST polling."""
    global _ws_connected, _ws_reconnects
    await asyncio.sleep(20)  # let REST fetch dead pairs first

    while True:
        try:
            # Collect ALL symbols (don't filter by dead pairs — they may come alive)
            symbols = set(SPOT_PAIRS)
            for a, b, cross, _ in ARB_TRIANGLES:
                symbols.add(a)
                symbols.add(b)
                symbols.add(cross)

            # Step 1: Get WS token from KuCoin
            async with aiohttp.ClientSession() as session:
                r = await session.post(f"{KUCOIN_BASE_URL}/api/v1/bullet-public",
                                       timeout=aiohttp.ClientTimeout(total=10))
                data = await r.json()
            if data.get("code") != "200000":
                log_activity(f"[ws] token request failed: {data.get('msg')}")
                await asyncio.sleep(15)
                continue
            token = data["data"]["token"]
            srv = data["data"]["instanceServers"][0]
            endpoint = srv["endpoint"]
            ping_interval = srv.get("pingInterval", 18000) / 1000  # ms → sec
            ws_url = f"{endpoint}?token={token}&connectId=arb_{int(time.time())}"

            # Step 2: Connect and subscribe
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(ws_url, heartbeat=None,
                                               timeout=aiohttp.ClientTimeout(total=60)) as ws:
                    _ws_connected = True
                    log_activity(f"[ws] connected — subscribing to {len(symbols)} symbols, ping every {ping_interval:.0f}s")

                    # Subscribe in batches of 100 (KuCoin limit)
                    sym_list = list(symbols)
                    for i in range(0, len(sym_list), 100):
                        batch = ",".join(sym_list[i:i+100])
                        await ws.send_json({
                            "id": f"sub_{i}",
                            "type": "subscribe",
                            "topic": f"/market/ticker:{batch}",
                            "privateChannel": False,
                            "response": True
                        })

                    # Step 3: Read messages with KuCoin JSON ping
                    last_ping = time.time()
                    ping_id = 0
                    while True:
                        # Send KuCoin-level ping (JSON, not WebSocket ping)
                        if time.time() - last_ping > ping_interval * 0.8:
                            ping_id += 1
                            try:
                                await ws.send_json({"id": str(ping_id), "type": "ping"})
                                last_ping = time.time()
                            except Exception:
                                break

                        try:
                            msg = await asyncio.wait_for(ws.receive(), timeout=ping_interval)
                        except asyncio.TimeoutError:
                            # No message received — send ping and continue
                            continue

                        if msg.type == aiohttp.WSMsgType.TEXT:
                            d = json.loads(msg.data)
                            msg_type = d.get("type", "")
                            if msg_type == "message" and d.get("topic", "").startswith("/market/ticker:"):
                                sym = d["topic"].split(":")[-1]
                                price = float(d["data"].get("price", 0))
                                if price > 0:
                                    _ws_prices[sym] = {"price": price, "ts": time.time()}
                            elif msg_type == "pong":
                                pass  # healthy
                            elif msg_type == "ack":
                                pass  # subscription confirmed
                        elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                            log_activity(f"[ws] connection closed: {msg.type}")
                            break

        except Exception as e:
            log_activity(f"[ws] error: {e}")
        finally:
            _ws_connected = False
            _ws_reconnects += 1
            delay = min(30, 5 * _ws_reconnects)  # backoff: 5, 10, 15... max 30s
            await asyncio.sleep(delay)


def _get_rt_price(symbol: str) -> float:
    """Get real-time price from WebSocket feed, falling back to REST cache."""
    ws_entry = _ws_prices.get(symbol)
    if ws_entry and (time.time() - ws_entry["ts"]) < 30:
        return ws_entry["price"]
    # Fallback to REST cached prices
    cached = _cache_get("all_prices", 120)
    if cached:
        return cached.get("prices", {}).get(symbol, {}).get("price", 0)
    return 0


async def _arb_fast_scanner():
    """v8.3.3: Dedicated fast arb scanner using WebSocket prices.
    Scans every 5 seconds instead of 60, catches fleeting opportunities."""
    await asyncio.sleep(45)  # let WS connect first
    while True:
        try:
            if not _ws_connected or len(_ws_prices) < 5:
                await asyncio.sleep(10)
                continue
            # Build price snapshot from WS
            ws_snap = {}
            for sym, data in _ws_prices.items():
                if time.time() - data["ts"] < 30:  # fresh prices only
                    ws_snap[sym] = {"price": data["price"]}
            if len(ws_snap) > 10:
                arb_opps = await check_triangular_arb(ws_snap)
                for opp in arb_opps:
                    await _notify_arb(opp)
                    if ARB_EXEC_ENABLED:
                        await execute_triangular_arb(opp)
        except Exception as e:
            log_activity(f"[arb_fast] error: {e}")
        await asyncio.sleep(5)  # scan every 5 seconds!


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


# ── v9.2: F&G History + Auto-save ─────────────────────────────────────────────
async def save_fg_to_history(fg_data: dict):
    """Auto-save F&G value to history after each fetch."""
    if fg_data.get("success") and db.is_ready():
        await db.save_fg_value(fg_data["value"], fg_data.get("classification", ""))

async def get_fg_trend() -> dict:
    """Analyze F&G trend over last 7 days from our stored history."""
    history = await db.get_fg_history(7)
    if len(history) < 2:
        return {"trend": "insufficient_data", "values": [], "change": 0}
    values = [h["value"] for h in history]
    latest = values[0]  # most recent
    oldest = values[-1]  # oldest in window
    avg = round(sum(values) / len(values), 1)
    change = latest - oldest
    trend = "rising" if change > 5 else "falling" if change < -5 else "stable"
    return {
        "trend": trend, "latest": latest, "oldest": oldest,
        "avg": avg, "change": change, "samples": len(values),
        "values": values[:10]  # last 10 for context
    }


# ── v9.2: Macro Market Data (FREE APIs) ───────────────────────────────────────
_macro_cache: dict = {}
_macro_cache_ts: float = 0.0

async def fetch_macro_context() -> dict:
    """Fetch BTC dominance, total MCap, ETH/BTC ratio, top gainers/losers from CoinGecko."""
    global _macro_cache, _macro_cache_ts
    if time.time() - _macro_cache_ts < 900 and _macro_cache:  # 15 min cache
        return _macro_cache
    try:
        result = {}
        async with aiohttp.ClientSession() as s:
            # 1. Global market data — BTC dominance, total MCap
            r = await s.get("https://api.coingecko.com/api/v3/global",
                            timeout=aiohttp.ClientTimeout(total=8))
            if r.status == 200:
                gd = (await r.json()).get("data", {})
                result["btc_dominance"] = round(gd.get("market_cap_percentage", {}).get("btc", 0), 2)
                result["eth_dominance"] = round(gd.get("market_cap_percentage", {}).get("eth", 0), 2)
                result["total_mcap"] = round(gd.get("total_market_cap", {}).get("usd", 0) / 1e9, 1)  # billions
                result["mcap_change_24h"] = round(gd.get("market_cap_change_percentage_24h_usd", 0), 2)
                result["active_cryptos"] = gd.get("active_cryptocurrencies", 0)

            # 2. Top gainers/losers — trending coins
            r2 = await s.get("https://api.coingecko.com/api/v3/search/trending",
                              timeout=aiohttp.ClientTimeout(total=8))
            if r2.status == 200:
                trending = (await r2.json()).get("coins", [])
                result["trending"] = [
                    {"name": c["item"]["name"], "symbol": c["item"]["symbol"],
                     "rank": c["item"]["market_cap_rank"]}
                    for c in trending[:7]
                ]

            # 3. ETH/BTC price ratio
            r3 = await s.get("https://api.coingecko.com/api/v3/simple/price?ids=ethereum,bitcoin&vs_currencies=usd,btc",
                              timeout=aiohttp.ClientTimeout(total=5))
            if r3.status == 200:
                prices = await r3.json()
                result["eth_btc_ratio"] = round(prices.get("ethereum", {}).get("btc", 0), 6)
                result["btc_usd"] = prices.get("bitcoin", {}).get("usd", 0)
                result["eth_usd"] = prices.get("ethereum", {}).get("usd", 0)

        result["success"] = True
        result["ts"] = time.time()
        _macro_cache = result
        _macro_cache_ts = time.time()

        # Persist to DB
        if db.is_ready():
            await db.save_macro_snapshot(
                btc_dom=result.get("btc_dominance", 0),
                total_mcap=result.get("total_mcap", 0),
                eth_btc=result.get("eth_btc_ratio", 0),
                gainers=[],
                losers=[],
                extra={"trending": result.get("trending", []), "mcap_change_24h": result.get("mcap_change_24h", 0)}
            )

        log_activity(f"[macro] BTC dom={result.get('btc_dominance')}% MCap=${result.get('total_mcap')}B ETH/BTC={result.get('eth_btc_ratio')}")
        return result
    except Exception as e:
        log_activity(f"[macro] fetch error: {e}")
        return {"success": False, "error": str(e)}


# ── v9.2: Whale Alert — Large Transactions from Free APIs ─────────────────────
_whale_alert_cache: dict = {}
_whale_alert_ts: float = 0.0

async def fetch_whale_movements() -> dict:
    """Fetch large BTC/ETH movements from blockchain.info and Blockchair."""
    global _whale_alert_cache, _whale_alert_ts
    if time.time() - _whale_alert_ts < 300 and _whale_alert_cache:  # 5 min cache
        return _whale_alert_cache
    try:
        movements = []
        async with aiohttp.ClientSession() as s:
            # 1. Bitcoin large transactions via blockchain.info (free, no key)
            r = await s.get("https://blockchain.info/unconfirmed-transactions?format=json&limit=20",
                            timeout=aiohttp.ClientTimeout(total=8))
            if r.status == 200:
                data = await r.json()
                for tx in data.get("txs", []):
                    total_out = sum(o.get("value", 0) for o in tx.get("out", [])) / 1e8  # satoshi → BTC
                    usd_val = total_out * _macro_cache.get("btc_usd", 85000)
                    if usd_val >= 500_000:  # Only $500K+
                        # Determine direction: exchange → wallet = bullish, wallet → exchange = bearish
                        movements.append({
                            "symbol": "BTC", "amount_btc": round(total_out, 4),
                            "amount_usd": round(usd_val), "hash": tx.get("hash", "")[:12],
                            "type": "large_tx"
                        })

            # 2. Exchange net flow estimate from Blockchair (free tier)
            r2 = await s.get("https://api.blockchair.com/bitcoin/stats",
                              timeout=aiohttp.ClientTimeout(total=6))
            if r2.status == 200:
                stats = (await r2.json()).get("data", {})
                mempool_size = stats.get("mempool_transactions", 0)
                mempool_val = stats.get("mempool_total_fee_usd", 0)
                movements.append({
                    "type": "mempool_stats",
                    "mempool_txs": mempool_size,
                    "mempool_fees_usd": round(mempool_val, 2),
                    "hashrate": stats.get("hashrate_24h", 0),
                })

        # Analyze sentiment from movements
        large_txs = [m for m in movements if m.get("type") == "large_tx"]
        total_whale_usd = sum(m.get("amount_usd", 0) for m in large_txs)
        whale_count = len(large_txs)

        result = {
            "success": True, "whale_txs": whale_count,
            "total_whale_usd": round(total_whale_usd),
            "movements": movements[:10],
            "signal": "heavy" if total_whale_usd > 10_000_000 else "moderate" if total_whale_usd > 2_000_000 else "calm",
            "ts": time.time()
        }

        # Save significant events to DB
        if db.is_ready() and whale_count > 0:
            for m in large_txs[:5]:
                await db.save_whale_event(
                    event_type="large_btc_tx", symbol="BTC",
                    amount_usd=m.get("amount_usd", 0),
                    source="blockchain.info"
                )

        _whale_alert_cache = result
        _whale_alert_ts = time.time()
        if whale_count > 0:
            log_activity(f"[whale] {whale_count} large txs, total ${total_whale_usd:,.0f}, signal={result['signal']}")
        return result
    except Exception as e:
        log_activity(f"[whale_alert] error: {e}")
        return {"success": False, "whale_txs": 0, "signal": "error", "error": str(e)}


# ── v9.2: Copy-Trading Intelligence (ByBit Leaderboard) ───────────────────────
_copytrade_cache: dict = {}
_copytrade_ts: float = 0.0

async def fetch_top_traders_positions() -> dict:
    """Fetch top traders' positions from ByBit copy trading leaderboard (public API)."""
    global _copytrade_cache, _copytrade_ts
    if time.time() - _copytrade_ts < 600 and _copytrade_cache:  # 10 min cache
        return _copytrade_cache
    if not BYBIT_ENABLED:
        return {"success": False, "error": "ByBit not configured"}
    try:
        result = {"traders": [], "consensus": {}}
        async with aiohttp.ClientSession() as s:
            # ByBit copy trade leaderboard — public endpoint
            r = await s.get(
                f"{BYBIT_BASE_URL}/v5/copy-trading/leaderboard/get-leader-list",
                params={"sortBy": "TOTAL_PNL", "limit": "10"},
                timeout=aiohttp.ClientTimeout(total=8)
            )
            if r.status == 200:
                data = await r.json()
                leaders = data.get("result", {}).get("list", [])
                for leader in leaders[:10]:
                    result["traders"].append({
                        "name": leader.get("nickName", "?"),
                        "pnl": round(float(leader.get("totalPnl") or 0), 2),
                        "win_rate": round(float(leader.get("winRate") or 0) * 100, 1),
                        "followers": int(leader.get("followerNum") or 0),
                        "roi": round(float(leader.get("totalRoi") or 0) * 100, 1),
                    })

            # Try to get aggregate position data
            r2 = await s.get(
                f"{BYBIT_BASE_URL}/v5/market/account-ratio",
                params={"category": "linear", "symbol": "BTCUSDT", "period": "1h", "limit": "1"},
                timeout=aiohttp.ClientTimeout(total=5)
            )
            if r2.status == 200:
                data2 = await r2.json()
                ratios = data2.get("result", {}).get("list", [])
                if ratios:
                    buy_ratio = float(ratios[0].get("buyRatio", 0.5))
                    sell_ratio = float(ratios[0].get("sellRatio", 0.5))
                    result["consensus"]["BTC"] = {
                        "long_pct": round(buy_ratio * 100, 1),
                        "short_pct": round(sell_ratio * 100, 1),
                        "bias": "LONG" if buy_ratio > 0.55 else "SHORT" if sell_ratio > 0.55 else "NEUTRAL"
                    }

            # ETH ratio too
            r3 = await s.get(
                f"{BYBIT_BASE_URL}/v5/market/account-ratio",
                params={"category": "linear", "symbol": "ETHUSDT", "period": "1h", "limit": "1"},
                timeout=aiohttp.ClientTimeout(total=5)
            )
            if r3.status == 200:
                data3 = await r3.json()
                ratios3 = data3.get("result", {}).get("list", [])
                if ratios3:
                    buy_ratio = float(ratios3[0].get("buyRatio", 0.5))
                    sell_ratio = float(ratios3[0].get("sellRatio", 0.5))
                    result["consensus"]["ETH"] = {
                        "long_pct": round(buy_ratio * 100, 1),
                        "short_pct": round(sell_ratio * 100, 1),
                        "bias": "LONG" if buy_ratio > 0.55 else "SHORT" if sell_ratio > 0.55 else "NEUTRAL"
                    }

        result["success"] = True
        result["ts"] = time.time()
        _copytrade_cache = result
        _copytrade_ts = time.time()
        log_activity(f"[copytrade] loaded {len(result['traders'])} top traders, BTC consensus: {result.get('consensus', {}).get('BTC', {}).get('bias', '?')}")
        return result
    except Exception as e:
        log_activity(f"[copytrade] error: {e}")
        return {"success": False, "error": str(e), "traders": [], "consensus": {}}


# ── v10.0: LunarCrush Galaxy Score (Free API) ─────────────────────────────────
_lunarcrush_cache: dict = {}
_lunarcrush_ts: float = 0.0

async def fetch_lunarcrush_sentiment(symbols: list = None) -> dict:
    """Fetch Galaxy Score + AltRank for top coins from LunarCrush public API."""
    global _lunarcrush_cache, _lunarcrush_ts
    if time.time() - _lunarcrush_ts < 600 and _lunarcrush_cache:  # 10 min cache
        return _lunarcrush_cache
    if symbols is None:
        symbols = ["BTC", "ETH", "SOL", "XRP", "AVAX", "BNB", "MATIC", "DOT"]
    try:
        result = {"coins": {}, "success": False}
        async with aiohttp.ClientSession() as s:
            # LunarCrush v3 public endpoint (no key needed for basic data)
            for sym in symbols[:8]:
                r = await s.get(
                    f"https://lunarcrush.com/api4/public/coins/{sym.lower()}/v1",
                    timeout=aiohttp.ClientTimeout(total=5),
                    headers={"User-Agent": "QuantumTradeBot/10.0"}
                )
                if r.status == 200:
                    data = await r.json()
                    d = data.get("data", {})
                    result["coins"][sym] = {
                        "galaxy_score": d.get("galaxy_score", 0),
                        "alt_rank": d.get("alt_rank", 0),
                        "sentiment": d.get("sentiment", 0),
                        "social_volume": d.get("social_volume", 0),
                        "social_score": d.get("social_score", 0),
                        "price": d.get("price", 0),
                        "percent_change_24h": d.get("percent_change_24h", 0),
                    }
                await asyncio.sleep(0.3)  # respect rate limits

        if result["coins"]:
            result["success"] = True
            _lunarcrush_cache = result
            _lunarcrush_ts = time.time()
            log_activity(f"[lunarcrush] loaded {len(result['coins'])} coins")
        return result
    except Exception as e:
        log_activity(f"[lunarcrush] error: {e}")
        return {"coins": {}, "success": False, "error": str(e)}


# ── v10.0: Reddit Crypto Sentiment (Free, No API Key) ─────────────────────────
_reddit_cache: dict = {}
_reddit_ts: float = 0.0

async def fetch_reddit_sentiment() -> dict:
    """Scrape sentiment from r/cryptocurrency and r/bitcoin via public JSON API."""
    global _reddit_cache, _reddit_ts
    if time.time() - _reddit_ts < 900 and _reddit_cache:  # 15 min cache
        return _reddit_cache
    try:
        result = {"posts": [], "sentiment_score": 0, "bullish": 0, "bearish": 0, "success": False}
        subreddits = ["cryptocurrency", "bitcoin"]
        bullish_words = {"bullish", "moon", "pump", "buy", "long", "breakout", "ath", "rally", "surge", "bull"}
        bearish_words = {"bearish", "dump", "crash", "sell", "short", "dip", "bear", "drop", "plunge", "scam"}

        async with aiohttp.ClientSession() as s:
            for sub in subreddits:
                r = await s.get(
                    f"https://www.reddit.com/r/{sub}/hot.json?limit=25",
                    timeout=aiohttp.ClientTimeout(total=8),
                    headers={"User-Agent": "QuantumTradeBot/10.0 (research)"}
                )
                if r.status == 200:
                    data = await r.json()
                    for post in data.get("data", {}).get("children", []):
                        pd_ = post.get("data", {})
                        title = pd_.get("title", "").lower()
                        score = pd_.get("score", 0)
                        comments = pd_.get("num_comments", 0)

                        # Simple sentiment detection
                        bull_hits = sum(1 for w in bullish_words if w in title)
                        bear_hits = sum(1 for w in bearish_words if w in title)
                        weight = max(1, score // 100)  # high-score posts matter more

                        if bull_hits > bear_hits:
                            result["bullish"] += weight
                        elif bear_hits > bull_hits:
                            result["bearish"] += weight

                        result["posts"].append({
                            "title": pd_.get("title", "")[:80],
                            "score": score, "comments": comments,
                            "sub": sub, "bull": bull_hits, "bear": bear_hits
                        })
                await asyncio.sleep(1.0)  # Reddit rate limit

        total = result["bullish"] + result["bearish"]
        if total > 0:
            result["sentiment_score"] = round((result["bullish"] - result["bearish"]) / total * 100, 1)
        result["total_posts"] = len(result["posts"])
        result["success"] = True
        _reddit_cache = result
        _reddit_ts = time.time()
        log_activity(f"[reddit] {result['total_posts']} posts, sentiment={result['sentiment_score']:+.1f} (bull={result['bullish']} bear={result['bearish']})")
        return result
    except Exception as e:
        log_activity(f"[reddit] error: {e}")
        return {"posts": [], "sentiment_score": 0, "success": False, "error": str(e)}


# ── v10.0: Continuous Self-Learning v2 ─────────────────────────────────────────
_learning_insights: dict = {"best_fg_range": None, "best_hour": None, "best_pattern": None,
                             "avoid_symbols": [], "optimal_q": 77, "last_update": 0}

async def update_learning_insights():
    """v10.0: Analyze recent trades to find optimal parameters. Called every cycle."""
    global _learning_insights
    if time.time() - _learning_insights["last_update"] < 1800:  # every 30 min
        return _learning_insights
    if not db.is_ready():
        return _learning_insights
    try:
        deep = await db.get_deep_analytics()
        if not deep:
            return _learning_insights

        # Best F&G range from our trades
        fg_corr = await db.get_fg_trade_correlation()
        best_fg = None
        best_fg_wr = 0
        for fc in fg_corr:
            if fc.get("total", 0) >= 5:
                wr = fc["wins"] / fc["total"] * 100
                if wr > best_fg_wr:
                    best_fg_wr = wr
                    best_fg = fc["fg_zone"]
        _learning_insights["best_fg_range"] = best_fg

        # Best hour
        best_hour_data = None
        best_hour_pnl = -999
        for h in deep.get("by_hour", []):
            if h.get("total", 0) >= 3 and h.get("pnl", 0) > best_hour_pnl:
                best_hour_pnl = h["pnl"]
                best_hour_data = h
        if best_hour_data:
            _learning_insights["best_hour"] = best_hour_data["hour"]

        # Best pattern
        best_pat = None
        best_pat_wr = 0
        for p in deep.get("by_pattern", []):
            if p.get("total", 0) >= 5:
                wr = p["wins"] / p["total"] * 100
                if wr > best_pat_wr:
                    best_pat_wr = wr
                    best_pat = p["pattern"]
        _learning_insights["best_pattern"] = best_pat

        # Symbols to avoid (winrate < 30% with 5+ trades)
        avoid = []
        for sym in deep.get("by_symbol", []):
            if sym.get("total", 0) >= 5:
                wr = sym["wins"] / sym["total"] * 100
                if wr < 30:
                    avoid.append(sym["symbol"])
        _learning_insights["avoid_symbols"] = avoid

        # Optimal Q-Score from Q-range analysis
        best_q_pnl = -999
        for qr in deep.get("q_ranges", []):
            if qr.get("total", 0) >= 5 and qr.get("pnl", 0) > best_q_pnl:
                best_q_pnl = qr["pnl"]
                # Extract lower bound of range as minimum
                try:
                    lower = int(qr["q_range"].split("-")[0])
                    _learning_insights["optimal_q"] = max(70, min(lower, 90))
                except Exception:
                    pass

        _learning_insights["last_update"] = time.time()
        log_activity(f"[learning] insights updated: best_fg={best_fg} best_hour={_learning_insights.get('best_hour')} avoid={avoid}")
        return _learning_insights
    except Exception as e:
        log_activity(f"[learning] error: {e}")
        return _learning_insights


# ── v10.0: Rate Limiting Middleware ────────────────────────────────────────────
_rate_limits: dict = defaultdict(lambda: {"count": 0, "reset_ts": 0})
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 60  # requests per window

def _check_rate_limit(client_ip: str, limit: int = _RATE_LIMIT_MAX) -> bool:
    """Returns True if request should be blocked (rate limited)."""
    now = time.time()
    rl = _rate_limits[client_ip]
    if now > rl["reset_ts"]:
        rl["count"] = 1
        rl["reset_ts"] = now + _RATE_LIMIT_WINDOW
        return False
    rl["count"] += 1
    return rl["count"] > limit


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
    # v7.2.3: TP/SL ratio улучшен до 3:1 во всех стратегиях (было 2:1)
    "A": {"name": "Консервативная", "risk": 0.05, "leverage": 2, "tp": 0.03, "sl": 0.01,  "emoji": "🛡",  "tag": "real"},
    "B": {"name": "Стандартная",    "risk": 0.08, "leverage": 3, "tp": 0.045,"sl": 0.015, "emoji": "⚖️", "tag": "real"},
    "C": {"name": "Бонусная",       "risk": 0.12, "leverage": 3, "tp": 0.06, "sl": 0.02,  "emoji": "🚀",  "tag": "bonus"},
}
# v8.3.3: C was 25%/5x — reduced to 12%/3x per trading.md (max risk 15%, max leverage 5x)
# DUAL: одновременно B (реальный) + C (бонусный агрессивный)
STRATEGY_TIMEOUT = 60   # 1 минута


async def send_strategy_choice(trade_id, symbol, action, price, q, pattern, fg, poly_b, whale_b, mirofish=None):
    fg_txt = f"F&G: {fg.get('value',50)} {fg.get('classification','—')} ({fg.get('bonus',0):+d})" if fg.get("success") else ""
    poly_txt = f"Poly: {poly_b:+.0f}" if poly_b != 0 else ""
    whale_txt = f"Whale: {whale_b:+.0f}" if whale_b != 0 else ""
    mf_txt = ""
    if mirofish and not mirofish.get("error"):
        mf_txt = f"🐟 MiroFish: {mirofish['score']:+d} ({mirofish['direction']}, {mirofish['confidence']}%)"
    ctx = " · ".join(p for p in [fg_txt, poly_txt, whale_txt, mf_txt] if p)
    act_emoji = "🟢 BUY" if action == "BUY" else "🔴 SELL"
    text = (
        f"⚛ *QuantumTrade — {act_emoji}*\n\n"
        f"Пара: *{symbol}* · Цена: `${price:,.2f}`\n"
        f"Q-Score: `{q}` · Паттерн: `{pattern}`\n"
        f"{ctx}\n\n"
        f"*Выбери стратегию:*\n"
        f"🛡 *A* — Консерватив (5%, TP 3%, SL 1%) 3:1\n"
        f"⚖️ *B* — Стандарт (8%, TP 4.5%, SL 1.5%) 3:1\n"
        f"🚀 *C* — Бонусная (12%, TP 6%, SL 2%) 3:1\n"
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
    tp_res = await place_futures_stop_order(fut_symbol, close_side, n_contracts, tp, "up" if side == "buy" else "down")
    sl_res = await place_futures_stop_order(fut_symbol, close_side, n_contracts, sl, "down" if side == "buy" else "up")
    tp_ok = tp_res.get("code") == "200000"
    sl_ok = sl_res.get("code") == "200000"
    log_activity(f"[strategy] {fut_symbol} СТОПЫ: TP={'✅' if tp_ok else '❌ '+str(tp_res.get('msg','?'))} SL={'✅' if sl_ok else '❌ '+str(sl_res.get('msg','?'))}")
    if not tp_ok or not sl_ok:
        print(f"[WARN] {fut_symbol} стоп-ордер не выставлен! TP={tp_res} SL={sl_res}", flush=True)
    log_trade(fut_symbol, side, price, n_contracts, tp, sl,
              signal["confidence"], signal["q_score"], vision.get("pattern","?"), f"futures_{strategy}")
    last_signals[f"FUT_{symbol}"] = {"action": signal["action"], "ts": time.time()}
    log_activity(f"[strategy] {strategy} {fut_symbol} {side.upper()} OK TP={tp} SL={sl}")
    print(f"[TRADE] {strategy} {fut_symbol} {side.upper()} Q={signal['q_score']:.1f} n={n_contracts} @ ${price:,.2f} TP={tp} SL={sl}", flush=True)
    await notify(f"{s['emoji']} <b>Стратегия {strategy} — {s['name']}</b>\n<code>{fut_symbol}</code> {side.upper()} Q={signal['q_score']}")
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
    # v8.3.3: Conservative auto-strategy — only use C for very strong signals
    if q >= 85:
        auto_strategy = "C"
        label = "C (сильный сигнал 🚀)"
    elif q >= 75:
        auto_strategy = "B"
        label = "B (стандартная)"
    else:
        auto_strategy = "A"
        label = "A (консервативная)"
    log_activity(f"[strategy] timeout {trade_id} Q={q:.1f} → авто {label}")
    await notify(f"⏱ <i>Таймаут — Q={q:.0f} → стратегия {label}</i>")
    if auto_strategy == "D":
        await execute_dual_strategy(
            pending["symbol"], pending["signal"], pending["vision"],
            pending["price"], pending["fut_usdt"])
    else:
        await execute_with_strategy(
            auto_strategy, pending["symbol"], pending["signal"],
            pending["vision"], pending["price"], pending["fut_usdt"])


async def _safe_background_enrich(fg_data: dict):
    """v10.0: Non-blocking background fetch of all intelligence sources + persist F&G."""
    try:
        tasks = [
            save_fg_to_history(fg_data),
            fetch_macro_context(),
            fetch_whale_movements(),
            fetch_lunarcrush_sentiment(),
            fetch_reddit_sentiment(),
            update_learning_insights(),
        ]
        if BYBIT_ENABLED:
            tasks.append(fetch_top_traders_positions())
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        log_activity(f"[enrich] background error: {e}")


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

    # v9.2: Background enrichment — macro, whale, copy-trading (non-blocking)
    asyncio.create_task(_safe_background_enrich(fg_data))

    spot_usdt       = spot_bal.get("total_usdt", 0)
    fut_usdt        = fut_bal.get("available_balance", 0)

    # ── v10.0: ByBit balance for dual-exchange trading ────────────────────────
    bb_usdt = 0.0
    if BYBIT_ENABLED:
        try:
            bb_bal = await bybit_get_balance()
            if bb_bal["success"]:
                bb_usdt = bb_bal.get("total_usdt", 0)
        except Exception:
            pass

    # v10.0: Combined available capital across exchanges
    total_usdt = spot_usdt + bb_usdt

    # v10.0: Smart exchange selection — trade on whichever has more USDT
    # _trade_exchange: "kucoin", "bybit", or "both"
    _kc_tradeable = max(0, spot_usdt - ARB_RESERVE_USDT)
    _bb_tradeable = max(0, bb_usdt - ARB_RESERVE_USDT)

    def _calc_trade_size(available: float) -> float:
        """Calculate trade size for small accounts."""
        if available < SPOT_BUY_MIN_USDT:
            return 0.0
        risk = RISK_PER_TRADE
        if available < 50:
            risk = min(0.35, max(RISK_PER_TRADE, 5.0 / max(available, 1)))
        size = round(available * risk, 2)
        if 0 < size < 2.0:
            size = min(2.0, available * 0.35)
        if size > available * 0.35:
            size = round(available * 0.35, 2)
        return size

    spot_trade_usdt = _calc_trade_size(_kc_tradeable)
    bb_trade_usdt   = _calc_trade_size(_bb_tradeable) if BYBIT_ENABLED else 0

    # Choose primary exchange for this cycle (the one with more available)
    _primary_exchange = "kucoin"
    _primary_trade_usdt = spot_trade_usdt
    if bb_trade_usdt > spot_trade_usdt and BYBIT_ENABLED:
        _primary_exchange = "bybit"
        _primary_trade_usdt = bb_trade_usdt

    spot_buy_blocked = (spot_trade_usdt <= 0 and bb_trade_usdt <= 0)
    if spot_buy_blocked:
        log_activity(f"[cycle] ALL BUYS BLOCKED — KC=${spot_usdt:.2f} BB=${bb_usdt:.2f} (both below threshold)")

    fg_val = fg_data.get("value", 50)
    # Cache prices for arb monitor
    _cache_set("all_prices", prices_data)
    # Pre-initialize poly_events from cache so log line below is always safe
    poly_events = _cache_get("polymarket", 900) or []
    log_activity(f"[cycle] F&G={fg_val}({fg_data.get('bonus',0):+d}) KC=${spot_usdt:.1f} BB=${bb_usdt:.1f} primary={_primary_exchange} trade=${_primary_trade_usdt:.1f} poly={len(poly_events)}mkts")

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
                                except Exception: continue
                            if not pr: continue
                            try: yp = round(float(pr[0]) * 100, 1)
                            except Exception: continue
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

    # v8.3.0: Самообучение — динамическая коррекция Q-порога на основе статистики
    _q_adjust = 0
    if _perf_stats["total_trades"] >= 5:
        # На серии убытков (≥3) повышаем порог → более осторожная торговля
        if _perf_stats["streak"] <= -3:
            _q_adjust = min(abs(_perf_stats["streak"]), 8)  # макс +8
        # На серии побед (≥5) немного снижаем → агрессивнее
        elif _perf_stats["streak"] >= 5:
            _q_adjust = -2
        # Win rate < 40% → повышаем порог
        wr = _perf_stats["wins"] / _perf_stats["total_trades"] * 100
        if wr < 40 and _perf_stats["total_trades"] >= 10:
            _q_adjust = max(_q_adjust, 5)
    if _q_adjust != 0:
        log_activity(f"[self-learn] Q-adjust={_q_adjust:+d} (streak={_perf_stats['streak']}, trades={_perf_stats['total_trades']})")

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
        # v8.2: Log signal and Q-Score to PostgreSQL
        if db.is_ready():
            asyncio.ensure_future(db.insert_signal({
                "symbol": symbol, "side": action.lower() if action != "HOLD" else None,
                "q_score": q, "confidence": conf, "pattern": vision.get("pattern", "?"),
                "fg_bonus": bd.get("fear_greed", 0), "poly_bonus": bd.get("polymarket", 0),
                "whale_bonus": bd.get("whale", 0), "vision_bonus": vision.get("vision_bonus", 0),
                "quantum_bias": bd.get("quantum_bias", 0), "executed": action != "HOLD",
            }))
            asyncio.ensure_future(db.insert_q_score(symbol, q, bd))
        # v7.1.2: per-pair Q threshold (overrides global MIN_Q_SCORE per symbol)
        _pair_min_q = PAIR_Q_THRESHOLDS.get(symbol, MIN_Q_SCORE)
        # v8.3.0: self-learning корректировка + per-symbol статистика
        _sym_q_adj = _q_adjust
        sym_stats = _perf_stats["by_symbol"].get(symbol, {})
        if sym_stats.get("trades", 0) >= 5:
            sym_wr = sym_stats["wins"] / sym_stats["trades"] * 100
            if sym_wr < 30:
                _sym_q_adj += 5  # символ убыточный → порог ещё выше
            elif sym_wr > 70:
                _sym_q_adj -= 2  # символ прибыльный → чуть ниже
        _pair_min_q = max(40, min(90, _pair_min_q + _sym_q_adj))
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

        # ── v10.0: Position limit — don't drain all USDT ──────────────────────
        open_count = sum(1 for t in trade_log if t.get("status") == "open")
        if action == "BUY" and open_count >= MAX_OPEN_POSITIONS:
            log_activity(f"[cycle] {symbol}: SKIP BUY — {open_count} open positions (max {MAX_OPEN_POSITIONS})")
            continue

        # ── v10.0: Self-learning filter — skip symbols with terrible winrate ──
        if symbol in _learning_insights.get("avoid_symbols", []):
            log_activity(f"[cycle] {symbol}: SKIPPED by self-learning (avoid list)")
            continue

        # ── v9.0: MiroFish Lite — sentiment check before any trade ───────────
        mf_result = None
        if MIROFISH_ENABLED and action != "SELL":
            mf_result = await mirofish_simulate(
                symbol, price, q, fg_val,
                vision.get("pattern", "?"),
                rsi=vision.get("rsi", 50),
                context=f"conf={conf:.0%} whale={whale.get('bonus',0):+d}"
            )
            # MiroFish veto: if direction opposes action with high confidence
            if mf_result["direction"] == "SELL" and mf_result["confidence"] >= 75 and action == "BUY":
                log_activity(f"[cycle] {symbol}: MIROFISH VETO — score={mf_result['score']:+d} "
                             f"({mf_result['buy']}B/{mf_result['sell']}S/{mf_result['hold']}H) conf={mf_result['confidence']}%")
                continue

        # ── Спот (BUY + SELL) v8.3 ──────────────────────────────────────────────
        if action == "BUY":
            # v8.3.4: Block buying during Extreme Fear (F&G < 15) — per trading.md rules
            if fg_val < 15:
                log_activity(f"[cycle] {symbol}: SKIP BUY — F&G={fg_val} Extreme Fear (threshold 15)")
                continue
            elapsed = time.time() - last_signals.get(symbol, {}).get("ts", 0)
            eff_cd_spot = COOLDOWN // 2 if conf >= 0.80 else COOLDOWN  # v7.2.4
            if elapsed >= eff_cd_spot and spot_trade_usdt >= 1.0:
                # v8.3.3: Opus gate for significant trades
                gate = await opus_gate_check(symbol, "BUY", spot_trade_usdt, q, fg_val,
                                              vision.get("pattern", "?"))
                if not gate["approved"]:
                    log_activity(f"[cycle] {symbol}: BLOCKED by Opus — {gate['reason']}")
                    continue
                # ── v10.0: Dual-exchange — route BUY to best exchange ──
                _buy_exchange = _primary_exchange
                _buy_usdt = _primary_trade_usdt
                # Fallback: if primary has no funds but secondary does
                if _buy_usdt < 1.0:
                    if _buy_exchange == "bybit" and spot_trade_usdt >= 1.0:
                        _buy_exchange = "kucoin"
                        _buy_usdt = spot_trade_usdt
                    elif _buy_exchange == "kucoin" and bb_trade_usdt >= 1.0:
                        _buy_exchange = "bybit"
                        _buy_usdt = bb_trade_usdt

                log_activity(f"[cycle] {symbol}: PLACING spot BUY ${_buy_usdt:.2f} on {_buy_exchange}"
                             f"{' MF=' + str(mf_result['score']) if mf_result else ''}")

                # v10.1: Auto-Earn — redeem USDT from Savings before BUY if needed
                if EARN_ENABLED and _earn_positions:
                    try:
                        _redeem = await earn_redeem_for_trading(_buy_exchange, _buy_usdt)
                        if _redeem.get("redeemed", 0) > 0:
                            log_activity(f"[earn] redeemed ${_redeem['redeemed']:.2f} from {_buy_exchange} Earn for BUY")
                            await asyncio.sleep(1)  # brief wait for funds to settle
                    except Exception as _e:
                        log_activity(f"[earn] pre-BUY redeem error: {_e}")

                if _buy_exchange == "bybit" and BYBIT_ENABLED:
                    bb_res = await bybit_place_spot_order(symbol, "Buy", _buy_usdt)
                    ok = bb_res.get("success", False)
                    if ok:
                        size = round(_buy_usdt / price, 6)
                        tp = round(price * (1 + TP_PCT), 6)
                        sl = round(price * (1 - SL_PCT), 6)
                        log_trade(symbol, "buy", price, size, tp, sl, conf, q,
                                  vision.get("pattern", "?"), "bybit_spot")
                        last_signals[symbol] = {"action": "BUY", "ts": time.time()}
                    else:
                        log_activity(f"[cycle] {symbol}: ByBit BUY failed: {bb_res.get('error','?')}")
                        # Fallback to KuCoin
                        if spot_trade_usdt >= 1.0:
                            ok = await execute_spot_trade(symbol, signal, vision, price, spot_trade_usdt)
                else:
                    ok = await execute_spot_trade(symbol, signal, vision, price, _buy_usdt)

                if ok:
                    signals_fired.append({"account": _buy_exchange + "_spot", "symbol": symbol, "action": action,
                        "price": price, "confidence": conf, "q_score": q,
                        "pattern": vision.get("pattern","?"), "rsi": vision.get("rsi", 0),
                        "tp": round(price*(1+TP_PCT),4), "sl": round(price*(1-SL_PCT),4),
                        "mirofish": mf_result})
        elif action == "SELL":
            # v10.0: Sell existing spot position when SELL signal fires (KuCoin + ByBit)
            open_spot = [t for t in trade_log if t.get("status") == "open"
                         and t.get("symbol") == symbol
                         and t.get("account") in ("spot", "bybit_spot")]
            if open_spot:
                elapsed = time.time() - last_signals.get(symbol, {}).get("ts", 0)
                eff_cd_spot = COOLDOWN // 2 if conf >= 0.80 else COOLDOWN
                if elapsed >= eff_cd_spot:
                    t = open_spot[-1]
                    _sell_acct = t.get("account", "spot")
                    if _sell_acct == "bybit_spot":
                        sell_res = await bybit_sell_spot(symbol)
                    else:
                        sell_res = await sell_spot_to_usdt(symbol)
                    if sell_res.get("success"):
                        pnl_pct = (price - t["price"]) / t["price"] if t["side"] == "buy" else (t["price"] - price) / t["price"]
                        pnl_usdt = round(pnl_pct * t["price"] * t["size"], 4)
                        t["status"] = "closed"
                        t["pnl"] = pnl_usdt
                        t["close_price"] = price
                        t["close_reason"] = "📉 SELL signal"
                        _save_trades_to_disk()
                        _update_perf_on_trade({"pnl_usdt": pnl_usdt, "strategy": "spot",
                                               "symbol": symbol, "q_score": t.get("q_score", 0)})
                        if db.is_ready():
                            asyncio.ensure_future(db.close_trade(
                                symbol=symbol, pnl_usdt=pnl_usdt, pnl_pct=round(pnl_pct, 6),
                                close_price=price, close_reason="SELL signal", strategy="spot",
                                duration_sec=round(time.time() - t.get("open_ts", time.time()), 1)))
                        last_signals[symbol] = {"action": "SELL", "ts": time.time()}
                        signals_fired.append({"account": _sell_acct, "symbol": symbol, "action": "SELL",
                            "price": price, "confidence": conf, "q_score": q,
                            "pattern": vision.get("pattern","?"), "pnl": pnl_usdt})
                        _sell_label = "ByBit" if _sell_acct == "bybit_spot" else "KuCoin"
                        log_activity(f"[cycle] {symbol}: SELL signal → {_sell_label} SOLD PnL=${pnl_usdt:+.4f}")

        # ── Фьючерсы: собираем кандидатов ────────────────────────────────────
        if symbol in ("BTC-USDT", "ETH-USDT", "SOL-USDT"):
            # v8.3.4: Block LONG during Extreme Fear
            if action == "BUY" and fg_val < 15:
                log_activity(f"[cycle] {symbol}: SKIP fut LONG — F&G={fg_val} Extreme Fear")
                continue
            FMAP = {"BTC-USDT":("XBTUSDTM",0.001),"ETH-USDT":("ETHUSDTM",0.01),"SOL-USDT":("SOLUSDTM",1.0)}
            _, cs = FMAP[symbol]
            margin = (price * cs) / MAX_LEVERAGE
            elapsed = time.time() - last_signals.get(f"FUT_{symbol}", {}).get("ts", 0)
            reason = None
            eff_cd = COOLDOWN // 2 if conf >= 0.80 else COOLDOWN  # v7.2.4
            if elapsed < eff_cd:  reason = f"cooldown {int(eff_cd-elapsed)}s"
            elif fut_usdt < 1.0:    reason = f"bal ${fut_usdt:.2f}<$1"
            elif margin > fut_usdt: reason = f"margin ${margin:.2f}>${fut_usdt:.2f}"
            if reason:
                log_activity(f"[cycle] {symbol}: SKIP fut — {reason}")
            else:
                # v8.3.3: Opus gate for futures (v9.0: enriched with MiroFish)
                f_trade_usdt = max(0, fut_usdt - ARB_RESERVE_USDT) * RISK_PER_TRADE
                mf_ctx = f" mirofish={mf_result['score']:+d}" if mf_result else ""
                gate = await opus_gate_check(symbol, action, f_trade_usdt, q, fg_val,
                                              vision.get("pattern", "?"), context=f"futures{mf_ctx}")
                if not gate["approved"]:
                    log_activity(f"[cycle] {symbol}: FUT BLOCKED by Opus — {gate['reason']}")
                else:
                    futures_candidates.append({
                        "symbol": symbol, "signal": signal, "vision": vision,
                        "price": price, "action": action, "conf": conf, "q": q,
                        "fg": fg_data, "poly": poly_b, "whale": whale.get("bonus", 0),
                        "pattern": vision.get("pattern","?"),
                        "mirofish": mf_result,
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
            best["q"], best["pattern"], best["fg"], best["poly"], best["whale"],
            mirofish=best.get("mirofish")
        )
        asyncio.create_task(auto_execute_dynamic(trade_id))

    # ── Уведомление спот ─────────────────────────────────────────────────────
    if signals_fired:
        mode = "TEST" if TEST_MODE else "LIVE"
        msg  = f"⚛ *QuantumTrade {mode}*\n\n"
        for s in signals_fired:
            emoji = "🟢" if s["action"] == "BUY" else "🔴"
            mf = s.get("mirofish")
            mf_line = f"\n   🐟 MiroFish: `{mf['score']:+d}` ({mf['direction']})" if mf and not mf.get("error") else ""
            msg += f"{emoji} *{s['symbol']}* {s['action']} [spot]\n   Q:`{s['q_score']}` TP:`${s['tp']:,.2f}` SL:`${s['sl']:,.2f}`{mf_line}\n\n"
        await notify(msg)

    # ── BTC Q-Score алерты ────────────────────────────────────────────────────
    btc_res = next((r for r in cv_results if not isinstance(r, Exception) and r[0] == "BTC-USDT"), None)
    if btc_res:
        _, _, btc_signal, _, _ = btc_res
        q = btc_signal["q_score"]; conf = btc_signal["confidence"]
        btc_price = prices_data["prices"].get("BTC-USDT", {}).get("price", 0)
        sell_thresh = 100 - MIN_Q_SCORE  # v7.2.2: динамический порог
        if q >= MIN_Q_SCORE and last_q_score < MIN_Q_SCORE:
            await notify(f"🚀 <b>Q-Score {q:.0f} — сигнал BUY!</b> BTC <code>${btc_price:,.0f}</code> · <code>{int(conf*100)}%</code> · F&G={fg_val}")
        elif q <= sell_thresh and last_q_score > sell_thresh:
            # v7.2.2: антиспам — не чаще раза в 5 мин
            now = time.time()
            if now - _q_alert_last.get("sell", 0) > 300:
                _q_alert_last["sell"] = now
                await notify(f"⚠️ <b>Q-Score {q:.0f} — зона SELL</b> · BTC <code>${btc_price:,.0f}</code>")
        last_q_score = q


# ── Startup ────────────────────────────────────────────────────────────────────
# ── Position Monitor ────────────────────────────────────────────────────────────

# ══════════════════════════════════════════════════════════════════════════════
# TRIANGULAR ARBITRAGE MONITOR v7.1
# Схема: USDT → A → B → USDT
# Проверяем отклонение реального кросс-курса A-B от имплицитного
# Если спред > 0.4% (>0.3% комиссий KuCoin) → алерт в Telegram
# ══════════════════════════════════════════════════════════════════════════════

# v8.3: Expanded triangles — all known KuCoin BTC + ETH cross-pairs
# Format: (coin_a-USDT, coin_b-USDT, cross_pair, description)
# The check_triangular_arb function auto-skips pairs that return 0 price
ARB_TRIANGLES = [
    # ══════════════════════════════════════════════════════════════════════
    # v8.3.2: 50 triangles (was 25) — BTC crosses, ETH crosses, KCS crosses
    # Dead pairs auto-detected at runtime via _arb_dead_pairs
    # ══════════════════════════════════════════════════════════════════════

    # ── BTC cross-pairs (USDT → X → BTC → USDT) — 20 pairs ─────────────
    ("ETH-USDT",   "BTC-USDT",  "ETH-BTC",   "USDT→ETH→BTC→USDT"),
    ("XRP-USDT",   "BTC-USDT",  "XRP-BTC",   "USDT→XRP→BTC→USDT"),
    ("ADA-USDT",   "BTC-USDT",  "ADA-BTC",   "USDT→ADA→BTC→USDT"),
    ("LINK-USDT",  "BTC-USDT",  "LINK-BTC",  "USDT→LINK→BTC→USDT"),
    ("LTC-USDT",   "BTC-USDT",  "LTC-BTC",   "USDT→LTC→BTC→USDT"),
    ("DOGE-USDT",  "BTC-USDT",  "DOGE-BTC",  "USDT→DOGE→BTC→USDT"),
    ("ETC-USDT",   "BTC-USDT",  "ETC-BTC",   "USDT→ETC→BTC→USDT"),
    ("DOT-USDT",   "BTC-USDT",  "DOT-BTC",   "USDT→DOT→BTC→USDT"),
    ("ATOM-USDT",  "BTC-USDT",  "ATOM-BTC",  "USDT→ATOM→BTC→USDT"),
    ("NEAR-USDT",  "BTC-USDT",  "NEAR-BTC",  "USDT→NEAR→BTC→USDT"),
    ("FIL-USDT",   "BTC-USDT",  "FIL-BTC",   "USDT→FIL→BTC→USDT"),
    ("UNI-USDT",   "BTC-USDT",  "UNI-BTC",   "USDT→UNI→BTC→USDT"),
    ("AVAX-USDT",  "BTC-USDT",  "AVAX-BTC",  "USDT→AVAX→BTC→USDT"),
    ("TRX-USDT",   "BTC-USDT",  "TRX-BTC",   "USDT→TRX→BTC→USDT"),
    ("BNB-USDT",   "BTC-USDT",  "BNB-BTC",   "USDT→BNB→BTC→USDT"),
    ("ALGO-USDT",  "BTC-USDT",  "ALGO-BTC",  "USDT→ALGO→BTC→USDT"),
    ("XLM-USDT",   "BTC-USDT",  "XLM-BTC",   "USDT→XLM→BTC→USDT"),
    ("VET-USDT",   "BTC-USDT",  "VET-BTC",   "USDT→VET→BTC→USDT"),
    ("AAVE-USDT",  "BTC-USDT",  "AAVE-BTC",  "USDT→AAVE→BTC→USDT"),
    ("AR-USDT",    "BTC-USDT",  "AR-BTC",    "USDT→AR→BTC→USDT"),

    # ── ETH cross-pairs (USDT → X → ETH → USDT) — 15 pairs ─────────────
    ("LTC-USDT",   "ETH-USDT",  "LTC-ETH",   "USDT→LTC→ETH→USDT"),
    ("ETC-USDT",   "ETH-USDT",  "ETC-ETH",   "USDT→ETC→ETH→USDT"),
    ("LINK-USDT",  "ETH-USDT",  "LINK-ETH",  "USDT→LINK→ETH→USDT"),
    ("ADA-USDT",   "ETH-USDT",  "ADA-ETH",   "USDT→ADA→ETH→USDT"),
    ("DOGE-USDT",  "ETH-USDT",  "DOGE-ETH",  "USDT→DOGE→ETH→USDT"),
    ("XRP-USDT",   "ETH-USDT",  "XRP-ETH",   "USDT→XRP→ETH→USDT"),
    ("DOT-USDT",   "ETH-USDT",  "DOT-ETH",   "USDT→DOT→ETH→USDT"),
    ("ATOM-USDT",  "ETH-USDT",  "ATOM-ETH",  "USDT→ATOM→ETH→USDT"),
    ("FIL-USDT",   "ETH-USDT",  "FIL-ETH",   "USDT→FIL→ETH→USDT"),
    ("UNI-USDT",   "ETH-USDT",  "UNI-ETH",   "USDT→UNI→ETH→USDT"),
    ("AVAX-USDT",  "ETH-USDT",  "AVAX-ETH",  "USDT→AVAX→ETH→USDT"),
    ("NEAR-USDT",  "ETH-USDT",  "NEAR-ETH",  "USDT→NEAR→ETH→USDT"),
    ("AAVE-USDT",  "ETH-USDT",  "AAVE-ETH",  "USDT→AAVE→ETH→USDT"),
    ("SNX-USDT",   "ETH-USDT",  "SNX-ETH",   "USDT→SNX→ETH→USDT"),
    ("CRV-USDT",   "ETH-USDT",  "CRV-ETH",   "USDT→CRV→ETH→USDT"),

    # ── KCS cross-pairs (USDT → X → KCS → USDT) — 8 pairs ──────────────
    ("BTC-USDT",   "KCS-USDT",  "BTC-KCS",   "USDT→BTC→KCS→USDT"),
    ("ETH-USDT",   "KCS-USDT",  "ETH-KCS",   "USDT→ETH→KCS→USDT"),
    ("DOGE-USDT",  "KCS-USDT",  "DOGE-KCS",  "USDT→DOGE→KCS→USDT"),
    ("XRP-USDT",   "KCS-USDT",  "XRP-KCS",   "USDT→XRP→KCS→USDT"),
    ("SOL-USDT",   "KCS-USDT",  "SOL-KCS",   "USDT→SOL→KCS→USDT"),
    ("DOT-USDT",   "KCS-USDT",  "DOT-KCS",   "USDT→DOT→KCS→USDT"),
    ("LINK-USDT",  "KCS-USDT",  "LINK-KCS",  "USDT→LINK→KCS→USDT"),
    ("UNI-USDT",   "KCS-USDT",  "UNI-KCS",   "USDT→UNI→KCS→USDT"),

    # ── Extra BTC crosses (mid-cap) — 7 pairs ───────────────────────────
    ("SOL-USDT",   "BTC-USDT",  "SOL-BTC",   "USDT→SOL→BTC→USDT"),
    ("MATIC-USDT", "BTC-USDT",  "MATIC-BTC", "USDT→MATIC→BTC→USDT"),
    ("OP-USDT",    "BTC-USDT",  "OP-BTC",    "USDT→OP→BTC→USDT"),
    ("APT-USDT",   "BTC-USDT",  "APT-BTC",   "USDT→APT→BTC→USDT"),
    ("SAND-USDT",  "BTC-USDT",  "SAND-BTC",  "USDT→SAND→BTC→USDT"),
    ("MANA-USDT",  "BTC-USDT",  "MANA-BTC",  "USDT→MANA→BTC→USDT"),
    ("GRT-USDT",   "BTC-USDT",  "GRT-BTC",   "USDT→GRT→BTC→USDT"),
]
# v8.3: Invalid pairs are auto-detected at runtime and silently skipped
_arb_dead_pairs: set = set()  # pairs that returned 0 price → skip next time
ARB_FEE       = 0.001   # 0.1% per trade, 0.3% for 3 trades
ARB_MIN_SPREAD = 0.003  # v8.3.5: 0.3% (was 0.4%) — more opportunities on tight markets
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
        # v8.3: skip pairs that don't exist on KuCoin (auto-detected)
        if cross_sym in _arb_dead_pairs:
            continue

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
            _arb_dead_pairs.add(cross_sym)  # mark as dead, don't query again
            log_activity(f"[arb] {cross_sym} → dead pair (no data), skipping in future")
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

def _fmt_price(val: float) -> str:
    """Smart price format — auto-adjust decimals for very small numbers."""
    if val == 0:
        return "0"
    av = abs(val)
    if av >= 1:
        return f"{val:.4f}"
    elif av >= 0.001:
        return f"{val:.6f}"
    elif av >= 0.0000001:
        return f"{val:.10f}"
    else:
        return f"{val:.2e}"

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
        f"\u0418\u043c\u043f\u043b\u0438\u0446\u0438\u0442\u043d\u044b\u0439:  <code>{_fmt_price(opp['implied'])}</code>\n"
        f"\u0420\u044b\u043d\u043e\u0447\u043d\u044b\u0439:     <code>{_fmt_price(opp['actual'])}</code>\n"
        f"\u0421\u043f\u0440\u0435\u0434:        <code>{opp['spread_pct']:+.3f}%</code>\n\n"
        f"\U0001f4b0 \u041f\u0440\u0438\u0431\u044b\u043b\u044c (\u043f\u043e\u0441\u043b\u0435 \u043a\u043e\u043c\u0438\u0441\u0441\u0438\u0439 0.3%):\n"
        f"  $100  \u2192 <code>${profit_100:+.3f}</code>\n"
        f"  $1000 \u2192 <code>${profit_1000:+.2f}</code>\n\n"
        f"\u23f0 <i>\u0414\u0435\u0439\u0441\u0442\u0432\u0443\u0439 \u0431\u044b\u0441\u0442\u0440\u043e \u2014 \u0430\u0440\u0431\u0438\u0442\u0440\u0430\u0436 \u0436\u0438\u0432\u0451\u0442 \u0441\u0435\u043a\u0443\u043d\u0434\u044b!</i>"
    )
    await notify(msg)
    # v8.3.3: Track arb opportunity
    _arb_stats["opportunities_found"] += 1
    _arb_stats["last_opp_ts"] = time.time()
    if abs(opp.get("spread_pct", 0)) > abs(_arb_stats["best_spread"]):
        _arb_stats["best_spread"] = opp["spread_pct"]
    _arb_history.append({
        "ts": time.time(), "path": opp["path"], "spread": opp["spread_pct"],
        "cross": opp["cross_sym"], "direction": opp["direction"],
        "executed": False, "pnl": 0
    })
    if len(_arb_history) > 50:
        _arb_history.pop(0)


# ── v7.3.9: Triangular Arb EXECUTION (safe) ───────────────────────────────────
ARB_EXEC_USDT     = float(os.getenv("ARB_EXEC_USDT", "5"))     # v8.3: lowered to $5 for small balance testing
ARB_EXEC_ENABLED  = os.getenv("ARB_EXEC_ENABLED", "true").lower() == "true"  # v8.3: ON by default
ARB_MIN_PROFIT_PCT = 0.35  # v8.3.5: 0.35% (was 0.5%) — execute more arbs, still above 3x fee
_arb_stats: dict   = {"total": 0, "success": 0, "failed": 0, "total_pnl": 0.0,
                       "opportunities_found": 0, "best_spread": 0.0, "last_opp_ts": 0}
_arb_history: list = []  # last 50 arb events [{ts, path, spread, executed, pnl}]
_arb_last_exec: dict = {}   # path_key → timestamp
_arb_executing: bool = False  # global lock — only ONE arb at a time

def _order_ok(r: dict) -> bool:
    """True if KuCoin returned a valid orderId (order accepted)."""
    return bool(r.get("code") == "200000" and r.get("data", {}).get("orderId"))

async def _spot_buy_funds(symbol: str, funds: float) -> dict:
    """Market BUY using quote-currency amount (funds=USDT). Safer than size for buys."""
    endpoint = "/api/v1/orders"
    body = json.dumps({
        "clientOid": f"qt_{int(time.time()*1000)}",
        "side": "buy", "symbol": symbol,
        "type": "market", "funds": str(round(funds, 4))
    })
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(KUCOIN_BASE_URL + endpoint,
                             headers=kucoin_headers("POST", endpoint, body),
                             data=body, timeout=aiohttp.ClientTimeout(total=10))
            return await r.json()
    except Exception as e:
        return {"code": "error", "msg": str(e)}

async def execute_triangular_arb(opp: dict) -> dict:
    """Safe triangular arb: 3 legs with abort + emergency sell-back on failure.

    Direction 1 (USDT→A→BTC→USDT):
        leg1: buy  a_sym  with USDT (funds-based buy)
        leg2: sell cross  (sell A for BTC via cross pair, e.g. ETH-BTC)
        leg3: sell b_sym  (sell BTC back to USDT)

    Direction 2 (USDT→BTC→A→USDT):
        leg1: buy  b_sym  with USDT (funds-based buy)
        leg2: buy  cross  (buy A with BTC)
        leg3: sell a_sym  (sell A back to USDT)

    Abort logic: if leg2 or leg3 fails → emergency sell-back of intermediate crypto.
    Global lock: only one triangle executes at a time.
    """
    global _arb_executing

    if not ARB_EXEC_ENABLED:
        return {"executed": False, "reason": "ARB_EXEC_ENABLED=false"}

    # Global lock — prevent concurrent arb executions
    if _arb_executing:
        return {"executed": False, "reason": "another arb in progress"}

    path_key = opp.get("path", "")
    now = time.time()

    # Cooldown per triangle path
    if now - _arb_last_exec.get(path_key, 0) < ARB_COOLDOWN_SEC:
        remaining = int(ARB_COOLDOWN_SEC - (now - _arb_last_exec.get(path_key, 0)))
        return {"executed": False, "reason": f"cooldown {remaining}s"}

    # Profit threshold — must be above fees + slippage
    profit_pct = opp.get("profit_pct", 0)
    if profit_pct < ARB_MIN_PROFIT_PCT:
        return {"executed": False, "reason": f"profit {profit_pct:.3f}% < min {ARB_MIN_PROFIT_PCT}%"}

    # Check spot USDT balance — v8.3.4: reserve-aware sizing
    bal = await get_balance()
    spot_usdt = bal.get("total_usdt", 0)
    # v8.3.4: never use more than (spot_usdt - ARB_RESERVE_USDT * 0.5) for arb
    # Keep at least half the reserve after arb execution
    usdt_for_arb = max(0, spot_usdt - ARB_RESERVE_USDT * 0.5)
    arb_amount = min(ARB_EXEC_USDT, usdt_for_arb)
    if not bal.get("success") or arb_amount < 3.0:
        return {"executed": False, "reason": f"low spot USDT {spot_usdt:.2f} (reserve ${ARB_RESERVE_USDT:.0f}, need ≥$3)"}

    _arb_executing = True
    _arb_last_exec[path_key] = now

    a_sym   = opp["a_sym"]      # e.g. ETH-USDT
    b_sym   = opp["b_sym"]      # e.g. BTC-USDT
    cross   = opp["cross_sym"]  # e.g. ETH-BTC
    d       = opp["direction"]
    price_a = opp["price_a"]
    price_b = opp["price_b"]
    actual  = opp["actual"]     # actual cross rate (A/B or B/A)

    FEE = 0.997  # 0.3% KuCoin taker fee buffer per leg

    try:
        if d == 1:
            # ── Leg 1: spend USDT, get A (ETH/XRP/etc) ──────────────────
            r1 = await _spot_buy_funds(a_sym, arb_amount)
            if not _order_ok(r1):
                log_activity(f"[arb] leg1 FAILED {a_sym}: {r1.get('msg','?')}")
                _arb_stats["failed"] += 1
                return {"executed": False, "reason": f"leg1 failed: {r1.get('msg')}"}

            size_a = round((arb_amount / price_a) * FEE, 6)  # conservative A received
            await asyncio.sleep(0.5)

            # ── Leg 2: sell A for BTC via cross pair ──────────────────────
            r2 = await place_spot_order(cross, "sell", size_a)
            if not _order_ok(r2):
                log_activity(f"[arb] leg2 FAILED {cross} — emergency sell {a_sym}")
                await place_spot_order(a_sym, "sell", size_a)  # sell A back to USDT
                _arb_stats["failed"] += 1
                await notify(f"⚠️ Арб {path_key}: leg2 провалился, {a_sym} продан обратно")
                return {"executed": False, "reason": "leg2 failed, emergency sell done"}

            btc_received = round(size_a * actual * FEE, 8)  # conservative BTC received
            await asyncio.sleep(0.5)

            # ── Leg 3: sell BTC → USDT ────────────────────────────────────
            r3 = await place_spot_order(b_sym, "sell", btc_received)
            if not _order_ok(r3):
                log_activity(f"[arb] leg3 FAILED {b_sym} — BTC {btc_received} stuck in spot")
                _arb_stats["failed"] += 1
                await notify(f"⚠️ Арб {path_key}: leg3 провалился, {btc_received} BTC на споте")
                return {"executed": False, "reason": "leg3 failed, BTC in spot account"}

        else:
            # ── Leg 1: spend USDT, get BTC ───────────────────────────────
            r1 = await _spot_buy_funds(b_sym, arb_amount)
            if not _order_ok(r1):
                log_activity(f"[arb] leg1 FAILED {b_sym}: {r1.get('msg','?')}")
                _arb_stats["failed"] += 1
                return {"executed": False, "reason": f"leg1 failed: {r1.get('msg')}"}

            size_b = round((arb_amount / price_b) * FEE, 8)
            await asyncio.sleep(0.5)

            # ── Leg 2: buy A with BTC via cross pair ──────────────────────
            size_a = round(size_b * actual * FEE, 6)
            r2 = await place_spot_order(cross, "buy", size_a)
            if not _order_ok(r2):
                log_activity(f"[arb] leg2 FAILED {cross} — emergency sell {b_sym}")
                await place_spot_order(b_sym, "sell", size_b)
                _arb_stats["failed"] += 1
                await notify(f"⚠️ Арб {path_key}: leg2 провалился, {b_sym} продан обратно")
                return {"executed": False, "reason": "leg2 failed, emergency sell done"}

            await asyncio.sleep(0.5)

            # ── Leg 3: sell A → USDT ─────────────────────────────────────
            r3 = await place_spot_order(a_sym, "sell", size_a)
            if not _order_ok(r3):
                log_activity(f"[arb] leg3 FAILED {a_sym} — {size_a} stuck in spot")
                _arb_stats["failed"] += 1
                await notify(f"⚠️ Арб {path_key}: leg3 провалился, {size_a} {a_sym} на споте")
                return {"executed": False, "reason": "leg3 failed"}

        # ── All 3 legs OK ─────────────────────────────────────────────────
        estimated_pnl = round(arb_amount * profit_pct / 100, 4)
        _arb_stats["total"] += 1
        _arb_stats["success"] += 1
        _arb_stats["total_pnl"] = round(_arb_stats["total_pnl"] + estimated_pnl, 4)
        log_activity(f"[arb] ✅ {path_key} profit≈{estimated_pnl:+.4f} USDT")

        msg = (
            f"✅ <b>Арбитраж завершён!</b>\n"
            f"<code>{path_key}</code>\n\n"
            f"💰 Прибыль ≈ <code>{estimated_pnl:+.4f} USDT</code>\n"
            f"📊 Успешных: {_arb_stats['success']} | "
            f"Ошибок: {_arb_stats['failed']} | "
            f"PnL: {_arb_stats['total_pnl']:+.4f} USDT"
        )
        await notify(msg)
        return {"executed": True, "success": True, "pnl": estimated_pnl}

    except Exception as e:
        log_activity(f"[arb_exec] EXCEPTION {path_key}: {e}")
        _arb_stats["failed"] += 1
        await notify(f"❌ <b>Арбитраж ошибка</b>: {e}\n<code>{path_key}</code>")
        return {"executed": False, "reason": str(e)}

    finally:
        _arb_executing = False  # always release lock


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
                # v7.3.2: если API не ответил — пропускаем итерацию, не закрываем позиции ошибочно
                if not pos_data.get("success"):
                    log_activity("[monitor] get_futures_positions FAILED — пропускаем проверку")
                    await asyncio.sleep(30)
                    continue
                open_syms  = {p.get("symbol") for p in pos_data.get("positions", [])}
                for trade in open_trades:
                    # v7.2.0: мин 5 мин до закрытия — защита от race condition
                    if (time.time() - trade.get("open_ts", time.time())) < 300:
                        continue
                    # v7.2.4: Trailing Stop — защищаем прибыль для открытых позиций
                    if trade["symbol"] in open_syms and not trade.get("trail_triggered"):
                        base_sym_t = SYM_REV.get(trade["symbol"], trade["symbol"].replace("USDTM", "-USDT").replace("XBT", "BTC"))
                        try:
                            cur_p = await get_ticker(base_sym_t)
                            ent   = trade["price"]
                            sd    = trade["side"]
                            pct_t = (cur_p - ent) / ent if sd == "buy" else (ent - cur_p) / ent
                            peak  = trade.get("peak_pct", 0.0)
                            if pct_t > peak:
                                trade["peak_pct"] = pct_t
                                peak = pct_t
                            if peak >= TRAIL_TRIGGER and (peak - pct_t) >= TRAIL_PCT:
                                cs = "sell" if sd == "buy" else "buy"
                                await place_futures_order(trade["symbol"], cs, trade.get("size", 1), reduce_only=True)
                                trade["trail_triggered"] = True
                                log_activity(f"[trail] {trade['symbol']} peak={peak*100:.1f}% now={pct_t*100:.1f}% CLOSED")
                                print(f"[TRAIL] {trade['symbol']} peak={peak*100:.1f}% pullback={(peak-pct_t)*100:.1f}%", flush=True)
                        except Exception as te:
                            print(f"[trail] {trade['symbol']} err: {te}", flush=True)
                    if trade["symbol"] not in open_syms:
                        # v8.3: спот-сделки мониторятся в spot_monitor_loop — пропускаем здесь
                        if trade.get("account") == "spot" or "USDTM" not in trade["symbol"]:
                            continue  # spot_monitor_loop will handle TP/SL
                        base_sym      = SYM_REV.get(trade["symbol"], trade["symbol"].replace("USDTM", "-USDT").replace("XBT", "BTC"))
                        entry         = trade["price"]
                        contract_size = CONTRACT_SIZES.get(trade["symbol"], 0.01)
                        open_ts       = trade.get("open_ts", time.time() - 400)
                        # v7.3.2: реальная цена из closing fills (только противоположная сторона)
                        real_close = await get_recent_futures_fills(trade["symbol"], open_ts, trade.get("side", "buy"))
                        price_now  = real_close if real_close else await get_ticker(base_sym)
                        price_source = "fills" if real_close else "ticker"
                        if trade["side"] == "sell":
                            pnl_pct = (entry - price_now) / entry
                        else:
                            pnl_pct = (price_now - entry) / entry
                        pnl_usdt = round(pnl_pct * entry * trade["size"] * contract_size, 4)
                        duration_min = round((time.time() - open_ts) / 60, 1)
                        # Определяем причину закрытия по реальной цене
                        tp  = trade.get("tp", entry * 1.03)
                        sl  = trade.get("sl", entry * 0.985)
                        if trade["side"] == "buy":
                            reason = "🎯 TP" if price_now >= tp * 0.995 else ("🛑 SL" if price_now <= sl * 1.005 else "📊 Монитор")
                        else:
                            reason = "🎯 TP" if price_now <= tp * 1.005 else ("🛑 SL" if price_now >= sl * 0.995 else "📊 Монитор")
                        trade["status"]       = "closed"
                        trade["pnl"]          = pnl_usdt
                        trade["close_price"]  = price_now
                        trade["price_source"] = price_source  # для диагностики
                        emoji = "✅" if pnl_usdt >= 0 else "❌"
                        strat = trade.get("account", "B").replace("futures_", "")
                        log_activity(f"[monitor] {trade['symbol']} {reason} closed PnL=${pnl_usdt:+.4f}")
                        print(f"[CLOSE] {trade['symbol']} {trade['side'].upper()} PnL=${pnl_usdt:+.4f} entry=${trade['price']} exit=${price_now}", flush=True)
                        _save_trades_to_disk()
                        # v7.5.0: обновляем статистику самообучения
                        _update_perf_on_trade({
                            "pnl_usdt": pnl_usdt,
                            "strategy": strat,
                            "symbol": trade["symbol"],
                            "q_score": trade.get("q_score", 0),
                        })
                        # v8.2: PostgreSQL persistent storage
                        if db.is_ready():
                            asyncio.ensure_future(db.close_trade(
                                symbol=trade["symbol"], pnl_usdt=pnl_usdt, pnl_pct=round(pnl_pct, 6),
                                close_price=price_now, close_reason=reason, strategy=strat,
                                duration_sec=round(time.time() - open_ts, 1)
                            ))
                            asyncio.ensure_future(db.save_perf_stats(_perf_stats))
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
                        if ARB_EXEC_ENABLED:
                            await execute_triangular_arb(opp)
        except Exception as e:
            log_activity(f"[arb] monitor error: {e}")

        await asyncio.sleep(30)


# ── v8.3: Spot Position Monitor ───────────────────────────────────────────────
async def spot_monitor_loop():
    """v8.3: Monitors spot trades — checks TP/SL, sells when conditions met.
    Unlike futures, spot trades need to be actively closed by selling the coin."""
    await asyncio.sleep(60)  # initial delay
    while True:
        try:
            open_spot = [t for t in trade_log
                         if t.get("status") == "open"
                         and t.get("account") in ("spot", "bybit_spot")]
            if not open_spot:
                await asyncio.sleep(45)
                continue

            # Fetch actual spot balances to verify we still hold the coins
            spot_bals = await get_spot_balances()
            # v10.0: Also fetch ByBit spot balances
            bb_spot_bals = {}
            if BYBIT_ENABLED:
                try:
                    bb_spot_bals = await bybit_get_spot_balances()
                except Exception:
                    pass

            for trade in open_spot:
                try:
                    symbol = trade["symbol"]
                    entry = trade["price"]
                    side = trade.get("side", "buy")
                    tp = trade.get("tp", entry * (1 + TP_PCT))
                    sl = trade.get("sl", entry * (1 - SL_PCT))
                    open_ts = trade.get("open_ts", time.time() - 400)

                    # Min 3 min before checking spot trades (order fill time)
                    if (time.time() - open_ts) < 180:
                        continue

                    # v10.0: Check balance on correct exchange
                    _trade_acct = trade.get("account", "spot")
                    if _trade_acct == "bybit_spot":
                        bal_info = bb_spot_bals.get(symbol)
                    else:
                        bal_info = spot_bals.get(symbol)
                    if not bal_info or bal_info["available"] <= 0:
                        trade["status"] = "closed"
                        trade["pnl"] = 0.0
                        trade["close_reason"] = "no_balance"
                        _save_trades_to_disk()
                        log_activity(f"[spot_mon] {symbol} ({_trade_acct}): no balance — closing as no_balance")
                        continue

                    price_now = bal_info["price"]
                    if price_now <= 0:
                        continue

                    # Calculate PnL
                    if side == "buy":
                        pnl_pct = (price_now - entry) / entry
                    else:
                        pnl_pct = (entry - price_now) / entry

                    trade_size = trade.get("size", 0)
                    pnl_usdt = round(pnl_pct * entry * trade_size, 4)

                    # Trailing stop for spot
                    peak = trade.get("peak_pct", 0.0)
                    if pnl_pct > peak:
                        trade["peak_pct"] = pnl_pct
                        peak = pnl_pct

                    should_close = False
                    reason = ""

                    # TP hit
                    if side == "buy" and price_now >= tp * 0.998:
                        should_close = True
                        reason = "🎯 TP"
                    # SL hit
                    elif side == "buy" and price_now <= sl * 1.002:
                        should_close = True
                        reason = "🛑 SL"
                    # Trailing stop (if peak was high enough and pulled back)
                    elif peak >= TRAIL_TRIGGER and (peak - pnl_pct) >= TRAIL_PCT:
                        should_close = True
                        reason = "📈 Trail"
                    # Emergency: loss > 5% → force close
                    elif pnl_pct <= -0.05:
                        should_close = True
                        reason = "🚨 MaxLoss"
                    # v10.0: Stale position — open > 12h with no significant move → free up capital
                    elif (time.time() - open_ts) > 43200 and abs(pnl_pct) < 0.015:
                        should_close = True
                        reason = "⏰ Stale (12h)"

                    if should_close:
                        # v10.0: Sell on correct exchange
                        sell_size = min(trade_size, bal_info["available"])
                        if _trade_acct == "bybit_spot":
                            sell_result = await bybit_sell_spot(symbol, sell_size)
                        else:
                            sell_result = await sell_spot_to_usdt(symbol, sell_size)
                        if sell_result.get("success"):
                            trade["status"] = "closed"
                            trade["pnl"] = pnl_usdt
                            trade["close_price"] = price_now
                            trade["close_reason"] = reason
                            _save_trades_to_disk()
                            duration_min = round((time.time() - open_ts) / 60, 1)
                            emoji = "✅" if pnl_usdt >= 0 else "❌"
                            _update_perf_on_trade({
                                "pnl_usdt": pnl_usdt, "strategy": "spot",
                                "symbol": symbol, "q_score": trade.get("q_score", 0),
                            })
                            if db.is_ready():
                                asyncio.ensure_future(db.close_trade(
                                    symbol=symbol, pnl_usdt=pnl_usdt, pnl_pct=round(pnl_pct, 6),
                                    close_price=price_now, close_reason=reason, strategy="spot",
                                    duration_sec=round(time.time() - open_ts, 1)
                                ))
                                asyncio.ensure_future(db.save_perf_stats(_perf_stats))
                            _exch_label = "ByBit" if _trade_acct == "bybit_spot" else "KuCoin"
                            await notify(
                                f"{emoji} <b>Спот закрыта — {reason}</b>\n"
                                f"<code>{symbol}</code> {side.upper()} ({_exch_label})\n"
                                f"Вход: <code>${entry:,.4f}</code> → Выход: <code>${price_now:,.4f}</code>\n"
                                f"PnL: <code>${pnl_usdt:+.4f}</code> ({pnl_pct*100:+.2f}%)\n"
                                f"Длительность: {duration_min}м"
                            )
                            log_activity(f"[spot_mon] {symbol} ({_exch_label}) {reason} SOLD PnL=${pnl_usdt:+.4f}")
                            # v10.1: Auto-Earn — place freed USDT into Flexible Savings
                            if EARN_ENABLED:
                                _earn_exch = "bybit" if _trade_acct == "bybit_spot" else "kucoin"
                                asyncio.ensure_future(earn_auto_place_idle(_earn_exch))
                        else:
                            log_activity(f"[spot_mon] {symbol} ({_exch_label}) sell FAILED: {sell_result.get('error', sell_result.get('msg','?'))}")
                    else:
                        # Just log status
                        if int(time.time()) % 300 < 50:  # every ~5 min
                            log_activity(f"[spot_mon] {symbol} open PnL={pnl_pct*100:+.2f}% peak={peak*100:.1f}% price=${price_now:.4f}")

                except Exception as te:
                    log_activity(f"[spot_mon] {trade.get('symbol','?')} error: {te}")

        except Exception as e:
            log_activity(f"[spot_mon] loop error: {e}")

        await asyncio.sleep(45)


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
    except Exception as e:
        log_activity(f"[_tg_answer] error: {e}")

async def _tg_main_menu(chat_id: int):
    """Главное меню бота."""
    ap  = "🟢 ВКЛ" if AUTOPILOT       else "🔴 ВЫКЛ"
    arb = "🟢"     if ARB_EXEC_ENABLED else "🔴"
    _webapp = WEBAPP_URL or RAILWAY_PUBLIC_DOMAIN and f"https://{RAILWAY_PUBLIC_DOMAIN}" or ""
    _dash_btn = [{"text": "🖥️ Открыть дашборд", "web_app": {"url": _webapp}}] if _webapp else [{"text": "🖥️ Дашборд (URL не задан)", "callback_data": "noop"}]
    kb = {"inline_keyboard": [
        _dash_btn,
        [{"text": "📊 Статистика", "callback_data": "menu_stats"},
         {"text": "🪂 Airdrops",   "callback_data": "menu_airdrops"}],
        [{"text": "⚙️ Настройки",  "callback_data": "menu_settings"},
         {"text": f"🤖 Автопилот: {ap}", "callback_data": "menu_autopilot"}],
        [{"text": "💰 Баланс",     "callback_data": "menu_balance"},
         {"text": "📈 Позиции",    "callback_data": "menu_positions"}],
        [{"text": f"⚡ Арбитраж {arb}", "callback_data": "menu_arb"}],
    ]}
    await _tg_send(chat_id,
        "⚛ <b>QuantumTrade AI v10.1.0</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Выбери раздел:", kb)

async def _tg_stats(chat_id: int):
    """Отправляет карточку статистики трейдинга. v9.0: uses _perf_stats (closed trades only)."""
    # v9.0: Use _perf_stats for accurate WR (only closed trades)
    total = _perf_stats.get("total_trades", 0)
    wins  = _perf_stats.get("wins", 0)
    losses = _perf_stats.get("losses", 0)
    pnl   = round(_perf_stats.get("total_pnl", 0.0), 2)
    wr    = round(wins / total * 100, 1) if total else 0
    open_ = sum(1 for t in trade_log if t.get("status", "") == "open")
    streak = _perf_stats.get("streak", 0)
    last_q = round(last_q_score, 1) if last_q_score else "—"
    pnl_emoji = "✅" if pnl >= 0 else "❌"
    streak_emoji = "🔥" if streak > 0 else "❄️" if streak < 0 else "➖"
    chip  = "Wukong 180 ⚛️" if _qcloud_ready else "CPU симулятор"
    # MiroFish stats
    mf_txt = ""
    if MIROFISH_ENABLED:
        mf_txt = f"\n🐟 MiroFish: <code>{_mirofish_stats['calls']}</code> calls · avg <code>{_mirofish_stats['avg_score']:+.1f}</code>"
    # ByBit stats
    bb_txt = ""
    if BYBIT_ENABLED:
        bb_txt = f"\n🟡 ByBit: <code>{_bybit_stats['calls']}</code> calls · X-Arb checks: <code>{_xarb_stats['checks']}</code>"
    kb = {"inline_keyboard": [[{"text": "◀️ Меню", "callback_data": "menu_main"}]]}
    await _tg_send(chat_id,
        f"📊 <b>Статистика трейдинга v10.0</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Закрытых сделок: <code>{total}</code> (открыто: <code>{open_}</code>)\n"
        f"Побед: <code>{wins}</code> / Потерь: <code>{losses}</code>\n"
        f"Win Rate: <code>{wr}%</code>\n"
        f"Итог PnL: {pnl_emoji} <code>${pnl:+.2f}</code>\n"
        f"{streak_emoji} Streak: <code>{streak:+d}</code>\n"
        f"Последний Q-Score: <code>{last_q}</code>\n"
        f"Автопилот: <code>{'ВКЛ' if AUTOPILOT else 'ВЫКЛ'}</code>\n"
        f"Min Q: <code>{MIN_Q_SCORE}</code> · Cooldown: <code>{COOLDOWN}s</code>\n"
        f"Квантовый чип: {chip}"
        f"{mf_txt}{bb_txt}", kb)

async def _tg_reset_stats(chat_id: int):
    """v10.0: Reset all trade stats and trade_log. Starts fresh."""
    global trade_log, _perf_stats
    old_total = _perf_stats.get("total_trades", 0)
    old_pnl = _perf_stats.get("total_pnl", 0.0)
    trade_log.clear()
    _perf_stats.update({
        "total_trades": 0, "wins": 0, "losses": 0, "total_pnl": 0.0,
        "by_strategy": {"B": {"trades": 0, "wins": 0, "pnl": 0.0}, "C": {"trades": 0, "wins": 0, "pnl": 0.0}, "DUAL": {"trades": 0, "wins": 0, "pnl": 0.0}},
        "by_symbol": {},
        "avg_q_score_win": 0.0, "avg_q_score_loss": 0.0,
        "best_hour_utc": None, "worst_hour_utc": None,
        "streak": 0, "max_streak": 0, "max_drawdown": 0.0,
        "updated": datetime.utcnow().isoformat(),
    })
    _save_trades_to_disk()
    _save_perf_stats()
    await _tg_send(chat_id,
        f"🗑 <b>Статистика сброшена</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Удалено: <code>{old_total}</code> сделок (PnL: <code>${old_pnl:+.2f}</code>)\n"
        f"Теперь: 0 сделок, $0.00 PnL\n\n"
        f"✅ Все новые сделки будут считаться с нуля.")
    log_activity(f"[reset] Stats reset by user: was {old_total} trades, ${old_pnl:+.2f}")

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

async def _tg_diag(chat_id: int):
    """v8.3.4: Full diagnostic check of all API connections."""
    await _tg_send(chat_id, "🔍 <i>Running diagnostics...</i>")
    results = []

    # 1. DeepSeek API
    ds_status = "❌ No API key"
    if DEEPSEEK_API_KEY and time.time() < _deepseek_disabled_until:
        remaining = int((_deepseek_disabled_until - time.time()) / 60)
        ds_status = f"⏸ Disabled ({remaining}m left) — using Haiku fallback"
    elif DEEPSEEK_API_KEY:
        try:
            async with aiohttp.ClientSession() as s:
                r = await s.post(
                    f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                    json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5},
                    timeout=aiohttp.ClientTimeout(total=15)
                )
                data = await r.json()
                if r.status == 200:
                    ds_status = f"✅ OK (HTTP 200, model: {data.get('model', '?')})"
                else:
                    err = data.get("error", {}).get("message", str(data)[:100])
                    ds_status = f"⚠️ HTTP {r.status}: {err}"
        except asyncio.TimeoutError:
            ds_status = "❌ Timeout (15s) — API не отвечает"
        except Exception as e:
            ds_status = f"❌ Error: {str(e)[:80]}"
    results.append(f"<b>DeepSeek V3:</b> {ds_status}")

    # 2. Claude API (Haiku)
    cl_status = "❌ No API key"
    if ANTHROPIC_API_KEY:
        try:
            async with aiohttp.ClientSession() as s:
                r = await s.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json={"model": "claude-haiku-4-5-20251001", "max_tokens": 5, "messages": [{"role": "user", "content": "ping"}]},
                    timeout=aiohttp.ClientTimeout(total=10)
                )
                data = await r.json()
                if r.status == 200:
                    cl_status = f"✅ OK (Haiku)"
                else:
                    err = data.get("error", {}).get("message", str(data)[:100])
                    cl_status = f"⚠️ HTTP {r.status}: {err}"
        except Exception as e:
            cl_status = f"❌ Error: {str(e)[:80]}"
    results.append(f"<b>Claude API:</b> {cl_status}")

    # 3. KuCoin Spot
    try:
        bal = await get_balance()
        if bal.get("success"):
            results.append(f"<b>KuCoin Spot:</b> ✅ OK (${bal.get('total_usdt', 0):.2f} USDT)")
        else:
            results.append(f"<b>KuCoin Spot:</b> ⚠️ {bal.get('error', 'unknown')}")
    except Exception as e:
        results.append(f"<b>KuCoin Spot:</b> ❌ {str(e)[:80]}")

    # 4. WebSocket
    results.append(f"<b>WebSocket:</b> {'✅ Connected' if _ws_connected else '❌ Disconnected'} ({len(_ws_prices)} prices, {_ws_reconnects} reconnects)")

    # 5. PostgreSQL
    pg_ok = db.is_ready() if hasattr(db, 'is_ready') else False
    results.append(f"<b>PostgreSQL:</b> {'✅ Connected' if pg_ok else '❌ Disconnected'}")

    # 6. Arb status
    active_tri = sum(1 for _, _, c, _ in ARB_TRIANGLES if c not in _arb_dead_pairs)
    results.append(f"<b>Arbitrage:</b> {active_tri}/{len(ARB_TRIANGLES)} active, {_arb_stats.get('total', 0)} attempts, PnL ${_arb_stats.get('total_pnl', 0):.4f}")

    # 7. Performance
    wr = _perf_stats["wins"] / max(1, _perf_stats["total_trades"]) * 100
    results.append(f"<b>Performance:</b> {_perf_stats['total_trades']} trades, WR {wr:.1f}%, PnL ${_perf_stats['total_pnl']:.2f}, streak {_perf_stats['streak']}")

    # 8. AI call stats
    results.append(f"<b>AI Calls:</b> DS={_ai_call_stats['deepseek']} H={_ai_call_stats['haiku']} O={_ai_call_stats['opus']} err={_ai_call_stats['errors']}")

    # 9. ByBit
    if BYBIT_ENABLED:
        try:
            bb_bal = await bybit_get_balance()
            if bb_bal["success"]:
                results.append(f"<b>🟡 ByBit:</b> ✅ Connected (${bb_bal['total_usdt']:.2f} USDT) | calls={_bybit_stats['calls']} err={_bybit_stats['errors']}")
            else:
                results.append(f"<b>🟡 ByBit:</b> ⚠️ {bb_bal.get('error', 'unknown')}")
        except Exception as e:
            results.append(f"<b>🟡 ByBit:</b> ❌ {str(e)[:80]}")
    else:
        results.append(f"<b>🟡 ByBit:</b> ❌ Not configured")

    # 10. Cross-Exchange Arb
    results.append(f"<b>🔀 X-Arb:</b> {'✅' if XARB_ENABLED and BYBIT_ENABLED else '❌'} checks={_xarb_stats['checks']} opps={_xarb_stats['opportunities']} best={_xarb_stats['best_spread']*100:.4f}%")

    # 11. MiroFish Lite v9.1
    mf_en = "✅ Enabled" if MIROFISH_ENABLED else "❌ Disabled"
    mf_calls = _mirofish_stats['calls']
    mf_cache = _mirofish_stats['cache_hits']
    mf_avg = _mirofish_stats['avg_score']
    mf_mem = sum(len(v) for v in _mirofish_memory.values())
    mf_last = ""
    if _mirofish_stats['last_call'] > 0:
        ago = int(time.time() - _mirofish_stats['last_call'])
        mf_last = f", last {ago}s ago"
    results.append(f"<b>🐟 MiroFish v2:</b> {mf_en} | agents={len(MIROFISH_PERSONAS)} calls={mf_calls} cache={mf_cache} avg={mf_avg:+.1f} mem={mf_mem}{mf_last}")

    # 12. v9.2: Macro + Whale + Copy-Trading
    macro_ok = "✅" if _macro_cache.get("success") else "❌"
    macro_age = int(time.time() - _macro_cache_ts) if _macro_cache_ts else 0
    results.append(f"<b>🌍 Macro:</b> {macro_ok} BTC dom={_macro_cache.get('btc_dominance','?')}% MCap=${_macro_cache.get('total_mcap','?')}B age={macro_age}s")

    whale_ok = "✅" if _whale_alert_cache.get("success") else "❌"
    whale_sig = _whale_alert_cache.get("signal", "?")
    results.append(f"<b>🐋 Whales:</b> {whale_ok} signal={whale_sig} txs={_whale_alert_cache.get('whale_txs',0)}")

    ct_ok = "✅" if _copytrade_cache.get("success") else "❌"
    ct_traders = len(_copytrade_cache.get("traders", []))
    btc_bias = _copytrade_cache.get("consensus", {}).get("BTC", {}).get("bias", "?")
    results.append(f"<b>📋 CopyTrade:</b> {ct_ok} traders={ct_traders} BTC bias={btc_bias}")

    # 13. v10.0: Advanced TA (pandas-ta)
    ta_status = "✅ Available" if _TA_AVAILABLE else "❌ Not installed"
    results.append(f"<b>📐 Advanced TA:</b> {ta_status} (MACD, BB, Stoch, ADX, OBV)")

    # 14. v10.0: LunarCrush
    lc_ok = "✅" if _lunarcrush_cache else "❌ No data"
    lc_age = int(time.time() - _lunarcrush_ts) if _lunarcrush_ts else 0
    lc_coins = len(_lunarcrush_cache.get("coins", {})) if _lunarcrush_cache else 0
    results.append(f"<b>🌙 LunarCrush:</b> {lc_ok} coins={lc_coins} age={lc_age}s")

    # 15. v10.0: Reddit Sentiment
    rd_ok = "✅" if _reddit_cache else "❌ No data"
    rd_age = int(time.time() - _reddit_ts) if _reddit_ts else 0
    results.append(f"<b>🔴 Reddit:</b> {rd_ok} age={rd_age}s")

    # 16. v10.0: Self-Learning v2
    sl_avoid = len(_learning_insights.get("avoid_symbols", []))
    sl_best_fg = _learning_insights.get("best_fg_range", "?")
    sl_best_hr = _learning_insights.get("best_hour", "?")
    sl_opt_q = _learning_insights.get("optimal_q", "?")
    results.append(f"<b>🧠 Self-Learn:</b> avoid={sl_avoid} best_fg={sl_best_fg} best_hr={sl_best_hr} opt_q={sl_opt_q}")

    # 17. v10.0: Security
    results.append(f"<b>🔒 Security:</b> Auth=✅ InputValidation=✅ RateLimit=func")

    text = "🔬 <b>QuantumTrade Diagnostics v10.0</b>\n" + "━" * 30 + "\n\n" + "\n\n".join(results)
    await _tg_send(chat_id, text)


async def _tg_mirofish(chat_id: int, raw: str):
    """v9.0: Manual MiroFish sentiment check. Usage: /mirofish BTC-USDT"""
    parts = raw.split()
    symbol = parts[1].upper() if len(parts) > 1 else "BTC-USDT"
    if not symbol.endswith("-USDT"):
        symbol = f"{symbol}-USDT"

    await _tg_send(chat_id, f"🐟 <i>MiroFish анализирует {symbol}...</i>")

    # Get current market data for the symbol
    price = _ws_prices.get(symbol.replace("-", "/"), {}).get("price")
    if not price:
        try:
            async with aiohttp.ClientSession() as s:
                r = await s.get(f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={symbol}",
                                timeout=aiohttp.ClientTimeout(total=5))
                d = await r.json()
                price = float(d["data"]["price"])
        except Exception:
            await _tg_send(chat_id, f"❌ Не удалось получить цену {symbol}")
            return

    # Get F&G
    fg_val = 50
    try:
        fg = await get_fear_greed()
        if fg.get("success"):
            fg_val = fg.get("value", 50)
    except Exception:
        pass

    result = await mirofish_simulate(symbol, price, 75, fg_val, "manual_check", rsi=50,
                                      context="manual /mirofish command")

    if result.get("error"):
        await _tg_send(chat_id, f"❌ MiroFish ошибка: {result['error']}")
        return

    # Format agent votes
    agent_lines = []
    for a in result.get("agents", []):
        vote = a.get("vote", "?").upper()
        emoji = "🟢" if vote == "BUY" else "🔴" if vote == "SELL" else "⚪"
        name = a.get("id", "?")
        reason = a.get("reason", "")[:60]
        agent_lines.append(f"  {emoji} <b>{name}</b>: {vote} — {reason}")

    dir_emoji = "🟢" if result["direction"] == "BUY" else "🔴" if result["direction"] == "SELL" else "⚪"
    cached_txt = " (кэш)" if result.get("cached") else ""

    # v9.1: Historical trend from memory
    mem = _mirofish_memory.get(symbol, [])
    mem_txt = ""
    if len(mem) >= 2:
        prev_scores = [m["score"] for m in mem[-5:]]
        trend = "📈 бычий" if sum(prev_scores) > 50 else "📉 медвежий" if sum(prev_scores) < -50 else "↔️ смешанный"
        mem_txt = f"\n🧠 Тренд ({len(mem)} анализов): {trend} [{', '.join(f'{s:+d}' for s in prev_scores)}]"

    text = (
        f"🐟 <b>MiroFish v2 — {symbol}</b>{cached_txt}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Цена: <code>${price:,.2f}</code> | F&G: <code>{fg_val}</code>\n"
        f"{dir_emoji} Решение: <b>{result['direction']}</b> (score: <code>{result['score']:+d}</code>)\n"
        f"📊 Уверенность: <code>{result['confidence']}%</code>\n"
        f"🗳 Голоса: 🟢{result['buy']} 🔴{result['sell']} ⚪{result['hold']}{mem_txt}\n\n"
        f"<b>Агенты ({len(result.get('agents', []))}):</b>\n" + "\n".join(agent_lines) + "\n\n"
        f"<i>Model: {result.get('model', '?')} | Calls: {_mirofish_stats['calls']}</i>"
    )
    # Telegram 4096 char limit
    if len(text) > 4000:
        mid = text.find("<b>Агенты")
        if mid > 0:
            await _tg_send(chat_id, text[:mid])
            await _tg_send(chat_id, text[mid:])
        else:
            await _tg_send(chat_id, text[:4000])
    else:
        await _tg_send(chat_id, text)


async def _tg_analyze(chat_id: int):
    """v9.1: Deep trade pattern analysis — finds what works and what doesn't."""
    await _tg_send(chat_id, "🔬 <i>Анализирую все закрытые сделки...</i>")

    data = await db.get_deep_analytics()
    if not data:
        await _tg_send(chat_id, "❌ Нет данных для анализа (PostgreSQL не подключена или нет закрытых сделок)")
        return

    DOW_NAMES = ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"]

    # ── Part 1: Symbol Performance ──
    sym_lines = []
    for s in data.get("by_symbol", [])[:10]:
        wr = round(s["wins"] / s["total"] * 100) if s["total"] else 0
        emoji = "🟢" if s["total_pnl"] > 0 else "🔴"
        sym_lines.append(
            f"  {emoji} <b>{s['symbol']}</b>: {wr}% WR ({s['wins']}/{s['total']}) "
            f"PnL: <code>${s['total_pnl']}</code> avg: ${s['avg_pnl']}"
        )

    # ── Part 2: Best Hours ──
    hour_lines = []
    for h in data.get("by_hour", [])[:6]:
        wr = round(h["wins"] / h["total"] * 100) if h["total"] else 0
        emoji = "🟢" if h["pnl"] > 0 else "🔴"
        hour_lines.append(f"  {emoji} {h['hour']:02d}:00 UTC: {wr}% WR ({h['total']} сд.) PnL: ${h['pnl']}")

    # ── Part 3: Q-Score Ranges ──
    q_lines = []
    for q in data.get("q_ranges", []):
        wr = round(q["wins"] / q["total"] * 100) if q["total"] else 0
        emoji = "🟢" if q["pnl"] > 0 else "🔴"
        q_lines.append(f"  {emoji} Q {q['q_range']}: {wr}% WR ({q['total']} сд.) avg: ${q['avg_pnl']}")

    # ── Part 4: Patterns ──
    pat_lines = []
    for p in data.get("by_pattern", [])[:6]:
        wr = round(p["wins"] / p["total"] * 100) if p["total"] else 0
        emoji = "🟢" if p["pnl"] > 0 else "🔴"
        pat_lines.append(f"  {emoji} {p['pattern']}: {wr}% WR ({p['total']} сд.) PnL: ${p['pnl']}")

    # ── Part 5: Day of Week ──
    dow_lines = []
    for d in data.get("by_weekday", []):
        wr = round(d["wins"] / d["total"] * 100) if d["total"] else 0
        emoji = "🟢" if d["pnl"] > 0 else "🔴"
        dow_lines.append(f"  {emoji} {DOW_NAMES[d['dow']]}: {wr}% ({d['total']} сд.) ${d['pnl']}")

    # ── Part 6: Duration Buckets ──
    dur_lines = []
    for dd in data.get("by_duration", []):
        wr = round(dd["wins"] / dd["total"] * 100) if dd["total"] else 0
        emoji = "🟢" if dd["pnl"] > 0 else "🔴"
        dur_lines.append(f"  {emoji} {dd['duration_bucket']}: {wr}% WR ({dd['total']} сд.) ${dd['pnl']}")

    # ── Part 7: Best/Worst 5 ──
    best_lines = []
    for b in data.get("best5", []):
        best_lines.append(f"  🏆 {b['symbol']} +${b['pnl_usdt']:.2f} Q:{b['q_score']:.0f} @{b['hour']}:00")
    worst_lines = []
    for w in data.get("worst5", []):
        worst_lines.append(f"  💀 {w['symbol']} ${w['pnl_usdt']:.2f} Q:{w['q_score']:.0f} @{w['hour']}:00")

    # ── Part 8: Strategy ──
    strat_lines = []
    for st in data.get("by_strategy", []):
        wr = round(st["wins"] / st["total"] * 100) if st["total"] else 0
        strat_lines.append(f"  {'🟢' if st['pnl'] > 0 else '🔴'} {st['strategy']}: {wr}% WR ({st['total']} сд.) PnL: ${st['pnl']}")

    # ── Part 9: Account type ──
    acc_lines = []
    for a in data.get("by_account", []):
        wr = round(a["wins"] / a["total"] * 100) if a["total"] else 0
        acc_lines.append(f"  {a['account']}: {wr}% WR ({a['total']} сд.) PnL: ${a['pnl']}")

    text = (
        f"🔬 <b>DEEP TRADE ANALYSIS</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"

        f"📊 <b>По символам (Top 10):</b>\n" + "\n".join(sym_lines) + "\n\n"

        f"⏰ <b>Лучшие часы (UTC):</b>\n" + "\n".join(hour_lines) + "\n\n"

        f"🎯 <b>Q-Score диапазоны:</b>\n" + "\n".join(q_lines) + "\n\n"

        f"🔮 <b>Паттерны Vision:</b>\n" + "\n".join(pat_lines) + "\n\n"

        f"📅 <b>Дни недели:</b>\n" + "\n".join(dow_lines) + "\n\n"

        f"⏱ <b>Длительность сделки:</b>\n" + "\n".join(dur_lines) + "\n\n"

        f"🏆 <b>Лучшие 5 сделок:</b>\n" + "\n".join(best_lines) + "\n\n"
        f"💀 <b>Худшие 5 сделок:</b>\n" + "\n".join(worst_lines) + "\n\n"

        f"📋 <b>Стратегии:</b>\n" + "\n".join(strat_lines) + "\n\n"
        f"💼 <b>Тип аккаунта:</b>\n" + "\n".join(acc_lines)
    )

    # Telegram limit 4096 chars — split if needed
    if len(text) > 4000:
        mid = text.find("🏆 <b>Лучшие")
        if mid > 0:
            await _tg_send(chat_id, text[:mid])
            await _tg_send(chat_id, text[mid:])
        else:
            await _tg_send(chat_id, text[:4000])
            await _tg_send(chat_id, text[4000:])
    else:
        await _tg_send(chat_id, text)


async def _tg_macro(chat_id: int):
    """v9.2: Show macro market context — BTC dominance, MCap, trends, whale activity."""
    await _tg_send(chat_id, "🌍 <i>Собираю макро-данные...</i>")

    # Fetch fresh data
    macro, whales, fg_trend = await asyncio.gather(
        fetch_macro_context(),
        fetch_whale_movements(),
        get_fg_trend(),
        return_exceptions=True
    )

    parts = ["🌍 <b>MACRO DASHBOARD v9.2</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"]

    # Macro
    if isinstance(macro, dict) and macro.get("success"):
        parts.append(
            f"📊 <b>Рынок:</b>\n"
            f"  BTC Dominance: <code>{macro.get('btc_dominance',0)}%</code>\n"
            f"  ETH Dominance: <code>{macro.get('eth_dominance',0)}%</code>\n"
            f"  Total MCap: <code>${macro.get('total_mcap',0)}B</code> ({macro.get('mcap_change_24h',0):+.1f}% 24h)\n"
            f"  ETH/BTC: <code>{macro.get('eth_btc_ratio',0)}</code>\n"
            f"  BTC: <code>${macro.get('btc_usd',0):,.0f}</code> | ETH: <code>${macro.get('eth_usd',0):,.0f}</code>"
        )
        trending = macro.get("trending", [])
        if trending:
            trend_txt = ", ".join(f"{t['symbol']}(#{t.get('rank','?')})" for t in trending[:5])
            parts.append(f"\n🔥 <b>Trending:</b> {trend_txt}")

    # F&G Trend
    if isinstance(fg_trend, dict) and fg_trend.get("trend") != "insufficient_data":
        emoji = "📈" if fg_trend["trend"] == "rising" else "📉" if fg_trend["trend"] == "falling" else "↔️"
        parts.append(
            f"\n\n😱 <b>Fear & Greed тренд (3д):</b>\n"
            f"  {emoji} {fg_trend['trend'].upper()} | Сейчас: <code>{fg_trend.get('latest',0)}</code> "
            f"→ Было: <code>{fg_trend.get('oldest',0)}</code> (Δ{fg_trend.get('change',0):+d})\n"
            f"  Значения: {fg_trend.get('values',[])} "
        )

    # Whale activity
    if isinstance(whales, dict) and whales.get("success"):
        signal_emoji = "🔴" if whales["signal"] == "heavy" else "🟡" if whales["signal"] == "moderate" else "🟢"
        parts.append(
            f"\n\n🐋 <b>Whale Activity:</b>\n"
            f"  {signal_emoji} Signal: <code>{whales['signal']}</code>\n"
            f"  Крупных транзакций: <code>{whales['whale_txs']}</code>\n"
            f"  Общий объём: <code>${whales.get('total_whale_usd',0):,.0f}</code>"
        )
        mempool = [m for m in whales.get("movements", []) if m.get("type") == "mempool_stats"]
        if mempool:
            mp = mempool[0]
            parts.append(f"\n  Mempool: <code>{mp.get('mempool_txs',0):,}</code> txs, fees: ${mp.get('mempool_fees_usd',0):,.0f}")

    # Copy-trading consensus
    ct = _copytrade_cache
    if ct.get("success"):
        parts.append(f"\n\n📋 <b>Copy-Trading (ByBit Top Traders):</b>")
        for coin, data in ct.get("consensus", {}).items():
            bias_emoji = "🟢" if data["bias"] == "LONG" else "🔴" if data["bias"] == "SHORT" else "⚪"
            parts.append(
                f"\n  {bias_emoji} {coin}: Long <code>{data['long_pct']}%</code> / "
                f"Short <code>{data['short_pct']}%</code> → <b>{data['bias']}</b>"
            )
        traders = ct.get("traders", [])
        if traders:
            parts.append(f"\n  Топ трейдеры ({len(traders)}):")
            for t in traders[:5]:
                parts.append(
                    f"\n    {'🏆' if t.get('roi',0)>100 else '👤'} {t['name']}: "
                    f"ROI <code>{t['roi']}%</code> WR <code>{t['win_rate']}%</code> "
                    f"({t['followers']} followers)"
                )

    # F&G correlation with our trades
    fg_corr = await db.get_fg_trade_correlation()
    if fg_corr:
        parts.append(f"\n\n🎯 <b>F&G → Наш WR (корреляция):</b>")
        for fc in fg_corr:
            if fc["total"] > 0:
                wr = round(fc["wins"] / fc["total"] * 100)
                emoji = "🟢" if fc["pnl"] > 0 else "🔴"
                parts.append(
                    f"\n  {emoji} {fc['fg_zone']}: {wr}% WR ({fc['total']} сделок) PnL: ${fc['pnl']}"
                )

    text = "\n".join(parts)
    if len(text) > 4000:
        mid = text.find("📋 <b>Copy-Trading")
        if mid > 0:
            await _tg_send(chat_id, text[:mid])
            await _tg_send(chat_id, text[mid:])
        else:
            await _tg_send(chat_id, text[:4000])
            await _tg_send(chat_id, text[4000:])
    else:
        await _tg_send(chat_id, text)


async def _tg_sentiment(chat_id: int, raw: str):
    """v10.0: Unified social + whale + macro intelligence for a symbol."""
    parts = raw.split()
    symbol = parts[1].upper() if len(parts) > 1 else "BTC"
    await _tg_send(chat_id, f"🧠 <i>Собираю intelligence для {symbol}...</i>")

    # Parallel fetch all sources
    lc_data, reddit_data = await asyncio.gather(
        fetch_lunarcrush_sentiment([symbol]),
        fetch_reddit_sentiment(),
        return_exceptions=True
    )

    text_parts = [f"🧠 <b>SENTIMENT INTELLIGENCE — {symbol}</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"]

    # LunarCrush
    if isinstance(lc_data, dict) and lc_data.get("success"):
        lc = lc_data.get("coins", {}).get(symbol, {})
        if lc:
            gs = lc.get("galaxy_score", 0)
            gs_emoji = "🟢" if gs > 70 else "🔴" if gs < 40 else "🟡"
            text_parts.append(
                f"🌙 <b>LunarCrush:</b>\n"
                f"  {gs_emoji} Galaxy Score: <code>{gs}/100</code>\n"
                f"  📊 Sentiment: <code>{lc.get('sentiment',0)}</code>\n"
                f"  📢 Social Volume: <code>{lc.get('social_volume',0):,}</code>\n"
                f"  💰 Price 24h: <code>{lc.get('percent_change_24h',0):+.1f}%</code>"
            )

    # Reddit
    if isinstance(reddit_data, dict) and reddit_data.get("success"):
        rs = reddit_data.get("sentiment_score", 0)
        rs_emoji = "🟢" if rs > 20 else "🔴" if rs < -20 else "🟡"
        text_parts.append(
            f"\n\n📱 <b>Reddit ({reddit_data.get('total_posts',0)} постов):</b>\n"
            f"  {rs_emoji} Sentiment: <code>{rs:+.1f}</code>\n"
            f"  🟢 Bullish: <code>{reddit_data.get('bullish',0)}</code> | 🔴 Bearish: <code>{reddit_data.get('bearish',0)}</code>"
        )
        # Top trending posts
        top_posts = sorted(reddit_data.get("posts", []), key=lambda x: x.get("score", 0), reverse=True)[:3]
        if top_posts:
            text_parts.append("\n  <b>Топ посты:</b>")
            for p in top_posts:
                text_parts.append(f"\n    ↗ [{p.get('score',0)}⬆] {p.get('title','')[:50]}")

    # Whale activity
    wc = _whale_alert_cache
    if wc.get("success"):
        text_parts.append(
            f"\n\n🐋 <b>Whale Activity:</b> {wc.get('signal','?')} "
            f"({wc.get('whale_txs',0)} txs, ${wc.get('total_whale_usd',0):,.0f})"
        )

    # Copy-trading
    ct = _copytrade_cache
    if ct.get("success"):
        cons = ct.get("consensus", {}).get(symbol, ct.get("consensus", {}).get("BTC", {}))
        if cons:
            text_parts.append(
                f"\n\n📋 <b>Copy-Trading:</b> Long <code>{cons.get('long_pct',0)}%</code> / "
                f"Short <code>{cons.get('short_pct',0)}%</code> → <b>{cons.get('bias','?')}</b>"
            )

    # Self-learning insights
    li = _learning_insights
    if li.get("last_update"):
        text_parts.append(
            f"\n\n🎓 <b>Self-Learning:</b>\n"
            f"  Best F&G zone: <code>{li.get('best_fg_range','?')}</code>\n"
            f"  Best hour: <code>{li.get('best_hour','?')}:00 UTC</code>\n"
            f"  Avoid: <code>{', '.join(li.get('avoid_symbols', [])) or 'none'}</code>"
        )

    text = "\n".join(text_parts)
    if len(text) > 4000:
        await _tg_send(chat_id, text[:4000])
        await _tg_send(chat_id, text[4000:])
    else:
        await _tg_send(chat_id, text)


async def _tg_bybit(chat_id: int):
    """v9.0: ByBit account status and balance."""
    if not BYBIT_ENABLED:
        await _tg_send(chat_id, "❌ ByBit не подключен. Добавь BYBIT_API_KEY и BYBIT_API_SECRET в Railway Variables.")
        return
    await _tg_send(chat_id, "🔄 <i>Проверяю ByBit...</i>")
    bal = await bybit_get_balance()
    if not bal["success"]:
        await _tg_send(chat_id, f"❌ ByBit ошибка: {bal.get('error', '?')}")
        return

    coins_lines = []
    for cur, info in sorted(bal.get("balances", {}).items(), key=lambda x: -x[1]["usd_value"]):
        coins_lines.append(f"  {cur}: <code>{info['equity']:.4f}</code> (${info['usd_value']:.2f})")

    # Get funding rates
    rates_txt = ""
    try:
        rates = await bybit_get_funding_rates_all()
        if rates:
            rate_lines = [f"  {sym}: <code>{rate*100:.4f}%</code>" for sym, rate in rates.items()]
            rates_txt = "\n\n<b>📊 Funding Rates:</b>\n" + "\n".join(rate_lines)
    except Exception:
        pass

    text = (
        f"🟡 <b>ByBit — Статус</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 USDT: <code>${bal['total_usdt']:,.2f}</code>\n"
        f"\n<b>Балансы:</b>\n" + ("\n".join(coins_lines) if coins_lines else "  (пусто)") +
        rates_txt +
        f"\n\n<b>📈 API Stats:</b> calls={_bybit_stats['calls']} err={_bybit_stats['errors']}"
    )
    await _tg_send(chat_id, text)


async def _tg_earn(chat_id: int):
    """v10.1: Earn Engine — show status, APR, positions."""
    if not EARN_ENABLED:
        await _tg_send(chat_id, "❌ <b>Earn Engine выключен</b>\nВключи через Railway: EARN_ENABLED=true")
        return

    await _tg_send(chat_id, "🏦 <i>Проверяю Earn позиции...</i>")

    # Get best rate
    best = await earn_get_best_rate("USDT")

    # Get current positions from exchanges
    kc_holds = []
    bb_holds = []
    try:
        kc_holds = await kucoin_earn_get_hold_assets("USDT")
    except Exception:
        pass
    try:
        bb_holds = await bybit_earn_get_positions("USDT")
    except Exception:
        pass

    total_kc = sum(float(h.get("holdAmount", h.get("amount", 0))) for h in kc_holds)
    total_bb = sum(float(h.get("amount", h.get("holdAmount", 0))) for h in bb_holds)
    total_earn = total_kc + total_bb

    # Calculate daily/monthly estimated earnings
    apr = best["apr"] if best["apr"] > 0 else 3.0  # default 3% if unknown
    daily_est = round(total_earn * (apr / 100) / 365, 4)
    monthly_est = round(daily_est * 30, 4)

    pos_lines = []
    for h in kc_holds:
        amt = float(h.get("holdAmount", h.get("amount", 0)))
        if amt > 0:
            pos_lines.append(f"  🟢 KuCoin: <code>${amt:.2f}</code> USDT")
    for h in bb_holds:
        amt = float(h.get("amount", h.get("holdAmount", 0)))
        if amt > 0:
            pos_lines.append(f"  🟣 ByBit: <code>${amt:.2f}</code> USDT")

    text = (
        f"🏦 <b>Earn Engine v10.1</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Лучшая ставка:</b> {best['exchange']} — <code>{best['apr']}%</code> APR\n"
        f"<b>Продукт:</b> {best.get('product_name', '?')}\n\n"
        f"<b>Текущие позиции:</b>\n"
    )
    if pos_lines:
        text += "\n".join(pos_lines)
    else:
        text += "  <i>Нет активных Earn позиций</i>"

    text += (
        f"\n\n<b>Всего в Earn:</b> <code>${total_earn:.2f}</code>\n"
        f"<b>Доход/день:</b> ~<code>${daily_est:.4f}</code>\n"
        f"<b>Доход/месяц:</b> ~<code>${monthly_est:.4f}</code>\n\n"
        f"<b>Статистика:</b>\n"
        f"  Подписок: <code>{_earn_stats['subscriptions']}</code> | "
        f"Погашений: <code>{_earn_stats['redemptions']}</code>\n"
        f"  Всего размещено: <code>${_earn_stats['total_subscribed']:.2f}</code>\n"
        f"  Всего погашено: <code>${_earn_stats['total_redeemed']:.2f}</code>\n"
        f"  Ошибок: <code>{_earn_stats['errors']}</code>\n\n"
        f"💡 <i>Auto-Earn: USDT после продажи → Flexible Savings\n"
        f"Auto-Redeem: перед покупкой → погашение из Savings</i>"
    )
    await _tg_send(chat_id, text)


async def _tg_xarb(chat_id: int):
    """v9.0: Cross-exchange arbitrage status."""
    if not BYBIT_ENABLED:
        await _tg_send(chat_id, "❌ ByBit не подключен — кросс-арбитраж недоступен.")
        return

    await _tg_send(chat_id, "🔄 <i>Сканирую спреды KuCoin ↔ ByBit...</i>")
    opps = await check_cross_exchange_arb()

    # Current spreads for all symbols
    spread_lines = []
    for symbol in XARB_SYMBOLS:
        kc = await get_ticker(symbol)
        bb = await bybit_get_ticker(symbol)
        if kc > 0 and bb > 0:
            spread = abs(kc - bb) / min(kc, bb) * 100
            emoji = "🟢" if spread >= XARB_MIN_SPREAD * 100 else "⚪"
            spread_lines.append(f"  {emoji} {symbol}: KC=<code>${kc:,.2f}</code> BB=<code>${bb:,.2f}</code> → <code>{spread:.4f}%</code>")

    recent = _xarb_history[-5:] if _xarb_history else []
    hist_lines = []
    for h in reversed(recent):
        ago = int(time.time() - h["ts"])
        hist_lines.append(f"  {h['symbol']}: {h['spread_pct']:.3f}% ({ago}s ago)")

    text = (
        f"🔀 <b>Cross-Exchange Arbitrage</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Текущие спреды:</b>\n" + "\n".join(spread_lines) +
        f"\n\nMin spread: <code>{XARB_MIN_SPREAD*100:.2f}%</code>\n"
        f"Checks: <code>{_xarb_stats['checks']}</code> | "
        f"Opportunities: <code>{_xarb_stats['opportunities']}</code> | "
        f"Best: <code>{_xarb_stats['best_spread']*100:.4f}%</code>\n"
    )
    if hist_lines:
        text += f"\n<b>Последние возможности:</b>\n" + "\n".join(hist_lines)
    else:
        text += "\n<i>Пока нет возможностей выше порога</i>"

    await _tg_send(chat_id, text)


async def _tg_settings(chat_id: int):
    """Карточка настроек с рабочими кнопками."""
    ap_icon  = "🟢 ВКЛ" if AUTOPILOT        else "🔴 ВЫКЛ"
    arb_icon = "🟢 ВКЛ" if ARB_EXEC_ENABLED  else "🔴 ВЫКЛ"
    kb = {"inline_keyboard": [
        # ── Переключатели ──────────────────────────────────────────────────
        [{"text": f"🤖 Торговля: {ap_icon}",   "callback_data": "toggle_autopilot"},
         {"text": f"⚡ Арбитраж: {arb_icon}",  "callback_data": "toggle_arb"}],
        # ── Min Q-Score ────────────────────────────────────────────────────
        [{"text": "🟢 Min Q: 62 (страх рынка)", "callback_data": "set_minq_62"},
         {"text": "📉 Min Q: 65 (мягкий)",      "callback_data": "set_minq_65"}],
        [{"text": "📊 Min Q: 70 (умеренный)",   "callback_data": "set_minq_70"},
         {"text": "📊 Min Q: 78 (стандарт)",    "callback_data": "set_minq_78"}],
        [{"text": "📈 Min Q: 82 (строгий)",     "callback_data": "set_minq_82"},
         {"text": f"✅ Текущий: {MIN_Q_SCORE}", "callback_data": "set_minq_cur"}],
        # ── Cooldown ───────────────────────────────────────────────────────
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
        f"🤖 Торговля: <code>{'ВКЛ' if AUTOPILOT else 'ВЫКЛ'}</code>\n"
        f"⚡ Арбитраж: <code>{'ВКЛ' if ARB_EXEC_ENABLED else 'ВЫКЛ'}</code>\n\n"
        f"🧠 <b>AI модели:</b>\n"
        f"  Vision: <code>{AI_TIER_VISION}</code> | Chat: <code>{AI_TIER_CHAT}</code> | Critical: <code>{AI_TIER_CRITICAL}</code>\n"
        f"  DeepSeek: {'✅' if DEEPSEEK_API_KEY else '❌'} | Claude: {'✅' if ANTHROPIC_API_KEY else '❌'}\n"
        f"  Вызовы: DS={_ai_call_stats['deepseek']} H={_ai_call_stats['haiku']} S={_ai_call_stats['sonnet']} O={_ai_call_stats['opus']} err={_ai_call_stats['errors']}\n\n"
        f"<i>Нажми кнопку переключателя выше чтобы вкл/выкл</i>", kb)


async def _tg_arb(chat_id: int):
    """Telegram: arbitrage monitor status."""
    now = time.time()
    lines = []
    active_count = 0
    dead_count = len(_arb_dead_pairs)
    for _, _, cross_sym, path in ARB_TRIANGLES:
        if cross_sym in _arb_dead_pairs:
            continue  # don't show dead pairs
        active_count += 1
        last    = ARB_COOLDOWNS.get(path, 0)
        elapsed = now - last
        status  = "\U0001f50d" if elapsed > ARB_COOLDOWN_SEC else f"\u23f3 {int(ARB_COOLDOWN_SEC - elapsed)}s"
        lines.append(f"  {status} {path}")
    ap_status = "\u0412\u041a\u041b" if AUTOPILOT else "\u0412\u042b\u041a\u041b (\u0432\u043a\u043b\u044e\u0447\u0438 \u0430\u0432\u0442\u043e\u043f\u0438\u043b\u043e\u0442)"
    body = "\n".join(lines)
    text = (
        f"\u26a1 <b>\u0410\u0440\u0431\u0438\u0442\u0440\u0430\u0436 KuCoin \u2014 \u0421\u0442\u0430\u0442\u0443\u0441</b>\n\n"
        f"\U0001f504 \u041c\u043e\u043d\u0438\u0442\u043e\u0440\u0438\u043d\u0433: <b>{ap_status}</b>\n"
        f"\U0001f4d0 \u041c\u0438\u043d. \u0441\u043f\u0440\u0435\u0434: <code>{ARB_MIN_SPREAD*100:.1f}%</code> (\u043f\u043e\u0441\u043b\u0435 0.3% \u043a\u043e\u043c\u0438\u0441\u0441\u0438\u0439)\n"
        f"\u23f1 Cooldown: <code>{ARB_COOLDOWN_SEC}s</code>\n"
        f"📡 Связки: <code>{active_count}</code> активных" + (f" / <code>{dead_count}</code> отключены" if dead_count else "") + f" (всего {len(ARB_TRIANGLES)})\n"
        f"🔌 WebSocket: <code>{'✅ live' if _ws_connected else '❌ offline'}</code> · Цен: <code>{len(_ws_prices)}</code>\n"
        f"🛡️ Opus Gate: <code>{_opus_gate_stats['approved']}</code>✅ / <code>{_opus_gate_stats['rejected']}</code>❌ из <code>{_opus_gate_stats['asked']}</code>\n\n"
        f"<b>\u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0435 \u0441\u0432\u044f\u0437\u043a\u0438:</b>\n{body}\n\n"
        f"\U0001f4a1 \u0410\u043b\u0435\u0440\u0442 \u043f\u0440\u0438\u0445\u043e\u0434\u0438\u0442 \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438 \u043f\u0440\u0438 \u043e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d\u0438\u0438 \u0432\u043e\u0437\u043c\u043e\u0436\u043d\u043e\u0441\u0442\u0438."
    )
    exec_status = "✅ ВКЛ" if ARB_EXEC_ENABLED else "🔴 ВЫКЛ"
    arb_btn_text = "🔴 Выключить исполнение" if ARB_EXEC_ENABLED else "🟢 Включить исполнение"
    text += (
        f"\n\n💎 <b>Исполнение:</b> {exec_status}\n"
        f"💵 Размер: <code>${ARB_EXEC_USDT:.0f}</code> USDT\n"
        f"📊 Мин. прибыль: <code>{ARB_MIN_PROFIT_PCT}%</code>\n"
        f"📈 Статистика: {_arb_stats['success']}✅ / {_arb_stats['failed']}❌ | PnL: ${_arb_stats['total_pnl']:+.4f}"
    )
    kb = {"inline_keyboard": [
        [{"text": arb_btn_text, "callback_data": "toggle_arb"}],
        [{"text": "◀️ Меню",   "callback_data": "menu_main"}],
    ]}
    await _tg_send(chat_id, text, kb)


async def _tg_sell_all_spot(chat_id: int):
    """v8.3: Sell all spot coins back to USDT."""
    balances = await get_spot_balances()
    if not balances:
        await _tg_send(chat_id, "💰 Нет монет на споте для продажи (только USDT).")
        return
    lines = ["🔄 <b>Продаю все монеты в USDT...</b>\n"]
    total_sold = 0.0
    for symbol, info in balances.items():
        sell_res = await sell_spot_to_usdt(symbol, info["available"])
        if sell_res.get("success"):
            lines.append(f"✅ {info['currency']}: {info['available']:.6f} → ~${info['usdt_value']:.2f}")
            total_sold += info["usdt_value"]
            # Close all open spot trades for this symbol
            for t in trade_log:
                if t.get("status") == "open" and t.get("symbol") == symbol and t.get("account") == "spot":
                    pnl_pct = (info["price"] - t["price"]) / t["price"] if t["side"] == "buy" else 0
                    t["status"] = "closed"
                    t["pnl"] = round(pnl_pct * t["price"] * t["size"], 4)
                    t["close_price"] = info["price"]
                    t["close_reason"] = "manual_sell_all"
            _save_trades_to_disk()
        else:
            lines.append(f"❌ {info['currency']}: {sell_res.get('msg', 'ошибка')}")
    lines.append(f"\n💵 Всего продано: ~${total_sold:.2f}")
    kb = {"inline_keyboard": [[{"text": "◀️ Меню", "callback_data": "menu_main"}]]}
    await _tg_send(chat_id, "\n".join(lines), kb)


async def _tg_spot_status(chat_id: int):
    """v8.3: Show current spot holdings and open spot trades."""
    balances = await get_spot_balances()
    bal = await get_balance()
    usdt = bal.get("total_usdt", 0)
    lines = ["💰 <b>Спот-портфель</b>", "━━━━━━━━━━━━━━━━━━━━━━"]
    lines.append(f"USDT: <code>${usdt:.2f}</code>")
    total = usdt
    for symbol, info in sorted(balances.items()):
        lines.append(f"{info['currency']}: <code>{info['balance']:.6f}</code> ≈ ${info['usdt_value']:.2f}")
        total += info["usdt_value"]
    lines.append(f"\n💎 <b>Всего: ${total:.2f}</b>")
    # Open spot trades
    open_spot = [t for t in trade_log if t.get("status") == "open" and t.get("account") == "spot"]
    if open_spot:
        lines.append(f"\n📊 <b>Открытые спот-сделки ({len(open_spot)}):</b>")
        for t in open_spot[:5]:
            price = balances.get(t["symbol"], {}).get("price", 0)
            pnl_pct = ((price - t["price"]) / t["price"] * 100) if price and t["price"] else 0
            emoji = "📈" if pnl_pct >= 0 else "📉"
            lines.append(f"  {emoji} {t['symbol']} {t['side'].upper()} @ ${t['price']:.4f} → ${price:.4f} ({pnl_pct:+.1f}%)")
    lines.append(f"\n💡 <code>/sell XRP</code> · <code>/sell ETH 50</code> · <code>/sell all</code>\n"
                 f"💡 <code>/buy ETH 30</code> · <code>/buy BTC 50</code>")
    kb = {"inline_keyboard": [[{"text": "◀️ Меню", "callback_data": "menu_main"}]]}
    await _tg_send(chat_id, "\n".join(lines), kb)


async def _tg_universal_sell(chat_id: int, raw: str):
    """v8.3: Universal sell command.
    /sell all              — sell everything to USDT
    /sell XRP              — sell all XRP
    /sell ETH 50           — sell $50 worth of ETH
    /sell ETH 50%          — sell 50% of ETH holdings
    """
    parts = raw.strip().split()
    # /sell (no args) → show help + current balances
    if len(parts) < 2:
        balances = await get_spot_balances()
        if not balances:
            await _tg_send(chat_id, "💰 Нет монет для продажи. Только USDT на споте.")
            return
        lines = ["ℹ️ <b>Формат команды /sell:</b>\n",
                 "<code>/sell all</code> — продать все монеты",
                 "<code>/sell XRP</code> — продать весь XRP",
                 "<code>/sell ETH 50</code> — продать ETH на $50",
                 "<code>/sell ETH 50%</code> — продать 50% ETH\n",
                 "📊 <b>Текущие монеты:</b>"]
        for sym, info in balances.items():
            lines.append(f"  {info['currency']}: {info['balance']:.6f} ≈ ${info['usdt_value']:.2f}")
        await _tg_send(chat_id, "\n".join(lines))
        return

    target = parts[1].upper()

    # /sell all
    if target == "ALL":
        await _tg_sell_all_spot(chat_id)
        return

    # Normalize coin name → pair
    coin = target.replace("-USDT", "").replace("-", "")
    pair = f"{coin}-USDT"
    balances = await get_spot_balances()
    info = balances.get(pair)
    if not info or info["available"] <= 0:
        await _tg_send(chat_id, f"❌ Нет {coin} на споте для продажи.")
        return

    sell_size = info["available"]  # default: sell all
    sell_label = f"весь {coin}"

    # /sell ETH 50 or /sell ETH 50%
    if len(parts) >= 3:
        amount_str = parts[2]
        try:
            if amount_str.endswith("%"):
                pct = float(amount_str[:-1]) / 100.0
                if not 0 < pct <= 1:
                    await _tg_send(chat_id, "❌ Процент должен быть от 1% до 100%")
                    return
                sell_size = round(info["available"] * pct, 8)
                sell_label = f"{amount_str} {coin} ({sell_size:.6f})"
            else:
                usdt_amount = float(amount_str)
                if usdt_amount <= 0:
                    await _tg_send(chat_id, "❌ Сумма должна быть > 0")
                    return
                if usdt_amount >= info["usdt_value"]:
                    sell_label = f"весь {coin} (запрошено ${usdt_amount}, есть ${info['usdt_value']:.2f})"
                else:
                    sell_size = round(usdt_amount / info["price"], 8)
                    sell_label = f"${usdt_amount} {coin} ({sell_size:.6f})"
        except ValueError:
            await _tg_send(chat_id, "❌ Неверная сумма. Примеры: <code>/sell ETH 50</code> или <code>/sell ETH 50%</code>")
            return

    # Execute sell
    result = await sell_spot_to_usdt(pair, sell_size)
    if result.get("success"):
        usdt_received = round(sell_size * info["price"], 2)
        # Close matching open trades
        for t in trade_log:
            if t.get("status") == "open" and t.get("symbol") == pair and t.get("account") == "spot":
                pnl_pct = (info["price"] - t["price"]) / t["price"] if t["side"] == "buy" else 0
                t["status"] = "closed"
                t["pnl"] = round(pnl_pct * t["price"] * t["size"], 4)
                t["close_price"] = info["price"]
                t["close_reason"] = "manual_sell"
        _save_trades_to_disk()
        await _tg_send(chat_id,
            f"✅ <b>Продано: {sell_label}</b>\n"
            f"💵 Получено: ~<code>${usdt_received}</code> USDT\n"
            f"📊 Цена: <code>${info['price']:,.2f}</code>")
    else:
        await _tg_send(chat_id, f"❌ Ошибка продажи {coin}: {result.get('msg', '?')}")


async def _tg_universal_buy(chat_id: int, raw: str):
    """v8.3: Universal buy command.
    /buy ETH 30    — buy $30 worth of ETH
    /buy BTC 50    — buy $50 worth of BTC
    """
    parts = raw.strip().split()
    if len(parts) < 3:
        await _tg_send(chat_id, "ℹ️ <b>Формат:</b>\n<code>/buy ETH 30</code> — купить ETH на $30\n<code>/buy BTC 50</code> — купить BTC на $50")
        return

    coin = parts[1].upper().replace("-USDT", "").replace("-", "")
    pair = f"{coin}-USDT"
    try:
        usdt_amount = float(parts[2])
    except ValueError:
        await _tg_send(chat_id, "❌ Неверная сумма. Пример: <code>/buy ETH 30</code>")
        return

    if usdt_amount < 1:
        await _tg_send(chat_id, "❌ Минимальная сумма: $1")
        return

    # Check USDT balance
    bal = await get_balance()
    usdt_avail = bal.get("total_usdt", 0)
    if usdt_avail < usdt_amount:
        await _tg_send(chat_id, f"❌ Недостаточно USDT: ${usdt_avail:.2f} < ${usdt_amount:.2f}")
        return

    # Get current price
    price = await get_ticker(pair)
    if price <= 0:
        await _tg_send(chat_id, f"❌ Не удалось получить цену {pair}")
        return

    # Buy using funds-based order
    result = await _spot_buy_funds(pair, usdt_amount)
    if _order_ok(result):
        size = round(usdt_amount / price, 8)
        tp = round(price * (1 + TP_PCT), 4)
        sl = round(price * (1 - SL_PCT), 4)
        log_trade(pair, "buy", price, size, tp, sl, 0.75, 70.0, "manual", "spot", "manual")
        await _tg_send(chat_id,
            f"✅ <b>Куплено: {coin} на ${usdt_amount}</b>\n"
            f"📊 Цена: <code>${price:,.2f}</code>\n"
            f"📦 Кол-во: ~<code>{size}</code>\n"
            f"🎯 TP: <code>${tp:,.2f}</code> | 🛑 SL: <code>${sl:,.2f}</code>")
    else:
        await _tg_send(chat_id, f"❌ Ошибка покупки {coin}: {result.get('msg', '?')}")


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
    open_trades = [t for t in trade_log if t.get("status", "") == "open"]
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


# ── v7.2.1: Railway Variables API ───────────────────────────────────────────
async def _update_railway_var(name: str, value: str) -> bool:
    """Persist a variable change to Railway environment via GraphQL API.
    Requires RAILWAY_TOKEN. Project/Environment/Service IDs are auto-injected by Railway."""
    if not RAILWAY_TOKEN:
        return False
    project_id  = os.getenv("RAILWAY_PROJECT_ID", "")
    env_id      = os.getenv("RAILWAY_ENVIRONMENT_ID", "")
    service_id  = os.getenv("RAILWAY_SERVICE_ID", "")
    if not (project_id and env_id and service_id):
        log_activity(f"[railway] Missing IDs — variable {name} changed only in memory")
        return False
    query = """
    mutation variableUpsert($input: VariableUpsertInput!) {
      variableUpsert(input: $input)
    }
    """
    payload = {
        "query": query,
        "variables": {
            "input": {
                "projectId":     project_id,
                "environmentId": env_id,
                "serviceId":     service_id,
                "name":          name,
                "value":         value,
            }
        }
    }
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                "https://backboard.railway.app/graphql/v2",
                json=payload,
                headers={"Authorization": f"Bearer {RAILWAY_TOKEN}", "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10)
            )
            data = await r.json()
            if "errors" in data:
                log_activity(f"[railway] API error for {name}: {data['errors']}")
                return False
            log_activity(f"[railway] Variable {name}={value} persisted to Railway ✅")
            return True
    except Exception as e:
        log_activity(f"[railway] Exception updating {name}: {e}")
        return False


# ── v7.2.0: AI Консультант ──────────────────────────────────────────────────
_ai_pending: dict = {}      # chat_id → {"param": ..., "value": ...}
_ai_history: dict = {}      # chat_id → list of messages

SAFE_PARAMS_TG = {
    "MIN_Q_SCORE":   {"min": 40,  "max": 85,  "desc": "Минимальный Q-Score для входа"},
    "COOLDOWN":      {"min": 120, "max": 1800, "desc": "Кулдаун между сделками (сек)"},
    "RISK_PER_TRADE":{"min": 0.05,"max": 0.30, "desc": "Риск на сделку (доля)"},
    "MAX_LEVERAGE":  {"min": 1,   "max": 15,   "desc": "Максимальное плечо"},
}

async def _tg_ai_ask(chat_id: int, question: str):
    """v7.2.0: AI консультант — отвечает на вопросы и предлагает настройки."""
    global MIN_Q_SCORE, COOLDOWN, RISK_PER_TRADE, MAX_LEVERAGE

    # Обработка подтверждения/отмены
    # v7.2.1: ловим "да" как первое слово (на случай "да, и ещё...")
    q_lower = question.lower().strip()
    first_word = q_lower.split()[0] if q_lower else ""
    is_confirm = first_word in ("да", "yes", "подтвердить", "применить", "ок", "ok", "+")
    is_cancel  = first_word in ("нет", "no", "отмена", "cancel", "-")

    if is_confirm:
        pending = _ai_pending.pop(chat_id, None)
        if not pending:
            await _tg_send(chat_id, "ℹ️ Нет ожидающих изменений.")
            return
        param, val = pending["param"], pending["value"]
        if param == "MIN_Q_SCORE":    MIN_Q_SCORE = int(val)
        elif param == "COOLDOWN":     COOLDOWN = int(val)
        elif param == "RISK_PER_TRADE": globals()["RISK_PER_TRADE"] = float(val)
        elif param == "MAX_LEVERAGE": globals()["MAX_LEVERAGE"] = int(val)
        log_activity(f"[ai_consultant] Applied {param}={val} (via Telegram /ask)")
        # v7.2.1: также сохраняем в Railway Variables для персистентности
        persisted = await _update_railway_var(param, str(int(val) if isinstance(val, float) and val == int(val) else val))
        persist_note = " • сохранено в Railway ♾️" if persisted else " • только в памяти (добавь RAILWAY_TOKEN для персистентности)"
        await _tg_send(chat_id, f"✅ <b>{param}</b> изменён на <b>{val}</b>\nПерезапуск не нужен — применено сразу.{persist_note}")
        return

    if is_cancel:
        _ai_pending.pop(chat_id, None)
        await _tg_send(chat_id, "↩️ Изменение отменено.")
        return

    if not ANTHROPIC_API_KEY and not DEEPSEEK_API_KEY:
        await _tg_send(chat_id, "❌ Нет API ключей (ANTHROPIC/DEEPSEEK) — AI консультант недоступен.")
        return

    # v8.3.4: Send "thinking" indicator immediately so user knows bot received the command
    await _tg_send(chat_id, "🤔 <i>Думаю...</i>")
    log_activity(f"[/ask] question from {chat_id}: {question[:80]}")

    # v8.3.4c: Use _perf_stats for accurate closed-trade stats (not trade_log which includes open)
    total = _perf_stats.get("total_trades", 0)
    wins = _perf_stats.get("wins", 0)
    win_rate = (wins / total * 100) if total else 0
    total_pnl = _perf_stats.get("total_pnl", 0.0)
    chip = "Wukong_180" if _qcloud_ready else "CPU_simulator"

    # v8.3.4: Include detailed perf stats for AI to answer stats questions
    streak = _perf_stats.get("streak", 0)
    max_dd = _perf_stats.get("max_drawdown", 0)
    by_sym_str = ""
    for sym, sdata in _perf_stats.get("by_symbol", {}).items():
        if sdata.get("trades", 0) >= 1:
            swr = round(sdata["wins"] / max(1, sdata["trades"]) * 100, 0)
            by_sym_str += f"\n  {sym}: {sdata['trades']} сделок, WR {swr}%, PnL ${sdata['pnl']:.2f}"
    arb_info = f"Арбитраж: {_arb_stats.get('total', 0)} попыток, {_arb_stats.get('success', 0)} успешных, PnL ${_arb_stats.get('total_pnl', 0):.4f}"

    system = f"""Ты — AI-консультант торгового бота QuantumTrade v10.0.
Текущие показатели:
- Всего сделок: {total}, Win Rate: {win_rate:.1f}%, PnL: ${total_pnl:.2f}
- Streak (серия): {streak} ({'побед' if streak > 0 else 'поражений' if streak < 0 else 'нейтральная'})
- Max Drawdown: ${max_dd:.2f}
- Q-Score последний: {last_q_score:.1f}, MIN_Q: {MIN_Q_SCORE}
- COOLDOWN: {COOLDOWN}s, RISK_PER_TRADE: {RISK_PER_TRADE:.0%}, MAX_LEVERAGE: {MAX_LEVERAGE}x
- Квантовый чип: {chip}
- Claude Vision: {"активен" if ANTHROPIC_API_KEY else "не активен"}
- {arb_info}
- По монетам: {by_sym_str if by_sym_str else 'нет данных'}

Ты можешь предложить изменить только эти параметры: MIN_Q_SCORE (40-85), COOLDOWN (120-1800), RISK_PER_TRADE (0.05-0.30), MAX_LEVERAGE (1-15).
ВАЖНО: если пользователь явно запрашивает конкретное значение в допустимом диапазоне — ты ОБЯЗАН предложить именно его через ПРЕДЛАГАЮ, не отказывай и не предлагай альтернативы. Твоё мнение о качестве сигналов не должно мешать исполнению явного запроса владельца системы.
Если предлагаешь изменение — заканчивай ответ строкой: ПРЕДЛАГАЮ: PARAM=VALUE
Отвечай кратко, по-русски, максимум 3-4 предложения."""

    hist = _ai_history.setdefault(chat_id, [])
    hist.append({"role": "user", "content": question})
    if len(hist) > 10: hist.pop(0)

    try:
        # v8.3.4: route through 3-tier AI dispatcher (deepseek by default for chat)
        log_activity(f"[/ask] calling ai_dispatch tier=chat")
        ai_result = await ai_dispatch("chat", hist[-6:], max_tokens=300, system=system)
        reply = ai_result.get("text", "").strip()
        ai_model = ai_result.get("model", "?")
        log_activity(f"[/ask] ai_result: model={ai_model} success={ai_result.get('success')} text_len={len(reply)}")
        if not reply:
            err_detail = ai_result.get("error", "пустой ответ")
            await _tg_send(chat_id, f"⚠️ AI не ответил ({ai_model}): {err_detail}\nПопробуй ещё раз или переформулируй вопрос.")
            return
        hist.append({"role": "assistant", "content": reply})

        # Проверяем предложение изменения
        import re as _re2
        m = _re2.search(r"ПРЕДЛАГАЮ:\s*(\w+)\s*=\s*([\d.]+)", reply)
        if m:
            param, val_str = m.group(1), m.group(2)
            if param in SAFE_PARAMS_TG:
                val = float(val_str)
                p_info = SAFE_PARAMS_TG[param]
                if p_info["min"] <= val <= p_info["max"]:
                    _ai_pending[chat_id] = {"param": param, "value": val}
                    clean_reply = reply.replace(f"ПРЕДЛАГАЮ: {param}={val_str}", "").strip()
                    await _tg_send(chat_id,
                        f"🤖 {clean_reply}\n\n"
                        f"💡 Предлагаю: <b>{param}</b> = <b>{val}</b> (сейчас: {globals().get(param, '?')})\n"
                        f"Напиши <b>да</b> для применения или <b>нет</b> для отмены."
                    )
                    return

        model_icon = "🧠" if "deepseek" in ai_model else "⚛️"
        await _tg_send(chat_id, f"🤖 {reply}\n\n<i>{model_icon} {ai_model}</i>")
    except Exception as e:
        await _tg_send(chat_id, f"❌ Ошибка AI консультанта: {e}")

@app.post("/api/telegram/callback")
async def telegram_callback(req: TelegramUpdate):
    global MIN_Q_SCORE, COOLDOWN, AUTOPILOT
    try:
     return await _telegram_callback_inner(req)
    except Exception as _tg_err:
        log_activity(f"[telegram_callback] unhandled error: {_tg_err}")
        return {"ok": True}

async def _telegram_callback_inner(req: TelegramUpdate):
    global MIN_Q_SCORE, COOLDOWN, AUTOPILOT, ARB_EXEC_ENABLED

    # ── Обработка текстовых команд ─────────────────────────────────────────
    if req.message:
        msg  = req.message
        raw  = msg.get("text", "").strip()
        # v8.3.4: Normalize command — fix spaces after / and common typos
        if raw.startswith("/"):
            # Remove extra spaces after /  :  "/ ask" → "/ask", "/  menu" → "/menu"
            import re as _re_cmd
            raw = _re_cmd.sub(r'^/\s+', '/', raw)
            # Fix common typos for /ask: /aks, /asl, /akk, /aask
            raw_lower_start = raw[:5].lower()
            if raw_lower_start.startswith("/aks") or raw_lower_start.startswith("/asl") or \
               raw_lower_start.startswith("/akk") or raw_lower_start.startswith("/aask"):
                raw = "/ask" + raw[raw.index(raw.split()[0]) + len(raw.split()[0]):]
        # Убираем @BotName суффикс: /menu@MyBot → /menu
        cmd  = raw.split("@")[0].lower() if raw.startswith("/") else raw
        chat_id = msg.get("chat", {}).get("id")
        if not chat_id: return {"ok": True}
        if cmd in ["/start", "/menu"]:     await _tg_main_menu(chat_id)
        elif cmd == "/stats":               await _tg_stats(chat_id)
        elif cmd == "/reset_stats":         await _tg_reset_stats(chat_id)
        elif cmd in ["/airdrops", "/air"]: await _tg_airdrops(chat_id)
        elif cmd == "/settings":            await _tg_settings(chat_id)
        elif cmd == "/diag":                await _tg_diag(chat_id)
        elif cmd == "/balance":             await _tg_balance(chat_id)
        elif cmd == "/positions":           await _tg_positions(chat_id)
        elif cmd == "/arb":                 await _tg_arb(chat_id)
        elif cmd == "/spot":                await _tg_spot_status(chat_id)
        elif cmd.startswith("/mirofish"):   await _tg_mirofish(chat_id, raw)
        elif cmd == "/analyze":             await _tg_analyze(chat_id)
        elif cmd == "/macro":              await _tg_macro(chat_id)
        elif cmd.startswith("/sentiment"):  await _tg_sentiment(chat_id, raw)
        elif cmd == "/bybit":               await _tg_bybit(chat_id)
        elif cmd == "/xarb":                await _tg_xarb(chat_id)
        elif cmd == "/earn":                await _tg_earn(chat_id)
        elif cmd == "/autopilot":
            AUTOPILOT = not AUTOPILOT
            state_emoji = "✅ ВКЛ" if AUTOPILOT else "❌ ВЫКЛ"
            await _tg_send(chat_id,
                f"🤖 <b>Автопилот: {state_emoji}</b>\n"
                f"{'Бот торгует автоматически. Ultra-Sniper режим активен.' if AUTOPILOT else 'Торговля приостановлена.'}")
            log_activity(f"[autopilot] toggled to {'ON' if AUTOPILOT else 'OFF'} by /autopilot command")
        elif cmd.startswith("/sell"):       await _tg_universal_sell(chat_id, raw)
        elif cmd.startswith("/buy"):
            if not cmd.startswith("/buy ") and cmd == "/buy":
                await _tg_send(chat_id, "ℹ️ <b>Формат:</b>\n<code>/buy ETH 30</code> — купить ETH на $30\n<code>/buy BTC 50</code> — купить BTC на $50")
            else:
                await _tg_universal_buy(chat_id, raw)
        # v7.2.0: AI консультант
        elif cmd.startswith("/ask"):
            # /ask текст или /ask@bot текст — v10.0: escape HTML in user input
            question = raw.split(None, 1)[1].strip() if len(raw.split(None, 1)) > 1 else ""
            question = html_mod.escape(question)
            if not question:
                await _tg_send(chat_id,
                    "🤖 <b>AI-консультант</b>\n\n"
                    "Напиши вопрос после команды:\n"
                    "<code>/ask как дела у бота?</code>\n"
                    "<code>/ask стоит ли снизить Q-Score?</code>\n"
                    "<code>/ask что такое арбитраж?</code>"
                )
                return
            await _tg_ai_ask(chat_id, question)
        # v7.2.1: прямая установка параметра без AI (/set PARAM VALUE)
        elif cmd.startswith("/set"):
            parts = raw.strip().split()
            if len(parts) == 3:
                _, s_param, s_val_str = parts
                s_param = s_param.upper()
                if s_param in SAFE_PARAMS_TG:
                    try:
                        s_val = float(s_val_str)
                        p = SAFE_PARAMS_TG[s_param]
                        if p["min"] <= s_val <= p["max"]:
                            global MIN_Q_SCORE, COOLDOWN, RISK_PER_TRADE, MAX_LEVERAGE
                            if s_param == "MIN_Q_SCORE":    MIN_Q_SCORE = int(s_val)
                            elif s_param == "COOLDOWN":     COOLDOWN = int(s_val)
                            elif s_param == "RISK_PER_TRADE": globals()["RISK_PER_TRADE"] = s_val
                            elif s_param == "MAX_LEVERAGE": globals()["MAX_LEVERAGE"] = int(s_val)
                            log_activity(f"[set_cmd] {s_param}={s_val} applied directly")
                            persisted = await _update_railway_var(s_param, str(int(s_val) if s_val == int(s_val) else s_val))
                            note = " • сохранено в Railway ♾️" if persisted else " • только в памяти"
                            await _tg_send(chat_id, f"✅ <b>{s_param}</b> = <b>{int(s_val) if s_val == int(s_val) else s_val}</b>{note}")
                        else:
                            await _tg_send(chat_id, f"❌ {s_param}: допустимый диапазон {p['min']}–{p['max']}")
                    except ValueError:
                        await _tg_send(chat_id, "❌ Неверное значение. Пример: /set MIN_Q_SCORE 55")
                else:
                    await _tg_send(chat_id, f"❌ Неизвестный параметр. Доступны: {', '.join(SAFE_PARAMS_TG)}")
            else:
                await _tg_send(chat_id, "ℹ️ Формат: /set PARAM VALUE\nПример: /set MIN_Q_SCORE 55")
        elif raw and not raw.startswith("/"):
            # Свободный текст → AI консультант (если есть pending action или начинается с да/нет)
            await _tg_ai_ask(chat_id, raw)
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
        # Кнопка в главном меню — тоглим и обновляем меню
        AUTOPILOT = not AUTOPILOT
        state = "ВКЛ 🟢" if AUTOPILOT else "ВЫКЛ 🔴"
        await _tg_answer(cb_id, f"Торговля {state}")
        log_activity(f"[settings] Автопилот → {state} (via main menu)")
        if chat_id: await _tg_main_menu(chat_id)

    elif data == "toggle_autopilot":
        # Кнопка в панели настроек — тоглим и обновляем настройки
        AUTOPILOT = not AUTOPILOT
        state = "ВКЛ 🟢" if AUTOPILOT else "ВЫКЛ 🔴"
        await _tg_answer(cb_id, f"Торговля {state}")
        log_activity(f"[settings] Автопилот → {state} (via settings panel)")
        if chat_id: await _tg_settings(chat_id)

    elif data == "toggle_arb":
        # Кнопка в настройках / панели арбитража
        ARB_EXEC_ENABLED = not ARB_EXEC_ENABLED
        state = "ВКЛ 🟢" if ARB_EXEC_ENABLED else "ВЫКЛ 🔴"
        await _tg_answer(cb_id, f"Арбитраж {state}")
        log_activity(f"[settings] ARB_EXEC_ENABLED → {state} (via Telegram)")
        if chat_id: await _tg_arb(chat_id)

    elif data == "sell_all_spot":
        await _tg_answer(cb_id, "Продаю всё в USDT...")
        if chat_id: await _tg_sell_all_spot(chat_id)

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
        log_activity(f"[settings] SAVED: MIN_Q={MIN_Q_SCORE} COOLDOWN={COOLDOWN}s AUTOPILOT={AUTOPILOT} ARB={ARB_EXEC_ENABLED}")
        await notify(
            f"💾 *Настройки сохранены*\n"
            f"Min Q-Score: `{MIN_Q_SCORE}`\n"
            f"Cooldown: `{COOLDOWN}s`\n"
            f"Торговля: `{'ВКЛ' if AUTOPILOT else 'ВЫКЛ'}`\n"
            f"Арбитраж: `{'ВКЛ' if ARB_EXEC_ENABLED else 'ВЫКЛ'}`"
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
    _load_trades_from_disk()          # загружаем историю сделок при старте (JSON fallback)

    # v8.2: PostgreSQL — persistent storage
    pg_ok = await db.init_db()
    if pg_ok:
        # One-time migration: JSON → PostgreSQL (if trades exist in JSON but not in DB)
        db_count = await db.get_trade_count()
        if db_count == 0 and trade_log:
            migrated = await db.migrate_from_json(trade_log, _perf_stats)
            print(f"[startup] migrated {migrated} trades JSON → PostgreSQL")
        # v8.3.3: Load trade history from PostgreSQL (survives container restarts)
        if db_count > 0 and not trade_log:
            db_trades = await db.get_trades(limit=200)
            if db_trades:
                trade_log.extend(reversed(db_trades))  # oldest first
                print(f"[startup] loaded {len(db_trades)} trades from PostgreSQL")
        # Load perf stats from DB
        db_stats = await db.load_perf_stats()
        if db_stats:
            _perf_stats.update(db_stats)
            print(f"[startup] perf stats loaded from PostgreSQL")

        # v9.2: Restore MiroFish memory from PostgreSQL
        global _mirofish_memory
        mem_data = await db.load_all_mirofish_memory()
        if mem_data:
            _mirofish_memory.update(mem_data)
            total_mem = sum(len(v) for v in mem_data.values())
            print(f"[startup] MiroFish memory restored: {total_mem} entries for {len(mem_data)} symbols")

    # Phase 6: пробуем подключить Origin QC Wukong 180
    qc_ok = await asyncio.get_event_loop().run_in_executor(None, _init_qcloud)

    asyncio.create_task(trading_loop())
    asyncio.create_task(position_monitor_loop())
    asyncio.create_task(spot_monitor_loop())      # v8.3: spot position TP/SL monitor
    asyncio.create_task(earn_monitor_loop())      # v10.1: Earn Engine — auto-place idle USDT
    asyncio.create_task(_ws_price_feed())          # v8.3.3: WebSocket real-time prices
    asyncio.create_task(_arb_fast_scanner())       # v8.3.3: fast arb scanner (every 5s)
    asyncio.create_task(airdrop_digest_loop())
    asyncio.create_task(auto_scanner_loop())  # v7.4.4: health scanner
    await get_airdrops()  # прогреваем кеш при старте

    # v7.4.0: авто-регистрация Telegram webhook при старте (если задан Railway домен)
    if BOT_TOKEN and RAILWAY_PUBLIC_DOMAIN:
        try:
            railway_base = f"https://{RAILWAY_PUBLIC_DOMAIN}"
            webhook_url  = f"{railway_base}/api/telegram/callback"
            webapp_url   = WEBAPP_URL or railway_base
            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
                    json={"url": webhook_url, "allowed_updates": ["message", "callback_query"]},
                    timeout=aiohttp.ClientTimeout(total=10)
                )
                await s.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/setChatMenuButton",
                    json={"menu_button": {"type": "web_app", "text": "🖥️ Дашборд", "web_app": {"url": webapp_url + "?v=830"}}},
                    timeout=aiohttp.ClientTimeout(total=10)
                )
        except Exception as e:
            print(f"[startup] webhook auto-setup failed: {e}")

    mode     = "TEST" if TEST_MODE else "LIVE"
    risk_pct = round(RISK_PER_TRADE * 100)
    qc_label = "⚛️ Wukong 180 реальный чип ✅" if qc_ok else "⚛️ QAOA CPU симулятор"
    arb_active = sum(1 for _, _, c, _ in ARB_TRIANGLES if c not in _arb_dead_pairs)
    ai_chat_model = AI_TIER_CHAT.upper()
    ai_crit_model = AI_TIER_CRITICAL.upper()
    await notify(
        f"⚛ <b>QuantumTrade v10.0</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Режим: {mode} · Риск: {risk_pct}% · Леверидж: {MAX_LEVERAGE}x\n"
        f"🎯 Q-min: {MIN_Q_SCORE} · Cooldown: {COOLDOWN}s\n"
        f"✅ Спот: {len(SPOT_PAIRS)} пар · Фьючерсы: {len(FUT_PAIRS)} пар\n"
        f"🔀 Биржи: KuCoin + ByBit (dual-exchange)\n"
        f"⚡ Арбитраж: {arb_active}/{len(ARB_TRIANGLES)} связок · X-Arb KuCoin↔ByBit\n"
        f"🛡️ Opus Gate: сделки >${OPUS_GATE_MIN_USDT:.0f} → подтверждение AI\n"
        f"🤖 AI: {ai_chat_model} (чат) · {ai_crit_model} (критич.)\n"
        f"{qc_label}\n"
        f"📦 Max позиций: {MAX_OPEN_POSITIONS} · Stale auto-sell: 12h\n"
        f"💰 Резерв: ${ARB_RESERVE_USDT:.0f} · Min сделка: ${SPOT_BUY_MIN_USDT:.0f} · История: {len(trade_log)}"
    )

async def trading_loop():
    while True:
        try: await auto_trade_cycle()
        except Exception as e: log_activity(f"[loop] error: {e}")
        # v9.0: Cross-exchange arb check every cycle
        if BYBIT_ENABLED and XARB_ENABLED:
            try:
                opps = await check_cross_exchange_arb()
                if opps:
                    for opp in opps:
                        await notify(
                            f"🔀 <b>Cross-Exchange Arb</b>\n"
                            f"{opp['symbol']}: спред <code>{opp['spread_pct']:.3f}%</code>\n"
                            f"KuCoin: <code>${opp['kc_price']:,.2f}</code> | ByBit: <code>${opp['bb_price']:,.2f}</code>\n"
                            f"→ {opp['direction']}"
                        )
            except Exception as e:
                log_activity(f"[xarb_loop] error: {e}")
        await asyncio.sleep(15)  # v7.2.0: 60→15s (4x faster signal response)


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

# ── v8.3.3: Arbitrage Analytics API ────────────────────────────────────────────
@app.get("/api/arb/stats")
async def arb_stats_api():
    """v8.3.3: Arb analytics for Mini App dashboard."""
    active_count = sum(1 for _, _, c, _ in ARB_TRIANGLES if c not in _arb_dead_pairs)
    return {
        "stats": _arb_stats,
        "opus_gate": _opus_gate_stats,
        "mirofish": {**_mirofish_stats, "enabled": MIROFISH_ENABLED, "agents": len(MIROFISH_PERSONAS), "memory_entries": sum(len(v) for v in _mirofish_memory.values())},
        "bybit": {**_bybit_stats, "enabled": BYBIT_ENABLED},
        "xarb": {**_xarb_stats, "enabled": XARB_ENABLED and BYBIT_ENABLED},
        "ws": {"connected": _ws_connected, "prices_count": len(_ws_prices), "reconnects": _ws_reconnects},
        "config": {
            "exec_enabled": ARB_EXEC_ENABLED, "exec_usdt": ARB_EXEC_USDT,
            "min_spread": ARB_MIN_SPREAD, "reserve_usdt": ARB_RESERVE_USDT,
            "total_triangles": len(ARB_TRIANGLES), "active": active_count,
            "dead": len(_arb_dead_pairs)
        },
        "history": _arb_history[-20:],  # last 20 events
    }


@app.get("/api/earn/status")
async def earn_status_api():
    """v10.1: Earn Engine status — positions, APR, stats."""
    best = {"exchange": "unknown", "apr": 0}
    try:
        best = await earn_get_best_rate("USDT")
    except Exception:
        pass
    return {
        "enabled": EARN_ENABLED,
        "stats": _earn_stats,
        "positions": _earn_positions,
        "best_rate": best,
        "config": {
            "min_idle_usdt": EARN_MIN_IDLE_USDT,
            "reserve_usdt": EARN_RESERVE_USDT,
        },
    }


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
    from datetime import timedelta
    _now = datetime.utcnow()
    today_str = _now.strftime("%Y-%m-%d")
    tomorrow_str = (_now + timedelta(days=1)).strftime("%Y-%m-%d")
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
async def update_settings(body: dict, _auth=Depends(verify_api_key)):  # v7.3.3: auth required
    """v6.7: runtime settings update without restart."""
    global MIN_Q_SCORE, COOLDOWN, AUTOPILOT, TEST_MODE, RISK_PER_TRADE, MAX_LEVERAGE
    changed = {}
    # v10.0: Input validation per trading.md rules
    if "min_q_score" in body:
        val = int(body["min_q_score"])
        if val < 65 or val > 100:
            raise HTTPException(400, "min_q_score must be 65-100 (per trading.md)")
        MIN_Q_SCORE = val
        changed["min_q_score"] = MIN_Q_SCORE
    if "cooldown" in body:
        val = int(body["cooldown"])
        if val < 300 or val > 7200:
            raise HTTPException(400, "cooldown must be 300-7200s (per trading.md)")
        COOLDOWN = val
        changed["cooldown"] = COOLDOWN
    if "autopilot" in body:
        AUTOPILOT = bool(body["autopilot"])
        changed["autopilot"] = AUTOPILOT
    if "test_mode" in body:
        TEST_MODE = bool(body["test_mode"])
        RISK_PER_TRADE = 0.05 if TEST_MODE else 0.08
        changed["test_mode"] = TEST_MODE
        changed["risk_per_trade"] = RISK_PER_TRADE
    if "max_leverage" in body:
        val = int(body["max_leverage"])
        if val < 1 or val > 5:
            raise HTTPException(400, "max_leverage must be 1-5 (per trading.md)")
        MAX_LEVERAGE = val
        changed["max_leverage"] = MAX_LEVERAGE
    log_activity(f"[settings/api] changed: {changed}")
    return {"ok": True, "changed": changed,
            "current": {"min_q_score": MIN_Q_SCORE, "cooldown": COOLDOWN,
                        "autopilot": AUTOPILOT, "test_mode": TEST_MODE,
                        "risk_per_trade": RISK_PER_TRADE, "max_leverage": MAX_LEVERAGE}}

@app.get("/health")
async def health():
    # v7.3.3: публичный эндпоинт — минимум информации, без внутренних настроек
    return {
        "status": "ok",
        "version": "10.1.0",
        "auto_trading": AUTOPILOT,
        "earn_engine": EARN_ENABLED,
        "earn_total": round(_earn_stats.get("kucoin_subscribed", 0) + _earn_stats.get("bybit_subscribed", 0), 2),
        "quantum_chip": "Wukong_180" if _qcloud_ready else "CPU_simulator",
        "timestamp": datetime.utcnow().isoformat(),
    }

@app.post("/api/setup-webhook")
async def setup_webhook(request: Request):
    """v7.4.0: Регистрирует Telegram Webhook + команды + Mini App кнопку.
    WEBAPP_URL теперь авто-определяется из Railway домена."""
    if not BOT_TOKEN:
        return {"ok": False, "error": "BOT_TOKEN не задан"}
    base_url = str(request.base_url).rstrip("/").replace("http://", "https://")
    webhook_url = f"{base_url}/api/telegram/callback"

    # v7.4.0: Mini App URL = Railway URL (тот же сервис, GET / отдаёт index.html)
    webapp_url = WEBAPP_URL or base_url  # если WEBAPP_URL задан — используем его, иначе Railway URL

    results = {}
    try:
        async with aiohttp.ClientSession() as s:
            # 1. Регистрируем webhook (v10.0: with secret_token if configured)
            wh_payload = {"url": webhook_url, "allowed_updates": ["message", "callback_query"]}
            if TG_WEBHOOK_SECRET:
                wh_payload["secret_token"] = TG_WEBHOOK_SECRET
            r = await s.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
                json=wh_payload,
                timeout=aiohttp.ClientTimeout(total=10)
            )
            results["webhook"] = await r.json()

            # 2. Регистрируем команды — появятся в меню "/" у пользователя
            r2 = await s.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setMyCommands",
                json={"commands": [
                    {"command": "menu",      "description": "🏠 Главное меню"},
                    {"command": "stats",     "description": "📊 Статистика торговли"},
                    {"command": "mirofish",  "description": "🐟 MiroFish анализ (напр. /mirofish BTC)"},
                    {"command": "sentiment", "description": "🌐 Полный анализ настроений рынка"},
                    {"command": "analyze",   "description": "🔬 Глубокая аналитика сделок"},
                    {"command": "macro",     "description": "🌍 Макро-дашборд + F&G корреляция"},
                    {"command": "balance",   "description": "💰 Баланс счёта"},
                    {"command": "positions", "description": "📈 Открытые позиции"},
                    {"command": "settings",  "description": "⚙️ Настройки (Q-Score, Cooldown)"},
                    {"command": "diag",      "description": "🔬 Диагностика всех подключений"},
                ]},
                timeout=aiohttp.ClientTimeout(total=10)
            )
            results["commands"] = await r2.json()

            # 3. v7.4.4: Кнопка меню → Railway Mini App с ?v= для сброса кеша Telegram
            versioned_url = f"{webapp_url}?v=830"
            r3 = await s.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setChatMenuButton",
                json={"menu_button": {"type": "web_app", "text": "🖥️ Дашборд", "web_app": {"url": versioned_url}}},
                timeout=aiohttp.ClientTimeout(total=10)
            )
            results["menu_button"] = await r3.json()

        return {"ok": True, "webhook_url": webhook_url, "webapp_url": webapp_url, "results": results}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/debug")
async def api_debug(_auth=Depends(verify_api_key)):
    """v8.3.0: Protected diagnostics — checks all systems, returns status JSON."""
    import time as _time
    results = {"version": "8.3.0", "timestamp": datetime.utcnow().isoformat(), "checks": {}}
    t0 = _time.time()

    # 1. KuCoin REST prices
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(f"{KUCOIN_BASE_URL}/api/v1/market/orderbook/level1?symbol=BTC-USDT",
                            timeout=aiohttp.ClientTimeout(total=6))
            d = await r.json()
            ok = d.get("code") == "200000"
            results["checks"]["kucoin_price"] = {"ok": ok, "price": d.get("data", {}).get("price", "?") if ok else None, "error": d.get("msg") if not ok else None}
    except Exception as e:
        results["checks"]["kucoin_price"] = {"ok": False, "error": str(e)}

    # 2. KuCoin authenticated (spot balance)
    try:
        bal = await get_balance()
        results["checks"]["kucoin_spot"] = {"ok": bal.get("success", False), "total_usdt": bal.get("total_usdt", 0), "accounts": len(bal.get("accounts", [])), "error": bal.get("error") if not bal.get("success") else None}
    except Exception as e:
        results["checks"]["kucoin_spot"] = {"ok": False, "error": str(e)}

    # 3. KuCoin futures balance
    try:
        fb = await get_futures_balance()
        results["checks"]["kucoin_futures"] = {"ok": fb.get("success", False), "equity": fb.get("account_equity", 0), "error": fb.get("error") if not fb.get("success") else None}
    except Exception as e:
        results["checks"]["kucoin_futures"] = {"ok": False, "error": str(e)}

    # 4. Fear & Greed API
    try:
        fg = await get_fear_greed()
        results["checks"]["fear_greed"] = {"ok": isinstance(fg, dict) and "value" in fg, "value": fg.get("value"), "label": fg.get("label")}
    except Exception as e:
        results["checks"]["fear_greed"] = {"ok": False, "error": str(e)}

    # 5. CoinGecko fallback
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd",
                            timeout=aiohttp.ClientTimeout(total=6))
            d = await r.json()
            results["checks"]["coingecko"] = {"ok": "bitcoin" in d, "btc_usd": d.get("bitcoin", {}).get("usd")}
    except Exception as e:
        results["checks"]["coingecko"] = {"ok": False, "error": str(e)}

    # 6. Config
    results["checks"]["config"] = {
        "ok": True, "min_q": MIN_Q_SCORE, "cooldown": COOLDOWN,
        "autopilot": AUTOPILOT, "arb": ARB_EXEC_ENABLED,
        "kucoin_key_set": bool(KUCOIN_API_KEY), "api_secret_set": bool(API_SECRET),
        "bot_token_set": bool(BOT_TOKEN),
    }

    results["elapsed_ms"] = round((_time.time() - t0) * 1000)
    all_ok = all(v.get("ok", False) for v in results["checks"].values())
    results["overall"] = "✅ ALL OK" if all_ok else "⚠️ ISSUES DETECTED"
    results["scanner"] = {
        "runs": _scanner_state.get("ok_streak", 0),
        "issues": len(_scanner_state.get("issues", [])),
        "last_run": _scanner_state.get("last_run"),
    }
    return results

# ── Auto-Scanner Background Task ───────────────────────────────────────────────
_scanner_state = {"last_run": None, "issues": [], "ok_streak": 0, "alert_sent": False}

async def auto_scanner_loop():
    """v7.5.0: Полный health scanner — 10+ проверок каждые 5 мин, алерты + рекомендации."""
    await asyncio.sleep(60)
    while True:
        try:
            issues = []
            warnings = []
            recommendations = []

            # ── 1. KuCoin Prices ──────────────────────────────────────────────
            prices = await get_all_prices()
            if not prices.get("success") or not prices.get("prices"):
                issues.append("❌ KuCoin цены недоступны")

            # ── 2. KuCoin Auth (Spot) ─────────────────────────────────────────
            if KUCOIN_API_KEY:
                bal = await get_balance()
                if not bal.get("success"):
                    issues.append(f"❌ KuCoin Spot: {bal.get('error', '?')[:60]}")
                else:
                    total = bal.get("total_usdt", 0)
                    if total < 10:
                        warnings.append(f"⚠️ Баланс спот: ${total:.2f} — недостаточно для торговли")
            else:
                issues.append("❌ KUCOIN_API_KEY не задан")

            # ── 3. KuCoin Futures ─────────────────────────────────────────────
            if KUCOIN_API_KEY:
                fb = await get_futures_balance()
                if not fb.get("success"):
                    warnings.append(f"⚠️ KuCoin Futures: {fb.get('error', '?')[:60]}")

            # ── 4. Telegram ───────────────────────────────────────────────────
            if not BOT_TOKEN:
                issues.append("❌ BOT_TOKEN не задан")
            if not API_SECRET:
                warnings.append("⚠️ API_SECRET не задан — Mini App без авторизации")

            # ── 5. Claude Vision AI ───────────────────────────────────────────
            if not ANTHROPIC_API_KEY:
                warnings.append("⚠️ ANTHROPIC_API_KEY не задан — Claude Vision отключён (Q-Score снижен)")

            # ── 6. Торговая активность ────────────────────────────────────────
            if trade_log:
                last_trade_ts = trade_log[-1].get("open_ts", 0)  # v8.2: use numeric open_ts, not ISO string ts
                if isinstance(last_trade_ts, str):
                    try: last_trade_ts = datetime.fromisoformat(last_trade_ts.replace("Z","")).timestamp()
                    except Exception: last_trade_ts = 0
                hours_since = (time.time() - last_trade_ts) / 3600 if last_trade_ts else float("inf")
                if AUTOPILOT and hours_since > 24:
                    warnings.append(f"⚠️ Автопилот ВКЛ, но 0 сделок за {int(hours_since)}ч — проверь Q-min ({MIN_Q_SCORE})")
                    if MIN_Q_SCORE > 80:
                        recommendations.append("💡 MIN_Q_SCORE={} слишком высок. Попробуй 72-77 для большей активности".format(MIN_Q_SCORE))

            # ── 7. Производительность (self-learning) ─────────────────────────
            if _perf_stats["total_trades"] >= 10:
                wr = _perf_stats["wins"] / _perf_stats["total_trades"] * 100
                if wr < 40:
                    warnings.append(f"⚠️ Win rate {wr:.0f}% (низкий) — рекомендуется поднять MIN_Q_SCORE")
                    recommendations.append("💡 Повысь MIN_Q_SCORE на 5 пунктов для улучшения качества сигналов")
                if _perf_stats["max_drawdown"] < -50:
                    issues.append(f"❌ Max drawdown ${_perf_stats['max_drawdown']:.2f} — критическая просадка")
                # Анализ по стратегиям
                for strat, data in _perf_stats["by_strategy"].items():
                    if data["trades"] >= 5:
                        swr = data["wins"] / data["trades"] * 100
                        if swr < 30:
                            recommendations.append(f"💡 Стратегия {strat}: WR {swr:.0f}%, PnL ${data['pnl']:.2f} — рассмотри отключение")
                # Анализ по символам
                for sym, data in _perf_stats["by_symbol"].items():
                    if data["trades"] >= 5 and data["pnl"] < -20:
                        recommendations.append(f"💡 {sym}: убыток ${data['pnl']:.2f} за {data['trades']} сделок — рассмотри исключение")
                # Лучший Q-Score для побед
                if _perf_stats["avg_q_score_win"] > _perf_stats["avg_q_score_loss"] + 5:
                    recommendations.append(f"💡 Средний Q побед: {_perf_stats['avg_q_score_win']}, поражений: {_perf_stats['avg_q_score_loss']}")

            # ── 8. Streak detection ───────────────────────────────────────────
            if _perf_stats["streak"] <= -3:
                warnings.append(f"⚠️ Серия из {abs(_perf_stats['streak'])} убыточных сделок подряд")
                recommendations.append("💡 При серии -3 рекомендуется пауза. Рассмотри /set cooldown 1200")

            # ── 9. Railway & trade log persistence ────────────────────────────
            if not os.path.exists(_TRADES_FILE):
                warnings.append("⚠️ Trade log файл не найден — история может быть утеряна")

            # ── 10. QAOA status ───────────────────────────────────────────────
            if not _qcloud_ready:
                pass  # CPU fallback работает, не алертим

            # ── Формируем статус ──────────────────────────────────────────────
            _scanner_state["last_run"] = datetime.utcnow().isoformat()
            _scanner_state["issues"] = issues
            _scanner_state["warnings"] = warnings
            _scanner_state["recommendations"] = recommendations
            _scanner_state["perf"] = {
                "trades": _perf_stats["total_trades"],
                "wr": round(_perf_stats["wins"] / max(1, _perf_stats["total_trades"]) * 100, 1),
                "pnl": _perf_stats["total_pnl"],
                "streak": _perf_stats["streak"],
            }

            if issues:
                _scanner_state["ok_streak"] = 0
                if not _scanner_state["alert_sent"]:
                    _scanner_state["alert_sent"] = True
                    msg = "🔍 <b>QuantumTrade AutoScanner v8.3.0</b>\n\n"
                    msg += "\n".join(issues)
                    if warnings: msg += "\n\n" + "\n".join(warnings[:3])
                    if recommendations: msg += "\n\n" + "\n".join(recommendations[:2])
                    msg += f"\n\n🕐 {datetime.utcnow().strftime('%H:%M UTC')}"
                    await notify(msg)
            else:
                _scanner_state["ok_streak"] += 1
                _scanner_state["alert_sent"] = False
                if _scanner_state["ok_streak"] % 12 == 1:
                    wr = _perf_stats["wins"] / max(1, _perf_stats["total_trades"]) * 100
                    msg = (
                        f"✅ <b>AutoScanner: все системы в норме</b>\n"
                        f"📊 Q-min: {MIN_Q_SCORE} · Cooldown: {COOLDOWN}s\n"
                        f"🤖 AP: {'ВКЛ' if AUTOPILOT else 'ВЫКЛ'} · Arb: {'ВКЛ' if ARB_EXEC_ENABLED else 'ВЫКЛ'}\n"
                        f"📋 Сделок: {_perf_stats['total_trades']} · WR: {wr:.0f}% · PnL: ${_perf_stats['total_pnl']:.2f}\n"
                        f"🔥 Streak: {_perf_stats['streak']} · Версия: 10.0.0"
                    )
                    if warnings: msg += "\n\n" + "\n".join(warnings[:2])
                    if recommendations: msg += "\n\n" + "\n".join(recommendations[:2])
                    await notify(msg)
        except Exception as e:
            print(f"[scanner] error: {e}", flush=True)
        await asyncio.sleep(300)

@app.get("/api/scanner/status")
async def api_scanner_status():
    """v7.5.0: Статус автосканера + производительность + рекомендации."""
    return _scanner_state

@app.get("/api/public/performance")
async def api_public_performance():
    """v7.5.0: Статистика производительности бота для самообучения и Mini App."""
    return {
        "total_trades": _perf_stats["total_trades"],
        "wins": _perf_stats["wins"],
        "losses": _perf_stats["losses"],
        "win_rate": round(_perf_stats["wins"] / max(1, _perf_stats["total_trades"]) * 100, 1),
        "total_pnl": _perf_stats["total_pnl"],
        "max_drawdown": _perf_stats["max_drawdown"],
        "streak": _perf_stats["streak"],
        "max_streak": _perf_stats["max_streak"],
        "avg_q_win": _perf_stats["avg_q_score_win"],
        "avg_q_loss": _perf_stats["avg_q_score_loss"],
        "by_strategy": _perf_stats["by_strategy"],
        "by_symbol": _perf_stats["by_symbol"],
        "recommendations": _scanner_state.get("recommendations", []),
        "version": "10.0.0",
    }

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
async def api_balance(_auth=Depends(verify_api_key)): return await get_balance()  # v7.3.3: auth

@app.get("/api/futures/balance")
async def api_futures_balance(_auth=Depends(verify_api_key)): return await get_futures_balance()  # v7.3.3

@app.get("/api/futures/positions")
async def api_futures_positions(_auth=Depends(verify_api_key)): return await get_futures_positions()  # v7.3.3

@app.get("/api/combined/balance")
async def api_combined_balance(_auth=Depends(verify_api_key)):  # v7.3.3: auth
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

async def _get_prices_with_fallback() -> dict:
    """v7.4.2: Try KuCoin first, fallback to CoinGecko if empty."""
    kucoin_result = await get_all_prices()
    if kucoin_result.get("success") and kucoin_result.get("prices"):
        return kucoin_result
    # Fallback: CoinGecko free API (no key needed)
    try:
        ids = "bitcoin,ethereum,solana,binancecoin,ripple,avalanche-2"
        sym_map = {"bitcoin": "BTC-USDT", "ethereum": "ETH-USDT", "solana": "SOL-USDT",
                   "binancecoin": "BNB-USDT", "ripple": "XRP-USDT", "avalanche-2": "AVAX-USDT"}
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true",
                timeout=aiohttp.ClientTimeout(total=8),
                headers={"Accept": "application/json"}
            )
            data = await r.json()
            prices = {}
            for cg_id, kucoin_sym in sym_map.items():
                if cg_id in data:
                    prices[kucoin_sym] = {
                        "price": data[cg_id].get("usd", 0),
                        "change": data[cg_id].get("usd_24h_change", 0),
                    }
            return {"prices": prices, "success": True, "source": "coingecko"}
    except Exception as e:
        return {"prices": {}, "success": False, "error": f"kucoin+coingecko failed: {e}"}

@app.get("/api/public/balance")
async def api_public_balance():
    """v7.4.2: Public balance endpoint — no auth required. For Mini App balance tab."""
    spot, futures = await asyncio.gather(get_balance(), get_futures_balance(), return_exceptions=True)
    spot_data = spot if isinstance(spot, dict) else {"total_usdt": 0, "accounts": [], "success": False}
    fut_data  = futures if isinstance(futures, dict) else {"available_balance": 0, "account_equity": 0, "unrealised_pnl": 0, "success": False}
    total = spot_data.get("total_usdt", 0) + fut_data.get("account_equity", 0)
    return {
        "spot_usdt":          spot_data.get("total_usdt", 0),
        "spot_accounts":      spot_data.get("accounts", []),
        "spot_success":       spot_data.get("success", False),
        "futures_equity":     fut_data.get("account_equity", 0),
        "futures_available":  fut_data.get("available_balance", 0),
        "futures_unrealised": fut_data.get("unrealised_pnl", 0),
        "futures_success":    fut_data.get("success", False),
        "total_usdt":         round(total, 2),
    }

@app.get("/api/public/positions")
async def api_public_positions():
    """v7.4.2: Public futures positions — no auth required. For Mini App balance tab."""
    try:
        result = await get_futures_positions()
        return result
    except Exception as e:
        return {"positions": [], "error": str(e)}

@app.get("/api/public/stats")
async def api_public_stats():
    """Public read-only stats for Mini App — no auth required. v7.4.2: +price fallback +balance summary"""
    # Fetch in parallel: prices (with fallback), fear&greed, whale signals, balance
    MAIN_PAIRS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT"]
    prices_data, fg_data, balance_data, *whale_results = await asyncio.gather(
        _get_prices_with_fallback(),
        get_fear_greed(),
        api_public_balance(),
        *[get_whale_signal(sym) for sym in MAIN_PAIRS],
        return_exceptions=True
    )
    # Polymarket (cached — non-blocking)
    poly_cached = _cache_get("polymarket", 900) or []

    trades_total = len(trade_log)
    trades_wins  = sum(1 for t in trade_log if (t.get("pnl") or 0) > 0)
    total_pnl    = round(sum(t.get("pnl") or 0 for t in trade_log), 4)
    win_rate     = round(trades_wins / trades_total * 100, 1) if trades_total else 0
    open_pos     = sum(1 for t in trade_log if t.get("status") == "open")
    recent_trades = list(reversed(trade_log))[:10]
    safe_trades   = [{"symbol": t.get("symbol"), "side": t.get("side"),
                      "price": t.get("price"), "pnl": t.get("pnl"),
                      "status": t.get("status"), "account": t.get("account"),
                      "q_score": t.get("q_score"), "ts": t.get("ts")} for t in recent_trades]
    arb_info = {"enabled": ARB_EXEC_ENABLED, "total": _arb_stats.get("total", 0),
                "success": _arb_stats.get("success", 0), "pnl": round(_arb_stats.get("total_pnl", 0), 4)}

    # Whale summary per symbol
    whales = {}
    for sym, w in zip(MAIN_PAIRS, whale_results):
        if isinstance(w, dict):
            whales[sym] = {"bonus": w.get("bonus", 0), "signal": w.get("signal", "neutral"),
                           "description": w.get("description", "")}

    # Fear & Greed
    fg = {"value": fg_data.get("value", 50), "label": fg_data.get("label", "—")} if isinstance(fg_data, dict) else {"value": 50, "label": "—"}

    # Polymarket top events (already filtered for crypto)
    poly_events = [{"title": e.get("title"), "yes_prob": e.get("yes_prob"), "volume": e.get("volume")}
                   for e in poly_cached[:6]]

    # v7.4.2: balance summary included in public stats
    bal = balance_data if isinstance(balance_data, dict) else {}

    # v7.4.2: safe price extraction (prices_data might be exception)
    raw_prices = prices_data.get("prices", {}) if isinstance(prices_data, dict) else {}

    return {
        "autopilot": AUTOPILOT,
        "arb": arb_info,
        "trading": {"total": trades_total, "wins": trades_wins, "total_pnl": total_pnl,
                    "win_rate": win_rate, "open": open_pos},
        "settings": {"min_q_score": MIN_Q_SCORE, "cooldown": COOLDOWN,
                     "risk_pct": RISK_PER_TRADE},
        "prices":   {sym: {"price": v.get("price"), "change": v.get("change")}
                     for sym, v in raw_prices.items()},
        "recent_trades": safe_trades,
        "whales":    whales,
        "fear_greed": fg,
        "polymarket": poly_events,
        "balance": {
            "spot_usdt":     bal.get("spot_usdt", 0),
            "futures_equity": bal.get("futures_equity", 0),
            "total_usdt":    bal.get("total_usdt", 0),
        },
        "timestamp": datetime.utcnow().isoformat(),
        "version": "10.0.0",
    }

@app.get("/api/dashboard")
async def api_dashboard(_auth=Depends(verify_api_key)):  # v7.3.3: auth
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
async def api_trades(limit: int = 50, _auth=Depends(verify_api_key)):  # v7.3.3: auth
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

@app.get("/api/analytics")
async def api_analytics(x_api_key: str = Header(None)):
    """v8.2: Rich trade analytics from PostgreSQL for AI self-learning."""
    await verify_api_key(x_api_key)
    if not db.is_ready():
        return {"error": "PostgreSQL not connected", "fallback": _perf_stats}
    analytics = await db.get_analytics()
    analytics["perf_stats"] = _perf_stats
    analytics["db_trade_count"] = await db.get_trade_count()
    return analytics


@app.get("/api/spot/balances")
async def api_spot_balances(x_api_key: str = Header(None)):
    """v8.3: Get all spot coin balances."""
    await verify_api_key(x_api_key)
    balances = await get_spot_balances()
    usdt_bal = await get_balance()
    total = usdt_bal.get("total_usdt", 0) + sum(b["usdt_value"] for b in balances.values())
    return {"balances": balances, "usdt": usdt_bal.get("total_usdt", 0), "total_usdt": round(total, 2)}


@app.post("/api/spot/sell_all")
async def api_sell_all_spot(x_api_key: str = Header(None)):
    """v8.3: Sell all spot coins back to USDT."""
    await verify_api_key(x_api_key)
    balances = await get_spot_balances()
    results = []
    for symbol, info in balances.items():
        r = await sell_spot_to_usdt(symbol, info["available"])
        results.append({"symbol": symbol, "size": info["available"], "usdt_value": info["usdt_value"], "success": r.get("success", False)})
        # Close open spot trades
        for t in trade_log:
            if t.get("status") == "open" and t.get("symbol") == symbol and t.get("account") == "spot":
                t["status"] = "closed"
                t["close_reason"] = "api_sell_all"
                t["close_price"] = info["price"]
        _save_trades_to_disk()
    return {"results": results, "total_sold": sum(r["usdt_value"] for r in results if r["success"])}


@app.get("/api/polymarket")
async def api_polymarket():
    CRYPTO_KEYWORDS = ["bitcoin","btc","ethereum","eth","crypto","solana","sol","binance","bnb","xrp","ripple","defi","nft","blockchain","coinbase","stablecoin","altcoin","web3"]
    def is_crypto(title): return any(kw in title.lower() for kw in CRYPTO_KEYWORDS)
    def parse_prices(raw):
        if isinstance(raw, list): return raw
        if isinstance(raw, str):
            try: return json.loads(raw)
            except Exception: return []
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
                except Exception: continue
            result = []
            for e in events:
                title = e.get("title", "")
                if not is_crypto(title): continue
                markets = e.get("markets", [])
                if not markets: continue
                prices_raw = parse_prices(markets[0].get("outcomePrices", "[]"))
                if not prices_raw: continue
                try: yes_prob = round(float(prices_raw[0]) * 100, 1)
                except Exception: continue
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
async def api_ai_chat(req: ChatRequest, request: Request):
    """Proxy for Claude API — solves CORS from browser."""
    # v7.3.3: Rate limiting — защита бюджета Claude API
    client_ip = request.client.host if request.client else "unknown"
    now_ts = time.time()
    rl = _ai_chat_rl.get(client_ip, (0, now_ts))
    if now_ts - rl[1] > _AI_CHAT_WINDOW:
        _ai_chat_rl[client_ip] = (1, now_ts)   # новое окно
    else:
        if rl[0] >= _AI_CHAT_LIMIT:
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Max 20 requests/min.")
        _ai_chat_rl[client_ip] = (rl[0] + 1, rl[1])
    if not ANTHROPIC_API_KEY:
        return {"error": "No AI API keys configured", "success": False}
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
        # v8.3: route through 3-tier AI dispatcher
        ai_result = await ai_dispatch("chat", req.messages[-10:], max_tokens=1000, system=system_prompt)
        if ai_result.get("success"):
            return {"reply": ai_result["text"], "success": True, "model": ai_result.get("model", "?")}
        return {"error": ai_result.get("error", "AI call failed"), "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}


class ManualTrade(BaseModel):
    symbol: str; side: str; size: float; is_futures: bool = False; leverage: int = 3

    def validate_trade(self):
        """v10.0: Validate trade parameters before execution."""
        import re
        if not re.match(r'^[A-Z0-9]+-USDT$', self.symbol.upper()):
            raise HTTPException(400, f"Invalid symbol format: {self.symbol}")
        if self.side.upper() not in ("BUY", "SELL"):
            raise HTTPException(400, f"Invalid side: {self.side}. Must be BUY or SELL")
        if self.size <= 0 or self.size > 100000:
            raise HTTPException(400, f"Invalid size: {self.size}. Must be 0-100000")
        if self.leverage < 1 or self.leverage > 5:
            raise HTTPException(400, f"Invalid leverage: {self.leverage}. Must be 1-5 (per trading.md)")


# In-memory activity log
activity_log = []
def log_activity(msg: str):
    activity_log.append({"ts": datetime.utcnow().isoformat(), "msg": msg})
    if len(activity_log) > 100: activity_log.pop(0)

@app.get("/api/debug/internal")
async def api_debug_internal(_auth=Depends(verify_api_key)):  # v7.3.3: auth required (renamed to avoid duplicate route)
    """Returns last known state for debugging (internal, auth required)."""
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
async def manual_trade(req: ManualTrade, _auth=Depends(verify_api_key)):  # v8.3.0: auth + error handling
    try:
        req.validate_trade()  # v10.0: input validation
        result = await place_futures_order(req.symbol, req.side, int(req.size), req.leverage) if req.is_futures else await place_spot_order(req.symbol, req.side, req.size)
        success = result.get("code") == "200000"
        if success:
            emoji = "🟢" if req.side == "buy" else "🔴"
            await notify(f"{emoji} <b>Ручная сделка</b>\n<code>{req.symbol}</code> {req.side.upper()} · <code>{req.size}</code>")
        return {"success": success, "data": result}
    except Exception as e:
        log_activity(f"[manual_trade] error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/autopilot/{state}")
async def toggle_autopilot(state: str, _auth=Depends(verify_api_key)):  # v8.3.0: auth required
    global AUTOPILOT
    # Accept: "on"/"true"/1 → True; "off"/"false"/0 → False
    AUTOPILOT = state.lower() in ("on", "true", "1", "yes")
    await notify(f"⚙️ Автопилот {'включён ✅' if AUTOPILOT else 'выключен 🔴'} (Mini App)")
    return {"autopilot": AUTOPILOT, "ok": True}

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
    except WebSocketDisconnect:
        log_activity("[websocket] client disconnected normally")
    except Exception as e:
        log_activity(f"[websocket] connection closed: {e}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
