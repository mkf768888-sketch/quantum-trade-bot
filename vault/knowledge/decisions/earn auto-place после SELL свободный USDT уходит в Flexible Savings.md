---
tags: [decision, earn, trading-hook]
date: 2026-04-01
---
# Earn auto-place: после SELL свободный USDT уходит в Flexible Savings

## Принцип:
Каждый доллар должен работать 24/7. После продажи монеты USDT не должен лежать без дела.

## Реализация (~строка 4511 server.py):
```python
# v10.1: Auto-Earn — place freed USDT into Flexible Savings
if EARN_ENABLED:
    _earn_exch = "bybit" if _trade_acct == "bybit_spot" else "kucoin"
    asyncio.ensure_future(earn_auto_place_idle(_earn_exch))
```

## earn_auto_place_idle() логика:
1. Получить USDT баланс на бирже
2. Вычесть EARN_RESERVE_USDT ($3)
3. Если остаток > $1 → подписать в Flexible Savings с лучшим APR
4. Flexible = мгновенный redeem → деньги доступны для торговли

## Связано:
- [[earn redeem автоматический перед BUY если есть позиции в Earn]]
- [[KuCoin Earn API требует три fallback endpoint пути]]
- [[ByBit Earn API категория FlexibleSaving пробовать три варианта]]
