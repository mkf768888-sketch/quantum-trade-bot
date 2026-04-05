# QuantumTrade AI — ROADMAP
> Волновая дорожная карта · GSD v2 Architecture · Обновлено: 2026-04-05
> Философия: Персональная финансовая экосистема с бешеной маржинальностью
> Версия: v10.12.0 · Smart Trading v2 + Security + DCI · Деньги НИКОГДА не простаивают

---

## 📍 ГДЕ МЫ СЕЙЧАС (v10.12.0)

**Работает:**
- Dual-exchange торговля (KuCoin + ByBit) — 15 AI-агентов MiroFish
- Smart Money Router — авто-распределение: Arb → Trade → Earn
- Earn Engine — Flexible Savings (KuCoin + ByBit ✅)
- DCI (Dual Currency Investment) — ByBit ~877-985% APY
- Auto-Redeem перед BUY, auto-route в Earn после SELL
- Q-Score торговля + Opus Gate + Self-Learning v2
- Security hardening: ADMIN_CHAT_IDS, webhook/WS auth, locks
- Wave 2A Smart Filters: Volume + 4h MTF + Partial Exit

**Что сделано с v10.3.2 → v10.12.0:**
- [x] ByBit Balance full display (FUNDING + UNIFIED + SPOT)
- [x] DCI integration + precision fix + auto-transfer fix
- [x] KuCoin Earn display fix (3-endpoint fallback)
- [x] Full Opus security audit (237 functions, 75 issues found+fixed)
- [x] ADMIN_CHAT_IDS authorization + confirmation dialogs
- [x] asyncio.Lock for DCI + Earn + Arb (H-06 fix)
- [x] Volume filter (vol_ratio ≥ 0.65) + 4h trend filter
- [x] Partial Exit: 50% at TP1, trail to TP2
- [x] /stats visual upgrade: win rate bar + top symbols

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

### Phase A: Улучшение входов ✅ v10.12.0
- [x] Минимум 2 подтверждающих индикатора для BUY — v10.11.1
- [x] Volume filter: не покупать при vol_ratio < 0.65 — v10.12.0
- [x] Multi-timeframe: 1h + 4h согласованность тренда — v10.12.0
- [x] Cooldown per-symbol: 4 часа между покупками — v10.11.1
- [ ] Max portfolio allocation: не более 30% в одну монету

### Phase B: Улучшение выходов (частично готово)
- [ ] Trailing stop v2: динамический trail по ATR (не фиксированный 1%)
- [x] Partial exit: продаём 50% при TP1, трейлим до TP2 — v10.12.0
- [ ] Stale position analyzer: позиции без движения 24h+ → уведомление
- [ ] Time-based exit: позиция не в прибыли 48h → auto-sell (есть 48h stale)

### Phase C: Analytics & Backtesting
- [ ] Win rate по символам (в Telegram: /winrate) — приоритет!
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

### 🔴 СРОЧНО (сегодня):
1. **Проверить DCI** — /dciplace с $41 в ByBit Funding (precision fix v10.11.4)
2. **DOUBLE_WIN_ENABLED=true** — Railway Variables, следующий поток пассивного дохода
3. **Мониторинг логов** — убедиться что vol_ratio + 4h фильтры работают корректно

### 🟡 СКОРО (неделя):
4. **Wave 2C: /winrate команда** — топ символы по win rate в Telegram
5. **Wave 1B: KuCoin Lending Pro** — автоматическое размещение когда rate > 10% APR
6. **Max portfolio allocation** — не более 30% баланса в одну монету

### 🟢 ПОТОМ (месяц):
7. **Wave 3A: CCXT + Binance/OKX** — нужны API ключи, больше бирж = больше возможностей
8. **Wave 5: Cyberpunk+Glassmorphism UI** — красивый Mini App (index.html redesign)
9. **Wave 5B: AI upgrades** — DeepSeek V3.2, ML price prediction (LSTM)

---

## 🔄 Wave Status
```
Current: v10.12.0 — Wave 2A Smart Trading + Security Hardening
Active:  Wave 1A ✅ (Earn + DCI), Wave 2A ✅ (Smart Filters deployed)
Next:    Wave 2B (backtesting + /winrate) → Wave 3A (CCXT) → Wave 5 (Design)
Blocked: Binance/OKX API keys (Wave 3A multi-exchange)
Quick wins: /dciplace test + DOUBLE_WIN_ENABLED=true
Last Updated: 2026-04-05 · v10.11.4→v10.12.0 (5 commits this session)
```
