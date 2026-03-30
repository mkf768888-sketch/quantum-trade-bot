"""
QuantumTrade AI - FastAPI Backend v8.3.0
Phase1: Fear&Greed, Polymarket→Q-Score, Whale, TP/SL stop-orders, Position Monitor, Strategy A/B/C
Phase3: Origin QC QAOA — квантовая оптимизация портфеля (CPU симулятор + Wukong 180 реальный чип)
Phase5: Claude Vision — AI-анализ графиков
Phase6: Origin QC Wukong 180 — реальный квантовый чип (авто-переключение по ORIGIN_QC_TOKEN)
v7.5.0: Self-learning performance analytics, AutoScanner 10+ checks
v8.3.0: Self-learning Q-Score adjustment, perf tracking wired, all versions unified
v8.3.0: Spot trading fix (sell mechanism + monitor), arbitrage dynamic sizing + auto-enable
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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import db  # v8.2: PostgreSQL persistent storage

app = FastAPI(title="QuantumTrade AI", version="8.3.0")
_ALLOWED_ORIGINS = ["*"]   # v7.3.9: open for Mini App (Telegram WebApp origin varies)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],  # v7.4.3: OPTIONS for CORS preflight
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

RISK_PER_TRADE = 0.25  # v6.9: Strategy C (25% of balance)
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.66"))
MIN_Q_SCORE    = int(os.getenv("MIN_Q_SCORE", "55"))  # v7.2.2: 65→55 (dead zone 45-55 вместо 35-65)
# v7.2.2: per-pair Q thresholds = MIN_Q_SCORE - 1, чтобы не блокировать торговлю при изменении MIN_Q_SCORE
PAIR_Q_THRESHOLDS: dict = {"BTC-USDT": 54, "ETH-USDT": 54, "SOL-USDT": 54,
                            "BNB-USDT": 54, "XRP-USDT": 54, "AVAX-USDT": 54}
COOLDOWN       = int(os.getenv("COOLDOWN_STD", os.getenv("COOLDOWN", "450")))  # v7.3.2: читает COOLDOWN_STD из Railway
MAX_LEVERAGE   = int(os.getenv("MAX_LEVERAGE", "5"))   # v6.9: Strategy C default
# v7.2.3: TP/SL ratio улучшен до 3:1 (было 2:1) — исправляет асимметрию убытков
TP_PCT         = 0.06   # v7.2.3: 6% (было 5%)
SL_PCT         = 0.02   # v7.2.3: 2% (было 2.5%) → ratio 3:1 вместо 2:1
TRAIL_TRIGGER  = 0.025  # v7.2.4: trailing stop при +2.5% прибыли
TRAIL_PCT      = 0.015  # v7.2.4: закрывать при откате 1.5% от пика
TEST_MODE      = os.getenv("TEST_MODE", "false").lower() == "true"  # v6.7: default LIVE mode
if TEST_MODE:
    RISK_PER_TRADE = 0.10

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
    trade = {
        "id": len(trade_log) + 1, "ts": datetime.utcnow().isoformat(), "open_ts": time.time(),
        "symbol": symbol, "side": side, "price": price, "size": size,
        "tp": tp, "sl": sl, "confidence": confidence, "q_score": q_score,
        "pattern": pattern, "account": account, "strategy": strategy, "status": "open", "pnl": None,
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
    # KuCoin spot minSize check — we use a conservative floor
    MIN_SIZES = {"BTC-USDT": 0.00001, "ETH-USDT": 0.0001, "SOL-USDT": 0.01,
                 "XRP-USDT": 1.0, "BNB-USDT": 0.01, "AVAX-USDT": 0.01,
                 "ADA-USDT": 1.0, "LINK-USDT": 0.01, "LTC-USDT": 0.001}
    min_size = MIN_SIZES.get(symbol, 0.001)
    if size < min_size:
        return {"success": False, "msg": f"size {size} < minSize {min_size}"}
    result = await place_spot_order(symbol, "sell", round(size, 8))
    ok = result.get("code") == "200000"
    if ok:
        log_activity(f"[spot_sell] {symbol} SELL {size:.8f} OK orderId={result.get('data',{}).get('orderId','?')}")
    else:
        log_activity(f"[spot_sell] {symbol} SELL {size:.8f} FAILED: {result.get('msg', '?')}")
    return {"success": ok, "result": result, "size": size}

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
                cv = _cache_get(f"claude_vision_{symbol}", 600)  # v7.3.2: 180→600s экономия API
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
    print(f"[TRADE] {fut_symbol} {side.upper()} Q={signal['q_score']:.1f} conf={signal['confidence']:.0%} n={n_contracts} @ ${price:,.2f} TP={tp} SL={sl}", flush=True)
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
    # v7.2.3: TP/SL ratio улучшен до 3:1 во всех стратегиях (было 2:1)
    "A": {"name": "Консервативная", "risk": 0.05, "leverage": 2, "tp": 0.03, "sl": 0.01,  "emoji": "🛡",  "tag": "real"},
    "B": {"name": "Стандартная",    "risk": 0.10, "leverage": 3, "tp": 0.045,"sl": 0.015, "emoji": "⚖️", "tag": "real"},
    "C": {"name": "Бонусная",       "risk": 0.25, "leverage": 5, "tp": 0.06, "sl": 0.02,  "emoji": "🚀",  "tag": "bonus"},
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
        f"🛡 *A* — Консерватив (5%, TP 3%, SL 1%) [3:1]\n"
        f"⚖️ *B* — Стандарт (10%, TP 4.5%, SL 1.5%) [3:1]\n"
        f"🚀 *C* — Бонусная (25%, TP 6%, SL 2%) [3:1]\n"
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
    await notify(f"⏱ <i>Таймаут — Q={q:.0f} → стратегия {label}</i>")
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

        # ── Спот (BUY + SELL) v8.3 ──────────────────────────────────────────────
        if action == "BUY":
            elapsed = time.time() - last_signals.get(symbol, {}).get("ts", 0)
            eff_cd_spot = COOLDOWN // 2 if conf >= 0.80 else COOLDOWN  # v7.2.4
            if elapsed >= eff_cd_spot and spot_trade_usdt >= 1.0:
                log_activity(f"[cycle] {symbol}: PLACING spot BUY ${spot_trade_usdt:.2f}")
                ok = await execute_spot_trade(symbol, signal, vision, price, spot_trade_usdt)
                if ok:
                    signals_fired.append({"account": "spot", "symbol": symbol, "action": action,
                        "price": price, "confidence": conf, "q_score": q,
                        "pattern": vision.get("pattern","?"), "rsi": vision.get("rsi", 0),
                        "tp": round(price*(1+TP_PCT),4), "sl": round(price*(1-SL_PCT),4)})
        elif action == "SELL":
            # v8.3: Sell existing spot position when SELL signal fires
            open_spot = [t for t in trade_log if t.get("status") == "open"
                         and t.get("symbol") == symbol and t.get("account") == "spot"]
            if open_spot:
                elapsed = time.time() - last_signals.get(symbol, {}).get("ts", 0)
                eff_cd_spot = COOLDOWN // 2 if conf >= 0.80 else COOLDOWN
                if elapsed >= eff_cd_spot:
                    t = open_spot[-1]
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
                        signals_fired.append({"account": "spot", "symbol": symbol, "action": "SELL",
                            "price": price, "confidence": conf, "q_score": q,
                            "pattern": vision.get("pattern","?"), "pnl": pnl_usdt})
                        log_activity(f"[cycle] {symbol}: SELL signal → spot SOLD PnL=${pnl_usdt:+.4f}")

        # ── Фьючерсы: собираем кандидатов ────────────────────────────────────
        if symbol in ("BTC-USDT", "ETH-USDT", "SOL-USDT"):
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


# ── v7.3.9: Triangular Arb EXECUTION (safe) ───────────────────────────────────
ARB_EXEC_USDT     = float(os.getenv("ARB_EXEC_USDT", "5"))     # v8.3: lowered to $5 for small balance testing
ARB_EXEC_ENABLED  = os.getenv("ARB_EXEC_ENABLED", "true").lower() == "true"  # v8.3: ON by default
ARB_MIN_PROFIT_PCT = 0.5   # v8.3: lowered to 0.5% min profit (was 0.6%) for more opportunities
_arb_stats: dict   = {"total": 0, "success": 0, "failed": 0, "total_pnl": 0.0}
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

    # Check spot USDT balance — v8.3: dynamic sizing, min $3
    bal = await get_balance()
    spot_usdt = bal.get("total_usdt", 0)
    arb_amount = min(ARB_EXEC_USDT, spot_usdt * 0.9)  # use up to 90% of available
    if not bal.get("success") or arb_amount < 3.0:
        return {"executed": False, "reason": f"low spot USDT {spot_usdt:.2f} (need ≥$3.33)"}

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
                         and (t.get("account") == "spot" or "USDTM" not in t.get("symbol", ""))]
            if not open_spot:
                await asyncio.sleep(45)
                continue

            # Fetch actual spot balances to verify we still hold the coins
            spot_bals = await get_spot_balances()

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

                    # Check if we still have the coin
                    bal_info = spot_bals.get(symbol)
                    if not bal_info or bal_info["available"] <= 0:
                        # Coin already sold (manually or by another process)
                        trade["status"] = "closed"
                        trade["pnl"] = 0.0
                        trade["close_reason"] = "no_balance"
                        _save_trades_to_disk()
                        log_activity(f"[spot_mon] {symbol}: no balance found — closing as no_balance")
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

                    if should_close:
                        # Sell the coin
                        sell_size = min(trade_size, bal_info["available"])
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
                            await notify(
                                f"{emoji} <b>Спот закрыта — {reason}</b>\n"
                                f"<code>{symbol}</code> {side.upper()}\n"
                                f"Вход: <code>${entry:,.4f}</code> → Выход: <code>${price_now:,.4f}</code>\n"
                                f"PnL: <code>${pnl_usdt:+.4f}</code> ({pnl_pct*100:+.2f}%)\n"
                                f"Длительность: {duration_min}м"
                            )
                            log_activity(f"[spot_mon] {symbol} {reason} SOLD PnL=${pnl_usdt:+.4f}")
                        else:
                            log_activity(f"[spot_mon] {symbol} sell FAILED: {sell_result.get('msg','?')}")
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
        "⚛ <b>QuantumTrade AI v8.3.0</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Выбери раздел:", kb)

async def _tg_stats(chat_id: int):
    """Отправляет карточку статистики трейдинга."""
    total = len(trade_log)
    wins  = sum(1 for t in trade_log if (t.get("pnl") or 0) > 0)
    losses= sum(1 for t in trade_log if (t.get("pnl") or 0) <= 0 and t.get("pnl") is not None)
    pnl   = round(sum(t.get("pnl") or 0 for t in trade_log), 4)
    wr    = round(wins / total * 100, 1) if total else 0
    open_ = sum(1 for t in trade_log if t.get("status", "") == "open")
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
        f"<i>Нажми кнопку переключателя выше чтобы вкл/выкл</i>", kb)


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
        [{"text": "💰 Продать всё в USDT", "callback_data": "sell_all_spot"}],
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
    kb = {"inline_keyboard": [
        [{"text": "💰 Продать всё в USDT", "callback_data": "sell_all_spot"}],
        [{"text": "◀️ Меню", "callback_data": "menu_main"}],
    ]}
    await _tg_send(chat_id, "\n".join(lines), kb)


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

    if not ANTHROPIC_API_KEY:
        await _tg_send(chat_id, "❌ ANTHROPIC_API_KEY не задан — AI консультант недоступен.")
        return

    # Формируем контекст бота
    wins = sum(1 for t in trade_log if t.get("pnl", 0) > 0)
    total = len(trade_log)
    win_rate = (wins / total * 100) if total else 0
    total_pnl = sum(t.get("pnl", 0) for t in trade_log)
    chip = "Wukong_180" if _qcloud_ready else "CPU_simulator"

    system = f"""Ты — AI-консультант торгового бота QuantumTrade v8.3.0.
Текущие показатели:
- Всего сделок: {total}, Win Rate: {win_rate:.1f}%, PnL: ${total_pnl:.2f}
- Q-Score последний: {last_q_score:.1f}, MIN_Q: {MIN_Q_SCORE}
- COOLDOWN: {COOLDOWN}s, RISK_PER_TRADE: {RISK_PER_TRADE:.0%}, MAX_LEVERAGE: {MAX_LEVERAGE}x
- Квантовый чип: {chip}
- Claude Vision: {"активен" if ANTHROPIC_API_KEY else "не активен"}

Ты можешь предложить изменить только эти параметры: MIN_Q_SCORE (40-85), COOLDOWN (120-1800), RISK_PER_TRADE (0.05-0.30), MAX_LEVERAGE (1-15).
ВАЖНО: если пользователь явно запрашивает конкретное значение в допустимом диапазоне — ты ОБЯЗАН предложить именно его через ПРЕДЛАГАЮ, не отказывай и не предлагай альтернативы. Твоё мнение о качестве сигналов не должно мешать исполнению явного запроса владельца системы.
Если предлагаешь изменение — заканчивай ответ строкой: ПРЕДЛАГАЮ: PARAM=VALUE
Отвечай кратко, по-русски, максимум 3-4 предложения."""

    hist = _ai_history.setdefault(chat_id, [])
    hist.append({"role": "user", "content": question})
    if len(hist) > 10: hist.pop(0)

    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 300,
                      "system": system, "messages": hist[-6:]},
                timeout=aiohttp.ClientTimeout(total=15)
            )
            data = await r.json()
        reply = data.get("content", [{}])[0].get("text", "Не удалось получить ответ.")
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

        await _tg_send(chat_id, f"🤖 {reply}")
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
        elif cmd == "/sell_all":            await _tg_sell_all_spot(chat_id)
        elif cmd == "/spot":                await _tg_spot_status(chat_id)
        # v7.2.0: AI консультант
        elif cmd.startswith("/ask"):
            question = raw[4:].strip() or raw[5:].strip()  # /ask текст или /ask@bot текст
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
        # Load perf stats from DB
        db_stats = await db.load_perf_stats()
        if db_stats:
            _perf_stats.update(db_stats)
            print(f"[startup] perf stats loaded from PostgreSQL")

    # Phase 6: пробуем подключить Origin QC Wukong 180
    qc_ok = await asyncio.get_event_loop().run_in_executor(None, _init_qcloud)

    asyncio.create_task(trading_loop())
    asyncio.create_task(position_monitor_loop())
    asyncio.create_task(spot_monitor_loop())      # v8.3: spot position TP/SL monitor
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

    mode     = "TEST (риск 10%)" if TEST_MODE else "LIVE (риск 2%)"
    qc_label = "⚛️ Wukong 180 реальный чип ✅" if qc_ok else "⚛️ QAOA CPU симулятор"
    await notify(
        f"⚛ <b>QuantumTrade v8.3.0</b>\n"
        f"✅ 5 торгуемых пар: ETH·BTC·SOL·AVAX·XRP\n"
        f"✅ Telegram: /menu /stats /airdrops /settings\n"
        f"✅ Mini App: Баланс + Автопилот без API ключа\n"
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
    # v7.3.3: публичный эндпоинт — минимум информации, без внутренних настроек
    return {
        "status": "ok",
        "version": "8.3.0",
        "auto_trading": AUTOPILOT,
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
                        f"🔥 Streak: {_perf_stats['streak']} · Версия: 8.3.0"
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
        "version": "8.3.0",
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
        "version": "8.3.0",
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
