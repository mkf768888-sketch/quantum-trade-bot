---
tags: [bug, lunarcrush, rate-limit, fixed]
date: 2026-04-03
---
# LunarCrush 429 death spiral — кеш никогда не заполняется при rate limit

## Проблема
`fetch_lunarcrush_sentiment()` вызывается каждый торговый цикл (~20 сек).
Кеш 10 минут, но при HTTP 429 данные НЕ кешируются → следующий цикл опять стучит в API → ещё 429.
Бесконечный цикл: 429 → нет кеша → запрос → 429.

## Решение (v10.2.2)
1. **Fail cache** — при 429 запоминаем время отказа, не повторяем 30 минут
2. **Exponential backoff** — при повторных 429: 30мин → 60мин → 120мин (max 2ч)
3. Если bulk endpoint вернул 429 — **пропускаем per-coin** (тоже будут 429)
4. При успехе — backoff сбрасывается

## Связано с
- [[DeepSeek единственный AI провайдер в торговом цикле]]
- LunarCrush v4 API требует Bearer token auth (LUNARCRUSH_API_KEY)

## Переменные
```python
_lunarcrush_fail_ts: float = 0.0   # время последнего неудачного запроса
_lunarcrush_backoff: int = 1800    # начальный backoff 30 мин
```
