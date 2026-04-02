# QuantumTrade AI — ROADMAP
> Волновая дорожная карта · GSD v2 Architecture · Обновлено: 2026-04-02
> Философия: Персональная финансовая экосистема с бешеной маржинальностью
> Новое: Telegram→Claude Code автономия + Design System plugins

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

## 🌊 Wave 3 — v11.1: Telegram→Claude Code Autonomy
> Приоритет: ВЫСОКИЙ · Сложность: M · Агент: wave-orchestrator
> Зависимости: нет (можно начинать сейчас, бесплатно)

### Phase A: Instar Setup + Knowledge Vault
- [x] Obsidian Knowledge Vault — 17 заметок, wiki-ссылки, CLAUDE.md обновлён
- [ ] `npx instar` — установка и настройка
- [ ] Подключение Telegram бота к Claude Code через instar
- [ ] Persistent memory: контекст сохраняется между сессиями (vault + instar memory)
- [ ] Job scheduling: автозапуск задач по расписанию
- [ ] Telegram команды: /status, /deploy, /fix, /logs → Claude Code

### Phase B: Remote Control & Monitoring
- [ ] Telegram→Claude Code: отправка произвольных задач
- [ ] Auto-diagnostics: scheduled job каждые 6ч → отчёт в Telegram
- [ ] Crash recovery: автоматическое обнаружение и fix через Telegram
- [ ] Deploy pipeline: Telegram → Claude Code → git push → Railway auto-deploy
- [ ] Context survival: memory.md + STATE.md синхронизация

### Phase C: Full Autonomy Loop
- [ ] Self-improvement: Claude Code анализирует trade results → предлагает улучшения
- [ ] Auto-update: scheduled weekly code review + optimization
- [ ] Alert escalation: critical issues → Telegram notification → auto-fix attempt
- [ ] Multi-session: параллельные задачи (trading + research + monitoring)

---

## 🌊 Wave 4 — v11.2: Polymarket Integration
> Приоритет: СРЕДНИЙ · Сложность: M · Агент: polymarket-trader
> Зависимости: Polygon wallet

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

## 🌊 Wave 5 — v12.0: AI & Design Evolution
> Приоритет: СРЕДНИЙ · Сложность: L · Агент: design-system + wave-orchestrator
> Инструменты: wilwaldon/Frontend-Design-Toolkit, anthropics/design plugin, OhMySkills

### Phase 0: Настройка Claude Code Супер-Дизайнер (MacBook)
> Подготовка инфраструктуры — установка всех инструментов на MacBook
> 📄 Полный чеклист: QuantumTrade_SuperDesigner_Checklist.docx

#### Шаг 0.1: Установка Claude Code CLI
- [ ] Установить Node.js v18+ (brew install node)
- [ ] Установить Claude Code CLI (npm install -g @anthropic-ai/claude-code)
- [ ] Авторизация (claude auth)
- [ ] Проверить: claude --version

#### Шаг 0.2: Дизайн-плагины и скиллы
- [ ] Frontend Design Skill от Anthropic (claude plugin add anthropic/frontend-design)
- [ ] Claude-Code-Frontend-Design-Toolkit (github.com/wilwaldon) — клонировать → .claude/skills/
- [ ] OhMySkills/design-style (github.com/NakanoSanku) — 30+ стилей → .claude/skills/design-style/
- [ ] Design Tokens Skill (OKLCH математика) — уже в design-system.md агенте ✅
- [ ] UI/UX Pro Max — 240+ стилей, 127 шрифтовых пар

#### Шаг 0.3: MCP-серверы
- [ ] Playwright MCP (claude mcp add playwright npx @anthropic-ai/mcp-playwright)
- [ ] GitHub MCP (claude mcp add github npx @anthropic-ai/mcp-github)

#### Шаг 0.4: Telegram-управление Claude Code (выбрать один)
- [ ] Вариант A: Claude Channels (простой) — claude plugin install telegram@claude-plugins-official
- [ ] Вариант B: @gonzih/cc-tg (продвинутый) — голос, файлы, cron
- [ ] Вариант C: instar (максимум) — память, планировщик, кросс-сессии
- [ ] Проверить: отправить тестовую команду из Telegram → Claude Code

### Phase A: Design System Overhaul (применение к проекту)
- [ ] CSS Design Tokens (OKLCH color system, анимации) в index.html
- [ ] Glassmorphism + Cyberpunk стиль карточек (из OhMySkills/design-style)
- [ ] Микро-анимации: hover, press, update pulse
- [ ] Skeleton loading states
- [ ] Tab slide transitions
- [ ] Number animations (PnL, баланс, sparklines)
- [ ] Новый таб: Earn Dashboard
- [ ] Новый таб: Polymarket Monitor
- [ ] Mobile-first responsive (Telegram Mini App viewport)

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

## 🌊 Wave 6 — v13.0: Financial Ecosystem
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
| API cost/day | $0/day | $0.10-0.50 | $1-2 (с ML) |
| Портфель | ~$45 | $200+ | $1000+ |
| Направления | Spot + Arb | +Earn +Poly | +DeFi +NFT |
| Win rate | TBD | 55%+ | 65%+ |
| Автономия | Manual | Telegram→CC | Full Auto |
| UI качество | Basic | Cyberpunk v1 | Glassmorphism |

---

## 🎯 Приоритизированный план (что делать и за что платить)

### 🟢 БЕСПЛАТНО — можно делать прямо сейчас:
1. **Wave 1B: Earn Advanced** — Lending, Staking Combo (код, нет оплаты)
2. **Wave 3: Telegram→Claude Code** — instar setup (бесплатный, npx instar)
3. **Wave 5A: Design System** — Frontend Design Toolkit (бесплатный)
4. **Earn API fix** — проверить permissions на биржах для Earn endpoints

### 💰 ТРЕБУЕТ ВЛОЖЕНИЙ:
| Что | Стоимость | ROI | Приоритет |
|-----|-----------|-----|-----------|
| DeepSeek V3.2 API | ~$5-10/мес | Качество AI торговли x3-5 | ВЫСОКИЙ |
| Binance API ключ | $0 (регистрация) | Доступ к крупнейшей бирже | ВЫСОКИЙ |
| OKX API ключ | $0 (регистрация) | Ещё больше ликвидности | СРЕДНИЙ |
| Polygon wallet | $5-10 MATIC | Polymarket trading | НИЗКИЙ |

### 📋 Рекомендуемый порядок:
```
Сейчас:  Earn $35 → ночной доход ✅ → Wave 5-Phase0 (Claude Code CLI на MacBook)
Скоро:   Wave 3A (instar/TG) → Wave 1B (Lending Spike) → DeepSeek PayPal
Потом:   Wave 5A (Design) → Wave 2A (CCXT) → Wave 4 (Poly) → Wave 6 (DeFi)
```

---

## 🔄 Wave Status
```
Current Wave: 1A fix (Earn APR v10.2.3) + 5-Phase0 (Супер-Дизайнер чеклист готов)
Completed: Wave 0 (v10.0), Wave 1A (Earn Engine — APR fix v10.2.3)
Next Wave: 1B (Earn Advanced) + 3A (Telegram→CC)
Blocked: Binance/OKX API keys (Wave 2), DeepSeek PayPal (AI quality)
Ready: Wave 5 Phase 0 (чеклист создан, ожидает установки Claude Code CLI на MacBook)
Last Updated: 2026-04-03
```
