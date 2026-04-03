---
tags: [decision, earn, bybit]
date: 2026-04-03
---
# ByBit Earn subscribe — пробовать UNIFIED потом FUND

## Контекст
ByBit хранит средства на UNIFIED аккаунте, но Earn API изначально использовал accountType=FUND.
Подписка не проходила — баланс есть на UNIFIED, а API ищет на FUND.

## Решение (v10.2.1)
```python
for account_type in ["UNIFIED", "FUND"]:
    res = await bybit_request("POST", "/v5/earn/place-order", {
        "accountType": account_type, ...
    })
```
Пробуем UNIFIED первым (где деньги), FUND как fallback.

## Связано с
- [[ByBit Earn API категория FlexibleSaving пробовать три варианта]]
- Реальный баланс: ~$38 USDT на UNIFIED
