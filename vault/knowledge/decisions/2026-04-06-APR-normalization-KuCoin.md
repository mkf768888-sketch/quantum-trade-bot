---
date: 2026-04-06
tags: [decision, apr, kucoin, normalize]
---

# APR нормализация KuCoin

## Проблема
KuCoin API возвращает APR в разных форматах:
- Иногда как decimal: `0.107` (10.7%)
- Иногда как процент: `10.7` (10.7%)

## Решение (v10.16.3)
```python
apr = apr_raw if apr_raw >= 1 else apr_raw * 100
```

Проверяем: если значение меньше 1, это decimal → умножаем на 100. Иначе уже процент.

## Применение
- `/portfolio` endpoint
- `/yrouter` yield calculation
- KuCoin Lending rate display

## Ссылки
- [[KuCoin Lending margin lending 10-50% APR авто-размещение]]
- [[Yield Router v2 сравнение 7 продуктов с режим-коэффициентами]]
