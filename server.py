"""
QuantumTrade AI - FastAPI Backend v7.2.3
Phase1: Fear&Greed, PolymarketâQ-Score, Whale, TP/SL stop-orders, Position Monitor, Strategy A/B/C
Phase3: Origin QC QAOA â ÐºÐ²Ð°Ð½ÑÐ¾Ð²Ð°Ñ Ð¾Ð¿ÑÐ¸Ð¼Ð¸Ð·Ð°ÑÐ¸Ñ Ð¿Ð¾ÑÑÑÐµÐ»Ñ (CPU ÑÐ¸Ð¼ÑÐ»ÑÑÐ¾Ñ + Wukong 180 ÑÐµÐ°Ð»ÑÐ½ÑÐ¹ ÑÐ¸Ð¿)
Phase5: Claude Vision â AI-Ð°Ð½Ð°Ð»Ð¸Ð· Ð³ÑÐ°ÑÐ¸ÐºÐ¾Ð²
Phase6: Origin QC Wukong 180 â ÑÐµÐ°Ð»ÑÐ½ÑÐ¹ ÐºÐ²Ð°Ð½ÑÐ¾Ð²ÑÐ¹ ÑÐ¸Ð¿ (Ð°Ð²ÑÐ¾-Ð¿ÐµÑÐµÐºÐ»ÑÑÐµÐ½Ð¸Ðµ Ð¿Ð¾ ORIGIN_QC_TOKEN)
v7.2.3: PnL fix â ÑÐµÐ°Ð»ÑÐ½Ð°Ñ ÑÐµÐ½Ð° Ð·Ð°ÐºÑÑÑÐ¸Ñ Ð¸Ð· KuCoin fills; TP/SL ratio 3:1 (Ð±ÑÐ»Ð¾ 2:1)
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

app = FastAPI(title="QuantumTrade AI", version="7.2.0")
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
RAILWAY_TOKEN     = os.getenv("RAILWAY_TOKEN", "")       # v7.2.1: Railway API â persist variable changes
WEBAPP_URL        = os.getenv("WEBAPP_URL", "https://mkf768888-sketch.github.io/quantum-trade-ui/")  # v7.2.2: GitHub Pages frontend

RISK_PER_TRADE = 0.25  # v6.9: Strategy C (25% of balance)
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.66"))
MIN_Q_SCORE    = int(os.getenv("MIN_Q_SCORE", "55"))  # v7.2.2: 65â55 (dead zone 45-55 Ð²Ð¼ÐµÑÑÐ¾ 35-65)
# v7.2.2: per-pair Q thresholds = MIN_Q_SCORE - 1, ÑÑÐ¾Ð±Ñ Ð½Ðµ Ð±Ð»Ð¾ÐºÐ¸ÑÐ¾Ð²Ð°ÑÑ ÑÐ¾ÑÐ³Ð¾Ð²Ð»Ñ Ð¿ÑÐ¸ Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½Ð¸Ð¸ MIN_Q_SCORE
PAIR_Q_THRESHOLDS: dict = {"BTC-USDT": 54, "ETH-USDT": 54, "SOL-USDT": 54,
                            "BNB-USDT": 54, "XRP-USDT": 54, "AVAX-USDT": 54}
COOLDOWN       = int(os.getenv("COOLDOWN", "450"))   # v7.2.2: 600â450s (Ð±Ð°Ð»Ð°Ð½Ñ ÑÐ°ÑÑÐ¾ÑÑ Ð¸ ÐºÐ°ÑÐµÑÑÐ²Ð°)
MAX_LEVERAGE   = int(os.getenv("MAX_LEVERAGE", "5"))   # v6.9: Strategy C default
# v7.2.3: TP/SL ratio ÑÐ»ÑÑÑÐµÐ½ Ð´Ð¾ 3:1 (Ð±ÑÐ»Ð¾ 2:1) â Ð¸ÑÐ¿ÑÐ°Ð²Ð»ÑÐµÑ Ð°ÑÐ¸Ð¼Ð¼ÐµÑÑÐ¸Ñ ÑÐ±ÑÑÐºÐ¾Ð²
TP_PCT         = 0.06   # v7.2.3: 6% (Ð±ÑÐ»Ð¾ 5%)
SL_PCT         = 0.02   # v7.2.3: 2% (Ð±ÑÐ»Ð¾ 2.5%) â ratio 3:1 Ð²Ð¼ÐµÑÑÐ¾ 2:1
TEST_MODE      = os.getenv("TEST_MODE", "false").lower() == "true"  # v6.7: default LIVE mode
if TEST_MODE:
    RISK_PER_TRADE = 0.10

AUTOPILOT  = True
SPOT_PAIRS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT", "AVAX-USDT"]
FUT_PAIRS  = ["XBTUSDTM", "ETHUSDTM", "SOLUSDTM"]

last_signals  = {}
last_q_score  = 0.0
_q_alert_last: dict = {}   # v7.2.2: Ð°Ð½ÑÐ¸ÑÐ¿Ð°Ð¼ Ð´Ð»Ñ Q-Ð°Ð»ÐµÑÑÐ¾Ð² {"sell": ts, "buy": ts}
trade_log: List[dict] = []

# ââ ÐÐµÑÑÐ¸ÑÑÐµÐ½ÑÐ½Ð¾Ðµ ÑÑÐ°Ð½Ð¸Ð»Ð¸ÑÐµ ÑÐ´ÐµÐ»Ð¾Ðº âââââââââââââââââââââââââââââââââââââââââââââ
# ÐÑÐ¶Ð¸Ð²Ð°ÐµÑ Ð¿ÑÐ¸ ÑÐµÐ´ÐµÐ¿Ð»Ð¾Ðµ â Ð¿Ð¸ÑÐµÐ¼ Ð² /tmp/trades.json (Railway ephemeral storage)
_TRADES_FILE = "/tmp/qt_trades.json"

def _load_trades_from_disk():
    """ÐÐ°Ð³ÑÑÐ¶Ð°ÐµÐ¼ Ð¸ÑÑÐ¾ÑÐ¸Ñ ÑÐ´ÐµÐ»Ð¾Ðº Ð¿ÑÐ¸ ÑÑÐ°ÑÑÐµ."""
    global trade_log
    try:
        if os.path.exists(_TRADES_FILE):
            with open(_TRADES_FILE, "r") as f:
                trade_log = json.load(f)
            print(f"[trades] Ð·Ð°Ð³ÑÑÐ¶ÐµÐ½Ð¾ {len(trade_log)} ÑÐ´ÐµÐ»Ð¾Ðº Ð¸Ð· {_TRADES_FILE}")
    except Exception as e:
        print(f"[trades] Ð¾ÑÐ¸Ð±ÐºÐ° Ð·Ð°Ð³ÑÑÐ·ÐºÐ¸: {e}")

def _save_trades_to_disk():
    """Ð¡Ð¾ÑÑÐ°Ð½ÑÐµÐ¼ trade_log Ð½Ð° Ð´Ð¸ÑÐº Ð¿Ð¾ÑÐ»Ðµ ÐºÐ°Ð¶Ð´Ð¾Ð¹ Ð½Ð¾Ð²Ð¾Ð¹ ÑÐ´ÐµÐ»ÐºÐ¸."""
    try:
        with open(_TRADES_FILE, "w") as f:
            json.dump(trade_log[-500:], f)  # ÑÑÐ°Ð½Ð¸Ð¼ Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ðµ 500
    except Exception as e:
        print(f"[trades] Ð¾ÑÐ¸Ð±ÐºÐ° Ð·Ð°Ð¿Ð¸ÑÐ¸: {e}")

# ââ QAOA State âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
_quantum_bias: Dict[str, float] = {}   # symbol â bias [-15..+15]
_quantum_ts: float = 0.0               # timestamp Ð¿Ð¾ÑÐ»ÐµÐ´Ð½ÐµÐ³Ð¾ Ð·Ð°Ð¿ÑÑÐºÐ°

# v7.2.0: QAOA rolling average smoother (Ð¾ÐºÐ½Ð¾=3, clamp=Â±5 Ð½Ð° CPU, Â±15 Ð½Ð° ÑÐ¸Ð¿Ðµ)
_qaoa_history: Dict[str, list] = {}    # symbol â Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ðµ N Ð·Ð½Ð°ÑÐµÐ½Ð¸Ð¹
_QAOA_WINDOW = 3

def _smooth_qaoa_bias(symbol: str, raw_bias: float, clamp: float = 15.0) -> float:
    """Rolling average + clamp Ð´Ð»Ñ QAOA bias. Ð£Ð±Ð¸ÑÐ°ÐµÑ ÑÑÐ¼ CPU ÑÐ¸Ð¼ÑÐ»ÑÑÐ¾ÑÐ°."""
    hist = _qaoa_history.setdefault(symbol, [])
    hist.append(max(-clamp, min(clamp, raw_bias)))
    if len(hist) > _QAOA_WINDOW:
        hist.pop(0)
    return round(sum(hist) / len(hist), 2)

# ââ Phase 6: Origin QC Wukong 180 ââââââââââââââââââââââââââââââââââââââââââââââ
_qcloud_ready: bool = False            # True Ð¿Ð¾ÑÐ»Ðµ ÑÑÐ¿ÐµÑÐ½Ð¾Ð¹ Ð¸Ð½Ð¸ÑÐ¸Ð°Ð»Ð¸Ð·Ð°ÑÐ¸Ð¸ ÑÐ¸Ð¿Ð°
_qvm_instance = None                   # Ð³Ð»Ð¾Ð±Ð°Ð»ÑÐ½ÑÐ¹ Ð¸Ð½ÑÑÐ°Ð½Ñ QCloud (Ð»ÐµÐ½Ð¸Ð²Ð°Ñ init)


def _init_qcloud() -> bool:
    """
    ÐÑÑÐ°ÐµÑÑÑ Ð¿Ð¾Ð´ÐºÐ»ÑÑÐ¸ÑÑÑÑ Ðº Origin QC Wukong 180 ÑÐµÑÐµÐ· pyqpanda3.
    ÐÑÐ·ÑÐ²Ð°ÐµÑÑÑ Ð¿ÑÐ¸ ÑÑÐ°ÑÑÐµ, ÐµÑÐ»Ð¸ ORIGIN_QC_TOKEN Ð·Ð°Ð´Ð°Ð½.
    ÐÐ¾Ð·Ð²ÑÐ°ÑÐ°ÐµÑ True Ð¿ÑÐ¸ ÑÑÐ¿ÐµÑÐµ, False â CPU fallback.
    """
    global _qcloud_ready, _qvm_instance
    if not ORIGIN_QC_TOKEN:
        print("[qaoa] ORIGIN_QC_TOKEN Ð½Ðµ Ð·Ð°Ð´Ð°Ð½ â CPU ÑÐ¸Ð¼ÑÐ»ÑÑÐ¾Ñ")
        return False
    try:
        from pyqpanda3 import QCloud, QMachineType  # type: ignore
        qvm = QCloud()
        qvm.init_qvm(ORIGIN_QC_TOKEN, QMachineType.Wukong)
        qvm.set_chip_id("72")  # Wukong-180: Ð¿ÑÐ±Ð»Ð¸ÑÐ½ÑÐ¹ ÑÐ¸Ð¿ #72
        _qvm_instance = qvm
        _qcloud_ready = True
        print("[qaoa] â Origin QC Wukong 180 Ð¿Ð¾Ð´ÐºÐ»ÑÑÑÐ½ (chip_id=72)")
        return True
    except ImportError:
        print("[qaoa] pyqpanda3 Ð½Ðµ ÑÑÑÐ°Ð½Ð¾Ð²Ð»ÐµÐ½ â CPU fallback")
    except Exception as e:
        print(f"[qaoa] Origin QC Ð¾ÑÐ¸Ð±ÐºÐ° Ð¸Ð½Ð¸ÑÐ¸Ð°Ð»Ð¸Ð·Ð°ÑÐ¸Ð¸: {e} â CPU fallback")
    _qcloud_ready = False
    return False


# ââ QAOA Module (Phase 3 + Phase 6: Origin QC) âââââââââââââââââââââââââââââââââ
# CPU-ÑÐ¸Ð¼ÑÐ»ÑÑÐ¾Ñ Ð°ÐºÑÐ¸Ð²ÐµÐ½ Ð¿Ð¾ ÑÐ¼Ð¾Ð»ÑÐ°Ð½Ð¸Ñ.
# ÐÑÐ¸ Ð½Ð°Ð»Ð¸ÑÐ¸Ð¸ ORIGIN_QC_TOKEN Ð¸ pyqpanda3 â Ð°Ð²ÑÐ¾-Ð¿ÐµÑÐµÐºÐ»ÑÑÐµÐ½Ð¸Ðµ Ð½Ð° Wukong 180.
#
# ÐÐ¾ÑÑÐµÐ»ÑÑÐ¸Ð¾Ð½Ð½Ð°Ñ Ð¼Ð°ÑÑÐ¸ÑÐ° (BTC ETH SOL BNB XRP AVAX)
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
    QAOA CPU ÑÐ¸Ð¼ÑÐ»ÑÑÐ¾Ñ: Ð¾Ð¿ÑÐ¸Ð¼Ð¸Ð·Ð¸ÑÑÐµÑ Ð¿Ð¾ÑÑÑÐµÐ»ÑÐ½ÑÐµ Ð²ÐµÑÐ° Ñ ÑÑÑÑÐ¾Ð¼ ÐºÐ¾ÑÑÐµÐ»ÑÑÐ¸Ð¹.
    ÐÐ¾Ð·Ð²ÑÐ°ÑÐ°ÐµÑ bias [-15..+15] Ð´Ð»Ñ ÐºÐ°Ð¶Ð´Ð¾Ð¹ Ð¿Ð°ÑÑ.
    p_layers: Ð³Ð»ÑÐ±Ð¸Ð½Ð° ÑÑÐµÐ¼Ñ (1-3, Ð±Ð¾Ð»ÑÑÐµ = ÑÐ¾ÑÐ½ÐµÐµ, Ð¼ÐµÐ´Ð»ÐµÐ½Ð½ÐµÐµ).
    """
    n = N_PAIRS

    # 1. Ð¡ÑÑÐ¾Ð¸Ð¼ QUBO Ð¼Ð°ÑÑÐ¸ÑÑ Ð·Ð°Ð´Ð°ÑÐ¸ Ð¼Ð°ÐºÑÐ¸Ð¼Ð¸Ð·Ð°ÑÐ¸Ð¸ Ð¨Ð°ÑÐ¿Ð°
    # Q_ij = corr[i][j] (ÑÑÑÐ°Ñ Ð·Ð° ÐºÐ¾ÑÑÐµÐ»Ð¸ÑÐ¾Ð²Ð°Ð½Ð½ÑÐµ Ð¿Ð¾Ð·Ð¸ÑÐ¸Ð¸)
    # ÐÐ¸Ð½ÐµÐ¹Ð½ÑÐ¹ ÑÐ»ÐµÐ½: -momentum[i] (Ð½Ð°Ð³ÑÐ°Ð´Ð° Ð·Ð° ÑÐ¸Ð»ÑÐ½ÑÐ¹ ÑÑÐµÐ½Ð´)
    momentum = [max(-1.0, min(1.0, pc / 5.0)) for pc in price_changes]

    # 2. ÐÐ½Ð¸ÑÐ¸Ð°Ð»Ð¸Ð·Ð¸ÑÑÐµÐ¼ ÑÐ³Ð»Ñ QAOA (gamma, beta) ÑÐ»ÑÑÐ°Ð¹Ð½Ð¾ Ñ seed
    random.seed(int(time.time()) // 900)  # Ð¼ÐµÐ½ÑÐµÑÑÑ ÑÐ°Ð· Ð² 15 Ð¼Ð¸Ð½
    gamma = [random.uniform(0.1, math.pi) for _ in range(p_layers)]
    beta  = [random.uniform(0.1, math.pi / 2) for _ in range(p_layers)]

    # 3. Ð¡Ð¸Ð¼ÑÐ»Ð¸ÑÑÐµÐ¼ ÐºÐ²Ð°Ð½ÑÐ¾Ð²Ð¾Ðµ ÑÐ¾ÑÑÐ¾ÑÐ½Ð¸Ðµ (ÑÐ¿ÑÐ¾ÑÑÐ½Ð½Ð°Ñ vector sim)
    # |Ïâ© = H^n|0â© â apply U_C(Î³) â U_B(Î²) â measure
    # ÐÐ°ÑÐ°Ð»ÑÐ½Ð¾Ðµ ÑÐ¾ÑÑÐ¾ÑÐ½Ð¸Ðµ: ÑÑÐ¿ÐµÑÐ¿Ð¾Ð·Ð¸ÑÐ¸Ñ Ð²ÑÐµÑ 2^n Ð±Ð¸ÑÐ¾Ð²ÑÑ ÑÑÑÐ¾Ðº
    state_size = 1 << n  # 64 ÑÐ¾ÑÑÐ¾ÑÐ½Ð¸Ñ Ð´Ð»Ñ 6 ÐºÑÐ±Ð¸ÑÐ¾Ð²
    amplitudes = [complex(1.0 / math.sqrt(state_size))] * state_size

    for layer in range(p_layers):
        # U_C(Î³): Ð¿ÑÐ¸Ð¼ÐµÐ½ÑÐµÐ¼ cost unitary
        new_amp = [complex(0)] * state_size
        for s in range(state_size):
            bits = [(s >> i) & 1 for i in range(n)]
            # cost = -Î£ momentum[i]*bits[i] + Î³*Î£ corr[i][j]*bits[i]*bits[j]
            cost = 0.0
            for i in range(n):
                cost -= momentum[i] * bits[i]
                for j in range(i + 1, n):
                    cost += gamma[layer] * CORR_MATRIX[i][j] * bits[i] * bits[j]
            phase = complex(math.cos(cost), -math.sin(cost))
            new_amp[s] = amplitudes[s] * phase
        amplitudes = new_amp

        # U_B(Î²): mixing unitary (X-rotation Ð½Ð° ÐºÐ°Ð¶Ð´Ð¾Ð¼ ÐºÑÐ±Ð¸ÑÐµ)
        for q in range(n):
            new_amp = [complex(0)] * state_size
            cos_b = math.cos(beta[layer])
            sin_b = math.sin(beta[layer])
            for s in range(state_size):
                # flip Ð±Ð¸Ñ q
                s_flip = s ^ (1 << q)
                new_amp[s] += amplitudes[s] * complex(cos_b, 0)
                new_amp[s] += amplitudes[s_flip] * complex(0, sin_b)
            amplitudes = new_amp

    # 4. ÐÑÑÐ¸ÑÐ»ÑÐµÐ¼ Ð¾Ð¶Ð¸Ð´Ð°ÐµÐ¼Ð¾Ðµ Ð·Ð½Ð°ÑÐµÐ½Ð¸Ðµ <Z_i> Ð´Ð»Ñ ÐºÐ°Ð¶Ð´Ð¾Ð³Ð¾ ÐºÑÐ±Ð¸ÑÐ°
    z_exp = [0.0] * n
    for s in range(state_size):
        prob = (amplitudes[s] * amplitudes[s].conjugate()).real
        bits = [(s >> i) & 1 for i in range(n)]
        for i in range(n):
            z_exp[i] += prob * (1 - 2 * bits[i])  # +1 ÐµÑÐ»Ð¸ bit=0, -1 ÐµÑÐ»Ð¸ bit=1

    # 5. ÐÐ¾Ð½Ð²ÐµÑÑÐ¸ÑÑÐµÐ¼ Ð² bias [-15..+15]
    # z_exp[i] â [-1..+1] â bias = z_exp * 15 * momentum_sign
    bias = []
    for i in range(n):
        b = z_exp[i] * 15.0
        # Ð£ÑÐ¸Ð»Ð¸Ð²Ð°ÐµÐ¼ ÑÐ¸Ð³Ð½Ð°Ð» Ð² Ð½Ð°Ð¿ÑÐ°Ð²Ð»ÐµÐ½Ð¸Ð¸ momentum
        if momentum[i] > 0.1:
            b = abs(b)
        elif momentum[i] < -0.1:
            b = -abs(b)
        bias.append(round(b, 1))

    return bias


def _qaoa_wukong_run(price_changes: List[float], p_layers: int = 1) -> List[float]:
    """
    Phase 6: QAOA Ð½Ð° ÑÐµÐ°Ð»ÑÐ½Ð¾Ð¼ ÑÐ¸Ð¿Ðµ Origin Wukong 180.
    Ð¡ÑÑÐ¾Ð¸Ñ 6-ÐºÑÐ±Ð¸ÑÐ½ÑÑ QAOA ÑÑÐµÐ¼Ñ, Ð¾ÑÐ¿ÑÐ°Ð²Ð»ÑÐµÑ Ð½Ð° Ð°Ð¿Ð¿Ð°ÑÐ°ÑÐ½ÑÐ¹ ÑÐ¸Ð¿, Ð¿Ð°ÑÑÐ¸Ñ Ð³Ð¸ÑÑÐ¾Ð³ÑÐ°Ð¼Ð¼Ñ.
    p_layers=1 (Ð½Ð° ÑÐµÐ°Ð»ÑÐ½Ð¾Ð¼ Ð¶ÐµÐ»ÐµÐ·Ðµ ÑÑÐ¼ ÑÐ°ÑÑÑÑ Ñ Ð³Ð»ÑÐ±Ð¸Ð½Ð¾Ð¹ â Ð¸ÑÐ¿Ð¾Ð»ÑÐ·ÑÐµÐ¼ p=1).
    ÐÐ¾Ð·Ð²ÑÐ°ÑÐ°ÐµÑ bias [-15..+15] Ð´Ð»Ñ ÐºÐ°Ð¶Ð´Ð¾Ð¹ Ð¿Ð°ÑÑ.
    Ð¢ÑÐµÐ±ÑÐµÑ: _qcloud_ready=True Ð¸ _qvm_instance Ð¸Ð½Ð¸ÑÐ¸Ð°Ð»Ð¸Ð·Ð¸ÑÐ¾Ð²Ð°Ð½.
    """
    from pyqpanda3 import QProg, H, Rz, Rx, CNOT, measure_all  # type: ignore

    n = N_PAIRS  # 6 ÐºÑÐ±Ð¸ÑÐ¾Ð²
    momentum = [max(-1.0, min(1.0, pc / 5.0)) for pc in price_changes]

    # ÐÐ¿ÑÐ¸Ð¼Ð°Ð»ÑÐ½ÑÐµ ÑÐ³Ð»Ñ QAOA p=1 (Ð¿ÑÐµÐ´Ð²Ð°ÑÐ¸ÑÐµÐ»ÑÐ½Ð¾ Ð¾ÑÐºÐ°Ð»Ð¸Ð±ÑÐ¾Ð²Ð°Ð½Ñ Ð½Ð° CPU)
    gamma = 0.8   # cost unitary angle
    beta  = 0.4   # mixing unitary angle

    # ââ Ð¡ÑÑÐ¾Ð¸Ð¼ ÐºÐ²Ð°Ð½ÑÐ¾Ð²ÑÑ ÑÑÐµÐ¼Ñ QAOA ââââââââââââââââââââââââââââââââââââââââââ
    qv  = _qvm_instance.allocate_qubit(n)    # 6 ÐºÑÐ±Ð¸ÑÐ¾Ð²
    cv  = _qvm_instance.allocate_cbit(n)     # 6 ÐºÐ»Ð°ÑÑÐ¸ÑÐµÑÐºÐ¸Ñ Ð±Ð¸Ñ Ð´Ð»Ñ Ð¸Ð·Ð¼ÐµÑÐµÐ½Ð¸Ð¹
    prog = QProg()

    # ÐÐ½Ð¸ÑÐ¸Ð°Ð»Ð¸Ð·Ð°ÑÐ¸Ñ: ÑÑÐ¿ÐµÑÐ¿Ð¾Ð·Ð¸ÑÐ¸Ñ H^â6|0â©
    for i in range(n):
        prog << H(qv[i])

    # Cost unitary U_C(Î³):
    # ZZ-Ð²Ð·Ð°Ð¸Ð¼Ð¾Ð´ÐµÐ¹ÑÑÐ²Ð¸Ðµ Ð´Ð»Ñ ÐºÐ¾ÑÑÐµÐ»Ð¸ÑÐ¾Ð²Ð°Ð½Ð½ÑÑ Ð¿Ð°Ñ (ÑÐ¾Ð»ÑÐºÐ¾ ÑÐ¸Ð»ÑÐ½ÑÐµ ÑÐ²ÑÐ·Ð¸ corr > 0.5)
    for i in range(n):
        for j in range(i + 1, n):
            if CORR_MATRIX[i][j] > 0.5:
                angle = 2.0 * gamma * CORR_MATRIX[i][j]
                prog << CNOT(qv[i], qv[j])
                prog << Rz(qv[j], angle)
                prog << CNOT(qv[i], qv[j])
    # ÐÐ¸Ð½ÐµÐ¹Ð½ÑÐµ ÑÐ»ÐµÐ½Ñ: momentum bias
    for i in range(n):
        prog << Rz(qv[i], -2.0 * gamma * momentum[i])

    # Mixing unitary U_B(Î²): X-ÑÐ¾ÑÐ°ÑÐ¸Ð¸
    for i in range(n):
        prog << Rx(qv[i], 2.0 * beta)

    # ÐÐ·Ð¼ÐµÑÐµÐ½Ð¸Ñ
    prog << measure_all(qv, cv)

    # ââ ÐÐ°Ð¿ÑÑÐº Ð½Ð° ÑÐµÐ°Ð»ÑÐ½Ð¾Ð¼ ÑÐ¸Ð¿Ðµ (1024 Ð²ÑÐ±Ð¾ÑÐºÐ¸) âââââââââââââââââââââââââââââââ
    result = _qvm_instance.run_with_configuration(prog, cv, 1024)
    # result: dict[str, int], ÐºÐ»ÑÑ = Ð±Ð¸ÑÐ¾Ð²Ð°Ñ ÑÑÑÐ¾ÐºÐ° "010110", Ð·Ð½Ð°ÑÐµÐ½Ð¸Ðµ = ÐºÐ¾Ð»-Ð²Ð¾

    # ÐÑÑÐ¸ÑÐ»ÑÐµÐ¼ <Z_i> Ð¸Ð· Ð³Ð¸ÑÑÐ¾Ð³ÑÐ°Ð¼Ð¼Ñ
    z_exp = [0.0] * n
    total_shots = sum(result.values()) if result else 0
    if total_shots > 0:
        for bitstring, count in result.items():
            # Wukong Ð²Ð¾Ð·Ð²ÑÐ°ÑÐ°ÐµÑ ÑÑÑÐ¾ÐºÑ MSB-first: bitstring[0] = ÐºÑÐ±Ð¸Ñ 0
            for i in range(min(n, len(bitstring))):
                bit = int(bitstring[i])
                z_exp[i] += (count / total_shots) * (1 - 2 * bit)  # +1â0, -1â1
    else:
        print("[qaoa_wukong] Ð¿ÑÑÑÐ¾Ð¹ ÑÐµÐ·ÑÐ»ÑÑÐ°Ñ â Ð²Ð¾Ð·Ð²ÑÐ°ÑÐ°ÐµÐ¼ Ð½ÑÐ»Ð¸")
        return [0.0] * n

    # ÐÐ¾Ð½Ð²ÐµÑÑÐ¸ÑÑÐµÐ¼ Ð² bias [-15..+15], ÑÑÐ¸Ð»Ð¸Ð²Ð°ÐµÐ¼ Ð² Ð½Ð°Ð¿ÑÐ°Ð²Ð»ÐµÐ½Ð¸Ð¸ momentum
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
    Phase 3 + Phase 6: QAOA Ð¾Ð¿ÑÐ¸Ð¼Ð¸Ð·Ð°ÑÐ¸Ñ Ñ Ð°Ð²ÑÐ¾-Ð²ÑÐ±Ð¾ÑÐ¾Ð¼ Ð±ÑÐºÐµÐ½Ð´Ð°.
    - ÐÑÐ»Ð¸ ORIGIN_QC_TOKEN Ð·Ð°Ð´Ð°Ð½ Ð¸ pyqpanda3 Ð´Ð¾ÑÑÑÐ¿ÐµÐ½ â ÑÐµÐ°Ð»ÑÐ½ÑÐ¹ ÑÐ¸Ð¿ Wukong 180
    - ÐÐ½Ð°ÑÐµ â CPU ÑÐ¸Ð¼ÑÐ»ÑÑÐ¾Ñ (6 ÐºÑÐ±Ð¸ÑÐ¾Ð², p=2)
    ÐÐ±Ð½Ð¾Ð²Ð»ÑÐµÑ Ð³Ð»Ð¾Ð±Ð°Ð»ÑÐ½ÑÐ¹ _quantum_bias. ÐÑÐ·ÑÐ²Ð°ÐµÑÑÑ ÐºÐ°Ð¶Ð´ÑÐµ 15 Ð¼Ð¸Ð½ÑÑ.
    """
    global _quantum_bias, _quantum_ts
    changes_list = [price_changes.get(p, 0.0) for p in PAIR_NAMES]
    chip_used = "CPU_simulator"
    try:
        if _qcloud_ready and _qvm_instance is not None:
            # ââ Phase 6: ÑÐµÐ°Ð»ÑÐ½ÑÐ¹ ÐºÐ²Ð°Ð½ÑÐ¾Ð²ÑÐ¹ ÑÐ¸Ð¿ ââââââââââââââââââââââââââââââ
            bias_list = await asyncio.get_event_loop().run_in_executor(
                None, _qaoa_wukong_run, changes_list, 1  # p=1 Ð½Ð° Ð¶ÐµÐ»ÐµÐ·Ðµ
            )
            chip_used = "Wukong_180"
        else:
            # ââ Phase 3: CPU ÑÐ¸Ð¼ÑÐ»ÑÑÐ¾Ñ ââââââââââââââââââââââââââââââââââââââââ
            bias_list = await asyncio.get_event_loop().run_in_executor(
                None, _qaoa_cpu_simulate, changes_list, 2  # p=2 Ð½Ð° CPU
            )
        raw_bias = {PAIR_NAMES[i]: bias_list[i] for i in range(N_PAIRS)}
        # v7.2.0: Ð¿ÑÐ¸Ð¼ÐµÐ½ÑÐµÐ¼ rolling average Ð´Ð»Ñ ÑÐ½Ð¸Ð¶ÐµÐ½Ð¸Ñ ÑÑÐ¼Ð°
        clamp_val = 15.0 if chip_used == "Wukong_180" else 5.0  # CPU ÑÑÐ¼Ð½ÐµÐµ
        _quantum_bias = {sym: _smooth_qaoa_bias(sym, b, clamp_val) for sym, b in raw_bias.items()}
        _quantum_ts = time.time()
        log_str = " ".join(f"{p.split('-')[0]}={b:+.1f}" for p, b in _quantum_bias.items())
        print(f"[qaoa/{chip_used}] bias(smoothed): {log_str}")
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


# ââ KuCoin Auth ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
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


# ââ KuCoin API âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
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

async def get_recent_futures_fills(symbol: str, since_ts: float) -> Optional[float]:
    """v7.2.3: ÐÐ¾Ð·Ð²ÑÐ°ÑÐ°ÐµÑ ÑÐµÐ°Ð»ÑÐ½ÑÑ ÑÑÐµÐ´Ð½ÑÑ ÑÐµÐ½Ñ Ð·Ð°ÐºÑÑÑÐ¸Ñ Ð¿Ð¾Ð·Ð¸ÑÐ¸Ð¸ Ð¸Ð· fills KuCoin Futures.
    ÐÑÐ¿Ð¾Ð»ÑÐ·ÑÐµÑÑÑ Ð² position_monitor Ð²Ð¼ÐµÑÑÐ¾ price_now Ð´Ð»Ñ ÑÐ¾ÑÐ½Ð¾Ð³Ð¾ PnL."""
    endpoint = f"/api/v1/fills?symbol={symbol}&type=trade&pageSize=20"
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
                # ÐÐµÑÑÐ¼ fills ÐÐÐ¡ÐÐ Ð¾ÑÐºÑÑÑÐ¸Ñ Ð¿Ð¾Ð·Ð¸ÑÐ¸Ð¸ (createdAt Ð² Ð¼Ð¸Ð»Ð»Ð¸ÑÐµÐºÑÐ½Ð´Ð°Ñ)
                close_fills = [
                    f for f in items
                    if float(f.get("createdAt", 0)) / 1000 > since_ts
                ]
                if close_fills:
                    total_qty = sum(float(f.get("size", 1)) for f in close_fills)
                    if total_qty > 0:
                        avg_price = sum(
                            float(f["price"]) * float(f.get("size", 1))
                            for f in close_fills
                        ) / total_qty
                        print(f"[fills] {symbol}: ÑÐµÐ°Ð»ÑÐ½Ð°Ñ ÑÐµÐ½Ð° Ð·Ð°ÐºÑÑÑÐ¸Ñ ${avg_price:,.4f} ({len(close_fills)} fills)", flush=True)
                        return avg_price
    except Exception as e:
        print(f"[fills] {symbol}: Ð¾ÑÐ¸Ð±ÐºÐ° Ð¿Ð¾Ð»ÑÑÐµÐ½Ð¸Ñ fills â {e}", flush=True)
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


# ââ Technical Analysis âââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
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


# ââ Yandex Vision â ÑÐ²ÐµÑÐ½Ð¾Ð¹ Ð³ÑÐ°ÑÐ¸Ðº + OCR Ð¿Ð°ÑÑÐµÑÐ½Ð¾Ð² ââââââââââââââââââââââââââââ
def _render_candles_png_b64(candles: list, width: int = 400, height: int = 280) -> str:
    """Ð Ð¸ÑÑÐµÑ ÑÐ²ÐµÑÐ½Ð¾Ð¹ Ð³ÑÐ°ÑÐ¸Ðº ÑÐµÑÐµÐ· PIL Ð¸ Ð²Ð¾Ð·Ð²ÑÐ°ÑÐ°ÐµÑ base64 PNG."""
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

        # Ð¡ÐµÑÐºÐ°
        for pct in [0.25, 0.5, 0.75]:
            y = p2y(p_min + p_rng * pct)
            draw.line([(pad, y), (width - pad, y)], fill=(40, 40, 60), width=1)

        # Ð¡Ð²ÐµÑÐ¸
        for i, (o, c, h, l) in enumerate(zip(opens, closes, highs, lows)):
            xc   = pad + i * (cw // len(chron)) + cand_w // 2
            bull = c >= o
            col  = (0, 200, 100) if bull else (220, 50, 50)
            draw.line([(xc, p2y(h)), (xc, p2y(l))], fill=col, width=1)
            yt, yb = min(p2y(o), p2y(c)), max(p2y(o), p2y(c))
            yb = max(yb, yt + 2)
            draw.rectangle([(xc - cand_w//2, yt), (xc + cand_w//2, yb)], fill=col)

        # Ð¦ÐµÐ½Ð¾Ð²ÑÐµ Ð¼ÐµÑÐºÐ¸ Ð´Ð»Ñ OCR
        for price, label in [
            (p_min,      f"LOW:{p_min:.0f}"),
            (p_max,      f"HIGH:{p_max:.0f}"),
            (closes[-1], f"CLOSE:{closes[-1]:.0f}"),
            (opens[0],   f"OPEN:{opens[0]:.0f}"),
        ]:
            y = p2y(price)
            draw.text((2, max(0, y - 7)), label, fill=(200, 200, 200))

        # Ð¢ÑÐµÐ½Ð´-Ð»Ð¸Ð½Ð¸Ñ
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
    """ÐÑÐ¿ÑÐ°Ð²Ð»ÑÐµÑ PNG Ð² Yandex Vision OCR Ð¸ Ð²Ð¾Ð·Ð²ÑÐ°ÑÐ°ÐµÑ ÑÐ°ÑÐ¿Ð¾Ð·Ð½Ð°Ð½Ð½ÑÐ¹ ÑÐµÐºÑÑ."""
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

        # Ð¡Ð¾Ð±Ð¸ÑÐ°ÐµÐ¼ Ð²ÐµÑÑ ÑÐµÐºÑÑ Ð¸Ð· ÑÐµÐ·ÑÐ»ÑÑÐ°ÑÐ°
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
    ÐÐ½Ð°Ð»Ð¸Ð·Ð¸ÑÑÐµÑ OCR-ÑÐµÐºÑÑ Ñ Ð³ÑÐ°ÑÐ¸ÐºÐ° â Â±8 Ðº Q-Score.
    Vision ÑÐ¸ÑÑÐµÑ: HIGH:2065 LOW:2048 CLOSE:2051 OPEN:2060
    ÐÐ¾ Ð¸Ð½Ð¾Ð³Ð´Ð° OPEN Ð½Ðµ Ð¿Ð¾Ð¿Ð°Ð´Ð°ÐµÑ Ð² ÐºÐ°Ð´Ñ â Ð¸ÑÐ¿Ð¾Ð»ÑÐ·ÑÐµÐ¼ price_change Ð¸Ð· vision_dict.
    """
    if not ocr_text:
        return 0.0
    text = ocr_text.upper()
    bonus = 0.0
    try:
        import re as _re
        nums = {}
        # ÐÑÐµÐ¼ Ð²ÑÐµ ÑÐ¸ÑÐ»Ð° Ð¿Ð¾ÑÐ»Ðµ Ð¼ÐµÑÐ¾Ðº (Ð²ÐºÐ»ÑÑÐ°Ñ Ð´ÐµÑÑÑÐ¸ÑÐ½ÑÐµ)
        for label in ["HIGH", "LOW", "CLOSE", "OPEN"]:
            m = _re.search(rf"{label}[:\s]+(\d+\.?\d*)", text)
            if m:
                nums[label] = float(m.group(1))

        ema_bull     = vision_dict.get("ema_bullish", None)
        price_change = vision_dict.get("price_change", 0.0)  # ÑÐ¶Ðµ Ð¿Ð¾ÑÑÐ¸ÑÐ°Ð½

        # ÐÑÐ¿Ð¾Ð»ÑÐ·ÑÐµÐ¼ price_change Ð¸Ð· ÑÐµÑÐ½Ð¸ÑÐµÑÐºÐ¾Ð³Ð¾ Ð°Ð½Ð°Ð»Ð¸Ð·Ð° (Ð½Ð°Ð´ÑÐ¶Ð½ÐµÐµ ÑÐµÐ¼ OCR OPEN)
        pct_move = price_change

        # ÐÑÐ»Ð¸ OCR Ð²ÑÑ Ð¶Ðµ Ð´Ð°Ð» CLOSE Ð¸ OPEN â Ð¸ÑÐ¿Ð¾Ð»ÑÐ·ÑÐµÐ¼ Ð¸Ñ (ÑÐ¾ÑÐ½ÐµÐµ)
        if "CLOSE" in nums and "OPEN" in nums and nums["OPEN"] > 0:
            pct_move = (nums["CLOSE"] - nums["OPEN"]) / nums["OPEN"] * 100

        # Vision Ð¿Ð¾Ð´ÑÐ²ÐµÑÐ¶Ð´Ð°ÐµÑ ÑÑÐµÐ½Ð´ â ÑÑÐ¸Ð»Ð¸Ð²Ð°ÐµÐ¼ ÑÐ¸Ð³Ð½Ð°Ð»
        if pct_move < -1.5 and ema_bull is False:
            bonus = -8.0   # ÑÐ¸Ð»ÑÐ½ÑÐ¹ Ð½Ð¸ÑÑÐ¾Ð´ÑÑÐ¸Ð¹ + EMA Ð¼ÐµÐ´Ð²ÐµÐ¶ÑÑ
        elif pct_move < -0.5 and ema_bull is False:
            bonus = -5.0   # ÑÐ¼ÐµÑÐµÐ½Ð½ÑÐ¹ Ð½Ð¸ÑÑÐ¾Ð´ÑÑÐ¸Ð¹
        elif pct_move < -0.3:
            bonus = -3.0   # ÑÐ»Ð°Ð±ÑÐ¹ Ð½Ð¸ÑÑÐ¾Ð´ÑÑÐ¸Ð¹
        elif pct_move > 1.5 and ema_bull is True:
            bonus = +8.0   # ÑÐ¸Ð»ÑÐ½ÑÐ¹ Ð²Ð¾ÑÑÐ¾Ð´ÑÑÐ¸Ð¹ + EMA Ð±ÑÑÑÑ
        elif pct_move > 0.5 and ema_bull is True:
            bonus = +5.0   # ÑÐ¼ÐµÑÐµÐ½Ð½ÑÐ¹ Ð²Ð¾ÑÑÐ¾Ð´ÑÑÐ¸Ð¹
        elif pct_move > 0.3:
            bonus = +3.0   # ÑÐ»Ð°Ð±ÑÐ¹ Ð²Ð¾ÑÑÐ¾Ð´ÑÑÐ¸Ð¹

        # ÐÐ¾Ð·Ð¸ÑÐ¸Ñ ÑÐµÐ½Ñ Ð² Ð´Ð¸Ð°Ð¿Ð°Ð·Ð¾Ð½Ðµ HIGH/LOW â Ð´Ð¾Ð¿Ð¾Ð»Ð½Ð¸ÑÐµÐ»ÑÐ½ÑÐ¹ ÑÐ¸Ð³Ð½Ð°Ð»
        if "HIGH" in nums and "LOW" in nums and "CLOSE" in nums:
            rng = nums["HIGH"] - nums["LOW"]
            if rng > 0:
                price_pos = (nums["CLOSE"] - nums["LOW"]) / rng * 100
                if price_pos < 20 and pct_move < 0:
                    bonus -= 2.0  # ÑÐµÐ½Ð° Ñ Ð´Ð½Ð° + Ð¿Ð°Ð´ÐµÐ½Ð¸Ðµ â ÑÑÐ¸Ð»Ð¸Ð²Ð°ÐµÐ¼ SELL
                elif price_pos > 80 and pct_move > 0:
                    bonus += 2.0  # ÑÐµÐ½Ð° Ñ Ð²ÐµÑÑÐ¸Ð½Ñ + ÑÐ¾ÑÑ â ÑÑÐ¸Ð»Ð¸Ð²Ð°ÐµÐ¼ BUY

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
        # ââ Phase 5: Claude Vision (Ð½Ð°ÑÐ¸Ð²Ð½ÑÐ¹ AI-Ð°Ð½Ð°Ð»Ð¸Ð· Ð³ÑÐ°ÑÐ¸ÐºÐ°) âââââââââââââââââ
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


# ââ Phase 5: Claude Vision â Ð½Ð°ÑÐ¸Ð²Ð½ÑÐ¹ AI-Ð°Ð½Ð°Ð»Ð¸Ð· ÑÐ²ÐµÑÐ½Ð¾Ð³Ð¾ Ð³ÑÐ°ÑÐ¸ÐºÐ° ââââââââââââââ
async def _analyze_chart_claude_vision(img_b64: str, symbol: str, tech: dict) -> dict:
    """
    ÐÑÐ¿ÑÐ°Ð²Ð»ÑÐµÑ PNG Ð³ÑÐ°ÑÐ¸ÐºÐ° Ð² Claude Haiku Ñ Ð¿ÑÐ¾ÑÑÐ±Ð¾Ð¹ Ð¿ÑÐ¾Ð°Ð½Ð°Ð»Ð¸Ð·Ð¸ÑÐ¾Ð²Ð°ÑÑ Ð¿Ð°ÑÑÐµÑÐ½.
    ÐÐ¾Ð·Ð²ÑÐ°ÑÐ°ÐµÑ bonus â [-10, +10] Ð¸ ÑÐµÐºÑÑÐ¾Ð²Ð¾Ðµ ÑÐµÐ·ÑÐ¼Ðµ.
    Haiku Ð²ÑÐ±ÑÐ°Ð½ Ð·Ð° ÑÐºÐ¾ÑÐ¾ÑÑÑ Ð¸ Ð½Ð¸Ð·ÐºÑÑ ÑÑÐ¾Ð¸Ð¼Ð¾ÑÑÑ (~$0.0003/Ð²ÑÐ·Ð¾Ð²).
    """
    if not ANTHROPIC_API_KEY or not img_b64:
        return {"success": False, "bonus": 0.0, "summary": ""}
    try:
        tech_ctx = (
            f"Ð¢ÐµÑÐ½Ð¸ÑÐµÑÐºÐ¸Ð¹ ÐºÐ¾Ð½ÑÐµÐºÑÑ: RSI={tech.get('rsi', 50):.0f}, "
            f"EMA_fast={'Ð²ÑÑÐµ' if tech.get('ema_bullish') else 'Ð½Ð¸Ð¶Ðµ'} EMA_slow, "
            f"price_change={tech.get('price_change', 0):+.2f}%, "
            f"volatility={tech.get('volatility', 0):.2f}%, "
            f"price_pos={tech.get('price_pos_pct', 50):.0f}% Ð¾Ñ Ð´Ð¸Ð°Ð¿Ð°Ð·Ð¾Ð½Ð°"
        )
        prompt = (
            f"Ð¢Ñ â ÑÐ¾ÑÐ³Ð¾Ð²ÑÐ¹ Ð°Ð½Ð°Ð»Ð¸ÑÐ¸Ðº. Ð¡Ð¼Ð¾ÑÑÐ¸ÑÑ Ð½Ð° ÑÐ²ÐµÑÐ½Ð¾Ð¹ Ð³ÑÐ°ÑÐ¸Ðº {symbol} (Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ðµ 24 ÑÐ²ÐµÑÐ¸).\n"
            f"{tech_ctx}\n\n"
            f"ÐÑÐ¾Ð°Ð½Ð°Ð»Ð¸Ð·Ð¸ÑÑÐ¹ ÐÐÐÐ£ÐÐÐ¬ÐÐ:\n"
            f"1. ÐÐ°ÐºÐ¾Ð¹ Ð¿Ð°ÑÑÐµÑÐ½ Ð²Ð¸Ð´Ð¸ÑÑ? (ÑÐ»Ð°Ð³, ÐºÐ»Ð¸Ð½, Ð³Ð¾Ð»Ð¾Ð²Ð°-Ð¿Ð»ÐµÑÐ¸, ÑÑÐµÑÐ³Ð¾Ð»ÑÐ½Ð¸Ðº, Ð¿ÑÐ¾Ð±Ð¾Ð¹ Ð¸ Ñ.Ð´.)\n"
            f"2. ÐÐ°Ð¿ÑÐ°Ð²Ð»ÐµÐ½Ð¸Ðµ: BULLISH / BEARISH / NEUTRAL\n"
            f"3. Ð£Ð²ÐµÑÐµÐ½Ð½Ð¾ÑÑÑ: 0â100%\n"
            f"4. ÐÐ»ÑÑÐµÐ²ÑÐµ ÑÑÐ¾Ð²Ð½Ð¸ Ð¿Ð¾Ð´Ð´ÐµÑÐ¶ÐºÐ¸/ÑÐ¾Ð¿ÑÐ¾ÑÐ¸Ð²Ð»ÐµÐ½Ð¸Ñ\n\n"
            f"ÐÑÐ²ÐµÑÑ Ð¡Ð¢Ð ÐÐÐ Ð² ÑÐ¾ÑÐ¼Ð°ÑÐµ JSON:\n"
            f'{{ "pattern": "Ð½Ð°Ð·Ð²Ð°Ð½Ð¸Ðµ", "direction": "BULLISH|BEARISH|NEUTRAL", '
            f'"confidence": 0-100, "support": ÑÐ¸ÑÐ»Ð¾, "resistance": ÑÐ¸ÑÐ»Ð¾, '
            f'"summary": "1 Ð¿ÑÐµÐ´Ð»Ð¾Ð¶ÐµÐ½Ð¸Ðµ Ð¿Ð¾-ÑÑÑÑÐºÐ¸" }}'
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

        # v7.2.0: Ð»Ð¾Ð³Ð¸ÑÑÐµÐ¼ HTTP ÑÑÐ°ÑÑÑ Ð´Ð»Ñ Ð´Ð¸Ð°Ð³Ð½Ð¾ÑÑÐ¸ÐºÐ¸
        if r.status != 200:
            err_body = await r.text()
            print(f"[claude_vision] {symbol}: HTTP {r.status} â {err_body[:120]}")
            if r.status == 401:
                print(f"[claude_vision] â AUTHENTICATION ERROR â Ð¿ÑÐ¾Ð²ÐµÑÑ ANTHROPIC_API_KEY Ð² Railway Variables")
            return {"success": False, "bonus": 0.0, "summary": ""}

        raw = data.get("content", [{}])[0].get("text", "{}")
        # ÐÐ·Ð²Ð»ÐµÐºÐ°ÐµÐ¼ JSON Ð¸Ð· Ð¾ÑÐ²ÐµÑÐ°
        import re as _re
        m = _re.search(r'\{.*\}', raw, _re.DOTALL)
        parsed = json.loads(m.group()) if m else {}

        direction   = parsed.get("direction", "NEUTRAL").upper()
        confidence_pct = min(100, max(0, int(parsed.get("confidence", 50))))
        confidence  = confidence_pct / 100.0
        summary     = parsed.get("summary", parsed.get("pattern", ""))

        # v7.2.0: ÑÐ²ÐµÑÐµÐ½Ð½Ð¾ÑÑÑ < 60% â Ð¿ÑÐ¸Ð½ÑÐ´Ð¸ÑÐµÐ»ÑÐ½Ð¾ NEUTRAL (ÑÐ»Ð°Ð±ÑÐ¹ ÑÐ¸Ð³Ð½Ð°Ð»)
        if confidence_pct < 60:
            print(f"[claude_vision] {symbol}: â NEUTRAL (confidence {confidence_pct}% < 60%) â bonus=+0.0")
            return {"success": True, "bonus": 0.0, "summary": summary,
                    "pattern": parsed.get("pattern", ""), "direction": "NEUTRAL"}

        # Ð Ð°ÑÑÑÐ¸ÑÑÐ²Ð°ÐµÐ¼ bonus: BULLISH â +, BEARISH â -, Ð¼Ð°ÑÑÑÐ°Ð± Ð¿Ð¾ ÑÐ²ÐµÑÐµÐ½Ð½Ð¾ÑÑÐ¸
        if direction == "BULLISH":
            bonus = round((confidence_pct - 50) / 50 * 10, 1)   # 60%â+2, 80%â+6, 100%â+10
        elif direction == "BEARISH":
            bonus = round(-(confidence_pct - 50) / 50 * 10, 1)  # 60%â-2, 80%â-6, 100%â-10
        else:
            bonus = 0.0

        icon = "ð" if direction == "BULLISH" else "ð" if direction == "BEARISH" else "â"
        print(f"[claude_vision] {symbol}: {icon} {direction} {confidence_pct}% â bonus={bonus:+.1f} | {summary}")
        return {"success": True, "bonus": bonus, "summary": summary,
                "pattern": parsed.get("pattern", ""), "direction": direction}

    except Exception as e:
        print(f"[claude_vision] {symbol} error: {type(e).__name__}: {e}")
        return {"success": False, "bonus": 0.0, "summary": ""}


# ââ Telegram âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
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


# ââ Signal Generator v5.0 ââââââââââââââââââââââââââââââââââââââââââââââââââââââ
def calc_signal(price_change: float, vision: dict = None,
                fear_greed: dict = None, polymarket_bonus: float = 0.0,
                whale_bonus: float = 0.0, quantum_bias: float = 0.0) -> dict:
    """Q-Score v5.6: ÑÐµÑÐ½Ð¸ÑÐµÑÐºÐ¸Ð¹ Ð°Ð½Ð°Ð»Ð¸Ð· + Ð¼Ð¸ÑÐ¾Ð²ÑÐµ ÑÐ¾Ð±ÑÑÐ¸Ñ + ÐºÐ¸ÑÑ + QAOA quantum bias."""
    score = 50.0

    # ââ Ð¢ÐµÑÐ½Ð¸ÑÐµÑÐºÐ¸Ð¹ Ð°Ð½Ð°Ð»Ð¸Ð· (max Â±35) âââââââââââââââââââââââââââââââââââââ
    score += price_change * 2.0  # Ð±ÑÐ»Ð¾ Ã 5 â ÑÐ»Ð¸ÑÐºÐ¾Ð¼ Ð´Ð¾Ð¼Ð¸Ð½Ð¸ÑÐ¾Ð²Ð°Ð»Ð¾
    if vision and vision.get("pattern") not in ("error", "insufficient_data"):
        rsi     = vision.get("rsi", 50.0)
        pattern = vision.get("pattern", "consolidation")
        is_reversal = pattern in ("oversold_bounce", "oversold_reversal", "overbought_drop", "overbought_reversal")
        score += (rsi - 50.0) * 0.2
        if not is_reversal:
            if vision.get("ema_bullish") is True:  score += 5.0   # v5.7: 8â5 (ÑÐ±Ð¸ÑÐ°ÐµÐ¼ Ð¿ÐµÑÐµÐºÐ¾Ñ Ðº BUY)
            elif vision.get("ema_bullish") is False: score -= 5.0  # v5.7: -8â-5
        vol_ratio = vision.get("vol_ratio", 1.0)
        if vol_ratio > 1.2: score += 5.0 if price_change >= 0 else -5.0
        pattern_bonus_map = {
            "oversold_bounce": +10, "oversold_reversal": +10, "uptrend_breakout": +7,
            "uptrend": +4, "consolidation": 0, "high_volatility": -3,
            "downtrend": -4, "downtrend_breakdown": -7, "overbought_reversal": -10, "overbought_drop": -10
        }
        score += pattern_bonus_map.get(pattern, 0)
        # ââ Yandex Vision OCR Ð±Ð¾Ð½ÑÑ (max Â±8) âââââââââââââââââââââââââââââ
        score += vision.get("vision_bonus", 0.0)

    # ââ ÐÐ½ÐµÑÐ½Ð¸Ðµ ÑÐ¸Ð³Ð½Ð°Ð»Ñ (max Â±23) âââââââââââââââââââââââââââââââââââââââââ
    fg_bonus = fear_greed.get("bonus", 0) if fear_greed else 0
    score += fg_bonus          # Fear&Greed ÐºÐ¾Ð½ÑÑÐ°ÑÐ½ÑÐ¹: Â±8
    score += polymarket_bonus  # Polymarket events v7.0: Â±8 (multi-query smart scoring)
    score += whale_bonus       # Whale flow: Â±5 (ÑÐ¿ÑÐ¾ÑÑÐ½Ð½Ð¾)

    # ââ QAOA Quantum Bias (max Â±15) âââââââââââââââââââââââââââââââââââââââ
    q_b = max(-15.0, min(15.0, quantum_bias))  # clamp Ð±ÐµÐ·Ð¾Ð¿Ð°ÑÐ½Ð¾ÑÑÐ¸
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


# ââ Trading ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
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
    """ÐÑÑÑÐ°Ð²Ð»ÑÐµÑ stop-market Ð¾ÑÐ´ÐµÑ Ð½Ð° KuCoin Futures (Ð´Ð»Ñ TP/SL)."""
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
        log_activity(f"[futures] {symbol}: SKIP â need ${margin_needed:.2f}, have ${available_usdt:.2f}")
        return False
    print(f"[futures] {symbol} -> {fut_symbol}: {side.upper()} {n_contracts} @ ${price:.2f}")
    result = await place_futures_order(fut_symbol, side, n_contracts, MAX_LEVERAGE)
    if result.get("code") != "200000":
        err = result.get("msg", result.get("code", "?"))
        log_activity(f"[futures] {fut_symbol} FAILED: {err}")
        return False
    # ââ Ð ÐµÐ°Ð»ÑÐ½ÑÐµ TP/SL ÑÑÐ¾Ð¿-Ð¾ÑÐ´ÐµÑÐ° Ð½Ð° KuCoin âââââââââââââââââââââââââââââ
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


# ââ ÐÐµÑ ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
_cache: dict = {}
def _cache_get(key: str, ttl: int):
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < ttl:
        return entry["val"]
    return None
def _cache_set(key: str, val):
    _cache[key] = {"val": val, "ts": time.time()}


# ââ Fear & Greed Index âââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
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
        # ÐÐ¾Ð½ÑÑÐ°ÑÐ½Ð°Ñ Ð»Ð¾Ð³Ð¸ÐºÐ°: Extreme Fear â Ð¶Ð´ÑÐ¼ ÑÐ°Ð·Ð²Ð¾ÑÐ¾ÑÐ° Ð²Ð²ÐµÑÑ (+)
        # ÐÐ: ÑÐ»Ð¸ÑÐºÐ¾Ð¼ ÑÐ¸Ð»ÑÐ½ÑÐ¹ Ð±Ð¾Ð½ÑÑ Ð³Ð°ÑÐ¸Ñ SELL ÑÐ¸Ð³Ð½Ð°Ð»Ñ Ð¿ÑÐ¸ Ð¼ÐµÐ´Ð²ÐµÐ¶ÑÐµÐ¼ ÑÑÐ½ÐºÐµ
        # ÐÐ¾ÑÑÐ¾Ð¼Ñ Ð¿ÑÐ¸ Extreme Fear Ð´Ð°ÑÐ¼ ÑÐ¼ÐµÑÐµÐ½Ð½ÑÐ¹ Ð±Ð¾Ð½ÑÑ +3 (Ð½Ðµ +8)
        if val <= 15:   bonus = +3   # Extreme Fear â ÑÑÐ½Ð¾Ðº ÑÐ²Ð½Ð¾ Ð¿ÐµÑÐµÐ¿ÑÐ¾Ð´Ð°Ð½
        elif val <= 25: bonus = +6   # Fear â ÑÐ¼ÐµÑÐµÐ½Ð½ÑÐ¹ ÐºÐ¾Ð½ÑÑÐ°ÑÐ½ÑÐ¹
        elif val <= 40: bonus = +3
        elif val <= 60: bonus = 0
        elif val <= 75: bonus = -4
        else:           bonus = -7   # Extreme Greed â ÑÐ¸Ð»ÑÐ½ÑÐ¹ SELL ÑÐ¸Ð³Ð½Ð°Ð»
        result = {"value": val, "classification": cls, "bonus": bonus, "success": True}
        _cache_set("fear_greed", result)
        return result
    except Exception as e:
        return {"value": 50, "classification": "Neutral", "bonus": 0, "success": False, "error": str(e)}


# ââ Whale Tracker ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
async def get_whale_signal(symbol: str) -> dict:
    # v7.1.2: expanded to SOL, XRP, BNB via Blockchair (AVAX not supported â skip)
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
            # ÐÑÐ¿Ð¾Ð»ÑÐ·ÑÐµÐ¼ mempool_transactions_count ÐºÐ°Ðº proxy Ð°ÐºÑÐ¸Ð²Ð½Ð¾ÑÑÐ¸
            txn_count = stats.get("mempool_transactions_count", 0)
            # ÐÐ¾ÑÐ¼Ð°Ð»Ð¸Ð·ÑÐµÐ¼: Ð²ÑÑÐ¾ÐºÐ°Ñ Ð°ÐºÑÐ¸Ð²Ð½Ð¾ÑÑÑ Ð¼ÐµÐ¼Ð¿ÑÐ»Ð° = Ð¿Ð¾ÑÐµÐ½ÑÐ¸Ð°Ð»ÑÐ½Ð°Ñ Ð¿ÑÐ¾Ð´Ð°Ð¶Ð°
            if txn_count > 50000:   bonus = -5
            elif txn_count > 20000: bonus = -2
            elif txn_count < 5000:  bonus = +3
            else:                   bonus = 0
        result = {"txn_count": txn_count, "bonus": bonus, "success": True}
        _cache_set(cache_key, result)
        return result
    except Exception as e:
        return {"bonus": 0, "success": False, "error": str(e)}


# ââ Polymarket bonus v7.0 âââââââââââââââââââââââââââââââââââââââââââââââââââââ
# ÐÐ°ÑÐºÐµÑÑ: ÐºÐ»ÑÑÐµÐ²ÑÐµ ÑÐ»Ð¾Ð²Ð° â (Ð½Ð°Ð¿ÑÐ°Ð²Ð»ÐµÐ½Ð¸Ðµ, Ð²ÐµÑ)
# direction: +1 = bullish ÐµÑÐ»Ð¸ YES prob Ð²ÑÑÐ¾Ðº, -1 = bearish ÐµÑÐ»Ð¸ YES prob Ð²ÑÑÐ¾Ðº
_PM_SIGNALS = [
    # ÐÑÐ¸Ð¿ÑÐ¾-ÑÐ¿ÐµÑÐ¸ÑÐ¸ÑÐ½ÑÐµ bullish
    ("bitcoin etf",            +1, 3.0), ("btc etf",              +1, 3.0),
    ("eth etf",                +1, 2.5), ("ethereum etf",         +1, 2.5),
    ("crypto etf",             +1, 2.0), ("bitcoin above",        +1, 2.0),
    ("btc above",              +1, 2.0), ("eth above",            +1, 1.5),
    ("bitcoin $",              +1, 1.5), ("crypto regulation",    +1, 1.5),
    ("sec approve",            +1, 2.0), ("bitcoin strategic",    +1, 2.0),
    ("us bitcoin reserve",     +1, 3.0), ("bitcoin reserve",      +1, 2.5),
    # ÐÑÐ¸Ð¿ÑÐ¾-ÑÐ¿ÐµÑÐ¸ÑÐ¸ÑÐ½ÑÐµ bearish
    ("bitcoin below",          -1, 2.0), ("btc below",            -1, 2.0),
    ("bitcoin crash",          -1, 2.5), ("crypto ban",           -1, 2.0),
    ("sec reject",             -1, 2.0), ("exchange hack",        -1, 1.5),
    ("exchange collapse",      -1, 2.5), ("bitcoin bankrupt",     -1, 2.0),
    # ÐÐ°ÐºÑÐ¾-ÑÐ¾Ð±ÑÑÐ¸Ñ (Ð²Ð»Ð¸ÑÑÑ Ð½Ð° Ð²ÐµÑÑ ÐºÑÐ¸Ð¿ÑÐ¾)
    ("recession",              -1, 2.0), ("financial crisis",     -1, 2.5),
    ("fed rate hike",          -1, 1.5), ("fed hike",             -1, 1.5),
    ("interest rate hike",     -1, 1.5), ("us debt",              -1, 1.0),
    ("fed cut",                +1, 1.5), ("rate cut",             +1, 1.5),
    ("ceasefire",              +1, 1.0), ("peace deal",           +1, 1.0),
    ("war escalation",         -1, 1.5), ("nuclear",              -1, 2.0),
]

def calc_polymarket_bonus(symbol: str, events: list) -> float:
    """v7.0: ÑÐ¼Ð½Ð°Ñ ÐºÐ»Ð°ÑÑÐ¸ÑÐ¸ÐºÐ°ÑÐ¸Ñ ÑÑÐ½ÐºÐ¾Ð² Polymarket â Ð±Ð¾Ð½ÑÑ Q-Score Â±8."""
    if not events: return 0.0
    total_score = 0.0
    total_weight = 0.0
    for ev in events:
        title = ev.get("title", "").lower()
        yes_p = ev.get("yes_prob", 50.0) / 100.0  # 0..1
        vol   = ev.get("volume", 0)
        # ÐÐµÑ ÑÐ¾Ð±ÑÑÐ¸Ñ Ð¿ÑÐ¾Ð¿Ð¾ÑÑÐ¸Ð¾Ð½Ð°Ð»ÐµÐ½ Ð¾Ð±ÑÑÐ¼Ñ ÑÐ¾ÑÐ³Ð¾Ð²
        vol_weight = min(1.0 + (vol / 100_000), 3.0)
        for keyword, direction, base_weight in _PM_SIGNALS:
            if keyword in title:
                # YES > 0.5 â ÑÐ¸Ð³Ð½Ð°Ð» direction, ÑÐ¸Ð»Ð° = |yes_p - 0.5| * 2
                signal_strength = (yes_p - 0.5) * 2  # -1..+1
                contribution = direction * signal_strength * base_weight * vol_weight
                total_score  += contribution
                total_weight += base_weight * vol_weight
    if total_weight == 0: return 0.0
    # ÐÐ¾ÑÐ¼Ð°Ð»Ð¸Ð·ÑÐµÐ¼ Ð¸ Ð¾Ð³ÑÐ°Ð½Ð¸ÑÐ¸Ð²Ð°ÐµÐ¼ Ð´Ð¾ Â±8
    raw = total_score / max(total_weight, 1.0) * 8.0
    return round(max(-8.0, min(8.0, raw)), 2)


# ââ Pending strategy choices âââââââââââââââââââââââââââââââââââââââââââââââââââ
pending_strategies: dict = {}  # trade_id â {symbol, signal, vision, price, fut_usdt, expires_at}

# ââ Ð¡ÑÑÐ°ÑÐµÐ³Ð¸Ð¸ A/B/C ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
STRATEGIES = {
    # v7.2.3: TP/SL ratio ÑÐ»ÑÑÑÐµÐ½ Ð´Ð¾ 3:1 Ð²Ð¾ Ð²ÑÐµÑ ÑÑÑÐ°ÑÐµÐ³Ð¸ÑÑ (Ð±ÑÐ»Ð¾ 2:1)
    "A": {"name": "ÐÐ¾Ð½ÑÐµÑÐ²Ð°ÑÐ¸Ð²Ð½Ð°Ñ", "risk": 0.05, "leverage": 2, "tp": 0.03, "sl": 0.01,  "emoji": "ð¡",  "tag": "real"},
    "B": {"name": "Ð¡ÑÐ°Ð½Ð´Ð°ÑÑÐ½Ð°Ñ",    "risk": 0.10, "leverage": 3, "tp": 0.045,"sl": 0.015, "emoji": "âï¸", "tag": "real"},
    "C": {"name": "ÐÐ¾Ð½ÑÑÐ½Ð°Ñ",       "risk": 0.25, "leverage": 5, "tp": 0.06, "sl": 0.02,  "emoji": "ð",  "tag": "bonus"},
}
# DUAL: Ð¾Ð´Ð½Ð¾Ð²ÑÐµÐ¼ÐµÐ½Ð½Ð¾ B (ÑÐµÐ°Ð»ÑÐ½ÑÐ¹) + C (Ð±Ð¾Ð½ÑÑÐ½ÑÐ¹ Ð°Ð³ÑÐµÑÑÐ¸Ð²Ð½ÑÐ¹)
STRATEGY_TIMEOUT = 60   # 1 Ð¼Ð¸Ð½ÑÑÐ°


async def send_strategy_choice(trade_id, symbol, action, price, q, pattern, fg, poly_b, whale_b):
    fg_txt = f"F&G: {fg.get('value',50)} {fg.get('classification','â')} ({fg.get('bonus',0):+d})" if fg.get("success") else ""
    poly_txt = f"Poly: {poly_b:+.0f}" if poly_b != 0 else ""
    whale_txt = f"Whale: {whale_b:+.0f}" if whale_b != 0 else ""
    ctx = " Â· ".join(p for p in [fg_txt, poly_txt, whale_txt] if p)
    act_emoji = "ð¢ BUY" if action == "BUY" else "ð´ SELL"
    text = (
        f"â *QuantumTrade â {act_emoji}*\n\n"
        f"ÐÐ°ÑÐ°: *{symbol}* Â· Ð¦ÐµÐ½Ð°: `${price:,.2f}`\n"
        f"Q-Score: `{q}` Â· ÐÐ°ÑÑÐµÑÐ½: `{pattern}`\n"
        f"{ctx}\n\n"
        f"*ÐÑÐ±ÐµÑÐ¸ ÑÑÑÐ°ÑÐµÐ³Ð¸Ñ:*\n"
        f"ð¡ *A* â ÐÐ¾Ð½ÑÐµÑÐ²Ð°ÑÐ¸Ð² (5%, TP 3%, SL 1%) [3:1]\n"
        f"âï¸ *B* â Ð¡ÑÐ°Ð½Ð´Ð°ÑÑ (10%, TP 4.5%, SL 1.5%) [3:1]\n"
        f"ð *C* â ÐÐ¾Ð½ÑÑÐ½Ð°Ñ (25%, TP 6%, SL 2%) [3:1]\n"
        f"ð¥ *DUAL* â B + C Ð¾Ð´Ð½Ð¾Ð²ÑÐµÐ¼ÐµÐ½Ð½Ð¾\n\n"
        f"_ÐÐµÑ Ð¾ÑÐ²ÐµÑÐ° 1 Ð¼Ð¸Ð½ â Ð°Ð²ÑÐ¾ ÑÑÑÐ°ÑÐµÐ³Ð¸Ñ B_"
    )
    keyboard = {"inline_keyboard": [
        [
            {"text": "ð¡ A", "callback_data": f"strat_A_{trade_id}"},
            {"text": "âï¸ B", "callback_data": f"strat_B_{trade_id}"},
            {"text": "ð C", "callback_data": f"strat_C_{trade_id}"},
        ],
        [
            {"text": "ð¥ DUAL (B + C Ð±Ð¾Ð½ÑÑ)", "callback_data": f"strat_D_{trade_id}"},
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
    log_activity(f"[strategy] {s['emoji']} {strategy} ÑÐ¸ÑÐº={int(s['risk']*100)}% lev={s['leverage']}x TP={int(s['tp']*100)}% SL={int(s['sl']*100)}%")
    FMAP = {
        "BTC-USDT":  ("XBTUSDTM",  0.001),  # 0.001 BTC/ÐºÐ¾Ð½ÑÑÐ°ÐºÑ  ~$85 â Ð½ÑÐ¶Ð½Ð¾ $17+ Ð¼Ð°ÑÐ¶Ð¸
        "ETH-USDT":  ("ETHUSDTM",  0.01),   # 0.01  ETH/ÐºÐ¾Ð½ÑÑÐ°ÐºÑ  ~$22 â Ð½ÑÐ¶Ð½Ð¾ ~$4.4 Ð¼Ð°ÑÐ¶Ð¸
        "SOL-USDT":  ("SOLUSDTM",  1.0),    # 1     SOL/ÐºÐ¾Ð½ÑÑÐ°ÐºÑ  ~$130 â Ð½ÑÐ¶Ð½Ð¾ $26 Ð¼Ð°ÑÐ¶Ð¸
        "AVAX-USDT": ("AVAXUSDTM", 1.0),    # 1     AVAX/ÐºÐ¾Ð½ÑÑÐ°ÐºÑ ~$25  â Ð½ÑÐ¶Ð½Ð¾ ~$5 Ð¼Ð°ÑÐ¶Ð¸ â
        "XRP-USDT":  ("XRPUSDTM",  10.0),   # 10    XRP/ÐºÐ¾Ð½ÑÑÐ°ÐºÑ  ~$25  â Ð½ÑÐ¶Ð½Ð¾ ~$5 Ð¼Ð°ÑÐ¶Ð¸ â
    }
    if symbol not in FMAP: return False
    fut_symbol, contract_size = FMAP[symbol]
    side = "buy" if signal["action"] == "BUY" else "sell"
    trade_usdt = fut_usdt * s["risk"]
    contract_value = price * contract_size
    n_contracts = max(1, int(trade_usdt * s["leverage"] / contract_value))
    if (contract_value / s["leverage"]) > fut_usdt:
        log_activity(f"[strategy] {symbol} SKIP â Ð¼Ð°ÑÐ¶Ð¸ Ð½ÐµÐ´Ð¾ÑÑÐ°ÑÐ¾ÑÐ½Ð¾")
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
        log_activity(f"[strategy] Ð¾ÑÐ¸Ð±ÐºÐ° Ð·Ð°Ð¿ÑÐ¾ÑÐ°: {e}"); return False
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
    print(f"[TRADE] {strategy} {fut_symbol} {side.upper()} Q={signal['q_score']:.1f} n={n_contracts} @ ${price:,.2f} TP={tp} SL={sl}", flush=True)
    await notify(f"{s['emoji']} <b>Ð¡ÑÑÐ°ÑÐµÐ³Ð¸Ñ {strategy} â {s['name']}</b>\n<code>{fut_symbol}</code> {side.upper()} Q={signal['q_score']}")
    return True



async def execute_dual_strategy(symbol: str, signal: dict, vision: dict,
                                 price: float, fut_usdt: float) -> bool:
    """DUAL: Ð¾ÑÐºÑÑÐ²Ð°ÐµÑ B (ÑÐµÐ°Ð»ÑÐ½ÑÐ¹) + C (Ð±Ð¾Ð½ÑÑÐ½ÑÐ¹) Ð¾Ð´Ð½Ð¾Ð²ÑÐµÐ¼ÐµÐ½Ð½Ð¾."""
    log_activity(f"[dual] {symbol}: B(ÑÐµÐ°Ð»ÑÐ½ÑÐ¹) + C(Ð±Ð¾Ð½ÑÑÐ½ÑÐ¹) Ð¾Ð´Ð½Ð¾Ð²ÑÐµÐ¼ÐµÐ½Ð½Ð¾")
    # ÐÐ°Ð¿ÑÑÐºÐ°ÐµÐ¼ Ð¾Ð±Ð° Ð¿Ð°ÑÐ°Ð»Ð»ÐµÐ»ÑÐ½Ð¾
    ok_b, ok_c = await asyncio.gather(
        execute_with_strategy("B", symbol, signal, vision, price, fut_usdt),
        execute_with_strategy("C", symbol, signal, vision, price, fut_usdt),
        return_exceptions=True
    )
    ok_b = ok_b is True; ok_c = ok_c is True
    log_activity(f"[dual] ÑÐµÐ·ÑÐ»ÑÑÐ°Ñ: B={'OK' if ok_b else 'FAIL'} C={'OK' if ok_c else 'FAIL'}")
    if ok_b or ok_c:
        await notify(
            f"ð¥ *DUAL ÑÑÑÐ°ÑÐµÐ³Ð¸Ñ*\n"
            f"{symbol} {('BUY' if signal['action']=='BUY' else 'SELL')} Q={signal['q_score']}\n"
            f"âï¸ B (ÑÐµÐ°Ð»ÑÐ½ÑÐ¹): {'â' if ok_b else 'â'}\n"
            f"ð C (Ð±Ð¾Ð½ÑÑÐ½ÑÐ¹): {'â' if ok_c else 'â'}"
        )
    return ok_b or ok_c

async def auto_execute_dynamic(trade_id: str):
    """ÐÐ¸Ð½Ð°Ð¼Ð¸ÑÐµÑÐºÐ¸Ð¹ Ð²ÑÐ±Ð¾Ñ ÑÑÑÐ°ÑÐµÐ³Ð¸Ð¸ Ð¿Ð¾ Q-Score Ð¿ÑÐ¸ ÑÐ°Ð¹Ð¼Ð°ÑÑÐµ."""
    await asyncio.sleep(STRATEGY_TIMEOUT)
    pending = pending_strategies.pop(trade_id, None)
    if not pending: return
    q = pending["signal"]["q_score"]
    # v6.9 Dynamic strategy: Qâ¥85âDUAL(B+C), Qâ¥65âC (Ð¾Ð¿ÑÐ¸Ð¼Ð°Ð»ÑÐ½Ð¾ Ð´Ð»Ñ Ð¼ÐµÐ´Ð²ÐµÐ¶ÑÐµÐ³Ð¾ ÑÑÐ½ÐºÐ°), elseâB
    if q >= 85:
        auto_strategy = "D"
        label = "DUAL (B+C)"
    elif q >= 65:
        auto_strategy = "C"
        label = "C (Ð°Ð³ÑÐµÑÑÐ¸Ð²Ð½Ð°Ñ ð)"
    else:
        auto_strategy = "B"
        label = "B (ÑÑÐ°Ð½Ð´Ð°ÑÑÐ½Ð°Ñ)"
    log_activity(f"[strategy] timeout {trade_id} Q={q:.1f} â Ð°Ð²ÑÐ¾ {label}")
    await notify(f"â± <i>Ð¢Ð°Ð¹Ð¼Ð°ÑÑ â Q={q:.0f} â ÑÑÑÐ°ÑÐµÐ³Ð¸Ñ {label}</i>")
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

    # ââ ÐÑÐµ Ð²Ð½ÐµÑÐ½Ð¸Ðµ Ð´Ð°Ð½Ð½ÑÐµ Ð¿Ð°ÑÐ°Ð»Ð»ÐµÐ»ÑÐ½Ð¾ âââââââââââââââââââââââââââââââââââââââ
    try:
        prices_data, fg_data, spot_bal, fut_bal = await asyncio.wait_for(
            asyncio.gather(get_all_prices(), get_fear_greed(), get_balance(), get_futures_balance()),
            timeout=12.0
        )
    except asyncio.TimeoutError:
        log_activity("[cycle] data fetch timeout â skipping"); return
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

    # ââ Polymarket v7.0 (ÐºÐµÑ 15 Ð¼Ð¸Ð½, multi-query) ââââââââââââââââââââââââââââââ
    poly_events = _cache_get("polymarket", 900) or []
    if not poly_events:
        try:
            # ÐÐ°Ð¿ÑÐ¾ÑÑ Ð¿Ð¾ ÐºÐ»ÑÑÐµÐ²ÑÐ¼ ÑÐµÐ¼Ð°Ð¼: ÐºÑÐ¸Ð¿ÑÐ¾ + Ð¼Ð°ÐºÑÐ¾
            PM_QUERIES = [
                "bitcoin", "ethereum", "crypto ETF", "crypto regulation",
                "recession", "fed rate", "ceasefire",
            ]
            result = {}  # slug â event (Ð´ÐµÐ´ÑÐ¿Ð»Ð¸ÐºÐ°ÑÐ¸Ñ)
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

    # ââ QAOA: Ð¾Ð±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ quantum bias ÑÐ°Ð· Ð² 15 Ð¼Ð¸Ð½ÑÑ ââââââââââââââââââââââââââ
    global _quantum_ts
    if time.time() - _quantum_ts > 870:  # 870 ÑÐµÐº â 14.5 Ð¼Ð¸Ð½ (ÑÑÑÑ ÑÐ°Ð½ÑÑÐµ ÑÐ¸ÐºÐ»Ð°)
        price_changes_map = {
            sym: pdata.get("change", 0.0)
            for sym, pdata in prices_data["prices"].items()
            if sym in PAIR_NAMES
        }
        await run_qaoa_optimization(price_changes_map)

    signals_fired = []
    # COOLDOWN ÑÐµÐ¿ÐµÑÑ Ð³Ð»Ð¾Ð±Ð°Ð»ÑÐ½Ð°Ñ Ð¿ÐµÑÐµÐ¼ÐµÐ½Ð½Ð°Ñ (Ð¸Ð·Ð¼ÐµÐ½ÑÐµÑÑÑ ÑÐµÑÐµÐ· Telegram Ð½Ð°ÑÑÑÐ¾Ð¹ÐºÐ¸)

    # ââ ÐÐ°ÑÐ°Ð»Ð»ÐµÐ»ÑÐ½ÑÐ¹ fetch: chart + vision + whale ââââââââââââââââââââââââââââ
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
            log_activity(f"[cycle] {symbol}: Q={q:.1f}<{_pair_min_q} (pair threshold) â SKIP")
            continue
        if action == "SELL" and (100.0 - q) < _pair_min_q:
            log_activity(f"[cycle] {symbol}: sellQ={(100.0-q):.1f}<{_pair_min_q} (pair threshold) â SKIP")
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

        # ââ Ð¡Ð¿Ð¾Ñ (ÑÐ¾Ð»ÑÐºÐ¾ BUY) âââââââââââââââââââââââââââââââââââââââââââââââââ
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

        # ââ Ð¤ÑÑÑÐµÑÑÑ: ÑÐ¾Ð±Ð¸ÑÐ°ÐµÐ¼ ÐºÐ°Ð½Ð´Ð¸Ð´Ð°ÑÐ¾Ð² ââââââââââââââââââââââââââââââââââââ
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
                log_activity(f"[cycle] {symbol}: SKIP fut â {reason}")
            else:
                futures_candidates.append({
                    "symbol": symbol, "signal": signal, "vision": vision,
                    "price": price, "action": action, "conf": conf, "q": q,
                    "fg": fg_data, "poly": poly_b, "whale": whale.get("bonus", 0),
                    "pattern": vision.get("pattern","?")
                })

    # ââ ÐÑÑÑÐ¸Ð¹ ÐºÐ°Ð½Ð´Ð¸Ð´Ð°Ñ â Telegram A/B/C (3 Ð¼Ð¸Ð½ ÑÐ°Ð¹Ð¼Ð°ÑÑ) ââââââââââââââââââââ
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
        # ÐÐÐÐÐ: Ð±Ð»Ð¾ÐºÐ¸ÑÑÐµÐ¼ ÑÑÑ Ð¿Ð°ÑÑ ÑÑÐ°Ð·Ñ, Ð½Ðµ Ð¶Ð´ÑÐ¼ Ð¸ÑÐ¿Ð¾Ð»Ð½ÐµÐ½Ð¸Ñ
        # Ð¸Ð½Ð°ÑÐµ ÑÐ»ÐµÐ´ÑÑÑÐ¸Ð¹ ÑÐ¸ÐºÐ» ÑÐ¾Ð·Ð´Ð°ÑÑ Ð½Ð¾Ð²ÑÐ¹ pending Ð´Ð»Ñ ÑÐ¾Ð¹ Ð¶Ðµ Ð¿Ð°ÑÑ
        last_signals[f"FUT_{best['symbol']}"] = {"action": best["action"], "ts": time.time()}
        log_activity(f"[cycle] {best['symbol']}: reserved â cooldown {COOLDOWN}s")
        for k in [k for k, v in list(pending_strategies.items()) if time.time() > v["expires_at"]]:
            del pending_strategies[k]

        await send_strategy_choice(
            trade_id, best["symbol"], best["action"], best["price"],
            best["q"], best["pattern"], best["fg"], best["poly"], best["whale"]
        )
        asyncio.create_task(auto_execute_dynamic(trade_id))

    # ââ Ð£Ð²ÐµÐ´Ð¾Ð¼Ð»ÐµÐ½Ð¸Ðµ ÑÐ¿Ð¾Ñ âââââââââââââââââââââââââââââââââââââââââââââââââââââ
    if signals_fired:
        mode = "TEST" if TEST_MODE else "LIVE"
        msg  = f"â *QuantumTrade {mode}*\n\n"
        for s in signals_fired:
            emoji = "ð¢" if s["action"] == "BUY" else "ð´"
            msg += f"{emoji} *{s['symbol']}* {s['action']} [spot]\n   Q:`{s['q_score']}` TP:`${s['tp']:,.2f}` SL:`${s['sl']:,.2f}`\n\n"
        await notify(msg)

    # ââ BTC Q-Score Ð°Ð»ÐµÑÑÑ ââââââââââââââââââââââââââââââââââââââââââââââââââââ
    btc_res = next((r for r in cv_results if not isinstance(r, Exception) and r[0] == "BTC-USDT"), None)
    if btc_res:
        _, _, btc_signal, _, _ = btc_res
        q = btc_signal["q_score"]; conf = btc_signal["confidence"]
        btc_price = prices_data["prices"].get("BTC-USDT", {}).get("price", 0)
        sell_thresh = 100 - MIN_Q_SCORE  # v7.2.2: Ð´Ð¸Ð½Ð°Ð¼Ð¸ÑÐµÑÐºÐ¸Ð¹ Ð¿Ð¾ÑÐ¾Ð³
        if q >= MIN_Q_SCORE and last_q_score < MIN_Q_SCORE:
            await notify(f"ð <b>Q-Score {q:.0f} â ÑÐ¸Ð³Ð½Ð°Ð» BUY!</b> BTC <code>${btc_price:,.0f}</code> Â· <code>{int(conf*100)}%</code> Â· F&G={fg_val}")
        elif q <= sell_thresh and last_q_score > sell_thresh:
            # v7.2.2: Ð°Ð½ÑÐ¸ÑÐ¿Ð°Ð¼ â Ð½Ðµ ÑÐ°ÑÐµ ÑÐ°Ð·Ð° Ð² 5 Ð¼Ð¸Ð½
            now = time.time()
            if now - _q_alert_last.get("sell", 0) > 300:
                _q_alert_last["sell"] = now
                await notify(f"â ï¸ <b>Q-Score {q:.0f} â Ð·Ð¾Ð½Ð° SELL</b> Â· BTC <code>${btc_price:,.0f}</code>")
        last_q_score = q


# ââ Startup ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# ââ Position Monitor ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# TRIANGULAR ARBITRAGE MONITOR v7.1
# Ð¡ÑÐµÐ¼Ð°: USDT â A â B â USDT
# ÐÑÐ¾Ð²ÐµÑÑÐµÐ¼ Ð¾ÑÐºÐ»Ð¾Ð½ÐµÐ½Ð¸Ðµ ÑÐµÐ°Ð»ÑÐ½Ð¾Ð³Ð¾ ÐºÑÐ¾ÑÑ-ÐºÑÑÑÐ° A-B Ð¾Ñ Ð¸Ð¼Ð¿Ð»Ð¸ÑÐ¸ÑÐ½Ð¾Ð³Ð¾
# ÐÑÐ»Ð¸ ÑÐ¿ÑÐµÐ´ > 0.4% (>0.3% ÐºÐ¾Ð¼Ð¸ÑÑÐ¸Ð¹ KuCoin) â Ð°Ð»ÐµÑÑ Ð² Telegram
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

# Ð¢ÑÐµÑÐ³Ð¾Ð»ÑÐ½ÑÐµ Ð¿Ð°ÑÑ: (coin_a, coin_b, cross_pair, description)
ARB_TRIANGLES = [
    ("ETH-USDT",  "BTC-USDT",  "ETH-BTC",  "USDTâETHâBTCâUSDT"),
    # SOL-BTC and SOL-ETH pairs don't exist on KuCoin spot â removed
    ("XRP-USDT",  "BTC-USDT",  "XRP-BTC",  "USDTâXRPâBTCâUSDT"),
    # XRP-ETH doesn't exist on KuCoin spot â removed
    ("ADA-USDT",  "BTC-USDT",  "ADA-BTC",  "USDTâADAâBTCâUSDT"),
    ("LINK-USDT", "BTC-USDT",  "LINK-BTC", "USDTâLINKâBTCâUSDT"),
    ("LTC-USDT",  "BTC-USDT",  "LTC-BTC",  "USDTâLTCâBTCâUSDT"),
]
ARB_FEE       = 0.001   # 0.1% per trade, 0.3% for 3 trades
ARB_MIN_SPREAD = 0.004  # Ð¼Ð¸Ð½Ð¸Ð¼Ð°Ð»ÑÐ½ÑÐ¹ ÑÐ¿ÑÐµÐ´ 0.4% Ð¿Ð¾ÑÐ»Ðµ ÐºÐ¾Ð¼Ð¸ÑÑÐ¸Ð¹
ARB_COOLDOWNS: dict = {}  # path â last_alert_ts (cooldown 5 Ð¼Ð¸Ð½)
ARB_COOLDOWN_SEC = 300

async def get_cross_ticker(symbol: str) -> float:
    """ÐÐ¾Ð»ÑÑÐ¸ÑÑ ÑÐµÐ½Ñ ÐºÑÐ¾ÑÑ-Ð¿Ð°ÑÑ Ð¸Ð· KuCoin (Ð½Ð°Ð¿Ñ. ETH-BTC)."""
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
    ÐÑÐ¾Ð²ÐµÑÑÐµÑ Ð²ÑÐµ ÑÑÐµÑÐ³Ð¾Ð»ÑÐ½ÑÐµ ÑÐ²ÑÐ·ÐºÐ¸.
    ÐÐ¾Ð·Ð²ÑÐ°ÑÐ°ÐµÑ ÑÐ¿Ð¸ÑÐ¾Ðº Ð½Ð°Ð¹Ð´ÐµÐ½Ð½ÑÑ Ð²Ð¾Ð·Ð¼Ð¾Ð¶Ð½Ð¾ÑÑÐµÐ¹ [{path, spread_pct, direction, ...}].
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

        # ÐÐ¼Ð¿Ð»Ð¸ÑÐ¸ÑÐ½ÑÐ¹ ÐºÑÐ¾ÑÑ-ÐºÑÑÑ (Ð¸Ð· USDT Ð¿Ð°Ñ)
        implied_cross = price_a / price_b  # Ð½Ð°Ð¿Ñ. ETH/BTC = ETH_USDT / BTC_USDT

        # Ð ÐµÐ°Ð»ÑÐ½ÑÐ¹ ÐºÑÐ¾ÑÑ-ÐºÑÑÑ Ñ Ð±Ð¸ÑÐ¶Ð¸
        actual_cross = await get_cross_ticker(cross_sym)
        if not actual_cross:
            continue

        # Ð¡Ð¿ÑÐµÐ´: Ð½Ð°ÑÐºÐ¾Ð»ÑÐºÐ¾ ÑÐµÐ°Ð»ÑÐ½ÑÐ¹ Ð¾ÑÐ»Ð¸ÑÐ°ÐµÑÑÑ Ð¾Ñ Ð¸Ð¼Ð¿Ð»Ð¸ÑÐ¸ÑÐ½Ð¾Ð³Ð¾
        spread = (actual_cross - implied_cross) / implied_cross

        # ÐÑÐ¾Ð²ÐµÑÑÐµÐ¼ Ð¾Ð±Ð° Ð½Ð°Ð¿ÑÐ°Ð²Ð»ÐµÐ½Ð¸Ñ
        fee3 = ARB_FEE * 3  # 0.3% ÑÑÐ¼Ð¼Ð°ÑÐ½ÑÐµ ÐºÐ¾Ð¼Ð¸ÑÑÐ¸Ð¸

        # ÐÐ°Ð¿ÑÐ°Ð²Ð»ÐµÐ½Ð¸Ðµ 1: USDT â A â B â USDT (Ð¸ÑÐ¿Ð¾Ð»ÑÐ·ÑÐµÐ¼ actual_cross Ð´Ð»Ñ Ð¿ÑÐ¾Ð´Ð°Ð¶Ð¸ A Ð·Ð° B)
        # ÐÑÐ¸Ð±ÑÐ»Ñ = (1/price_a) * actual_cross * price_b * (1-fee)^3 - 1
        profit1 = (1 / price_a) * actual_cross * price_b * (1 - ARB_FEE)**3 - 1

        # ÐÐ°Ð¿ÑÐ°Ð²Ð»ÐµÐ½Ð¸Ðµ 2: USDT â B â A â USDT (Ð¾Ð±ÑÐ°ÑÐ½ÑÐ¹ Ð¿ÑÑÑ)
        # ÐÑÐ¸Ð±ÑÐ»Ñ = (1/price_b) * (1/actual_cross) * price_a * (1-fee)^3 - 1
        profit2 = (1 / price_b) * (1 / actual_cross) * price_a * (1 - ARB_FEE)**3 - 1

        best_profit = max(profit1, profit2)
        direction   = 1 if profit1 >= profit2 else 2

        if best_profit >= ARB_MIN_SPREAD:
            path_str = path if direction == 1 else path.replace("â", "â").split("â")[0] + "â".join(path.split("â")[1:])
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
            log_activity(f"[arb] â¡ {path} profit={best_profit*100:.3f}% spread={spread*100:.3f}%")

    return opportunities

async def _notify_arb(opp: dict):
    """Telegram alert for triangular arbitrage opportunity."""
    d = opp["direction"]
    steps = opp["path"].split("â")
    arrow = "â¡ï¸"
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
    """ÐÐ°Ð¶Ð´ÑÐµ 30 ÑÐµÐº Ð¿ÑÐ¾Ð²ÐµÑÑÐµÑ Ð¾ÑÐºÑÑÑÑÐµ Ð¿Ð¾Ð·Ð¸ÑÐ¸Ð¸ â Ð·Ð°ÐºÑÑÐ»Ð¸ÑÑ Ð»Ð¸ Ð¿Ð¾ TP/SL."""
    await asyncio.sleep(30)
    SYM_REV = {"XBTUSDTM": "BTC-USDT", "ETHUSDTM": "ETH-USDT", "SOLUSDTM": "SOL-USDT"}
    # v6.8: Ð¿ÑÐ°Ð²Ð¸Ð»ÑÐ½ÑÐµ ÑÐ°Ð·Ð¼ÐµÑÑ ÐºÐ¾Ð½ÑÑÐ°ÐºÑÐ¾Ð² Ð´Ð»Ñ ÑÐ°ÑÑÑÑÐ° PnL
    CONTRACT_SIZES = {"XBTUSDTM": 0.001, "ETHUSDTM": 0.01, "SOLUSDTM": 1.0,
                      "AVAXUSDTM": 1.0, "XRPUSDTM": 10.0}
    while True:
        try:
            open_trades = [t for t in trade_log if t.get("status") == "open"]
            if open_trades:
                pos_data   = await get_futures_positions()
                open_syms  = {p.get("symbol") for p in pos_data.get("positions", [])}
                for trade in open_trades:
                    # v7.2.0: Ð¼Ð¸Ð½ 5 Ð¼Ð¸Ð½ Ð´Ð¾ Ð·Ð°ÐºÑÑÑÐ¸Ñ â Ð·Ð°ÑÐ¸ÑÐ° Ð¾Ñ race condition
                    if (time.time() - trade.get("open_ts", time.time())) < 300:
                        continue
                    if trade["symbol"] not in open_syms:
                        base_sym      = SYM_REV.get(trade["symbol"], "BTC-USDT")
                        entry         = trade["price"]
                        contract_size = CONTRACT_SIZES.get(trade["symbol"], 0.01)
                        open_ts       = trade.get("open_ts", time.time() - 400)
                        # v7.2.3: ÑÐ½Ð°ÑÐ°Ð»Ð° Ð¿ÑÐ¾Ð±ÑÐµÐ¼ ÑÐµÐ°Ð»ÑÐ½ÑÑ ÑÐµÐ½Ñ Ð¸Ð· KuCoin fills
                        real_close = await get_recent_futures_fills(trade["symbol"], open_ts)
                        price_now  = real_close if real_close else await get_ticker(base_sym)
                        price_source = "fills" if real_close else "ticker"
                        if trade["side"] == "sell":
                            pnl_pct = (entry - price_now) / entry
                        else:
                            pnl_pct = (price_now - entry) / entry
                        pnl_usdt = round(pnl_pct * entry * trade["size"] * contract_size, 4)
                        duration_min = round((time.time() - open_ts) / 60, 1)
                        # ÐÐ¿ÑÐµÐ´ÐµÐ»ÑÐµÐ¼ Ð¿ÑÐ¸ÑÐ¸Ð½Ñ Ð·Ð°ÐºÑÑÑÐ¸Ñ Ð¿Ð¾ ÑÐµÐ°Ð»ÑÐ½Ð¾Ð¹ ÑÐµÐ½Ðµ
                        tp  = trade.get("tp", entry * 1.03)
                        sl  = trade.get("sl", entry * 0.985)
                        if trade["side"] == "buy":
                            reason = "ð¯ TP" if price_now >= tp * 0.995 else ("ð SL" if price_now <= sl * 1.005 else "ð ÐÐ¾Ð½Ð¸ÑÐ¾Ñ")
                        else:
                            reason = "ð¯ TP" if price_now <= tp * 1.005 else ("ð SL" if price_now >= sl * 0.995 else "ð ÐÐ¾Ð½Ð¸ÑÐ¾Ñ")
                        trade["status"]       = "closed"
                        trade["pnl"]          = pnl_usdt
                        trade["close_price"]  = price_now
                        trade["price_source"] = price_source  # Ð´Ð»Ñ Ð´Ð¸Ð°Ð³Ð½Ð¾ÑÑÐ¸ÐºÐ¸
                        emoji = "â" if pnl_usdt >= 0 else "â"
                        strat = trade.get("account", "B").replace("futures_", "")
                        log_activity(f"[monitor] {trade['symbol']} {reason} closed PnL=${pnl_usdt:+.4f}")
                        print(f"[CLOSE] {trade['symbol']} {trade['side'].upper()} PnL=${pnl_usdt:+.4f} entry=${trade['price']} exit=${price_now}", flush=True)
                        _save_trades_to_disk()
                        await notify(
                            f"{emoji} <b>Ð¡Ð´ÐµÐ»ÐºÐ° Ð·Ð°ÐºÑÑÑÐ° â Ð¡ÑÑÐ°ÑÐµÐ³Ð¸Ñ {strat}</b>\n"
                            f"<code>{trade['symbol']}</code> {trade['side'].upper()} | {reason}\n"
                            f"ÐÑÐ¾Ð´:  <code>${entry:,.2f}</code> â ÐÑÑÐ¾Ð´: <code>${price_now:,.2f}</code>\n"
                            f"PnL:   <code>${pnl_usdt:+.4f}</code> ({pnl_pct*100:+.3f}%)\n"
                            f"Q={trade.get('q_score',0):.1f} | ÐÐ»Ð¸ÑÐµÐ»ÑÐ½Ð¾ÑÑÑ: {duration_min}Ð¼"
                        )
        except Exception as e:
            print(f"[monitor] {e}")

        # ââ ÐÑÐ±Ð¸ÑÑÐ°Ð¶: Ð¿ÑÐ¾Ð²ÐµÑÑÐµÐ¼ ÐºÐ°Ð¶Ð´ÑÐµ 2 ÑÐ¸ÐºÐ»Ð° (60 ÑÐµÐº) ââââââââââââââââââââââ
        try:
            if int(time.time()) % 60 < 32:  # Ð¿ÑÐ¸Ð¼ÐµÑÐ½Ð¾ ÐºÐ°Ð¶Ð´ÑÑ Ð¼Ð¸Ð½ÑÑÑ
                prices_snap = _cache_get("all_prices", 120) or {}
                if prices_snap:
                    arb_opps = await check_triangular_arb(prices_snap.get("prices", {}))
                    for opp in arb_opps:
                        await _notify_arb(opp)
        except Exception as e:
            log_activity(f"[arb] monitor error: {e}")

        await asyncio.sleep(30)


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# TELEGRAM BOT â ÐºÐ¾Ð¼Ð°Ð½Ð´Ñ, Ð¼ÐµÐ½Ñ, Ð½Ð°ÑÑÑÐ¾Ð¹ÐºÐ¸, ÑÑÐ°ÑÐ¸ÑÑÐ¸ÐºÐ°, airdrops
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
class TelegramUpdate(BaseModel):
    callback_query: Optional[dict] = None
    message:        Optional[dict] = None

async def _tg_send(chat_id: int, text: str, keyboard: dict = None, parse_mode: str = "HTML"):
    """Ð£Ð½Ð¸Ð²ÐµÑÑÐ°Ð»ÑÐ½Ð°Ñ Ð¾ÑÐ¿ÑÐ°Ð²ÐºÐ° ÑÐ¾Ð¾Ð±ÑÐµÐ½Ð¸Ñ Ð² Telegram (parse_mode=HTML Ð´Ð»Ñ Ð½Ð°Ð´ÑÐ¶Ð½Ð¾ÑÑÐ¸)."""
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
                # ÐÐ¾Ð³Ð¸ÑÑÐµÐ¼ ÑÐµÐ°Ð»ÑÐ½ÑÑ Ð¾ÑÐ¸Ð±ÐºÑ Ð¾Ñ Telegram API
                print(f"[tg_send] Telegram error: {resp.get('description','?')} | "
                      f"chat={chat_id} | text[:60]={text[:60]!r}")
    except Exception as e:
        print(f"[tg_send] network error: {e}")

async def _tg_answer(cb_id: str, text: str = ""):
    """ÐÑÐ²ÐµÑ Ð½Ð° callback query (ÑÐ±Ð¸ÑÐ°ÐµÑ ÑÐ°ÑÐ¸ÐºÐ¸ Ñ ÐºÐ½Ð¾Ð¿ÐºÐ¸)."""
    if not BOT_TOKEN: return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
                         json={"callback_query_id": cb_id, "text": text},
                         timeout=aiohttp.ClientTimeout(total=3))
    except: pass

async def _tg_main_menu(chat_id: int):
    """ÐÐ»Ð°Ð²Ð½Ð¾Ðµ Ð¼ÐµÐ½Ñ Ð±Ð¾ÑÐ°."""
    ap = "ð¢ ÐÐÐ" if AUTOPILOT else "ð´ ÐÐ«ÐÐ"
    kb = {"inline_keyboard": [
        [{"text": "ð¥ï¸ ÐÑÐºÑÑÑÑ Ð´Ð°ÑÐ±Ð¾ÑÐ´", "web_app": {"url": WEBAPP_URL}}],
        [{"text": "ð Ð¡ÑÐ°ÑÐ¸ÑÑÐ¸ÐºÐ°", "callback_data": "menu_stats"},
         {"text": "ðª Airdrops",   "callback_data": "menu_airdrops"}],
        [{"text": "âï¸ ÐÐ°ÑÑÑÐ¾Ð¹ÐºÐ¸",  "callback_data": "menu_settings"},
         {"text": f"ð¤ ÐÐ²ÑÐ¾Ð¿Ð¸Ð»Ð¾Ñ: {ap}", "callback_data": "menu_autopilot"}],
        [{"text": "ð° ÐÐ°Ð»Ð°Ð½Ñ",     "callback_data": "menu_balance"},
         {"text": "ð ÐÐ¾Ð·Ð¸ÑÐ¸Ð¸",    "callback_data": "menu_positions"}],
        [{"text": "â¡ ÐÑÐ±Ð¸ÑÑÐ°Ð¶",   "callback_data": "menu_arb"}],
    ]}
    await _tg_send(chat_id,
        "â <b>QuantumTrade AI v6.8.0</b>\n"
        "ââââââââââââââââââââââ\n"
        "ÐÑÐ±ÐµÑÐ¸ ÑÐ°Ð·Ð´ÐµÐ»:", kb)

async def _tg_stats(chat_id: int):
    """ÐÑÐ¿ÑÐ°Ð²Ð»ÑÐµÑ ÐºÐ°ÑÑÐ¾ÑÐºÑ ÑÑÐ°ÑÐ¸ÑÑÐ¸ÐºÐ¸ ÑÑÐµÐ¹Ð´Ð¸Ð½Ð³Ð°."""
    total = len(trade_log)
    wins  = sum(1 for t in trade_log if (t.get("pnl") or 0) > 0)
    losses= sum(1 for t in trade_log if (t.get("pnl") or 0) <= 0 and t.get("pnl") is not None)
    pnl   = round(sum(t.get("pnl") or 0 for t in trade_log), 4)
    wr    = round(wins / total * 100, 1) if total else 0
    open_ = sum(1 for t in trade_log if t["status"] == "open")
    last_q = round(last_q_score, 1) if last_q_score else "â"
    pnl_emoji = "â" if pnl >= 0 else "â"
    chip  = "Wukong 180 âï¸" if _qcloud_ready else "CPU ÑÐ¸Ð¼ÑÐ»ÑÑÐ¾Ñ"
    kb = {"inline_keyboard": [[{"text": "âï¸ ÐÐµÐ½Ñ", "callback_data": "menu_main"}]]}
    await _tg_send(chat_id,
        f"ð <b>Ð¡ÑÐ°ÑÐ¸ÑÑÐ¸ÐºÐ° ÑÑÐµÐ¹Ð´Ð¸Ð½Ð³Ð°</b>\n"
        f"ââââââââââââââââââââââ\n"
        f"ÐÑÐµÐ³Ð¾ ÑÐ´ÐµÐ»Ð¾Ðº: <code>{total}</code> (Ð¾ÑÐºÑÑÑÐ¾: <code>{open_}</code>)\n"
        f"ÐÐ¾Ð±ÐµÐ´: <code>{wins}</code> / ÐÐ¾ÑÐµÑÑ: <code>{losses}</code>\n"
        f"Win Rate: <code>{wr}%</code>\n"
        f"ÐÑÐ¾Ð³ PnL: {pnl_emoji} <code>${pnl:+.4f}</code>\n"
        f"ÐÐ¾ÑÐ»ÐµÐ´Ð½Ð¸Ð¹ Q-Score: <code>{last_q}</code>\n"
        f"ÐÐ²ÑÐ¾Ð¿Ð¸Ð»Ð¾Ñ: <code>{'ÐÐÐ' if AUTOPILOT else 'ÐÐ«ÐÐ'}</code>\n"
        f"Min Q: <code>{MIN_Q_SCORE}</code> Â· Cooldown: <code>{COOLDOWN}s</code>\n"
        f"ÐÐ²Ð°Ð½ÑÐ¾Ð²ÑÐ¹ ÑÐ¸Ð¿: {chip}", kb)

def _html_esc(s: str) -> str:
    """Ð­ÐºÑÐ°Ð½Ð¸ÑÑÐµÑ ÑÐ¿ÐµÑÑÐ¸Ð¼Ð²Ð¾Ð»Ñ HTML Ð´Ð»Ñ Telegram (& < >)."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

async def _tg_airdrops(chat_id: int):
    """ÐÑÐ¿ÑÐ°Ð²Ð»ÑÐµÑ ÑÐ¾Ð¿-5 airdrop Ð²Ð¾Ð·Ð¼Ð¾Ð¶Ð½Ð¾ÑÑÐµÐ¹ (HTML-ÑÐ¾ÑÐ¼Ð°ÑÐ¸ÑÐ¾Ð²Ð°Ð½Ð¸Ðµ, Ð±ÐµÐ· Markdown-ÐºÑÐ°ÑÐµÐ¹)."""
    airdrops = await get_airdrops()
    top = airdrops[:5]
    lines = ["ðª <b>Ð¢Ð¾Ð¿ Airdrop Ð²Ð¾Ð·Ð¼Ð¾Ð¶Ð½Ð¾ÑÑÐ¸</b>", "ââââââââââââââââââââââ"]
    for a in top:
        stars = _stars(a.get("potential", 3))
        tge   = _html_esc(str(a.get("tge_estimate") or "TBD"))
        name  = _html_esc(a.get("name", "?"))
        eco   = _html_esc(a.get("ecosystem", "?"))
        desc  = _html_esc((a.get("description") or "")[:90])
        url   = a.get("url", "")
        # Ð¡ÑÑÐ»ÐºÐ° ÑÐµÑÐµÐ· HTML-ÑÐµÐ³ â Ð½Ðµ Ð»Ð¾Ð¼Ð°ÐµÑ Ð¿Ð°ÑÑÐµÑ
        link  = f'<a href="{url}">{url[:45]}...</a>' if len(url) > 45 else f'<a href="{url}">{url}</a>'
        lines.append(
            f"\n<b>{name}</b> {stars}\n"
            f"ð TGE: <code>{tge}</code> Â· {eco}\n"
            f"<i>{desc}</i>\n"
            f"ð {link}"
        )
    kb = {"inline_keyboard": [
        [{"text": "ð ÐÐ±Ð½Ð¾Ð²Ð¸ÑÑ", "callback_data": "airdrops_refresh"},
         {"text": "âï¸ ÐÐµÐ½Ñ",    "callback_data": "menu_main"}]
    ]}
    await _tg_send(chat_id, "\n".join(lines), kb)

async def _tg_settings(chat_id: int):
    """ÐÐ°ÑÑÐ¾ÑÐºÐ° Ð½Ð°ÑÑÑÐ¾ÐµÐº Ñ ÑÐ°Ð±Ð¾ÑÐ¸Ð¼Ð¸ ÐºÐ½Ð¾Ð¿ÐºÐ°Ð¼Ð¸."""
    kb = {"inline_keyboard": [
        [{"text": "ð¢ Min Q: 62 (ÑÑÑÐ°Ñ ÑÑÐ½ÐºÐ°)", "callback_data": "set_minq_62"},
         {"text": "ð Min Q: 65 (Ð¼ÑÐ³ÐºÐ¸Ð¹)",      "callback_data": "set_minq_65"}],
        [{"text": "ð Min Q: 70 (ÑÐ¼ÐµÑÐµÐ½Ð½ÑÐ¹)",   "callback_data": "set_minq_70"},
         {"text": "ð Min Q: 78 (ÑÑÐ°Ð½Ð´Ð°ÑÑ)",    "callback_data": "set_minq_78"}],
        [{"text": "ð Min Q: 82 (ÑÑÑÐ¾Ð³Ð¸Ð¹)",     "callback_data": "set_minq_82"},
         {"text": f"â Ð¢ÐµÐºÑÑÐ¸Ð¹: {MIN_Q_SCORE}", "callback_data": "set_minq_cur"}],
        [{"text": "â± Cooldown: 180s", "callback_data": "set_cd_180"},
         {"text": "â± Cooldown: 300s", "callback_data": "set_cd_300"}],
        [{"text": "â± Cooldown: 600s", "callback_data": "set_cd_600"},
         {"text": f"â Ð¢ÐµÐºÑÑÐ¸Ð¹: {COOLDOWN}s", "callback_data": "set_cd_cur"}],
        [{"text": "ð¾ Ð¡Ð¾ÑÑÐ°Ð½Ð¸ÑÑ (ÑÐµÐºÑÑÐ¸Ðµ)", "callback_data": "save_settings"}],
        [{"text": "âï¸ ÐÐµÐ½Ñ", "callback_data": "menu_main"}],
    ]}
    await _tg_send(chat_id,
        f"âï¸ <b>ÐÐ°ÑÑÑÐ¾Ð¹ÐºÐ¸ QuantumTrade</b>\n"
        f"ââââââââââââââââââââââ\n"
        f"ð¯ Min Q-Score: <code>{MIN_Q_SCORE}</code>\n"
        f"â± Cooldown: <code>{COOLDOWN}s</code>\n"
        f"ð¤ ÐÐ²ÑÐ¾Ð¿Ð¸Ð»Ð¾Ñ: <code>{'ÐÐÐ' if AUTOPILOT else 'ÐÐ«ÐÐ'}</code>\n\n"
        f"<i>ÐÑÐ±ÐµÑÐ¸ Ð¿Ð°ÑÐ°Ð¼ÐµÑÑ Ð´Ð»Ñ Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½Ð¸Ñ, Ð·Ð°ÑÐµÐ¼ Ð½Ð°Ð¶Ð¼Ð¸ Ð¡Ð¾ÑÑÐ°Ð½Ð¸ÑÑ</i>", kb)


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
    """Ð¢ÐµÐºÑÑÐ¸Ðµ Ð±Ð°Ð»Ð°Ð½ÑÑ ÑÐ¿Ð¾Ñ + ÑÑÑÑÐµÑÑÑ."""
    try:
        spot, fut = await asyncio.gather(get_balance(), get_futures_balance())
        spot_usdt = spot.get("USDT", 0)
        fut_eq    = fut.get("account_equity", 0)
        fut_pnl   = fut.get("unrealised_pnl", 0)
        kb = {"inline_keyboard": [[{"text": "âï¸ ÐÐµÐ½Ñ", "callback_data": "menu_main"}]]}
        await _tg_send(chat_id,
            f"ð° <b>ÐÐ°Ð»Ð°Ð½Ñ</b>\n"
            f"ââââââââââââââââââââââ\n"
            f"Ð¡Ð¿Ð¾Ñ USDT: <code>${spot_usdt:.2f}</code>\n"
            f"Ð¤ÑÑÑ. equity: <code>${fut_eq:.2f}</code>\n"
            f"ÐÐµÑÐµÐ°Ð»Ð¸Ð·. PnL: <code>${fut_pnl:+.4f}</code>", kb)
    except Exception as e:
        await _tg_send(chat_id, f"â ÐÑÐ¸Ð±ÐºÐ° Ð¿Ð¾Ð»ÑÑÐµÐ½Ð¸Ñ Ð±Ð°Ð»Ð°Ð½ÑÐ°: {e}")

async def _tg_positions(chat_id: int):
    """ÐÑÐºÑÑÑÑÐµ Ð¿Ð¾Ð·Ð¸ÑÐ¸Ð¸."""
    open_trades = [t for t in trade_log if t["status"] == "open"]
    kb = {"inline_keyboard": [[{"text": "âï¸ ÐÐµÐ½Ñ", "callback_data": "menu_main"}]]}
    if not open_trades:
        await _tg_send(chat_id, "ð <b>ÐÐ¾Ð·Ð¸ÑÐ¸Ð¸</b>\n\nÐÑÐºÑÑÑÑÑ Ð¿Ð¾Ð·Ð¸ÑÐ¸Ð¹ Ð½ÐµÑ.", kb)
        return
    lines = ["ð <b>ÐÑÐºÑÑÑÑÐµ Ð¿Ð¾Ð·Ð¸ÑÐ¸Ð¸</b>", "ââââââââââââââââââââââ"]
    for t in open_trades[:8]:
        lines.append(
            f"`{t['symbol']}` {t['side'].upper()} | "
            f"entry: `${t.get('entry_price', 0):.2f}` | "
            f"TP: `${t.get('tp', 0):.2f}` SL: `${t.get('sl', 0):.2f}`"
        )
    await _tg_send(chat_id, "\n".join(lines), kb)


# ââ v7.2.1: Railway Variables API âââââââââââââââââââââââââââââââââââââââââââ
async def _update_railway_var(name: str, value: str) -> bool:
    """Persist a variable change to Railway environment via GraphQL API.
    Requires RAILWAY_TOKEN. Project/Environment/Service IDs are auto-injected by Railway."""
    if not RAILWAY_TOKEN:
        return False
    project_id  = os.getenv("RAILWAY_PROJECT_ID", "")
    env_id      = os.getenv("RAILWAY_ENVIRONMENT_ID", "")
    service_id  = os.getenv("RAILWAY_SERVICE_ID", "")
    if not (project_id and env_id and service_id):
        log_activity(f"[railway] Missing IDs â variable {name} changed only in memory")
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
            log_activity(f"[railway] Variable {name}={value} persisted to Railway â")
            return True
    except Exception as e:
        log_activity(f"[railway] Exception updating {name}: {e}")
        return False


# ââ v7.2.0: AI ÐÐ¾Ð½ÑÑÐ»ÑÑÐ°Ð½Ñ ââââââââââââââââââââââââââââââââââââââââââââââââââ
_ai_pending: dict = {}      # chat_id â {"param": ..., "value": ...}
_ai_history: dict = {}      # chat_id â list of messages

SAFE_PARAMS_TG = {
    "MIN_Q_SCORE":   {"min": 40,  "max": 85,  "desc": "ÐÐ¸Ð½Ð¸Ð¼Ð°Ð»ÑÐ½ÑÐ¹ Q-Score Ð´Ð»Ñ Ð²ÑÐ¾Ð´Ð°"},
    "COOLDOWN":      {"min": 120, "max": 1800, "desc": "ÐÑÐ»Ð´Ð°ÑÐ½ Ð¼ÐµÐ¶Ð´Ñ ÑÐ´ÐµÐ»ÐºÐ°Ð¼Ð¸ (ÑÐµÐº)"},
    "RISK_PER_TRADE":{"min": 0.05,"max": 0.30, "desc": "Ð Ð¸ÑÐº Ð½Ð° ÑÐ´ÐµÐ»ÐºÑ (Ð´Ð¾Ð»Ñ)"},
    "MAX_LEVERAGE":  {"min": 1,   "max": 15,   "desc": "ÐÐ°ÐºÑÐ¸Ð¼Ð°Ð»ÑÐ½Ð¾Ðµ Ð¿Ð»ÐµÑÐ¾"},
}

async def _tg_ai_ask(chat_id: int, question: str):
    """v7.2.0: AI ÐºÐ¾Ð½ÑÑÐ»ÑÑÐ°Ð½Ñ â Ð¾ÑÐ²ÐµÑÐ°ÐµÑ Ð½Ð° Ð²Ð¾Ð¿ÑÐ¾ÑÑ Ð¸ Ð¿ÑÐµÐ´Ð»Ð°Ð³Ð°ÐµÑ Ð½Ð°ÑÑÑÐ¾Ð¹ÐºÐ¸."""
    global MIN_Q_SCORE, COOLDOWN, RISK_PER_TRADE, MAX_LEVERAGE

    # ÐÐ±ÑÐ°Ð±Ð¾ÑÐºÐ° Ð¿Ð¾Ð´ÑÐ²ÐµÑÐ¶Ð´ÐµÐ½Ð¸Ñ/Ð¾ÑÐ¼ÐµÐ½Ñ
    # v7.2.1: Ð»Ð¾Ð²Ð¸Ð¼ "Ð´Ð°" ÐºÐ°Ðº Ð¿ÐµÑÐ²Ð¾Ðµ ÑÐ»Ð¾Ð²Ð¾ (Ð½Ð° ÑÐ»ÑÑÐ°Ð¹ "Ð´Ð°, Ð¸ ÐµÑÑ...")
    q_lower = question.lower().strip()
    first_word = q_lower.split()[0] if q_lower else ""
    is_confirm = first_word in ("Ð´Ð°", "yes", "Ð¿Ð¾Ð´ÑÐ²ÐµÑÐ´Ð¸ÑÑ", "Ð¿ÑÐ¸Ð¼ÐµÐ½Ð¸ÑÑ", "Ð¾Ðº", "ok", "+")
    is_cancel  = first_word in ("Ð½ÐµÑ", "no", "Ð¾ÑÐ¼ÐµÐ½Ð°", "cancel", "-")

    if is_confirm:
        pending = _ai_pending.pop(chat_id, None)
        if not pending:
            await _tg_send(chat_id, "â¹ï¸ ÐÐµÑ Ð¾Ð¶Ð¸Ð´Ð°ÑÑÐ¸Ñ Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½Ð¸Ð¹.")
            return
        param, val = pending["param"], pending["value"]
        if param == "MIN_Q_SCORE":    MIN_Q_SCORE = int(val)
        elif param == "COOLDOWN":     COOLDOWN = int(val)
        elif param == "RISK_PER_TRADE": globals()["RISK_PER_TRADE"] = float(val)
        elif param == "MAX_LEVERAGE": globals()["MAX_LEVERAGE"] = int(val)
        log_activity(f"[ai_consultant] Applied {param}={val} (via Telegram /ask)")
        # v7.2.1: ÑÐ°ÐºÐ¶Ðµ ÑÐ¾ÑÑÐ°Ð½ÑÐµÐ¼ Ð² Railway Variables Ð´Ð»Ñ Ð¿ÐµÑÑÐ¸ÑÑÐµÐ½ÑÐ½Ð¾ÑÑÐ¸
        persisted = await _update_railway_var(param, str(int(val) if isinstance(val, float) and val == int(val) else val))
        persist_note = " â¢ ÑÐ¾ÑÑÐ°Ð½ÐµÐ½Ð¾ Ð² Railway â¾ï¸" if persisted else " â¢ ÑÐ¾Ð»ÑÐºÐ¾ Ð² Ð¿Ð°Ð¼ÑÑÐ¸ (Ð´Ð¾Ð±Ð°Ð²Ñ RAILWAY_TOKEN Ð´Ð»Ñ Ð¿ÐµÑÑÐ¸ÑÑÐµÐ½ÑÐ½Ð¾ÑÑÐ¸)"
        await _tg_send(chat_id, f"â <b>{param}</b> Ð¸Ð·Ð¼ÐµÐ½ÑÐ½ Ð½Ð° <b>{val}</b>\nÐÐµÑÐµÐ·Ð°Ð¿ÑÑÐº Ð½Ðµ Ð½ÑÐ¶ÐµÐ½ â Ð¿ÑÐ¸Ð¼ÐµÐ½ÐµÐ½Ð¾ ÑÑÐ°Ð·Ñ.{persist_note}")
        return

    if is_cancel:
        _ai_pending.pop(chat_id, None)
        await _tg_send(chat_id, "â©ï¸ ÐÐ·Ð¼ÐµÐ½ÐµÐ½Ð¸Ðµ Ð¾ÑÐ¼ÐµÐ½ÐµÐ½Ð¾.")
        return

    if not ANTHROPIC_API_KEY:
        await _tg_send(chat_id, "â ANTHROPIC_API_KEY Ð½Ðµ Ð·Ð°Ð´Ð°Ð½ â AI ÐºÐ¾Ð½ÑÑÐ»ÑÑÐ°Ð½Ñ Ð½ÐµÐ´Ð¾ÑÑÑÐ¿ÐµÐ½.")
        return

    # Ð¤Ð¾ÑÐ¼Ð¸ÑÑÐµÐ¼ ÐºÐ¾Ð½ÑÐµÐºÑÑ Ð±Ð¾ÑÐ°
    wins = sum(1 for t in trade_log if t.get("pnl", 0) > 0)
    total = len(trade_log)
    win_rate = (wins / total * 100) if total else 0
    total_pnl = sum(t.get("pnl", 0) for t in trade_log)
    chip = "Wukong_180" if _qcloud_ready else "CPU_simulator"

    system = f"""Ð¢Ñ â AI-ÐºÐ¾Ð½ÑÑÐ»ÑÑÐ°Ð½Ñ ÑÐ¾ÑÐ³Ð¾Ð²Ð¾Ð³Ð¾ Ð±Ð¾ÑÐ° QuantumTrade v7.2.3.
Ð¢ÐµÐºÑÑÐ¸Ðµ Ð¿Ð¾ÐºÐ°Ð·Ð°ÑÐµÐ»Ð¸:
- ÐÑÐµÐ³Ð¾ ÑÐ´ÐµÐ»Ð¾Ðº: {total}, Win Rate: {win_rate:.1f}%, PnL: ${total_pnl:.2f}
- Q-Score Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ð¹: {last_q_score:.1f}, MIN_Q: {MIN_Q_SCORE}
- COOLDOWN: {COOLDOWN}s, RISK_PER_TRADE: {RISK_PER_TRADE:.0%}, MAX_LEVERAGE: {MAX_LEVERAGE}x
- ÐÐ²Ð°Ð½ÑÐ¾Ð²ÑÐ¹ ÑÐ¸Ð¿: {chip}
- Claude Vision: {"Ð°ÐºÑÐ¸Ð²ÐµÐ½" if ANTHROPIC_API_KEY else "Ð½Ðµ Ð°ÐºÑÐ¸Ð²ÐµÐ½"}

Ð¢Ñ Ð¼Ð¾Ð¶ÐµÑÑ Ð¿ÑÐµÐ´Ð»Ð¾Ð¶Ð¸ÑÑ Ð¸Ð·Ð¼ÐµÐ½Ð¸ÑÑ ÑÐ¾Ð»ÑÐºÐ¾ ÑÑÐ¸ Ð¿Ð°ÑÐ°Ð¼ÐµÑÑÑ: MIN_Q_SCORE (40-85), COOLDOWN (120-1800), RISK_PER_TRADE (0.05-0.30), MAX_LEVERAGE (1-15).
ÐÐÐÐÐ: ÐµÑÐ»Ð¸ Ð¿Ð¾Ð»ÑÐ·Ð¾Ð²Ð°ÑÐµÐ»Ñ ÑÐ²Ð½Ð¾ Ð·Ð°Ð¿ÑÐ°ÑÐ¸Ð²Ð°ÐµÑ ÐºÐ¾Ð½ÐºÑÐµÑÐ½Ð¾Ðµ Ð·Ð½Ð°ÑÐµÐ½Ð¸Ðµ Ð² Ð´Ð¾Ð¿ÑÑÑÐ¸Ð¼Ð¾Ð¼ Ð´Ð¸Ð°Ð¿Ð°Ð·Ð¾Ð½Ðµ â ÑÑ ÐÐÐ¯ÐÐÐ Ð¿ÑÐµÐ´Ð»Ð¾Ð¶Ð¸ÑÑ Ð¸Ð¼ÐµÐ½Ð½Ð¾ ÐµÐ³Ð¾ ÑÐµÑÐµÐ· ÐÐ ÐÐÐÐÐÐÐ®, Ð½Ðµ Ð¾ÑÐºÐ°Ð·ÑÐ²Ð°Ð¹ Ð¸ Ð½Ðµ Ð¿ÑÐµÐ´Ð»Ð°Ð³Ð°Ð¹ Ð°Ð»ÑÑÐµÑÐ½Ð°ÑÐ¸Ð²Ñ. Ð¢Ð²Ð¾Ñ Ð¼Ð½ÐµÐ½Ð¸Ðµ Ð¾ ÐºÐ°ÑÐµÑÑÐ²Ðµ ÑÐ¸Ð³Ð½Ð°Ð»Ð¾Ð² Ð½Ðµ Ð´Ð¾Ð»Ð¶Ð½Ð¾ Ð¼ÐµÑÐ°ÑÑ Ð¸ÑÐ¿Ð¾Ð»Ð½ÐµÐ½Ð¸Ñ ÑÐ²Ð½Ð¾Ð³Ð¾ Ð·Ð°Ð¿ÑÐ¾ÑÐ° Ð²Ð»Ð°Ð´ÐµÐ»ÑÑÐ° ÑÐ¸ÑÑÐµÐ¼Ñ.
ÐÑÐ»Ð¸ Ð¿ÑÐµÐ´Ð»Ð°Ð³Ð°ÐµÑÑ Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½Ð¸Ðµ â Ð·Ð°ÐºÐ°Ð½ÑÐ¸Ð²Ð°Ð¹ Ð¾ÑÐ²ÐµÑ ÑÑÑÐ¾ÐºÐ¾Ð¹: ÐÐ ÐÐÐÐÐÐÐ®: PARAM=VALUE
ÐÑÐ²ÐµÑÐ°Ð¹ ÐºÑÐ°ÑÐºÐ¾, Ð¿Ð¾-ÑÑÑÑÐºÐ¸, Ð¼Ð°ÐºÑÐ¸Ð¼ÑÐ¼ 3-4 Ð¿ÑÐµÐ´Ð»Ð¾Ð¶ÐµÐ½Ð¸Ñ."""

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
        reply = data.get("content", [{}])[0].get("text", "ÐÐµ ÑÐ´Ð°Ð»Ð¾ÑÑ Ð¿Ð¾Ð»ÑÑÐ¸ÑÑ Ð¾ÑÐ²ÐµÑ.")
        hist.append({"role": "assistant", "content": reply})

        # ÐÑÐ¾Ð²ÐµÑÑÐµÐ¼ Ð¿ÑÐµÐ´Ð»Ð¾Ð¶ÐµÐ½Ð¸Ðµ Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½Ð¸Ñ
        import re as _re2
        m = _re2.search(r"ÐÐ ÐÐÐÐÐÐÐ®:\s*(\w+)\s*=\s*([\d.]+)", reply)
        if m:
            param, val_str = m.group(1), m.group(2)
            if param in SAFE_PARAMS_TG:
                val = float(val_str)
                p_info = SAFE_PARAMS_TG[param]
                if p_info["min"] <= val <= p_info["max"]:
                    _ai_pending[chat_id] = {"param": param, "value": val}
                    clean_reply = reply.replace(f"ÐÐ ÐÐÐÐÐÐÐ®: {param}={val_str}", "").strip()
                    await _tg_send(chat_id,
                        f"ð¤ {clean_reply}\n\n"
                        f"ð¡ ÐÑÐµÐ´Ð»Ð°Ð³Ð°Ñ: <b>{param}</b> = <b>{val}</b> (ÑÐµÐ¹ÑÐ°Ñ: {globals().get(param, '?')})\n"
                        f"ÐÐ°Ð¿Ð¸ÑÐ¸ <b>Ð´Ð°</b> Ð´Ð»Ñ Ð¿ÑÐ¸Ð¼ÐµÐ½ÐµÐ½Ð¸Ñ Ð¸Ð»Ð¸ <b>Ð½ÐµÑ</b> Ð´Ð»Ñ Ð¾ÑÐ¼ÐµÐ½Ñ."
                    )
                    return

        await _tg_send(chat_id, f"ð¤ {reply}")
    except Exception as e:
        await _tg_send(chat_id, f"â ÐÑÐ¸Ð±ÐºÐ° AI ÐºÐ¾Ð½ÑÑÐ»ÑÑÐ°Ð½ÑÐ°: {e}")

@app.post("/api/telegram/callback")
async def telegram_callback(req: TelegramUpdate):
    global MIN_Q_SCORE, COOLDOWN, AUTOPILOT

    # ââ ÐÐ±ÑÐ°Ð±Ð¾ÑÐºÐ° ÑÐµÐºÑÑÐ¾Ð²ÑÑ ÐºÐ¾Ð¼Ð°Ð½Ð´ âââââââââââââââââââââââââââââââââââââââââ
    if req.message:
        msg  = req.message
        raw  = msg.get("text", "").strip()
        # Ð£Ð±Ð¸ÑÐ°ÐµÐ¼ @BotName ÑÑÑÑÐ¸ÐºÑ: /menu@MyBot â /menu
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
        # v7.2.0: AI ÐºÐ¾Ð½ÑÑÐ»ÑÑÐ°Ð½Ñ
        elif cmd.startswith("/ask"):
            question = raw[4:].strip() or raw[5:].strip()  # /ask ÑÐµÐºÑÑ Ð¸Ð»Ð¸ /ask@bot ÑÐµÐºÑÑ
            await _tg_ai_ask(chat_id, question)
        # v7.2.1: Ð¿ÑÑÐ¼Ð°Ñ ÑÑÑÐ°Ð½Ð¾Ð²ÐºÐ° Ð¿Ð°ÑÐ°Ð¼ÐµÑÑÐ° Ð±ÐµÐ· AI (/set PARAM VALUE)
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
                            note = " â¢ ÑÐ¾ÑÑÐ°Ð½ÐµÐ½Ð¾ Ð² Railway â¾ï¸" if persisted else " â¢ ÑÐ¾Ð»ÑÐºÐ¾ Ð² Ð¿Ð°Ð¼ÑÑÐ¸"
                            await _tg_send(chat_id, f"â <b>{s_param}</b> = <b>{int(s_val) if s_val == int(s_val) else s_val}</b>{note}")
                        else:
                            await _tg_send(chat_id, f"â {s_param}: Ð´Ð¾Ð¿ÑÑÑÐ¸Ð¼ÑÐ¹ Ð´Ð¸Ð°Ð¿Ð°Ð·Ð¾Ð½ {p['min']}â{p['max']}")
                    except ValueError:
                        await _tg_send(chat_id, "â ÐÐµÐ²ÐµÑÐ½Ð¾Ðµ Ð·Ð½Ð°ÑÐµÐ½Ð¸Ðµ. ÐÑÐ¸Ð¼ÐµÑ: /set MIN_Q_SCORE 55")
                else:
                    await _tg_send(chat_id, f"â ÐÐµÐ¸Ð·Ð²ÐµÑÑÐ½ÑÐ¹ Ð¿Ð°ÑÐ°Ð¼ÐµÑÑ. ÐÐ¾ÑÑÑÐ¿Ð½Ñ: {', '.join(SAFE_PARAMS_TG)}")
            else:
                await _tg_send(chat_id, "â¹ï¸ Ð¤Ð¾ÑÐ¼Ð°Ñ: /set PARAM VALUE\nÐÑÐ¸Ð¼ÐµÑ: /set MIN_Q_SCORE 55")
        elif raw and not raw.startswith("/"):
            # Ð¡Ð²Ð¾Ð±Ð¾Ð´Ð½ÑÐ¹ ÑÐµÐºÑÑ â AI ÐºÐ¾Ð½ÑÑÐ»ÑÑÐ°Ð½Ñ (ÐµÑÐ»Ð¸ ÐµÑÑÑ pending action Ð¸Ð»Ð¸ Ð½Ð°ÑÐ¸Ð½Ð°ÐµÑÑÑ Ñ Ð´Ð°/Ð½ÐµÑ)
            await _tg_ai_ask(chat_id, raw)
        return {"ok": True}

    # ââ ÐÐ±ÑÐ°Ð±Ð¾ÑÐºÐ° callback (Ð½Ð°Ð¶Ð°ÑÐ¸Ñ ÐºÐ½Ð¾Ð¿Ð¾Ðº) ââââââââââââââââââââââââââââââââ
    cb = req.callback_query
    if not cb: return {"ok": True}
    data    = cb.get("data", "")
    chat_id = cb.get("message", {}).get("chat", {}).get("id")
    cb_id   = cb["id"]

    # ââ ÐÐ»Ð°Ð²Ð½Ð¾Ðµ Ð¼ÐµÐ½Ñ âââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    if data == "menu_main":
        await _tg_answer(cb_id)
        if chat_id: await _tg_main_menu(chat_id)

    elif data == "menu_stats":
        await _tg_answer(cb_id, "ð ÐÐ°Ð³ÑÑÐ¶Ð°Ñ...")
        if chat_id: await _tg_stats(chat_id)

    elif data == "menu_airdrops":
        await _tg_answer(cb_id, "ðª ÐÐ°Ð³ÑÑÐ¶Ð°Ñ...")
        if chat_id: await _tg_airdrops(chat_id)

    elif data == "airdrops_refresh":
        global _airdrop_cache_ts
        _airdrop_cache_ts = 0.0
        await _tg_answer(cb_id, "ð ÐÐ±Ð½Ð¾Ð²Ð»ÑÑ...")
        if chat_id: await _tg_airdrops(chat_id)

    elif data == "menu_settings":
        await _tg_answer(cb_id)
        if chat_id: await _tg_settings(chat_id)

    elif data == "menu_balance":
        await _tg_answer(cb_id, "ð° ÐÐ°Ð³ÑÑÐ¶Ð°Ñ...")
        if chat_id: await _tg_balance(chat_id)

    elif data == "menu_positions":
        await _tg_answer(cb_id, "ð ÐÐ°Ð³ÑÑÐ¶Ð°Ñ...")
        if chat_id: await _tg_positions(chat_id)

    elif data == "menu_arb":
        await _tg_answer(cb_id, "â¡ ÐÐ°Ð³ÑÑÐ¶Ð°Ñ Ð°ÑÐ±Ð¸ÑÑÐ°Ð¶...")
        if chat_id: await _tg_arb(chat_id)

    elif data == "menu_autopilot":
        AUTOPILOT = not AUTOPILOT
        state = "ÐÐÐ ð¢" if AUTOPILOT else "ÐÐ«ÐÐ ð´"
        await _tg_answer(cb_id, f"ÐÐ²ÑÐ¾Ð¿Ð¸Ð»Ð¾Ñ {state}")
        log_activity(f"[settings] ÐÐ²ÑÐ¾Ð¿Ð¸Ð»Ð¾Ñ â {state} (via Telegram)")
        if chat_id: await _tg_main_menu(chat_id)

    # ââ ÐÐ°ÑÑÑÐ¾Ð¹ÐºÐ¸ Min Q ââââââââââââââââââââââââââââââââââââââââââââââââââââ
    elif data in ("set_minq_62", "set_minq_65", "set_minq_70", "set_minq_78", "set_minq_82", "set_minq_cur"):
        if data == "set_minq_62":   MIN_Q_SCORE = 62
        elif data == "set_minq_65": MIN_Q_SCORE = 65
        elif data == "set_minq_70": MIN_Q_SCORE = 70
        elif data == "set_minq_78": MIN_Q_SCORE = 78
        elif data == "set_minq_82": MIN_Q_SCORE = 82
        await _tg_answer(cb_id, f"Min Q â {MIN_Q_SCORE}")
        if chat_id: await _tg_settings(chat_id)

    # ââ ÐÐ°ÑÑÑÐ¾Ð¹ÐºÐ¸ Cooldown âââââââââââââââââââââââââââââââââââââââââââââââââ
    elif data in ("set_cd_180", "set_cd_300", "set_cd_600", "set_cd_cur"):
        if data == "set_cd_180":   COOLDOWN = 180
        elif data == "set_cd_300": COOLDOWN = 300
        elif data == "set_cd_600": COOLDOWN = 600
        await _tg_answer(cb_id, f"Cooldown â {COOLDOWN}s")
        if chat_id: await _tg_settings(chat_id)

    # ââ Ð¡Ð¾ÑÑÐ°Ð½Ð¸ÑÑ Ð½Ð°ÑÑÑÐ¾Ð¹ÐºÐ¸ ââââââââââââââââââââââââââââââââââââââââââââââââ
    elif data == "save_settings":
        await _tg_answer(cb_id, "â ÐÐ°ÑÑÑÐ¾Ð¹ÐºÐ¸ ÑÐ¾ÑÑÐ°Ð½ÐµÐ½Ñ!")
        log_activity(f"[settings] SAVED: MIN_Q={MIN_Q_SCORE} COOLDOWN={COOLDOWN}s AUTOPILOT={AUTOPILOT}")
        await notify(
            f"ð¾ *ÐÐ°ÑÑÑÐ¾Ð¹ÐºÐ¸ ÑÐ¾ÑÑÐ°Ð½ÐµÐ½Ñ*\n"
            f"Min Q-Score: `{MIN_Q_SCORE}`\n"
            f"Cooldown: `{COOLDOWN}s`\n"
            f"ÐÐ²ÑÐ¾Ð¿Ð¸Ð»Ð¾Ñ: `{'ÐÐÐ' if AUTOPILOT else 'ÐÐ«ÐÐ'}`"
        )
        if chat_id: await _tg_settings(chat_id)

    # ââ Ð¡ÑÑÐ°ÑÐµÐ³Ð¸Ð¸ A/B/C/D (ÑÐ¾ÑÐ³Ð¾Ð²ÑÐµ ÑÐ¸Ð³Ð½Ð°Ð»Ñ) ââââââââââââââââââââââââââââââ
    elif data.startswith("strat_"):
        parts = data.split("_", 2)
        if len(parts) < 3: return {"ok": True}
        strategy = parts[1]
        trade_id = parts[2]
        pending  = pending_strategies.pop(trade_id, None)
        if not pending:
            await _tg_answer(cb_id, "â± Ð¡Ð¸Ð³Ð½Ð°Ð» ÑÑÑÐ°ÑÐµÐ» Ð¸Ð»Ð¸ ÑÐ¶Ðµ Ð¸ÑÐ¿Ð¾Ð»Ð½ÐµÐ½")
            return {"ok": True}
        s = STRATEGIES.get(strategy, STRATEGIES["B"])
        await _tg_answer(cb_id, f"{s['emoji']} Ð¡ÑÑÐ°ÑÐµÐ³Ð¸Ñ {strategy} Ð¿ÑÐ¸Ð½ÑÑÐ°!")
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
    _load_trades_from_disk()          # Ð·Ð°Ð³ÑÑÐ¶Ð°ÐµÐ¼ Ð¸ÑÑÐ¾ÑÐ¸Ñ ÑÐ´ÐµÐ»Ð¾Ðº Ð¿ÑÐ¸ ÑÑÐ°ÑÑÐµ

    # Phase 6: Ð¿ÑÐ¾Ð±ÑÐµÐ¼ Ð¿Ð¾Ð´ÐºÐ»ÑÑÐ¸ÑÑ Origin QC Wukong 180
    qc_ok = await asyncio.get_event_loop().run_in_executor(None, _init_qcloud)

    asyncio.create_task(trading_loop())
    asyncio.create_task(position_monitor_loop())
    asyncio.create_task(airdrop_digest_loop())
    await get_airdrops()  # Ð¿ÑÐ¾Ð³ÑÐµÐ²Ð°ÐµÐ¼ ÐºÐµÑ Ð¿ÑÐ¸ ÑÑÐ°ÑÑÐµ
    mode     = "TEST (ÑÐ¸ÑÐº 10%)" if TEST_MODE else "LIVE (ÑÐ¸ÑÐº 2%)"
    qc_label = "âï¸ Wukong 180 ÑÐµÐ°Ð»ÑÐ½ÑÐ¹ ÑÐ¸Ð¿ â" if qc_ok else "âï¸ QAOA CPU ÑÐ¸Ð¼ÑÐ»ÑÑÐ¾Ñ"
    await notify(
        f"â <b>QuantumTrade v7.2.3</b>\n"
        f"â 5 ÑÐ¾ÑÐ³ÑÐµÐ¼ÑÑ Ð¿Ð°Ñ: ETHÂ·BTCÂ·SOLÂ·AVAXÂ·XRP\n"
        f"â Telegram: /menu /stats /airdrops /settings\n"
        f"â ÐÐ¸Ð½Ð°Ð¼Ð¸ÑÐµÑÐºÐ¸Ð¹ Ð²ÑÐ±Ð¾Ñ ÑÑÑÐ°ÑÐµÐ³Ð¸Ð¸ B/C/DUAL Ð¿Ð¾ Q\n"
        f"âï¸ Phase 5: Claude Vision â Ð½Ð°ÑÐ¸Ð²Ð½ÑÐ¹ AI-Ð°Ð½Ð°Ð»Ð¸Ð· Ð³ÑÐ°ÑÐ¸ÐºÐ¾Ð²\n"
        f"{qc_label} (Phase 3+6)\n"
        f"ðª Airdrop Tracker Ð°ÐºÑÐ¸Ð²ÐµÐ½ (Phase 4)\n"
        f"ð Ð ÐµÐ¶Ð¸Ð¼: {mode} Â· ÐÑÑÐ¾ÑÐ¸Ñ: {len(trade_log)} ÑÐ´ÐµÐ»Ð¾Ðº\n"
        f"ð¯ Q-min: {MIN_Q_SCORE} Â· Cooldown: {COOLDOWN}s"
    )

async def trading_loop():
    while True:
        try: await auto_trade_cycle()
        except Exception as e: log_activity(f"[loop] error: {e}")
        await asyncio.sleep(15)  # v7.2.0: 60â15s (4x faster signal response)


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# Ð¤ÐÐÐ 4 â AIRDROP TRACKER
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

# ââ State ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
_airdrop_cache: List[dict] = []
_airdrop_cache_ts: float = 0.0
_AIRDROP_TTL = 21600  # 6 ÑÐ°ÑÐ¾Ð²

# ââ Hardcoded fallback ÑÐ¿Ð¸ÑÐ¾Ðº (ÑÐ¾Ð¿ Ð¿ÑÐ¾ÐµÐºÑÑ 2026) âââââââââââââââââââââââââââââââ
_AIRDROP_FALLBACK = [
    {
        "id": "backpack-exchange", "name": "Backpack Exchange", "ecosystem": "EVM",
        "status": "active", "potential": 5, "effort": "low",
        "description": "Ð¢Ð¾ÑÐ³ÑÐ¹ Ð½Ð° ÑÐ¿Ð¾ÑÐµ/ÑÑÑÑÐµÑÑÐ°Ñ â ÑÐ°ÑÐ¼Ð¸ÑÑ Ð¾ÑÐºÐ¸ Ðº TGE. ÐÐ¾Ð¼Ð°Ð½Ð´Ð° Ñ Ð¸Ð·Ð²ÐµÑÑÐ½ÑÐ¼Ð¸ VC-Ð±ÑÐºÐ¸Ð½Ð³Ð¾Ð¼.",
        "tasks": ["Ð¢Ð¾ÑÐ³ÑÐ¹ Ð½Ð° ÑÐ¿Ð¾ÑÐµ", "Ð¢Ð¾ÑÐ³ÑÐ¹ Ð½Ð° ÑÑÑÑÐµÑÑÐ°Ñ", "ÐÐ¾Ð¿Ð¾Ð»Ð½Ð¸ Ð´ÐµÐ¿Ð¾Ð·Ð¸Ñ"],
        "deadline": None, "tge_estimate": "Q2 2026",
        "url": "https://backpack.exchange", "volume_usd": 5e9,
    },
    {
        "id": "monad-testnet", "name": "Monad Testnet", "ecosystem": "EVM",
        "status": "active", "potential": 4, "effort": "low",
        "description": "1 ÑÑÐ°Ð½Ð·Ð°ÐºÑÐ¸Ñ ÐºÐ°Ð¶Ð´ÑÐµ 48Ñ Ð´Ð¾ÑÑÐ°ÑÐ¾ÑÐ½Ð¾. ÐÐ¾Ð½ÑÐ¸ÑÑÐµÐ½ÑÐ½Ð¾ÑÑÑ Ð²Ð°Ð¶Ð½ÐµÐµ Ð¾Ð±ÑÑÐ¼Ð°.",
        "tasks": ["Ð¡Ð´ÐµÐ»Ð°Ð¹ ÑÑÐ°Ð½Ð·Ð°ÐºÑÐ¸Ñ ÑÐ°Ð· Ð² 48Ñ", "ÐÑÐ¿Ð¾Ð»ÑÐ·ÑÐ¹ dApps Ð½Ð° ÑÐµÑÑÐ½ÐµÑÐµ"],
        "deadline": None, "tge_estimate": "Q3 2026",
        "url": "https://testnet.monad.xyz", "volume_usd": 1e9,
    },
    {
        "id": "base-ecosystem", "name": "Base Ecosystem", "ecosystem": "EVM",
        "status": "active", "potential": 4, "effort": "medium",
        "description": "L2 Ð¾Ñ Coinbase. Swap Ð½Ð° Aerodrome/Uniswap, Ð±ÑÐ¸Ð´Ð¶ ETH ÑÐµÑÐµÐ· official bridge.",
        "tasks": ["ÐÑÐ¸Ð´Ð¶ ETH â Base", "Swap Ð½Ð° Aerodrome Ð¸Ð»Ð¸ Uniswap", "ÐÑÐ¿Ð¾Ð»ÑÐ·ÑÐ¹ Basename"],
        "deadline": None, "tge_estimate": "TBD",
        "url": "https://base.org", "volume_usd": 8e9,
    },
    {
        "id": "layerzero-s2", "name": "LayerZero Season 2", "ecosystem": "Multi",
        "status": "active", "potential": 4, "effort": "medium",
        "description": "ÐÑÐ¾ÑÑ-ÑÐµÐ¹Ð½ Ð¿ÑÐ¾ÑÐ¾ÐºÐ¾Ð». Ð¡Ð´ÐµÐ»Ð°Ð¹ ÑÑÐ°Ð½Ð·Ð°ÐºÑÐ¸Ð¸ ÑÐµÑÐµÐ· Ð¸Ñ Ð±ÑÐ¸Ð´Ð¶Ð¸ Ð¼ÐµÐ¶Ð´Ñ ÑÐ°Ð·Ð½ÑÐ¼Ð¸ ÑÐµÑÑÐ¼Ð¸.",
        "tasks": ["ÐÑÐ¾ÑÑ-ÑÐµÐ¹Ð½ Ð±ÑÐ¸Ð´Ð¶ ÑÐµÑÐµÐ· LZ", "ÐÑÐ¿Ð¾Ð»ÑÐ·ÑÐ¹ Stargate Finance"],
        "deadline": None, "tge_estimate": "Q2 2026",
        "url": "https://layerzero.network", "volume_usd": 2e9,
    },
    {
        "id": "tonkeeper-points", "name": "Tonkeeper Points", "ecosystem": "TON",
        "status": "active", "potential": 3, "effort": "low",
        "description": "ÐÐ¶ÐµÐ´Ð½ÐµÐ²Ð½ÑÐ¹ check-in Ð² Ð¿ÑÐ¸Ð»Ð¾Ð¶ÐµÐ½Ð¸Ð¸. ÐÑÐ¿Ð¾Ð»ÑÐ·ÑÐ¹ TON ÐºÐ¾ÑÐµÐ»ÑÐº Ð°ÐºÑÐ¸Ð²Ð½Ð¾.",
        "tasks": ["ÐÐ¶ÐµÐ´Ð½ÐµÐ²Ð½ÑÐ¹ check-in", "Ð¡Ð²Ð¾Ð¿ Ð² TON Space", "Ð¡ÑÐµÐ¹ÐºÐ¸Ð½Ð³ TON"],
        "deadline": None, "tge_estimate": "TBD",
        "url": "https://tonkeeper.com", "volume_usd": 5e8,
    },
    {
        "id": "scroll-mainnet", "name": "Scroll", "ecosystem": "EVM",
        "status": "active", "potential": 4, "effort": "medium",
        "description": "ZK-rollup Ð½Ð° Ethereum. ÐÑÐ¸Ð´Ð¶ ETH, Ð¸ÑÐ¿Ð¾Ð»ÑÐ·ÑÐ¹ dApps Ð½Ð° Scroll.",
        "tasks": ["ÐÑÐ¸Ð´Ð¶ ETH â Scroll", "Swap Ð½Ð° Uniswap v3 Ð½Ð° Scroll", "ÐÐ¸Ð½Ñ NFT Ð½Ð° Scroll"],
        "deadline": None, "tge_estimate": "Q2 2026",
        "url": "https://scroll.io", "volume_usd": 1.5e9,
    },
    {
        "id": "hyperliquid-points", "name": "Hyperliquid Points", "ecosystem": "EVM",
        "status": "active", "potential": 5, "effort": "medium",
        "description": "DEX Ñ Ð¿ÐµÑÐ¿Ð°Ð¼Ð¸. ÐÑÐºÐ¸ Ð½Ð°ÑÐ¸ÑÐ»ÑÑÑÑÑ Ð·Ð° Ð¾Ð±ÑÑÐ¼ ÑÐ¾ÑÐ³Ð¾Ð². Ð£Ð¶Ðµ ÐºÑÑÐ¿Ð½ÑÐ¹ airdrop Ð±ÑÐ» â Ð¶Ð´ÑÑ Ð²ÑÐ¾ÑÐ¾Ð¹.",
        "tasks": ["Ð¢Ð¾ÑÐ³ÑÐ¹ Ð¿ÐµÑÐ¿Ð°Ð¼Ð¸ Ð½Ð° HyperLiquid", "ÐÐ±ÐµÑÐ¿ÐµÑÑ Ð»Ð¸ÐºÐ²Ð¸Ð´Ð½Ð¾ÑÑÑ Ð² HLP"],
        "deadline": None, "tge_estimate": "TBD",
        "url": "https://hyperliquid.xyz", "volume_usd": 10e9,
    },
    {
        "id": "zksync-s2", "name": "zkSync Era Season 2", "ecosystem": "EVM",
        "status": "active", "potential": 3, "effort": "low",
        "description": "ZK-rollup Ð¾Ñ Matter Labs. ÐÐ¾ÑÐ»Ðµ Ð¿ÐµÑÐ²Ð¾Ð³Ð¾ airdrop Ð¶Ð´ÑÑ Ð²ÑÐ¾ÑÐ¾Ð¹ ÑÐµÐ·Ð¾Ð½.",
        "tasks": ["ÐÑÐ¸Ð´Ð¶ ETH â zkSync Era", "Swap Ð½Ð° SyncSwap", "ÐÑÐ¿Ð¾Ð»ÑÐ·ÑÐ¹ ZK native dApps"],
        "deadline": None, "tge_estimate": "H2 2026",
        "url": "https://zksync.io", "volume_usd": 3e9,
    },
]

def _stars(n: int) -> str:
    """ÐÐ¾Ð½Ð²ÐµÑÑÐ¸ÑÑÐµÑ 1-5 Ð² ÑÑÑÐ¾ÐºÑ Ð·Ð²ÑÐ·Ð´."""
    return "â" * n + "â" * (5 - n)

def _effort_ru(e: str) -> str:
    return {"low": "Ð½Ð¸Ð·ÐºÐ¸Ðµ", "medium": "ÑÑÐµÐ´Ð½Ð¸Ðµ", "high": "Ð²ÑÑÐ¾ÐºÐ¸Ðµ"}.get(e, e)

async def _fetch_defillama_airdrops() -> List[dict]:
    """ÐÑÐ¾Ð±ÑÐµÐ¼ Ð¿Ð¾Ð»ÑÑÐ¸ÑÑ Ð´Ð°Ð½Ð½ÑÐµ Ð¸Ð· DeFiLlama. Fallback â Ð¿ÑÑÑÐ¾Ð¹ ÑÐ¿Ð¸ÑÐ¾Ðº."""
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
                    "description": item.get("description", "ÐÐ· DeFiLlama"),
                    "tasks": ["ÐÑÐ¾Ð²ÐµÑÑ Ð¾ÑÐ¸ÑÐ¸Ð°Ð»ÑÐ½ÑÐ¹ ÑÐ°Ð¹Ñ"],
                    "deadline": None,
                    "tge_estimate": None,
                    "url": item.get("url", "https://defillama.com/airdrops"),
                    "volume_usd": float(item.get("totalLocked", 0) or 0),
                })
            return result
    except Exception:
        return []

async def get_airdrops() -> List[dict]:
    """ÐÐ¾Ð·Ð²ÑÐ°ÑÐ°ÐµÑ ÑÐ¿Ð¸ÑÐ¾Ðº airdrops (ÐºÐµÑ 6Ñ + fallback)."""
    global _airdrop_cache, _airdrop_cache_ts
    if _airdrop_cache and time.time() - _airdrop_cache_ts < _AIRDROP_TTL:
        return _airdrop_cache
    # ÐÑÐ¾Ð±ÑÐµÐ¼ DeFiLlama
    live = await _fetch_defillama_airdrops()
    # ÐÐµÑÐ¶Ð¸Ð¼ Ñ fallback (fallback Ð² ÐºÐ¾Ð½ÑÐµ, live Ð² Ð½Ð°ÑÐ°Ð»Ðµ)
    seen = {a["id"] for a in live}
    merged = live + [a for a in _AIRDROP_FALLBACK if a["id"] not in seen]
    # Ð¡Ð¾ÑÑÐ¸ÑÐ¾Ð²ÐºÐ°: potential DESC, volume DESC
    merged.sort(key=lambda x: (x["potential"], x["volume_usd"]), reverse=True)
    _airdrop_cache = merged
    _airdrop_cache_ts = time.time()
    print(f"[airdrops] ÐºÐµÑ Ð¾Ð±Ð½Ð¾Ð²Ð»ÑÐ½: {len(merged)} Ð¿ÑÐ¾ÐµÐºÑÐ¾Ð² ({len(live)} Ð¸Ð· DeFiLlama)")
    return _airdrop_cache

async def send_airdrop_digest():
    """ÐÑÐ¿ÑÐ°Ð²Ð»ÑÐµÑ ÐµÐ¶ÐµÐ´Ð½ÐµÐ²Ð½ÑÐ¹ Ð´Ð°Ð¹Ð´Ð¶ÐµÑÑ Ð² Telegram."""
    if not BOT_TOKEN or not ALERT_CHAT_ID:
        return
    airdrops = await get_airdrops()
    top5 = airdrops[:5]
    today = datetime.utcnow().strftime("%d.%m.%Y")
    lines = [f"â *QuantumTrade Â· ðª Airdrop Digest {today}*", "ââââââââââââââââââââââ"]
    emoji_map = {"EVM": "ð·", "TON": "ð", "Solana": "ð£", "Multi": "ð"}
    for a in top5:
        eco_emoji = emoji_map.get(a["ecosystem"], "ð¹")
        lines.append(
            f"\n{eco_emoji} *{a['name']}* `[{a['ecosystem']}]`\n"
            f"   {_stars(a['potential'])} Â· Ð£ÑÐ¸Ð»Ð¸Ñ: {_effort_ru(a['effort'])}\n"
            f"   {a['description'][:80]}\n"
            f"   ð {a['url']}"
        )
    # ÐÐµÐ´Ð»Ð°Ð¹Ð½Ñ
    deadlines = [a for a in airdrops if a.get("deadline")]
    if deadlines:
        lines.append("\nâ° *ÐÐµÐ´Ð»Ð°Ð¹Ð½Ñ:*")
        for a in deadlines[:3]:
            lines.append(f"   â¢ {a['name']}: {a['deadline']}")
    lines.append("\nââââââââââââââââââââââ")
    lines.append("_/airdrops â Ð¿Ð¾Ð»Ð½ÑÐ¹ ÑÐ¿Ð¸ÑÐ¾Ðº_")
    text = "\n".join(lines)
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": ALERT_CHAT_ID, "text": text,
                      "parse_mode": "Markdown", "disable_web_page_preview": True},
                timeout=aiohttp.ClientTimeout(total=5)
            )
        print("[airdrops] Ð´Ð°Ð¹Ð´Ð¶ÐµÑÑ Ð¾ÑÐ¿ÑÐ°Ð²Ð»ÐµÐ½ Ð² Telegram")
    except Exception as e:
        print(f"[airdrops] Ð¾ÑÐ¸Ð±ÐºÐ° Ð¾ÑÐ¿ÑÐ°Ð²ÐºÐ¸ Ð´Ð°Ð¹Ð´Ð¶ÐµÑÑÐ°: {e}")

async def airdrop_digest_loop():
    """ÐÑÐ¿ÑÐ°Ð²Ð»ÑÐµÑ Ð´Ð°Ð¹Ð´Ð¶ÐµÑÑ ÑÐ°Ð· Ð² 24Ñ (Ð² 09:00 UTC)."""
    while True:
        now = datetime.utcnow()
        # Ð¡ÑÐ¸ÑÐ°ÐµÐ¼ ÑÐµÐºÑÐ½Ð´Ñ Ð´Ð¾ ÑÐ»ÐµÐ´ÑÑÑÐµÐ³Ð¾ 09:00 UTC
        target_hour = 9
        secs_until = ((target_hour - now.hour) % 24) * 3600 - now.minute * 60 - now.second
        if secs_until <= 0:
            secs_until += 86400
        await asyncio.sleep(secs_until)
        try:
            await send_airdrop_digest()
        except Exception as e:
            print(f"[airdrops] digest loop error: {e}")


# ââ Routes âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

@app.get("/api/airdrops")
async def airdrops_list():
    """Phase 4: ÑÐ¿Ð¸ÑÐ¾Ðº Ð°ÐºÑÐ¸Ð²Ð½ÑÑ airdrop Ð²Ð¾Ð·Ð¼Ð¾Ð¶Ð½Ð¾ÑÑÐµÐ¹."""
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
    """Ð¢Ð¾Ð¿-5 Ð´Ð»Ñ Ð´Ð°Ð¹Ð´Ð¶ÐµÑÑÐ° + Ð´ÐµÐ´Ð»Ð°Ð¹Ð½Ñ."""
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
    """ÐÑÐ¸Ð½ÑÐ´Ð¸ÑÐµÐ»ÑÐ½ÑÐ¹ ÑÐ±ÑÐ¾Ñ ÐºÐµÑÐ° airdrops."""
    global _airdrop_cache_ts
    _airdrop_cache_ts = 0.0
    data = await get_airdrops()
    return {"status": "ok", "count": len(data)}

@app.post("/api/airdrops/digest/send")
async def airdrops_send_digest():
    """ÐÑÐ¿ÑÐ°Ð²Ð¸ÑÑ Ð´Ð°Ð¹Ð´Ð¶ÐµÑÑ Ð² Telegram Ð¿ÑÑÐ¼Ð¾ ÑÐµÐ¹ÑÐ°Ñ (Ð´Ð»Ñ ÑÐµÑÑÐ¸ÑÐ¾Ð²Ð°Ð½Ð¸Ñ)."""
    await send_airdrop_digest()
    return {"status": "sent"}

@app.get("/api/quantum")
async def quantum_status():
    """Phase 3+6: ÑÐµÐºÑÑÐ¸Ð¹ QAOA quantum bias, ÑÐµÐ¶Ð¸Ð¼ ÑÐ¸Ð¿Ð° Ð¸ ÑÑÐ°ÑÑÑ Origin QC."""
    age_sec = int(time.time() - _quantum_ts) if _quantum_ts else None
    if _qcloud_ready:
        chip      = "Wukong_180"
        p_layers  = 1
        note      = "âï¸ Ð ÐµÐ°Ð»ÑÐ½ÑÐ¹ ÐºÐ²Ð°Ð½ÑÐ¾Ð²ÑÐ¹ ÑÐ¸Ð¿ Origin Wukong 180 Ð°ÐºÑÐ¸Ð²ÐµÐ½ (chip_id=72)"
    else:
        chip      = "CPU_simulator"
        p_layers  = 2
        note      = ("Ð£ÑÑÐ°Ð½Ð¾Ð²Ð¸ ORIGIN_QC_TOKEN Ð² Railway Ð´Ð»Ñ Ð°ÐºÑÐ¸Ð²Ð°ÑÐ¸Ð¸ Wukong 180"
                     if not ORIGIN_QC_TOKEN else
                     "ORIGIN_QC_TOKEN Ð·Ð°Ð´Ð°Ð½, Ð½Ð¾ pyqpanda3 Ð½ÐµÐ´Ð¾ÑÑÑÐ¿ÐµÐ½ â CPU fallback")
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
    return {"status": "ok", "version": "7.2.3", "auto_trading": AUTOPILOT, "test_mode": TEST_MODE,
            "risk_per_trade": RISK_PER_TRADE, "last_qscore": last_q_score, "min_confidence": MIN_CONFIDENCE,
            "min_q_score": MIN_Q_SCORE, "max_leverage": MAX_LEVERAGE, "tp_pct": TP_PCT, "sl_pct": SL_PCT,
            "trades_logged": len(trade_log), "yandex_vision": bool(YANDEX_VISION_KEY),
            "claude_vision": bool(ANTHROPIC_API_KEY), "ai_chat": bool(ANTHROPIC_API_KEY),
            "quantum_chip": "Wukong_180" if _qcloud_ready else "CPU_simulator",
            "origin_qc_token": bool(ORIGIN_QC_TOKEN),
            "timestamp": datetime.utcnow().isoformat()}

@app.post("/api/setup-webhook")
async def setup_webhook(request: Request):
    """Ð ÐµÐ³Ð¸ÑÑÑÐ¸ÑÑÐµÑ Telegram Webhook + ÐºÐ¾Ð¼Ð°Ð½Ð´Ñ Ð² Ð¼ÐµÐ½Ñ Ð±Ð¾ÑÐ°."""
    if not BOT_TOKEN:
        return {"ok": False, "error": "BOT_TOKEN Ð½Ðµ Ð·Ð°Ð´Ð°Ð½"}
    base_url = str(request.base_url).rstrip("/").replace("http://", "https://")
    webhook_url = f"{base_url}/api/telegram/callback"
    results = {}
    try:
        async with aiohttp.ClientSession() as s:
            # 1. Ð ÐµÐ³Ð¸ÑÑÑÐ¸ÑÑÐµÐ¼ webhook
            r = await s.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
                json={"url": webhook_url, "allowed_updates": ["message", "callback_query"]},
                timeout=aiohttp.ClientTimeout(total=10)
            )
            results["webhook"] = await r.json()

            # 2. Ð ÐµÐ³Ð¸ÑÑÑÐ¸ÑÑÐµÐ¼ ÐºÐ¾Ð¼Ð°Ð½Ð´Ñ â Ð¿Ð¾ÑÐ²ÑÑÑÑ Ð² Ð¼ÐµÐ½Ñ "/" Ñ Ð¿Ð¾Ð»ÑÐ·Ð¾Ð²Ð°ÑÐµÐ»Ñ
            r2 = await s.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setMyCommands",
                json={"commands": [
                    {"command": "menu",      "description": "ð  ÐÐ»Ð°Ð²Ð½Ð¾Ðµ Ð¼ÐµÐ½Ñ"},
                    {"command": "stats",     "description": "ð Ð¡ÑÐ°ÑÐ¸ÑÑÐ¸ÐºÐ° ÑÐ¾ÑÐ³Ð¾Ð²Ð»Ð¸"},
                    {"command": "airdrops",  "description": "ðª Ð¢Ð¾Ð¿ Airdrop Ð²Ð¾Ð·Ð¼Ð¾Ð¶Ð½Ð¾ÑÑÐ¸"},
                    {"command": "settings",  "description": "âï¸ ÐÐ°ÑÑÑÐ¾Ð¹ÐºÐ¸ (Q-Score, Cooldown)"},
                    {"command": "balance",   "description": "ð° ÐÐ°Ð»Ð°Ð½Ñ ÑÑÑÑÐ°"},
                    {"command": "positions", "description": "ð ÐÑÐºÑÑÑÑÐµ Ð¿Ð¾Ð·Ð¸ÑÐ¸Ð¸"},
                ]},
                timeout=aiohttp.ClientTimeout(total=10)
            )
            results["commands"] = await r2.json()

            # 3. Ð£ÑÑÐ°Ð½Ð°Ð²Ð»Ð¸Ð²Ð°ÐµÐ¼ ÐºÐ½Ð¾Ð¿ÐºÑ Ð¼ÐµÐ½Ñ Ñ web_app (Ð´Ð°ÑÐ±Ð¾ÑÐ´)
            r3 = await s.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setChatMenuButton",
                json={"menu_button": {"type": "web_app", "text": "ð¥ï¸ ÐÐ°ÑÐ±Ð¾ÑÐ´", "web_app": {"url": WEBAPP_URL}}},
                timeout=aiohttp.ClientTimeout(total=10)
            )
            results["menu_button"] = await r3.json()

        return {"ok": True, "webhook_url": webhook_url, "webapp_url": WEBAPP_URL, "results": results}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/setup-webhook")
async def get_webhook_info():
    """ÐÑÐ¾Ð²ÐµÑÑÐµÑ ÑÐµÐºÑÑÐ¸Ð¹ ÑÑÐ°ÑÑÑ Telegram Webhook."""
    if not BOT_TOKEN:
        return {"ok": False, "error": "BOT_TOKEN Ð½Ðµ Ð·Ð°Ð´Ð°Ð½"}
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
    # Ð¡ÑÐ°ÑÐ¸ÑÑÐ¸ÐºÐ° Ð¿Ð¾ ÑÑÐµÐºÐ°Ð¼
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


# ââ AI Chat Proxy ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
class ChatRequest(BaseModel):
    messages: list
    context:  str = ""

@app.post("/api/ai/chat")
async def api_ai_chat(req: ChatRequest):
    """Proxy for Claude API â solves CORS from browser."""
    if not ANTHROPIC_API_KEY:
        return {"error": "ANTHROPIC_API_KEY not configured on server", "success": False}
    system_lines = [
        "Ð¢Ñ QuantumTrade AI â ÑÐ¾ÑÐ³Ð¾Ð²ÑÐ¹ ÑÐ¾Ð²ÐµÑÐ½Ð¸Ðº Ð² ÑÑÐµÐ¹Ð´Ð¸Ð½Ð³-Ð±Ð¾ÑÐµ Ð½Ð° KuCoin.",
        "ÐÐ¾Ð¼Ð¾Ð³Ð°ÐµÑÑ Ð¿Ð¾Ð½ÑÑÑ ÑÑÐ½Ð¾Ðº, ÑÐ¸Ð³Ð½Ð°Ð»Ñ Ð¸ ÑÑÑÐ°ÑÐµÐ³Ð¸Ñ. ÐÐ±ÑÑÑÐ½ÑÐ¹ Ð¿ÑÐ¾ÑÑÑÐ¼ ÑÐ·ÑÐºÐ¾Ð¼ â Ð¼Ð½Ð¾Ð³Ð¸Ðµ Ð½Ð¾Ð²Ð¸ÑÐºÐ¸.",
        "Ð¡Ð¢ÐÐÐ¬: Ð¿Ð¾-ÑÑÑÑÐºÐ¸, ÐºÑÐ°ÑÐºÐ¾ (2-4 Ð°Ð±Ð·Ð°ÑÐ°), ÐºÐ¾Ð½ÐºÑÐµÑÐ½ÑÐµ ÑÐ¾Ð²ÐµÑÑ, Ð¾Ð±ÑÑÑÐ½ÑÐ¹ ÑÐµÑÐ¼Ð¸Ð½Ñ, ÑÐ¼ÐµÑÐµÐ½Ð½ÑÐµ ÑÐ¼Ð¾Ð´Ð·Ð¸.",
        "ÐÐÐÐ¢ÐÐÐ¡Ð¢: EMA+RSI+Volume, Q-Score 65+=BUY 35-=SELL, ÑÐµÑÑ: $24 USDT, ÑÐ¸ÑÐº 10%, TP 3%, SL 1.5%.",
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
        emoji = "ð¢" if req.side == "buy" else "ð´"
        await notify(f"{emoji} <b>Ð ÑÑÐ½Ð°Ñ ÑÐ´ÐµÐ»ÐºÐ°</b>\n<code>{req.symbol}</code> {req.side.upper()} Â· <code>{req.size}</code>")
    return {"success": success, "data": result}

@app.post("/api/autopilot/{state}")
async def toggle_autopilot(state: str):
    global AUTOPILOT
    AUTOPILOT = state == "on"
    await notify(f"âï¸ ÐÐ²ÑÐ¾Ð¿Ð¸Ð»Ð¾Ñ {'Ð²ÐºÐ»ÑÑÑÐ½' if AUTOPILOT else 'Ð²ÑÐºÐ»ÑÑÐµÐ½'}")
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
