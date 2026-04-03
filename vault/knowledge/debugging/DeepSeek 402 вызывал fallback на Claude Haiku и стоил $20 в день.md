---
tags: [bug, cost, critical, resolved]
date: 2026-04-01
---
# DeepSeek 402 вызывал fallback на Claude Haiku и стоил $20 в день

## Симптом:
Два Anthropic инвойса по ~$10. Пользователь не понимал откуда расходы.

## Причина:
1. DeepSeek бесплатный лимит исчерпан → 402 Payment Required
2. `ai_call_deepseek()` имел fallback: `return await ai_call_claude(...)`
3. MiroFish вызывал 8 AI-запросов за раз, каждые ~10-30 минут
4. ВСЕ шли в Claude Haiku → десятки вызовов в час → $20/день

## Решение:
Полное удаление Claude из торгового цикла:
→ [[убрали все Claude fallback из торговли чтобы не платить $20 в день]]

## Коммит: `0909b9a`
## Статус: РАЗРЕШЁН — $0/день API cost

## Урок:
НИКОГДА не ставить Claude как fallback для high-frequency вызовов.
Даже Haiku при 100+ вызовах/час стоит дорого.
