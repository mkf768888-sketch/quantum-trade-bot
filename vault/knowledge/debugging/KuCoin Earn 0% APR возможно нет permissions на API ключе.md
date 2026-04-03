---
tags: [bug, kucoin, earn, unresolved]
date: 2026-04-01
---
# KuCoin Earn 0% APR: возможно нет permissions на API ключе

## Симптом:
Команда /earn в Telegram показывает 0.0% APR, нет продуктов.

## Что пробовали:
1. Три fallback endpoint пути — [[KuCoin Earn API требует три fallback endpoint пути]]
2. Разные параметры (currency, productCategory)
3. Commit: `77a0bad`

## Вероятная причина:
API ключ KuCoin создан БЕЗ Earn permissions.
В настройках KuCoin API → нужно включить "Earn" или "Savings" permission.

## Как проверить:
1. Зайти на kucoin.com → API Management
2. Найти активный ключ
3. Проверить permissions → включить Earn/Savings
4. Пересоздать ключ если нужно → обновить env vars на Railway

## Статус: ✅ РАЗРЕШЁН (2026-04-02)
- KuCoin: включён permission "KuCoin Earn" в API Management
- ByBit: включён permission "Продукты Earn" в настройках ключа
- Ждём 15 мин (earn_monitor_loop) для проверки APR
