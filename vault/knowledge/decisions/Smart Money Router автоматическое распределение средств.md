---
tags: [architecture, trading, earn, automation, router]
date: 2026-04-03
status: deployed
version: v10.3.0
---
# Smart Money Router — автоматическое распределение средств

## Концепция
Деньги НИКОГДА не простаивают. Автоматическое распределение по приоритетам:
1. **Arb Reserve** ($3) — всегда ликвидно для арбитража (секунды, ROI 1-3%)
2. **Trade Reserve** ($5) — минимум для спот-торговли (часы, ROI 2-4%)
3. **Earn** (всё остальное) — Flexible Savings (APR ~0.79%+, мгновенный redeem)

## Ключевые функции
- `smart_money_route()` — основной алгоритм распределения
- `smart_money_pre_buy()` — auto-redeem из Earn перед BUY
- `smart_money_post_sell()` — auto-route в Earn после SELL
- `smart_money_router_loop()` — фоновый цикл каждые 2 мин

## Интеграции
- **auto_trade_cycle**: перед BUY вызывает `smart_money_pre_buy()` вместо `earn_redeem_for_trading()`
- **spot_monitor_loop**: после SELL вызывает `smart_money_post_sell()` вместо `earn_auto_place_idle()`
- **startup**: `smart_money_router_loop()` добавлен в asyncio tasks

## Telegram
- `/router` — полная статистика: портфель, распределение, история решений

## ENV переменные
- `ROUTER_ENABLED=true` — вкл/выкл
- `ROUTER_INTERVAL=120` — интервал проверки (секунды)
- `ROUTER_TRADE_RESERVE=5.0` — резерв для торговли
- `ROUTER_EARN_THRESHOLD=2.0` — минимум для Earn

## Связанные заметки
- [[Earn поиск продуктов без coin фильтра как fallback]]
- [[ByBit Earn subscribe пробовать UNIFIED потом FUND]]
