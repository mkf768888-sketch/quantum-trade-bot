---
tags: [kucoin, dci, debugging, api, disabled]
date: 2026-04-05
version: v10.9.22
severity: info
---

# KuCoin DCI endpoint 400100 — официально недоступен

## Проблема
`GET /api/v1/struct-earn/dual/products` на KuCoin всегда возвращает:
```
code=400100 Invalid parameters
```
Даже без параметров.

## Попытки
1. С `?currency=USDT` → 400100
2. С `?investCurrency=USDT` → 400100
3. Без параметров → 400100

## Причина
Согласно официальной документации KuCoin (`kucoin-skills-hub`),
этот эндпоинт **официально недоступен** для публичного использования.

## Решение (v10.9.22)
Функция gracefully отключена с чётким логом:
```python
async def kucoin_dci_get_products(invest_currency: str = "USDT") -> list:
    """v10.9.22: KuCoin Structured Earn DCI API confirmed unavailable."""
    log_activity("[kc_dci] DCI API not available on KuCoin (400100 per official docs) — skipping")
    return []
```

## Следствие
Весь DCI трафик маршрутизируется только на ByBit.

## Не пытаться починить
Это не баг нашего кода. Endpoint недоступен на стороне KuCoin.
