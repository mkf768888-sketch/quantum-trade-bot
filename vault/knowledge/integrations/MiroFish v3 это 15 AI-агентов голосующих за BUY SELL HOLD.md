---
tags: [integration, mirofish, ai, trading]
date: 2026-04-02
---
# MiroFish v3: 15 AI-агентов голосующих за BUY/SELL/HOLD

MiroFish — совет из 15 AI-персон с разными стилями торговли.
Каждый анализирует монету и голосует: BUY, SELL или HOLD.

## Как работает:
1. Получаем TA-индикаторы (RSI, MACD, Bollinger, volume)
2. Формируем промпт с данными для каждой персоны
3. Отправляем в [[DeepSeek единственный AI провайдер в торговом цикле]]
4. Парсим голоса, считаем consensus
5. Если 60%+ за одно направление → сигнал

## Без DeepSeek:
Все 15 агентов голосуют rule-based:
- RSI < 30 → BUY
- RSI > 70 → SELL
- Иначе → HOLD

См. [[MiroFish rule-based RSI fallback когда нет DeepSeek]]

## Потребление:
Один вызов MiroFish = 8 параллельных API запросов к DeepSeek (не 15 — оптимизировано).
При бесплатном DeepSeek лимит быстро выбивался → 402 → fallback-катастрофа.
