---
tags: [bybit, dci, fund, unified, capital]
date: 2026-04-07
version: v10.19.3
---
# DCI capital должен быть из FUND, а не UNIFIED account

## Структура ByBit аккаунтов
```
ByBit
├── FUND account ($20.50)    ← депозиты, вывод, DCI
├── UNIFIED account ($19.82) ← spot/futures торговля
└── Earn/Simple Earn ($20)   ← Flexible Savings
```

## Проблема (до v10.19.3)
`_dci_get_fund_balances()` несмотря на название запрашивал **UNIFIED** аккаунт.
В `dci_auto_place_idle()` Step 3.6 проверялось: если FUND достаточен → не нужен трансфер.
Но `usdt_free` оставался = UNIFIED ($19.82), а не FUND ($20.50).

Расчёт capital: `min(19.82 * 0.8, 20.0)` = 15.856 → max с min_amount 20 = 20.0

Результат: ByBit получал amount="20.0" → "Amount out of range, min: 20"

## Fix (v10.19.3)
В else-branch Step 3.6:
```python
else:
    log_activity(f"[dci] FUND=${fund_usdt:.2f} sufficient, no transfer needed")
    usdt_free = fund_usdt  # v10.19.3: DCI debits from FUND
```

Теперь: `capital = $20.50`, `invest_amount = max(min(16.40, 20.0), 20.0) = 20.0`

## Второй fix: формат числа
Python: `str(round(20.0, 2))` → `"20.0"` (не `"20.00"`)!
ByBit API требует строгий формат с двумя знаками: `"20.00"`.

Замена в `bybit_dci_place_order`:
```python
# Было:
"amount": str(round(amount, 2)),
# Стало:
"amount": f"{amount:.2f}",
```

## Принцип работы DCI
1. Funds → FUND account (через депозит)
2. DCI order дебетует с FUND
3. Если FUND пуст → нужен трансфер UNIFIED→FUND
4. После settlement → средства возвращаются в FUND

## Связанные заметки
- [[ByBit Earn amount всегда 0 в API yield estimation workaround]]
- [[VIP-only DCI продукты надо пропускать по ошибке]]
