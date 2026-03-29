# QuantumTrade AI — CLAUDE.md
> Главный конфиг для AI-агентов. Читать при каждом запуске. Макс 120 строк.
> v7.5.2 · 2026-03-29 · github.com/mkf768888-sketch/quantum-trade-bot

## Стек и архитектура
- **Бэкенд:** Python 3.11, FastAPI, Railway Cloud → один файл: `server.py` (~3600 строк)
- **Фронтенд:** `index.html` — Telegram Mini App (WebApp), 6 табов
- **Деплой:** git push → Railway autodeploy → вызвать GET /api/setup-webhook

## Railway Variables (все обязательны)
```
KUCOIN_API_KEY / KUCOIN_SECRET / KUCOIN_PASSPHRASE  — KuCoin API
BOT_TOKEN             — Telegram Bot
API_SECRET            — X-API-Key для приватных эндпоинтов
RAILWAY_PUBLIC_DOMAIN — твой-домен.up.railway.app
ANTHROPIC_API_KEY     — Claude Vision AI
```

## API-контракт

### Публичные (без auth)
- GET /                    → Mini App HTML (no-cache)
- GET /api/public/stats    → цены + баланс + Q-score + whale + airdrops
- GET /api/public/balance  → спот + фьючерсы
- GET /api/public/positions → открытые позиции
- GET /api/debug           → ⚠️ диагностика (TODO: закрыть auth)
- GET /api/scanner/status  → статус AutoScanner

### Приватные (Header: X-API-Key: {API_SECRET})
- GET  /api/stats          → полная статистика
- POST /api/settings       → изменить параметры бота
- POST /api/autopilot/{state} → ⚠️ СЕЙЧАС БЕЗ AUTH (баг, backlog)
- POST /api/ai/chat        → Claude AI чат (rate limit 20/10min)
- GET  /api/setup-webhook  → обновить кнопку Telegram после деплоя

## Ключевые параметры
```python
MIN_Q_SCORE = 77      # порог входа в сделку
COOLDOWN = 600        # секунд между сделками
RISK_PER_TRADE = 0.02 # TODO: поднять до 0.08 через Railway Variables
MAX_LEVERAGE = 3
TRADING_PAIRS = ["ETH-USDT","BTC-USDT","SOL-USDT","AVAX-USDT","XRP-USDT"]
```

## Q-Score (0–100): Claude Vision 35% + Индикаторы 25% + Контекст 20% + Whale 10% + F&G 10%

## Стратегии: B (Q>85, TP3%/SL1.5%), C (Q60-85, TP1.5%/SL1%), DUAL (Q>90, Long+Short)

## Правила изменений
1. После изменения эндпоинта — обновить index.html одновременно (контракт!)
2. После деплоя — обязательно вызвать GET /api/setup-webhook
3. CORS оставить открытым — Telegram WebApp требует wildcard
4. Секреты только в Railway Variables, никогда в коде
5. server.py — один файл, не дробить на модули

## Security backlog (приоритет → v7.4.5)
- [ ] /api/autopilot/{state} — добавить Depends(verify_api_key) + key в Mini App
- [ ] /api/debug — убрать чувствительные поля или закрыть auth
- [ ] Rate limiting на публичные эндпоинты (100/min per IP)
- [ ] CORS → сузить до Telegram origins
- [ ] Security headers middleware
- [ ] Trade log → Railway Volume (сейчас теряется при редеплое)

## Чеклист деплоя
```
[ ] git push → Railway задеплоил (2-3 мин)
[ ] /api/scanner/status → сервис запущен
[ ] /api/debug → все checks зелёные
[ ] GET /api/setup-webhook → кнопка обновлена
[ ] Перезапустить Telegram → Mini App → Настройки → Диагностика
```
