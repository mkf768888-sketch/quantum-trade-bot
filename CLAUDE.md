# QuantumTrade AI — CLAUDE.md
> AI configuration file · Spec-First Methodology · max 120 lines

## Overview
Multi-layer crypto trading bot with quantum optimization, airdrop tracking, and arbitrage detection.
Deployed on Railway. Telegram notifications. KuCoin futures/spot trading.

## Stack
- **Backend**: FastAPI + Python 3.11, Railway (auto-deploy from GitHub main)
- **Trading**: KuCoin API (spot + futures, cross-margin, 3x leverage)
- **AI**: Anthropic Claude API (chat), Yandex Vision (chart OCR) → Kimi K2.5 (Phase 5)
- **Quantum**: pyqpanda3 CPU simulator → Origin QC Wukong 180 (Phase 6)
- **Notifications**: Telegram Bot API (inline keyboards, webhooks)
- **Monitoring**: UptimeRobot (5 min ping), /health endpoint

## Architecture — 6 Analytical Layers
```
Layer 1  KuCoin candles → EMA/RSI/Volume → pattern
Layer 2  Yandex Vision → chart PNG → OCR → vision_bonus ±8
Layer 3  Fear&Greed (alternative.me) → contrarian signal ±3
Layer 4  Polymarket events → crypto sentiment ±5
Layer 5  Whale tracker (Blockchair mempool) → flow signal ±5
Layer 6  QAOA CPU sim → portfolio correlation bias ±15  ← Phase 3
```

## Q-Score Formula (v5.6)
```
score = 50 + price×2 + rsi_delta + ema±8 + pattern_bonus
      + vision_bonus + fg_bonus + polymarket + whale + quantum_bias
BUY  if score ≥ 65  |  SELL if score ≤ 35  |  HOLD otherwise
```

## Key Files
```
server.py          Main FastAPI app (all logic, ~1500 lines)
requirements.txt   fastapi uvicorn aiohttp python-telegram-bot pydantic Pillow pyqpanda3
runtime.txt        python-3.11.0
CLAUDE.md          This file
AIRDROP_TRACKER_SPEC.md   Phase 4 specification
```

## API Endpoints
```
GET  /health                  Version, autopilot state, trade count
GET  /api/debug               Live cycle log, last signals, Q-scores
GET  /api/trades              Trade history, PnL by strategy track
GET  /api/signal/{symbol}     On-demand signal for any pair
GET  /api/quantum             QAOA bias for all 6 pairs
GET  /api/airdrops            [Phase 4] Airdrop opportunities list
GET  /api/dashboard           Combined dashboard data
POST /api/telegram/callback   Telegram inline button handler (A/B/C/DUAL)
POST /api/autopilot/{state}   Toggle auto-trading on/off
```

## Trading Strategies
```
A  Conservative  5% risk  2x lev  TP 2%  SL 1%
B  Standard     10% risk  3x lev  TP 3%  SL 1.5%   ← auto-default (60s timeout)
C  Bonus        25% risk  5x lev  TP 5%  SL 2.5%
DUAL  B + C simultaneously (real + bonus track)
```

## Environment Variables (Railway)
```
KUCOIN_API_KEY / KUCOIN_SECRET / KUCOIN_PASSPHRASE
BOT_TOKEN / ALERT_CHAT_ID
YANDEX_VISION_KEY / YANDEX_FOLDER_ID
ANTHROPIC_API_KEY
TEST_MODE=true          # false for live trading
MIN_CONFIDENCE=0.66
MIN_Q_SCORE=65
MAX_LEVERAGE=3
```

## Trading Pairs
```
Spot:    BTC-USDT ETH-USDT SOL-USDT BNB-USDT XRP-USDT AVAX-USDT
Futures: XBTUSDTM ETHUSDTM SOLUSDTM
QAOA correlation matrix: 6×6, updates every 15 min
```

## Phases Roadmap
```
✅ Phase 1  Fear&Greed + Polymarket + Whale + Strategies A/B/C/DUAL (v5.0-5.3)
✅ Phase 2  Yandex Vision chart OCR (v5.4)
✅ Phase 3  Origin QC QAOA CPU simulator (v5.6)
⏳ Phase 4  Airdrop Tracker — /api/airdrops + Telegram digest (v6.0)
⏳ Phase 5  Kimi K2.5 native vision (replace Yandex OCR hack)
⏳ Phase 6  Origin QC real chip Wukong 180 (uncomment REAL_QC_CHIP block)
⏳ Phase 7  Arbitrage module — cross-exchange price delta detection
⏳ Phase 8  AirdropOS — standalone commercial product
```

## Rules
- Never modify trading logic without updating Q-Score formula comment
- All new endpoints follow pattern: cache → fetch → parse → return
- Telegram messages use Markdown parse_mode, max 4096 chars
- All external API calls wrapped in try/except with fallback
- Cooldown 100s per pair to prevent duplicate trades
- pyqpanda3 REAL_QC_CHIP block: uncomment 3 lines + set ORIGIN_QC_TOKEN env
