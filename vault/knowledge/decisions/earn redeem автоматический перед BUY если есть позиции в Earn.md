---
tags: [decision, earn, trading-hook]
date: 2026-04-01
---
# Earn redeem: автоматический перед BUY, если есть позиции в Earn

## Принцип:
Если пришёл сигнал BUY, а USDT в Flexible Savings → автоматически вывести.

## Реализация (~строка 3335 server.py):
```python
if EARN_ENABLED and _earn_positions:
    _redeem = await earn_redeem_for_trading(_buy_exchange, _buy_usdt)
    if _redeem.get("redeemed", 0) > 0:
        log_activity(f"[earn] redeemed ${_redeem['redeemed']:.2f}")
        await asyncio.sleep(1)  # ждём зачисления
```

## Важно:
- Только Flexible Savings (мгновенный redeem)
- `asyncio.sleep(1)` после redeem — дать бирже зачислить
- Если redeem не удался → BUY продолжится с тем USDT что есть на балансе

## Связано:
- [[earn auto-place после SELL свободный USDT уходит в Flexible Savings]]
- [[dual exchange routing KuCoin и ByBit выбор по USDT балансу]]
