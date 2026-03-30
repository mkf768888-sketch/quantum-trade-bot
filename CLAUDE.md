# QuantumTrade AI — CLAUDE.md
> Главный конфиг для AI-агентов. Читать при каждом запуске.
> v10.0.0 · 2026-03-31 · github.com/mkf768888-sketch/quantum-trade-bot

## Архитектура
- **Бэкенд:** Python 3.11, FastAPI → `server.py` (~6500 строк), Railway Cloud
- **БД:** PostgreSQL (asyncpg) → `db.py` — trades, signals, F&G, MiroFish memory, macro, whales
- **Фронтенд:** `index.html` — Telegram Mini App, `quantum-dashboard.html` — extended viz
- **Деплой:** git push → Railway autodeploy → POST /api/setup-webhook

## Ключевые подсистемы
| Система | Описание | Ключевые функции |
|---------|----------|-----------------|
| Trading Engine | Q-Score оценка, ордера на KuCoin+ByBit | `evaluate_signals()`, `place_spot_order()`, `place_futures_order()` |
| MiroFish v3 | 15 ролевых AI-агентов для сентимента | `mirofish_analyze()`, `MIROFISH_PERSONAS` |
| Arbitrage | Треугольный + межбиржевый | `find_arb_opportunity()`, `execute_arb()` |
| Self-Learning v2 | Авто-настройка из истории | `update_learning_insights()` |
| LunarCrush | Galaxy Score (соц. сентимент) | `fetch_lunarcrush_sentiment()` |
| Reddit Sentiment | r/cryptocurrency + r/bitcoin | `fetch_reddit_sentiment()` |
| Whale Tracker | Мониторинг крупных транзакций | `get_whale_signal()` |
| Copy-Trading | ByBit leaderboard | `fetch_copytrade_intelligence()` |
| Advanced TA | MACD, BB, Stoch, ADX, OBV (pandas-ta) | `calc_advanced_ta()` |

## AI Tiers
- **DeepSeek V3** — text/strategy (free tier, primary)
- **Claude Haiku** — vision analysis, fallback chat
- **Claude Opus** — critical decisions

## Биржи
- **KuCoin**: Spot + Futures (HMAC-SHA256)
- **ByBit**: Spot (HMAC-SHA256, другая подпись)

## Railway Variables
```
KUCOIN_API_KEY / KUCOIN_SECRET / KUCOIN_PASSPHRASE
BYBIT_API_KEY / BYBIT_API_SECRET
BOT_TOKEN / API_SECRET / ANTHROPIC_API_KEY / DEEPSEEK_API_KEY
RAILWAY_PUBLIC_DOMAIN / TG_WEBHOOK_SECRET
RISK_PER_TRADE=0.08 / MIN_Q_SCORE=77
```

## Telegram Commands
/start, /stats, /mirofish, /sentiment, /analyze, /macro, /balance, /positions,
/settings, /diag, /ask, /buy, /sell, /arb, /xarb, /bybit, /spot

## Q-Score (0–100)
```
Claude Vision: 35% | Индикаторы: 25% | Контекст: 20% | Whale: 10% | F&G: 10%
+ Advanced TA confirmation: +0.02 за каждый подтверждающий сигнал (max +0.10)
```

## Security (v10.0)
- [x] Все приватные эндпоинты под verify_api_key
- [x] CORS → restricted origins (Telegram + Railway domain)
- [x] Security headers middleware (X-Content-Type-Options, X-Frame-Options, etc.)
- [x] Rate limiting middleware (60 req/min per IP)
- [x] Telegram webhook secret_token verification
- [x] Input validation on /api/settings and /api/trade/manual
- [x] HTML escaping on /ask user input
- [x] XSS protection в AI chat

## Правила изменений
1. Изменил эндпоинт → обнови index.html (контракт!)
2. После деплоя → POST /api/setup-webhook
3. Секреты только в Railway Variables, никогда в коде
4. server.py — один файл, не дробить (пока)
5. Каждый коммит — атомарный, с описанием что и зачем
6. Перед пушем: `python3 -c "import py_compile; py_compile.compile('server.py', doraise=True)"`

## Субагенты
See `.claude/agents/` for specialized agent configs:
- `debugger.md` — поиск и исправление багов
- `security-auditor.md` — аудит безопасности
- `deployer.md` — деплой и верификация
- `trade-analyst.md` — анализ торговых стратегий

See `.claude/rules/` for mandatory constraints (security.md, trading.md).
