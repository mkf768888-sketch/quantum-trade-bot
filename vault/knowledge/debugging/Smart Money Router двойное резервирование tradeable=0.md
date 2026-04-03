---
tags: [debugging, critical, router, trade-cycle]
date: 2026-04-03
fixed_in: v10.9.4
---
# Smart Money Router: двойное резервирование → tradeable = $0

## Симптом
- Autopilot ВКЛ, но 0 сделок за 97+ часов
- Логи: `[cycle] ALL BUYS BLOCKED — KC=$21.00 BB=$60.00 (both below threshold)`
- Баланс спота растёт после пополнения, но Router сразу уводит в Earn

## Причина
Router и trade cycle оба вычитают одни и те же резервы:

```
Router: balance=$31 → arb_lock=$1 + trade_lock=$2 → earnable=$28 → в Earn
Спот после Router: $31 - $28 = $3 (остаток = arb+trade reserve)

Trade cycle: tradeable = spot_usdt - (ARB_RESERVE + TRADE_RESERVE) = $3 - $3 = $0
→ Блокировка!
```

## Фикс (v10.9.4)
```python
# Было (двойное вычитание):
_total_reserve = ROUTER_ARB_RESERVE_USDT + ROUTER_TRADE_RESERVE_USDT
_kc_tradeable = max(0, spot_usdt - _total_reserve)

# Стало (вычитаем только arb):
_arb_only_reserve = ARB_RESERVE_USDT  # $3
_kc_tradeable = max(0, spot_usdt - _arb_only_reserve)
```

## Дополнительно
- `ROUTER_TRADE_RESERVE` поднят $2 → $20 (Router оставляет больше в споте)
- Trade size floor: 8% × $18 = $1.44 → поднимается до $5 min (торговля разблокирована)

## Мораль
Никогда не вычитать резервы дважды. Router "держит" их в споте,
trade cycle не должен их вычитать снова.
