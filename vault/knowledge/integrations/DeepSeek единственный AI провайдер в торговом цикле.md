---
tags: [integration, deepseek, ai, cost]
date: 2026-04-02
---
# DeepSeek — единственный AI провайдер в торговом цикле

После инцидента с $20/день (см. [[DeepSeek 402 вызывал fallback на Claude Haiku и стоил $20 в день]]) все Claude fallback были удалены.

## Текущая архитектура AI:
```
ai_call_deepseek() → DeepSeek API
  ├─ Если 200 OK → результат
  ├─ Если 402/429 → _deepseek_disabled_until + 1 час
  └─ Fallback → НЕТ Claude! → return _no_ai (пустой результат)
```

## Когда DeepSeek недоступен:
- MiroFish: [[MiroFish rule-based RSI fallback когда нет DeepSeek]]
- Opus Gate: [[Opus Gate автоодобряет сделки до $50 без AI вызова]]
- Vision: [[VISION_ENABLED false по умолчанию для экономии]]

## Как улучшить:
- Подключить PayPal к DeepSeek → стабильный доступ
- DeepSeek V3.2 с reasoning → качество торговли x3-5
- Стоимость: ~$5-10/мес при нашем объёме
