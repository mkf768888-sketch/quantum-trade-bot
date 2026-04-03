---
tags: [pattern, earn, background]
date: 2026-04-01
---
# earn_monitor_loop: фоновая задача каждые 15 минут

## Паттерн:
Все фоновые процессы запускаются как `asyncio.create_task()` при старте.

```python
# В startup:
asyncio.create_task(earn_monitor_loop())
asyncio.create_task(spot_monitor_loop())
asyncio.create_task(arb_monitor_loop())
```

## earn_monitor_loop():
Каждые 15 минут:
1. Проверить idle USDT на обеих биржах
2. Если idle > EARN_RESERVE_USDT → auto-place в Flexible Savings
3. Синхронизировать позиции (кэш)
4. Логировать статус

## Общий паттерн фоновых задач:
```python
async def my_loop():
    while True:
        try:
            await do_work()
        except Exception as e:
            log_activity(f"[loop] error: {e}")
        await asyncio.sleep(INTERVAL)
```

Всегда: try/except внутри цикла + sleep. Никогда не crash-ить весь сервер из-за одной задачи.
