---
tags: [bybit, earn, api-bug, workaround]
date: 2026-04-07
version: v10.19.2
---
# ByBit Earn amount всегда 0 в API — yield estimation workaround

## Проблема
`/v5/earn/position` возвращает `amount: "0"` для ВСЕХ активных Simple Earn позиций.
Это API bug на стороне ByBit — `yesterdayYield` при этом возвращается корректно.

```json
{
  "productId": "...",
  "amount": "0",         ← всегда ноль!
  "yesterdayYield": "0.00113291"  ← корректно
}
```

## Workaround (v10.19.2)
Оценить principal через дневной доход и известный APR:

```
principal = yesterdayYield × 365 / APR
```

APR для ByBit USDT Simple Earn (Flexible) = **2.06%** (подтверждён эмпирически):
- Наблюдаемый yield: $0.00113/день на $20 → 0.00113 × 365 / 20 = 2.06%

```python
if _yield_day > 0:
    _est_principal = round(_yield_day * 365 / 0.0206, 2)
    if 1.0 <= _est_principal <= 10000.0:
        _it["amount"] = str(_est_principal)
        _it["_estimated"] = True
```

## Ограничения
- APR может меняться → оценка может отличаться на ±5-10%
- При изменении ставки нужно откалибровать константу
- Работает только если yesterdayYield > 0 (ненулевой вчерашний доход)

## Категории Earn
Пробовали: FlexibleSaving, Flexible, flexibleSaving, Simple, simple, FLEX, без категории.
ВСЕ возвращают amount="0". Это системный баг, не проблема категории.

## Связанные заметки
- [[ByBit Earn API категория FlexibleSaving пробовать три варианта]]
- [[ByBit DCI orderType должен быть Stake а не BuyLow SellHigh]]
