---
tags: [decision, cost, trading]
date: 2026-04-01
---
# Opus Gate автоодобряет сделки до $50 без AI вызова

## Контекст:
Opus Gate — финальная проверка перед каждой сделкой. Раньше вызывал Claude Opus (самый дорогой) для оценки риска.

## Решение:
Если `amount_usdt < 50` → auto-approve без API вызова.
Наш весь портфель ~$45, поэтому ВСЕ сделки auto-approve.

```python
if amount_usdt < 50:
    return {"approved": True, "reason": "auto-approve (small account cost protection)", "model": "auto"}
```

## Важное уточнение:
Auto-approve = пропуск AI-проверки, НЕ увеличение количества сделок.
Без Opus Gate сделки просто проходят без expensive API call.
Раньше это стоило деньги (Opus API), теперь бесплатно.

Связано: [[убрали все Claude fallback из торговли чтобы не платить $20 в день]], [[small account algorithm ARB_RESERVE $3 TP 4% SL 2%]]
