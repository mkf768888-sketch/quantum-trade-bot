---
tags: [decision, cost, critical]
date: 2026-04-01
---
# Убрали все Claude fallback из торговли, чтобы не платить $20 в день

## Контекст:
DeepSeek бесплатный лимит закончился → 402 ошибки → каждый вызов fallback-ился на Claude Haiku → MiroFish делал десятки вызовов в час → $20/день Anthropic charges.

## Решение:
1. **ai_call_deepseek()**: все `return await ai_call_claude(...)` заменены на `return _no_ai`
2. **MiroFish**: rule-based RSI голосование когда нет AI
3. **Vision**: `VISION_ENABLED=false` по умолчанию
4. **Opus Gate**: auto-approve до $50 (без API вызова)

## Результат:
- Anthropic API cost: $20/день → $0/день
- Торговля продолжает работать (rule-based)
- Качество снижено, но можно восстановить через DeepSeek PayPal

## Коммит: `0909b9a`

Связано: [[DeepSeek 402 вызывал fallback на Claude Haiku и стоил $20 в день]], [[Opus Gate автоодобряет сделки до $50 без AI вызова]]
