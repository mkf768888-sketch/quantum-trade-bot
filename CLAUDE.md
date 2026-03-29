# QuantumTrade AI — CLAUDE.md
> Главный конфиг для AI-агентов. Читать при каждом запуске.
> v7.6.0 · 2026-03-29 · github.com/mkf768888-sketch/quantum-trade-bot

## Архитектура
- **Бэкенд:** Python 3.11, FastAPI → `server.py` (~3800 строк), Railway Cloud
- **Фронтенд:** `index.html` — Telegram Mini App, 10 табов
- **Деплой:** git push → Railway autodeploy → POST /api/setup-webhook
- **Память:** STATE.md (решения между сессиями), trade_log в /data/

## Railway Variables
```
KUCOIN_API_KEY / KUCOIN_SECRET / KUCOIN_PASSPHRASE
BOT_TOKEN / API_SECRET / ANTHROPIC_API_KEY
RAILWAY_PUBLIC_DOMAIN / RISK_PER_TRADE=0.08
```

## API-контракт

### Публичные (без auth)
- GET /                    → Mini App HTML (no-cache, ?v=752)
- GET /api/public/stats    → цены + баланс + Q-score + whale + polymarket
- GET /api/public/balance  → спот + фьючерсы
- GET /api/public/positions → открытые позиции
- GET /api/scanner/status  → статус AutoScanner
- GET /api/polymarket      → Polymarket события
- GET /api/signal/{pair}   → сигнал по паре

### Приватные (Header: X-API-Key)
- GET  /api/debug          → диагностика (v7.5.2: auth added)
- POST /api/autopilot/{state} → вкл/выкл торговлю (v7.5.2: auth added)
- POST /api/settings       → изменить параметры
- POST /api/trade/manual   → ручная сделка
- POST /api/ai/chat        → Claude AI (rate limit 20/10min)
- POST /api/setup-webhook  → обновить Telegram кнопку
- GET  /api/trades          → история сделок
- GET  /api/dashboard       → сводка для дашборда

## Q-Score (0–100)
```
Claude Vision: 35% | Индикаторы: 25% | Контекст: 20% | Whale: 10% | F&G: 10%
```
**Самообучение (v7.5.1+):** динамическая коррекция порога Q-Score на основе
streak, win rate, per-symbol статистики. Порог поднимается при проигрышах,
снижается при серии побед.

## Стратегии
| Стратегия | Q-Score | Take Profit | Stop Loss | Описание |
|-----------|---------|-------------|-----------|----------|
| B (основная) | >85 | 3% | 1.5% | Высокая уверенность |
| C (средняя) | 60-85 | 1.5% | 1% | Умеренный сигнал |
| DUAL | >90 | 2.5%+1.5% | 1%+0.8% | Long + Short хедж |

## Правила изменений
1. Изменил эндпоинт → обнови index.html (контракт!)
2. После деплоя → POST /api/setup-webhook (не GET!)
3. Секреты только в Railway Variables, никогда в коде
4. server.py — один файл, не дробить
5. Каждый коммит — атомарный, с описанием что и зачем

## Security (v7.5.2)
- [x] Все приватные эндпоинты под verify_api_key
- [x] /api/debug — auth added
- [x] /api/autopilot — auth added
- [x] XSS protection в AI chat (escHtml)
- [x] Fetch timeouts (15s) + .ok checks в index.html
- [x] WebSocket disconnect handling
- [ ] Rate limiting на публичные эндпоинты
- [ ] CORS → сузить origins
- [ ] Security headers middleware
- [ ] Trade log → Railway Volume (/data/)

## Чеклист деплоя
```
1. git push → Railway деплоит (2-3 мин)
2. GET /health → version + status ok
3. GET /api/debug (с API key) → все checks зелёные
4. POST /api/setup-webhook → кнопка обновлена (?v=XXX)
5. Telegram → Mini App → Настройки → Диагностика → всё ОК
```
