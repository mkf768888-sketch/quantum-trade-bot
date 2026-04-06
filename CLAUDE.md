# QuantumTrade AI — CLAUDE.md
> Главный конфиг для AI-агентов. Читать при каждом запуске.
> v10.13.0 · 2026-04-06 · github.com/mkf768888-sketch/quantum-trade-bot

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
| Funding Arb v10.12.7 | ByBit delta-neutral: spot long + perp short | `funding_arb_open()`, `funding_arb_close()`, `funding_arb_auto_check()` |
| KuCoin Lending v10.13.0 | Margin lending USDT, 10-50% APR | `kucoin_lending_auto_place()`, `kucoin_lending_get_market_rate()` |

## AI Tiers (v10.1 — cost protection)
- **DeepSeek V3** — единственный AI в торговом цикле. NO Claude fallback!
- **Rule-based RSI** — fallback когда нет DeepSeek (RSI<30=BUY, RSI>70=SELL)
- **Claude** — НЕ используется в торговле. $0/день API cost.
- **Vision** — отключено (VISION_ENABLED=false)

## Биржи (v10.0 Dual-Exchange)
- **KuCoin**: Spot + Futures (HMAC-SHA256) — `execute_spot_trade()`, `place_futures_order()`
- **ByBit**: Spot (HMAC-SHA256) — `bybit_place_spot_order()`, `bybit_sell_spot()`
- **Routing**: BUY → биржа с большим USDT, auto-fallback на вторую
- **Monitor**: `spot_monitor_loop()` проверяет обе биржи (account: spot / bybit_spot)

## Railway Variables
```
KUCOIN_API_KEY / KUCOIN_SECRET / KUCOIN_PASSPHRASE
BYBIT_API_KEY / BYBIT_API_SECRET
BOT_TOKEN / API_SECRET / ANTHROPIC_API_KEY / DEEPSEEK_API_KEY
RAILWAY_PUBLIC_DOMAIN / TG_WEBHOOK_SECRET
RISK_PER_TRADE=0.08 / MIN_Q_SCORE=77 / MAX_OPEN_POSITIONS=2
ARB_RESERVE_USDT=3 / SPOT_BUY_MIN_USDT=5
FUNDING_ARB_ENABLED=false / FUNDING_ARB_MIN_RATE=0.01 / FUNDING_ARB_MAX_USDT=50
LENDING_ENABLED=false / LENDING_MIN_APR=10.0 / LENDING_MAX_USDT=30.0 / LENDING_TERM_DAYS=7
```

## Telegram Commands
/start, /stats, /mirofish, /sentiment, /analyze, /macro, /balance, /positions,
/settings, /diag, /ask, /buy, /sell, /arb, /xarb, /bybit, /spot,
/dci, /dciplace, /lending, /fundarb, /earn, /earnplace, /health, /router

## Q-Score (0–100)
```
Claude Vision: 35% | Индикаторы: 25% | Контекст: 20% | Whale: 10% | F&G: 10%
+ Advanced TA confirmation: +0.02 за каждый подтверждающий сигнал (max +0.10)
```

## Security (v10.0)
- [x] Все приватные эндпоинты под verify_api_key
- [x] CORS: allow_origins=["*"] (упрощено — middleware вызывал проблемы)
- [x] Input validation on /api/settings and /api/trade/manual
- [x] HTML escaping on /ask user input
- [x] XSS protection в AI chat
- [x] Секреты только через os.getenv(), никогда в коде
- [ ] ~~Security headers middleware~~ — удалён (ломал запуск)
- [ ] ~~Rate limiting middleware~~ — удалён (ломал запуск)
- [ ] ~~TG_WEBHOOK_SECRET~~ — удалён (блокировал ВСЕ сообщения)

## Правила изменений
1. Изменил эндпоинт → обнови index.html (контракт!)
2. После деплоя → POST /api/setup-webhook
3. Секреты только в Railway Variables, никогда в коде
4. server.py — один файл, не дробить (пока)
5. Каждый коммит — атомарный, с описанием что и зачем
6. Перед пушем: `python3 -c "import py_compile; py_compile.compile('server.py', doraise=True)"`

## GSD v2 Wave Architecture (v10.0.1+)
Проект использует адаптацию GSD v2 для автономного выполнения:
- **Wave Execution**: задачи группируются в волны, state на диске (STATE.md)
- **Crash Recovery**: in_progress задачи в STATE.md, auto-resume
- **Parallel Research**: агенты работают по направлениям параллельно
- **Verification Gates**: syntax check → security scan → commit → (deploy only with user OK)

### Команды (`.claude/commands/`)
| Команда | Описание |
|---------|----------|
| `/auto` | Полный автопилот — волновое выполнение ROADMAP.md |
| `/wave` | Пошаговый — одна задача, пауза, подтверждение |
| `/discuss` | Обсуждение стратегии без изменения кода |
| `/forensics` | Диагностика и crash recovery |

### Агенты (`.claude/agents/`)
| Агент | Назначение | Модель |
|-------|-----------|--------|
| wave-orchestrator | Координатор волн, мозг системы | Sonnet |
| earn-strategist | Earn/Staking/Lending стратегии | Sonnet |
| polymarket-trader | Polymarket prediction markets | Sonnet |
| design-system | UI/UX, Cyberpunk + Glassmorphism | Sonnet |
| trade-analyst | Анализ торговой логики | Sonnet |
| deployer | Railway deploy pipeline | Haiku |
| debugger | Bug fixing | Sonnet |
| security-auditor | READ-ONLY аудит безопасности | Sonnet |

### Правила (`.claude/rules/`)
- `security.md` — абсолютные запреты, pre-deploy checklist
- `trading.md` — параметры риска, dual-exchange, self-learning

### Ключевые файлы GSD
- `ROADMAP.md` — волновая дорожная карта с задачами
- `STATE.md` — текущее состояние, wave status, crash recovery
- `HOWTO.md` — руководство по автономному режиму + Safe Mode

## Obsidian Knowledge Vault
Хранилище знаний: `vault/`

### При старте сессии
Прочитай `vault/00-home/index.md` и `vault/00-home/текущие приоритеты.md`.
Если задача касается конкретного модуля — прочитай заметку из `vault/knowledge/`.

### При завершении (пользователь: "сохрани сессию")
1. Создай заметку в `vault/sessions/` с датой
2. Обнови `vault/00-home/текущие приоритеты.md`
3. Если принято решение — создай заметку в `vault/knowledge/decisions/`
4. Если найден баг — создай заметку в `vault/knowledge/debugging/`
5. Обнови `vault/00-home/index.md` если новые заметки

### Правила vault
- Названия файлов = утверждения, не категории
- Wiki-ссылки `[[имя заметки]]` между связанными
- Frontmatter с tags и date
- Язык: русский
