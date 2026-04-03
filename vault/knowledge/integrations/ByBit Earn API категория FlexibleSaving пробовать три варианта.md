---
tags: [integration, bybit, earn, api]
date: 2026-04-02
---
# ByBit Earn API: категория FlexibleSaving, пробовать три варианта

ByBit Earn API (v5) тоже нестабилен по naming. Пробуем три категории:

1. `FlexibleSaving`
2. `Flexible`
3. `flexibleSaving`

## Endpoints:
- GET `/v5/earn/product` → список продуктов
- POST `/v5/earn/place-order` (orderType=Stake) → подписка
- POST `/v5/earn/place-order` (orderType=Redeem) → выкуп
- GET `/v5/earn/position` → текущие позиции

## Функции в server.py:
- `bybit_earn_get_products(coin)` — перебирает категории
- `bybit_earn_subscribe(product_id, amount, coin)`
- `bybit_earn_redeem(product_id, amount, coin)`
- `bybit_earn_get_positions(coin)`

## Кэширование:
`earn_get_best_rate(coin)` сравнивает APR обеих бирж, кэш 10 минут.

Связано: [[KuCoin Earn API требует три fallback endpoint пути]], [[earn auto-place после SELL свободный USDT уходит в Flexible Savings]]
