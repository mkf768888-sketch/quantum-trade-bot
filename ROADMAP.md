# QuantumTrade AI — ROADMAP
> Волновая дорожная карта · GSD v2 Architecture · Обновлено: 2026-04-03
> Философия: Персональная финансовая экосистема с бешеной маржинальностью
> Версия: v10.3.2 · Smart Money Router · Деньги НИКОГДА не простаивают

---

## 📍 ГДЕ МЫ СЕЙЧАС (v10.3.2)

**Работает:**
- Dual-exchange торговля (KuCoin + ByBit) — 15 AI-агентов MiroFish
- Smart Money Router — авто-распределение: Arb → Trade → Earn
- Earn Engine — Flexible Savings (KuCoin 0.79% APR, ByBit ✅ работает)
- Auto-Redeem перед BUY, auto-route в Earn после SELL
- Trade cycle уважает Router резервы (max $2 за сделку)
- Cross-exchange арбитраж (KuCoin ↔ ByBit спреды)
- Q-Score торговля + Opus Gate + Self-Learning v2
- PostgreSQL persistent storage (128 trades)

**Портфель ~$310:**
- KuCoin спот: ETH($130) + BTC($124) + DOT($12) + USDT($16)
- ByBit: $3 USDT + $4.47 в позиции + $2 в Earn
- Фьючерсы: $26.64 equity

**Проблемы решённые за сессию (6 коммитов):**
- [x] LunarCrush 429 death spiral → fail cache + exponential backoff
- [x] Earn 0% APR → правильные field names (returnRate, estimateApr)
- [x] ByBit "Empty order link ID" → orderLinkId fix
- [x] Smart Money Router v10.3.0 → авто-распределение средств
- [x] Пороги для малого счёта v10.3.1 → $1 reserves вместо $3-5
- [x] Бот тратил ВСЕ USDT v10.3.2 → max $2 за сделку, резервы Router

---

## 🏁 v10.0 — Dual-Exchange Foundation ✅ COMPLETE
- [x] ByBit Spot интеграция (BUY/SELL/Monitor)
- [x] Dual-exchange маршрутизация (→ биржа с большим USDT)
- [x] Ultra-Sniper pre-filter (экономия 80-90% на Vision API)
- [x] Small-account algorithm (<$50)
- [x] MiroFish v3 (15 AI-агентов)
- [x] Self-Learning v2
- [x] PostgreSQL persistent storage
- [x] GSD архитектура: CLAUDE.md, STATE.md, REQUIREMENTS.md

---

## 🌊 Wave 1 — Earn Engine (Пассивный доход)

### Phase A: KuCoin + ByBit Earn ✅ DEPLOYED (v10.2.3 + v10.3.x)
- [x] Earn API интеграция (KuCoin + ByBit Flexible Savings)
- [x] Auto-Earn: после SELL → свободные USDT → Flexible Savings
- [x] Auto-Redeem: перед BUY → redeem из Savings
- [x] Smart Money Router: Arb $1 → Trade $2 → Earn (всё остальное)
- [x] Trade cycle уважает Router резервы (не тратит Earn-деньги)
- [x] Telegram: /earn, /earnplace, /router
- [x] ByBit orderLinkId fix
- [x] APR field names fix (returnRate, estimateApr)

### Phase B: Lending + Advanced
- [ ] KuCoin Lending Pro: автоматическое размещение при rate > 10% APR
- [ ] Lending Spike Catcher: мониторинг hourly rates
- [ ] Staking Combo: stale позиции → stake вместо auto-sell
- [ ] Earn dashboard в Mini App (новый таб)
- [ ] Multi-asset Earn: не только USDT, но и ETH/BTC Flexible Savings

---

## 🌊 Wave 2 — Smart Trading v2 (Качество сделок)
> Приоритет: КРИТИЧЕСКИЙ · Бот покупает слишком часто и теряет деньги

### Phase A: Улучшение входов
- [ ] Минимум 2 подтверждающих индикатора для BUY (сейчас хватает одного)
- [ ] Volume filter: не покупать на низких объёмах
- [ ] Multi-timeframe: 15m + 1h + 4h согласованность тренда
- [ ] Cooldown per-symbol: 4 часа между покупками одного актива
- [ ] Max portfolio allocation: не более 30% в одну монету

### Phase B: Улучшение выходов
- [ ] Trailing stop v2: динамический trail по ATR (не фиксированный 1%)
- [ ] Partial exit: продавать 50% при +3%, остальное на trail
- [ ] Stale position analyzer: позиции без движения 24h+ → уведомление
- [ ] Time-based exit: позиция не в прибыли 48h → auto-sell

### Phase C: Analytics & Backtesting
- [ ] Win rate по символам (в Telegram: /winrate)
- [ ] PnL breakdown: какие монеты зарабатывают, какие теряют
- [ ] Backtesting engine: проверка стратегий на истории
- [ ] A/B testing: параллельное тестирование двух стратегий

---

## 🌊 Wave 3 — Multi-Exchange via CCXT
> Приоритет: ВЫСОКИЙ · Сложность: L

### Phase A: CCXT Foundation
- [ ] Установить ccxt в requirements.txt
- [ ] Абстракция: `exchange_factory(name)` → unified API
- [ ] Binance подключение (API ключи через Railway)
- [ ] OKX подключение

### Phase B: Cross-Exchange Yield Arbitrage
- [ ] `earn_compare_all_exchanges(asset)` — APR на всех биржах
- [ ] Автоматическая ротация USDT к лучшей ставке
- [ ] Promotional Rate Hunter — мониторинг промо-ставок

### Phase C: Enhanced Trading
- [ ] BUY routing: 3+ бирж (лучшая цена + баланс)
- [ ] SELL routing: лучший bid
- [ ] Portfolio rebalancing: auto-распределение по биржам

---

## 🌊 Wave 4 — Telegram→Claude Code Autonomy
> Приоритет: ВЫСОКИЙ · Сложность: M

### Phase A: Инфраструктура
- [x] Obsidian Knowledge Vault — 20 заметок, wiki-ссылки
- [ ] Claude Code CLI установка на MacBook (чеклист готов ✅)
- [ ] instar setup → Telegram→Claude Code мост
- [ ] Job scheduling: автозапуск задач по расписанию

### Phase B: Remote Control
- [ ] Telegram→Claude Code: отправка произвольных задач
- [ ] Auto-diagnostics: каждые 6ч → отчёт в Telegram
- [ ] Deploy pipeline: Telegram → Claude Code → git push → Railway
- [ ] Self-improvement: анализ trade results → предложения

---

## 🌊 Wave 5 — AI & Design Evolution
> Приоритет: СРЕДНИЙ · Сложность: L

### Phase 0: Настройка Claude Code Супер-Дизайнер (MacBook)
> 📄 Чеклист: QuantumTrade_SuperDesigner_Checklist.docx

- [ ] Claude Code CLI (npm install -g @anthropic-ai/claude-code)
- [ ] Design plugins (Anthropic, Wilwaldon, OhMySkills)
- [ ] MCP servers (Playwright, GitHub)
- [ ] Telegram control (instar / @gonzih/cc-tg)

### Phase A: Design System Overhaul
- [ ] CSS Design Tokens (OKLCH) + Glassmorphism + Cyberpunk
- [ ] Микро-анимации, skeleton loading, number animations
- [ ] Earn Dashboard + Router Dashboard в Mini App

### Phase B: AI Upgrades
- [ ] DeepSeek V3.2 reasoning (когда оплата пройдёт)
- [ ] ML price prediction (LSTM/Transformer)
- [ ] Backtesting engine

---

## 🌊 Wave 6 — Polymarket + DeFi
> Приоритет: НА БУДУЩЕЕ · Сложность: XL

- [ ] Polymarket API → signal integration → active trading
- [ ] DeFi integration (Uniswap, AAVE)
- [ ] Налоговый калькулятор
- [ ] Multi-user подписочная модель
- [ ] Mobile App (React Native)

---

## 📊 Метрики успеха
| Метрика | Сейчас (v10.3) | Цель v11.0 | Цель v13.0 |
|---------|---------------|-----------|-----------|
| Биржи | 2 (KC+BB) | 4-5 | 5+ DeFi |
| Пассивный доход | 0.79% APR | 3-8% APR | 10-15% APR |
| API cost/day | $0/day | $0.10-0.50 | $1-2 (с ML) |
| Портфель | ~$310 | $500+ | $1000+ |
| Направления | Spot+Arb+Earn | +Lending+Poly | +DeFi+NFT |
| Win rate | TBD (аудит!) | 55%+ | 65%+ |
| Max на сделку | $2 (Router) | $5-10 | Dynamic |
| Автономия | Router v10.3 | Telegram→CC | Full Auto |

---

## 🎯 Что делать дальше (по приоритету)

### 🔴 СРОЧНО (сегодня-завтра):
1. **Аудит торговли** — проверить win rate, PnL всех 128 сделок → понять где теряем
2. **Проверить Router** — после деплоя v10.3.2 убедиться что USDT не утекает
3. **ETH+BTC HOLD** — не продавать, мониторить через /positions

### 🟡 СКОРО (неделя):
4. **Wave 2A: Smart Trading v2** — фильтры входов, multi-timeframe, volume
5. **Wave 1B: Multi-asset Earn** — ETH/BTC в Flexible Savings (не только USDT)
6. **Claude Code CLI** — установка на MacBook (Phase 0 чеклист готов)

### 🟢 ПОТОМ (месяц):
7. **Wave 3: CCXT + Binance** — больше бирж = больше ликвидности
8. **Wave 4: Telegram→Claude Code** — instar + автономия
9. **Wave 5: Design + AI upgrades** — красивый UI + ML модели

---

## 🔄 Wave Status
```
Current: v10.3.2 — Smart Money Router + Trade Size Fix
Active:  Wave 1A ✅ (Earn Engine), Wave 2A (Smart Trading — в планах)
Next:    Аудит торговли → Wave 2A (качество сделок)
Blocked: Binance/OKX API keys (Wave 3), DeepSeek PayPal (AI quality)
Ready:   Wave 5 Phase 0 (чеклист готов, ждёт Claude Code CLI)
Last Updated: 2026-04-03 · 6 commits this session
```
