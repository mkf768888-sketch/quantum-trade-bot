# REQUIREMENTS.md — Спецификация требований
> Что бот должен уметь. Обновлять при добавлении фич.

## v1 (текущая — реализовано)
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

## v2 (следующая — планируется)
- [ ] Персистентный trade_log (Railway Volume)
- [ ] Фильтрация Polymarket (только крипто-события)
- [ ] WebSocket live-обновления в Mini App (без polling)
- [ ] Расширенные стратегии (scalping, mean reversion)
- [ ] Бэктестинг на исторических данных
- [ ] P&L графики в Mini App (recharts)
- [ ] Multi-exchange (Binance, Bybit)
- [ ] Rate limiting + security headers
- [ ] Алерты в Telegram при аномалиях (whale dump, flash crash)

## v3 (будущее)
- [ ] ML-модель предсказания цены (LSTM/Transformer)
- [ ] Sentiment анализ Twitter/Reddit
- [ ] Portfolio rebalancing
- [ ] Copy-trading для друзей
- [ ] Mobile app (React Native)
