---
tags: [bybit, double-win, earn, integration, v10.10]
date: 2026-04-05
version: v10.10.0
---

# ByBit Double Win — структурированный earn продукт

## Что это
Double Win — Advanced Earn продукт ByBit (раздел "Банкинг → Продвинутый Earn").
Аналог DCI: фиксированный срок, структурированная доходность.
Девиз: "Зарабатывайте на каждом движении рынка".

## API (та же семья что DCI)
```
GET  /v5/earn/advance/product       params: {"category": "DoubleWin"}
POST /v5/earn/advance/place-order   body: {category, productId, coin, amount, orderType, accountType, orderLinkId}
GET  /v5/earn/advance/orders        params: {"category": "DoubleWin"}
```

## Реализованные функции (v10.10.0)
```python
bybit_double_win_get_products(coin=None) → list
bybit_double_win_get_positions()         → list
double_win_auto_place(usdt_amount)       → dict{success, order_id, apy_pct, amount}
```

## Env vars (Railway)
```
DOUBLE_WIN_ENABLED=false       # включить после подтверждения DCI
DOUBLE_WIN_MIN_INVEST=5.0      # минимум USDT для размещения
DOUBLE_WIN_MAX_INVEST=20.0     # максимум USDT за ордер
```

## Интеграция в earn_monitor_loop
- Триггер: каждые 4 цикла (~60 мин), как DCI
- Проверяет свободный USDT через `_dci_get_fund_balances()`
- Выбирает продукт с лучшим APY из eligible (min_amount ≤ usdt_amount)
- Инвестирует 80% доступного (не больше MAX_INVEST)
- FUND → fallback UNIFIED

## Важные отличия от DCI
- Нет `dualAssetsExtra` — тело проще (нет вложенного объекта)
- APY parsing: `apy_val < 1 and no "%" in str` → умножить на 100

## Статус в /health
```
🎰 DW: ✅ вкл | 2 поз | products=12
```

## Связанные заметки
- [[ByBit DCI orderType должен быть Stake а не BuyLow SellHigh]]
