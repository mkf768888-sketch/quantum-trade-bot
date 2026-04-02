---
tags: [home, index]
date: 2026-04-03
---
# QuantumTrade AI — Knowledge Vault

## Архитектура
- [[архитектура проекта один файл server.py 7000+ строк FastAPI]]
- [[dual exchange routing KuCoin и ByBit выбор по USDT балансу]]
- [[MiroFish v3 это 15 AI-агентов голосующих за BUY SELL HOLD]]

## Интеграции
- [[KuCoin Earn API требует три fallback endpoint пути]]
- [[ByBit Earn API категория FlexibleSaving пробовать три варианта]]
- [[DeepSeek единственный AI провайдер в торговом цикле]]

## Ключевые решения
- [[убрали все Claude fallback из торговли чтобы не платить $20 в день]]
- [[MiroFish rule-based RSI fallback когда нет DeepSeek]]
- [[Opus Gate автоодобряет сделки до $50 без AI вызова]]
- [[small account algorithm ARB_RESERVE $3 TP 4% SL 2%]]
- [[earn auto-place после SELL свободный USDT уходит в Flexible Savings]]
- [[Smart Money Router автоматическое распределение средств]]
- [[ByBit Earn subscribe пробовать UNIFIED потом FUND]]
- [[Earn поиск продуктов без coin фильтра как fallback]]

## Баги и фиксы
- [[LunarCrush 429 death spiral кеш никогда не заполняется при rate limit]]
- [[pandas-ta не ставится на Python 3.11 нужен pandas-ta-classic]]
- [[KuCoin Earn 0% APR возможно нет permissions на API ключе]]
- [[DeepSeek 402 вызывал fallback на Claude Haiku и стоил $20 в день]]
- [[VISION_ENABLED false по умолчанию для экономии]]

## Паттерны
- [[earn monitor loop фоновая задача каждые 15 минут]]

## Текущие приоритеты
→ см. [[текущие приоритеты]]
