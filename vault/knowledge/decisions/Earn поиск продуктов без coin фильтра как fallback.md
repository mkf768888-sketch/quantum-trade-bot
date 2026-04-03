---
tags: [decision, earn, api]
date: 2026-04-03
---
# Earn — поиск продуктов без coin фильтра как fallback

## Контекст
KuCoin и ByBit Earn API возвращают HTTP 200 + success, но список продуктов пустой.
Возможные причины: нет USDT Flexible Savings в регионе, или coin фильтр слишком узкий.

## Решение (v10.2.2)
Для обеих бирж: сначала запрос с `coin=USDT`, потом без фильтра.
Если без фильтра есть продукты — фильтруем по coin в коде.
Добавлен item-level дебаг: productId, APR, minAmount для первого найденного.

## Паттерн
```
for coin_filter in [coin, ""]:
    # try with filter, then without
    items = api_call(coin_filter)
    if not coin_filter and items:
        items = [p for p in items if p["coin"] == coin]
```

## Связано с
- [[KuCoin Earn API требует три fallback endpoint пути]]
- [[ByBit Earn API категория FlexibleSaving пробовать три варианта]]
- [[earn auto-place после SELL свободный USDT уходит в Flexible Savings]]
