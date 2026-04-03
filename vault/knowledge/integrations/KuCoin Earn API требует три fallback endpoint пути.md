---
tags: [integration, kucoin, earn, api]
date: 2026-04-02
---
# KuCoin Earn API требует три fallback endpoint пути

KuCoin менял Earn API несколько раз. Единственный надёжный способ — пробовать три пути:

1. `/api/v1/earn/saving/products` (новый)
2. `/savings/products` (старый)
3. `/v3/earn/saving/products` (промежуточный)

Функция `kucoin_earn_get_savings_products(coin)` пробует все три по очереди.

## Аналогичные функции:
- `kucoin_earn_subscribe(product_id, amount)` → POST `/api/v1/earn/orders`
- `kucoin_earn_redeem(order_id, amount)` → DELETE `/api/v1/earn/orders`
- `kucoin_earn_get_hold_assets(coin)` → GET `/api/v1/earn/hold-assets`

## Важно:
- Если все три пути возвращают 0 продуктов или 0% APR → [[KuCoin Earn 0% APR возможно нет permissions на API ключе]]
- Параметры: `currency=USDT`, `productCategory=DEMAND` (Flexible Savings)

Связано: [[ByBit Earn API категория FlexibleSaving пробовать три варианта]]
