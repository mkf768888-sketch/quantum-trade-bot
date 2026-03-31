# QuantumTrade AI — ROADMAP
> Волновая дорожная карта · GSD v2 Architecture · Обновлено: 2026-04-01
> Философия: Персональная финансовая экосистема с бешеной маржинальностью

## 🏁 v10.0 — Dual-Exchange Foundation ✅ COMPLETE
- [x] ByBit Spot интеграция (BUY/SELL/Monitor)
- [x] Dual-exchange маршрутизация (→ биржа с большим USDT)
- [x] Ultra-Sniper pre-filter (экономия 80-90% на Vision API)
- [x] Small-account algorithm (<$50)
- [x] MiroFish v3 (15 AI-агентов)
- [x] Self-Learning v2
- [x] PostgreSQL persistent storage
- [x] /reset_stats, /autopilot fix
- [x] GSD архитектура: CLAUDE.md, STATE.md, REQUIREMENTS.md
- [x] Claude Code субагенты (4 агента)

---

## 🌊 Wave 1 — v10.1: Earn Engine (Пассивный доход)
> Приоритет: ВЫСОКИЙ · Сложность: M · Агент: earn-strategist

### Phase A: KuCoin + ByBit Earn (текущие API ключи) ✅ DEPLOYED
- [x] `earn_get_products(exchange)` — получить список Flexible products
- [x] `earn_get_best_rate(asset)` — сравнить APR KuCoin vs ByBit
- [x] `earn_subscribe_flexible(exchange, asset, amount)` — подписка
- [x] `earn_redeem(exchange, asset, amount)` — погашение
- [x] Auto-Earn: после SELL → свободные USDT → Flexible Savings
- [x] Auto-Redeem: перед BUY → redeem из Savings
- [x] Telegram: /earn — статус, APR, total earned
- [x] API endpoint: /api/earn/status

### Phase B: Lending + Advanced
- [ ] KuCoin Lending Pro: автоматическое размещение при rate > 10% APR
- [ ] Lending Spike Catcher: мониторинг hourly rates
- [ ] Staking Combo: stale позиции → stake вместо auto-sell
- [ ] Earn dashboard в Mini App (новый таб)

---

## 🌊 Wave 2 — v11.0: Multi-Exchange via CCXT
> Приоритет: ВЫСОКИЙ · Сложность: L · Агент: wave-orchestrator

### Phase A: CCXT Foundation
- [ ] Установить ccxt в requirements.txt
- [ ] Абстракция: `exchange_factory(name)` → unified API
- [ ] Binance подключение (API ключи через Railway)
- [ ] OKX подключение
- [ ] Gate.io подключение (опционально)

### Phase B: Cross-Exchange Yield Arbitrage
- [ ] `earn_compare_all_exchanges(asset)` — APR на всех биржах
- [ ] Автоматическая ротация USDT к лучшей ставке
- [ ] Promotional Rate Hunter — мониторинг промо-ставок
- [ ] Cross-exchange triangle: Earn + Spot + Arb

### Phase C: Enhanced Trading
- [ ] BUY routing: 3+ бирж (лучшая цена + баланс)
- [ ] SELL routing: лучший bid
- [ ] Cross-exchange spot arbitrage (3+ пар)
- [ ] Portfolio rebalancing: auto-распределение по биржам

---

## 🌊 Wave 3 — v11.1: Polymarket Integration
> Приоритет: СРЕДНИЙ · Сложность: M · Агент: polymarket-trader

### Phase A: Data Layer
- [ ] Polymarket API клиент (REST + WebSocket)
- [ ] Кэш активных рынков (обновление каждые 5 мин)
- [ ] Фильтр: только крипто-связанные markets
- [ ] Odds history tracking в PostgreSQL

### Phase B: Signal Integration
- [ ] `polymarket_get_signal(symbol)` → Q-Score фактор
- [ ] Корреляция: BTC price prediction markets → BUY/SELL weight
- [ ] Event hedging: хедж спот позиций через event markets
- [ ] Telegram: /poly — текущие рынки и odds

### Phase C: Active Trading
- [ ] Polygon wallet setup (secure key management)
- [ ] Limit order placement
- [ ] Position monitoring
- [ ] Auto-exit при settlement
- [ ] P&L tracking в общем dashboard

---

## 🌊 Wave 4 — v12.0: AI & Design Evolution
> Приоритет: СРЕДНИЙ · Сложность: L · Агент: design-system + wave-orchestrator

### Phase A: Design System Overhaul
- [ ] CSS Design Tokens (OKLCH, анимации) в index.html
- [ ] Glassmorphism + Cyberpunk стиль карточек
- [ ] Микро-анимации: hover, press, update pulse
- [ ] Skeleton loading states
- [ ] Tab slide transitions
- [ ] Number animations (PnL, баланс)
- [ ] Новый таб: Earn Dashboard
- [ ] Новый таб: Polymarket Monitor

### Phase B: AI Upgrades
- [ ] DeepSeek V3.2 reasoning integration (когда оплата пройдёт)
- [ ] LSTM/Transformer: price prediction model
- [ ] ML feature engineering: TA indicators → prediction
- [ ] Backtesting engine: историческая проверка стратегий

### Phase C: Advanced Features
- [ ] Social copy-trading (лидерборд ByBit → авто-повтор)
- [ ] Telegram Mini App WebSocket (real-time updates)
- [ ] Push-уведомления о Earn events (промо, спайки)
- [ ] Auto portfolio rebalancing across all exchanges

---

## 🌊 Wave 5 — v13.0: Financial Ecosystem
> Приоритет: НА БУДУЩЕЕ · Сложность: XL

- [ ] DeFi integration (Uniswap, AAVE) через Web3
- [ ] NFT мониторинг и trading
- [ ] Налоговый калькулятор (trade history → tax report)
- [ ] Multi-user: несколько портфелей
- [ ] Mobile App (React Native wrapper)
- [ ] Публичный бот: подписочная модель

---

## 📊 Метрики успеха
| Метрика | Текущее | Цель v11.0 | Цель v13.0 |
|---------|---------|-----------|-----------|
| Биржи | 2 | 4-5 | 5+ DeFi |
| Пассивный доход | 0% | 3-8% APR | 10-15% APR |
| API cost/day | $0.50-1.50 | $0.50-1.50 | $1-2 (с ML) |
| Портфель | ~$45 | $200+ | $1000+ |
| Направления | Spot + Arb | +Earn +Poly | +DeFi +NFT |
| Win rate | TBD | 55%+ | 65%+ |

---

## 🔄 Wave Status
```
Current Wave: 1 Phase B (Earn Advanced — Lending, Staking Combo)
Completed: Wave 1 Phase A (Earn Engine deployed v10.1.0)
Next Wave: 2 (Multi-Exchange)
Blocked: Binance/OKX API keys needed
Last Updated: 2026-04-01
```
