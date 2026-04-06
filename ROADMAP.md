# QuantumTrade AI — ROADMAP
> Волновая дорожная карта · GSD v2 Architecture · Обновлено: 2026-04-07
> Философия: Персональная финансовая экосистема с бешеной маржинальностью
> Версия: v10.19.5 · Passive Income Focus · 3 биржи · Telegram Duet Channel

---

## 📍 ГДЕ МЫ СЕЙЧАС (v10.19.5, АКТИВНА на Railway)

**Работает прямо сейчас:**
- Dual-exchange торговля (KuCoin + ByBit) — 15 AI-агентов MiroFish
- DCI (Dual Currency Investment) — ByBit 100-900% APY, auto-reinvest ✅ (+$20.12 сегодня!)
  - v10.19.3 FIX: DCI "Amount out of range" — FUND capital + "20.00" format ✅
  - v10.19.4: DCI admin alert + resilient error retry ✅
  - v10.19.5: DCI P&L → channel post on settlement ✅ (Wave 5A)
- Double Win ByBit — включён (DOUBLE_WIN_ENABLED=true) ✅
- KuCoin Lending Pro — код исправлен v10.17.2, LENDING_ENABLED=true ✅
- Gate.io Lending — код готов v10.18.0, ждёт API ключей ✅
- Funding Rate Arb — код готов, FUNDING_ARB_ENABLED=false (ждёт $30+ на ByBit)
- ByBit Snowball — код готов, SNOWBALL_ENABLED=false (включить при F&G 30-65)
- Yield Router v2 — 8 продуктов, каждый час + /yrouter ✅
- Telegram Duet Channel — Whale Alerts + BUY сигналы + News Digest ✅
- Earn Flex $107.35 KC + $20.03 BB активно работают ✅ (v10.19.2 BB Earn fix)
- Капитал ~$310, F&G=13 (Extreme Fear), торговля заблокирована

**Что сделано с v10.12.6 → v10.18.2 (сессии 2026-04-05 — 2026-04-06):**
- [x] ByBit Snowball полный модуль + /snowball команда (v10.14.0)
- [x] Yield Router v2: 7→8 продуктов, APY сравнение, /yrouter (v10.14.0)
- [x] Telegram Duet Channel: Whale Alerts + BUY сигналы + edu посты (v10.17.0)
- [x] DCI ping-pong fix: 4ч кулдаун на FUND→UNIFIED трансфер (v10.17.1)
- [x] Risk агент fix: KC total_usdt (был available_usdt) + BB FUND (v10.17.1/3)
- [x] KuCoin Lending fix: main+trade аккаунты, вычет резерва (v10.17.2)
- [x] Gate.io 3-я биржа: HMAC-SHA512, lending auto-place, /gate команда (v10.18.0)
- [x] Gate.io в Yield Router v2 как продукт #8 (v10.18.0)
- [x] _ru_plural(): правильное склонение в whale alerts (v10.18.1)
- [x] Per-coin cooldown 30мин для channel whale alerts (v10.18.1)
- [x] Улучшенные аналогии: зарплаты/авто/квартиры/особняк/ТЦ (v10.18.1)
- [x] News Engine: RSS (CoinDesk/CoinTelegraph/Decrypt) + Polymarket в дайджест (v10.18.2)
- [x] Обновлены STATE.md + ROADMAP.md (сессия 2026-04-06)

---

## 🏁 Wave 1 — Earn Engine ✅ COMPLETE (v10.2–v10.14)

### 1A: Flex Savings ✅ DEPLOYED
- [x] KuCoin + ByBit Flexible Savings — auto-earn после SELL, auto-redeem перед BUY
- [x] Smart Money Router: Arb $1 → Trade $2 → Earn (всё остальное)
- [x] /earn, /earnplace, /router

### 1B: Lending & Structured Products ✅ DEPLOYED
- [x] DCI ByBit — auto-reinvest + VIP-fallback + capital check (v10.12.x)
- [x] Double Win ByBit — включён, параллельно с DCI (v10.12.x)
- [x] KuCoin Lending Pro — 10-50% APR, код исправлен v10.17.2 ✅
- [x] ByBit Snowball — range-bound structured product (v10.14.0) ✅
- [x] /lending, /snowball, /dci, /dciplace

### 1C: Funding Rate Arb ✅ КОД ГОТОВ
- [x] funding_arb_open/close() — спот + перп, атомарное (v10.12.6)
- [x] funding_arb_auto_check() — авто при rate > threshold
- [x] /fundarb Telegram команда
- [ ] **Включить `FUNDING_ARB_ENABLED=true`** — когда $30+ USDT на ByBit UNIFIED

---

## 🏁 Wave 2 — Smart Trading v2 ✅ COMPLETE (v10.0–v10.12)

### 2A: Smart Filters ✅ DEPLOYED
- [x] Минимум 2 подтверждающих индикатора для BUY
- [x] Volume filter, Multi-timeframe 1h+4h, Cooldown per-symbol 4ч
- [x] MiroFish veto (≥75% против → отмена), Opus Gate (>$15 → Claude Opus)
- [x] Fear & Greed < 15 → не покупать (Extreme Fear block)

### 2B: Telegram Duet Channel ✅ DEPLOYED (v10.17–v10.18)
- [x] Whale Alerts — крупные транзакции с аналогиями (рублёвыми!)
- [x] BUY сигналы в канал при Q-Score ≥ MIN_Q_SCORE
- [x] Ежедневные образовательные посты — channel_edu_loop()
- [x] Crypto News Digest — RSS + Polymarket в дайджест
- [x] Duet формат: блок для новичков + блок для профи
- [ ] Рост канала — органический через качественный контент (3 подписчика сейчас)
- [ ] Авто-постинг о закрытых позициях с P&L в канал

### 2C: Analytics (частично)
- [x] /winrate — win rate по монетам из PostgreSQL
- [ ] Trailing stop v2: динамический ATR (не фиксированный 1%)
- [ ] Stale position analyzer: позиции без движения 24h+ → уведомление
- [ ] Backtesting engine на исторических данных

---

## 🌊 Wave 3 — Multi-Exchange Expansion
> Приоритет: ВЫСОКИЙ · Статус: В ПРОЦЕССЕ

### 3A: Gate.io ✅ КОД ГОТОВ (v10.18.0)
- [x] Gate.io авторизация HMAC-SHA512
- [x] gate_get_spot_balance(), gate_lending_auto_place()
- [x] /gate Telegram команда
- [x] Gate.io в Yield Router v2 (продукт #8)
- [ ] **⚠️ Добавить GATE_API_KEY + GATE_SECRET в Railway Variables** ← СДЕЛАТЬ!
- [ ] Gate.io Earn (Flexible savings, не только Lending)
- [ ] Gate.io спот торговля (BUY/SELL) — когда Lending работает стабильно

### 3B: Sub-Accounts (следующий шаг!)
> Удваиваем прибыль без нового кода. Приоритет #1 после Gate.io ключей.

- [ ] **KuCoin Sub-account sub1** — выделить $50-100 на отдельный аккаунт
  - Новый API ключ (KUCOIN_SUB1_API_KEY / SECRET / PASS)
  - Отдельный поток: DCI + Lending, изолированный от главного
  - Railway Variables: SUB_ACCOUNTS_ENABLED=true
- [ ] **ByBit Sub-account sub1** — аналогично
  - Новый API ключ (BYBIT_SUB1_API_KEY / SECRET)
  - DCI + Snowball независимо
- [ ] Мульти-аккаунт Yield Router: распределять между main + sub1
- [ ] Dashboard: отображать суммарный P&L по всем аккаунтам

### 3C: Binance Integration
> 4-я биржа. Нужно создать аккаунт + API ключ.

- [ ] **Создать Binance аккаунт** (отдельный email, не тот что был)
- [ ] Binance REST API: HMAC-SHA256, аналог ByBit
- [ ] binance_get_balance(), binance_place_spot_order()
- [ ] Binance Dual Investment (аналог ByBit DCI) — 20-200% APY
- [ ] Binance Simple Earn — Flexible + Locked
- [ ] Binance в Yield Router v2 (продукт #9, #10)
- [ ] 3-биржевый BUY routing: KuCoin + ByBit + Binance (лучшая цена)

### 3D: CCXT Foundation (при $1000+)
- [ ] ccxt в requirements.txt
- [ ] exchange_factory(name) → unified API abstraction
- [ ] 5+ бирж через одну абстракцию
- [ ] Cross-exchange spread arbitrage (автоматический)

---

## 🌊 Wave 4 — Trading Intelligence v2
> Приоритет: СРЕДНИЙ · Сложность: M

### 4A: Улучшение выходов
- [ ] **Trailing stop v2** — динамический ATR, не фиксированный 1%
  - Волатильность токена → адаптивный trail (высокая vol → шире стоп)
  - Время удержания → trail уменьшается (давление к выходу)
- [ ] Time-based exit: позиция >48h без прибыли → auto-sell
- [ ] Max portfolio allocation: ≤30% баланса в одну монету

### 4B: Signals Intelligence
- [ ] Polymarket сигналы в торговый цикл (уже в дайджесте, теперь в Q-Score)
  - polymarket_crypto_signal() → +/- к Q-Score по токену
- [ ] Binance order book imbalance анализ
- [ ] On-chain metrics (Glassnode free tier): SOPR, NUPL
- [ ] Корреляция с BTC: alt-season фильтр

### 4C: Backtesting
- [ ] Backtesting engine на исторических данных (PostgreSQL trades)
- [ ] A/B testing: параллельное тестирование стратегий
- [ ] PnL breakdown по монетам — какие зарабатывают

---

## 🌊 Wave 5 — Channel Growth & Monetisation
> Приоритет: СРЕДНИЙ · Долгосрочно

### 5A: Канал рост
- [ ] Авто-постинг: закрытые сделки с P&L → в канал (привлечение доверием)
- [ ] Еженедельный отчёт в канал: топ-сигналы, P&L, рыночная аналитика
- [ ] ByBit/KuCoin реферальные ссылки в сообщениях канала
- [ ] Конкурсы/активность: угадай движение BTC → engagement

### 5B: Монетизация канала
- [ ] Партнёрка с биржами (реферальный % от fees)
- [ ] Paid analytics tier (расширенные сигналы платно)
- [ ] Copy-trading подписка (следуй за нашим ботом)

### 5C: Design System
- [ ] CSS Design Tokens (OKLCH) + Glassmorphism + Cyberpunk
- [ ] Earn Dashboard + Yield Router в Mini App
- [ ] Микро-анимации, skeleton loading, number animations

---

## 🌊 Wave 6 — AI & DeFi
> Приоритет: НА БУДУЩЕЕ · Сложность: XL

- [ ] DeepSeek V3.2 reasoning (когда API стабилен)
- [ ] ML price prediction (LSTM/Transformer на исторических данных)
- [ ] Polymarket API → active trading (делаем ставки, не только читаем)
- [ ] DeFi integration (Uniswap USDC yield, AAVE)
- [ ] Налоговый калькулятор
- [ ] Multi-user подписочная модель

---

## 📊 Метрики успеха
| Метрика | Сейчас (v10.18) | Цель v11.0 | Цель v12.0 |
|---------|----------------|-----------|-----------|
| Биржи активных | 2 (KC+BB) | 3-4 (+ Gate + Binance) | 5+ |
| Пассивный доход | DCI +$20/сделка | DCI+Lending+Gate ежедневно | +Sub-accounts ×2 |
| Earn Flex | $107.35 | $200+ | $500+ |
| Капитал | ~$310 | $500+ | $1000+ |
| Канал подписчики | 3 | 100+ | 1000+ |
| API cost/day | $0/день | $0/день (DeepSeek only) | $0-0.10 |
| Биржи в Yield Router | 8 продуктов | 10+ (Binance Dual Inv.) | 15+ |
| Win rate | TBD (Extreme Fear) | 55%+ | 60%+ |

---

## 🎯 Что делать дальше (по приоритету)

### 🔴 СРОЧНО (сегодня):
1. **Ждать Railway deploy v10.18.2** — QUEUED из-за инцидента (всё починится само)
2. **После деплоя проверить:**
   - `/gate` — убедиться что Gate.io отвечает (без ключей покажет статус)
   - `/lending` — KuCoin Lending должен работать (v10.17.2 fix)
   - `/health` — все системы зелёные
   - Whale alerts — формат автомобилей без "-я" теперь правильный

### 🟡 СКОРО (эта неделя):
3. **Добавить Gate.io API ключи в Railway** → GATE_API_KEY, GATE_SECRET, GATE_LENDING_ENABLED=true
4. **Создать KuCoin Sub-account** → удвоить DCI + Lending без нового кода
5. **Создать Binance аккаунт** (новый email) → 4-я биржа, Dual Investment

### 🟢 СЛЕДУЮЩИЙ МЕСЯЦ:
6. **Wave 3B: Sub-accounts** (KC sub1 + BB sub1) → ×2 к пассивному доходу
7. **Wave 3C: Binance** → Dual Investment + Simple Earn + BUY routing
8. **Wave 4A: ATR Trailing Stop** → умнее выходы из позиций
9. **Wave 5A: Канал рост** → авто-постинг P&L, реферальные ссылки

### 💡 Стратегия роста капитала
```
Сейчас (~$310):   DCI + Earn Flex + Gate.io Lending (когда ключи)
                  Торговля заблокирована F&G=13 (Extreme Fear)
+Gate.io ключи:   3-я биржа работает → +$X/день через lending
+Sub-accounts:    KC sub1 + BB sub1 → ×2 прибыль, НИКАКОГО нового кода
+Binance:         Dual Investment аналог DCI → +4-я биржа
При $500+:        Funding Rate Arb активен (FUNDING_ARB_ENABLED=true)
При $1000+:       Full multi-exchange routing + CCXT
При $2000+:       ML signals + DeFi + Polymarket active trading
```

---

## 🔄 Wave Status
```
✅ Complete: Wave 1A (Earn+Flex) · Wave 1B (DCI+Lending+Snowball) · Wave 1C (FundingArb code)
✅ Complete: Wave 2A (SmartFilters+Security) · Wave 2B (DuetChannel+News+WhaleAlerts)
🔄 Active:   Wave 3A (Gate.io — код готов, ждёт API ключей)
🔜 Next:     Wave 3B (Sub-accounts) → Wave 3C (Binance) → Wave 4A (ATR stop)
⏸ Blocked:  Binance — нужен новый аккаунт + API ключ
             Gate.io Lending — ждём GATE_API_KEY в Railway
⏸ Deferred: Wave 3D (CCXT) при $1000+ · Wave 5 (Design) · Wave 6 (DeFi/ML)

Last Updated: 2026-04-06 · v10.12.6→v10.18.2 (большая сессия: Channel+Gate+News+Bugs)
Next session: Sub-accounts KuCoin/ByBit + Binance integration planning
```
