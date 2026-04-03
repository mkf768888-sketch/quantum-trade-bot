---
tags: [atlas, routing, exchanges]
date: 2026-04-02
---
# Dual Exchange Routing: KuCoin и ByBit выбор по USDT балансу

## BUY routing
При получении сигнала BUY система проверяет USDT баланс на обеих биржах и покупает на той, где больше средств.

Логика (~строка 3335 server.py):
1. Получить balance KuCoin spot + ByBit spot
2. Сравнить USDT
3. BUY на бирже с максимальным USDT
4. Перед покупкой: [[earn redeem автоматический перед BUY если есть позиции в Earn]]

## SELL routing
При SELL система определяет биржу по полю `account` из БД:
- `spot` → KuCoin
- `bybit_spot` → ByBit

После SELL: [[earn auto-place после SELL свободный USDT уходит в Flexible Savings]]

## Арбитражный резерв
`ARB_RESERVE=$3` — всегда держим минимум для арбитража.
`SPOT_BUY_MIN=$5` — минимальная сумма для покупки.

Связано: [[small account algorithm ARB_RESERVE $3 TP 4% SL 2%]]
