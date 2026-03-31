# REQUIREMENTS.md — Спецификация требований
> Что бот должен уметь. Обновлять при добавлении фич.

## v1 (реализовано)
- [x] Мониторинг цен KuCoin (6 пар) в реальном времени
- [x] Q-Score: композитный сигнал 0-100 из 5 источников
- [x] Claude Vision анализ графиков (35% Q-Score)
- [x] Whale tracking — on-chain анализ топ-500 кошельков
- [x] Fear & Greed Index интеграция
- [x] Polymarket — события как фактор Q-Score
- [x] Автопилот — автоматическое исполнение сигналов
- [x] Треугольный арбитраж (5 путей, порог 0.4%)
- [x] Telegram бот с полным меню команд
- [x] Mini App (WebApp) — 10 табов, тёмная тема
- [x] Самообучение — динамическая коррекция Q-порога
- [x] AutoScanner — 10+ health checks каждые 5 мин
- [x] AI-консультант через Claude API

## v2 (реализовано в v8-v10)
- [x] MiroFish v3 — 15 ролевых AI-агентов для сентимента
- [x] Multi-exchange: ByBit Spot (dual-exchange trading v10.0)
- [x] Cross-exchange arbitrage (KuCoin ↔ ByBit)
- [x] Copy-Trading Intelligence (ByBit leaderboard)
- [x] Self-Learning v2 — авто-анализ F&G, часы, символы
- [x] Reddit Sentiment (r/cryptocurrency + r/bitcoin)
- [x] LunarCrush Galaxy Score (соц. сентимент)
- [x] Opus Gate — AI подтверждение значимых сделок
- [x] Advanced TA (MACD, BB, Stoch, ADX, OBV)
- [x] Macro Dashboard (BTC dominance, ETH gas, DXY)
- [x] Small-account algorithm (MAX_OPEN_POSITIONS, smart sizing)
- [x] Stale position auto-sell (12h без движения)
- [x] Алерты в Telegram при аномалиях
- [x] PostgreSQL persistent storage (trades, signals, F&G)
- [x] Claude Code subagents (.claude/agents/)
- [ ] Персистентный trade_log (Railway Volume)
- [ ] WebSocket live-обновления в Mini App
- [ ] P&L графики в Mini App (recharts)
- [ ] Бэктестинг на исторических данных

## v3 (планируется)
- [ ] Multi-exchange через CCXT (Binance, OKX, Gate.io)
- [ ] Polymarket программная торговля (API ставки)
- [ ] DeepSeek V3.2 интеграция (reasoning model)
- [ ] ML-модель предсказания цены (LSTM/Transformer)
- [ ] Portfolio rebalancing автоматический
- [ ] Copy-trading для друзей (social trading)
- [ ] Mobile app (React Native)
- [ ] Расширенные стратегии (scalping, mean reversion, grid)
