---
tags: [atlas, architecture]
date: 2026-04-02
---
# Архитектура: один файл server.py, 7000+ строк, FastAPI

Весь проект — один монолит `server.py` на FastAPI + uvicorn.
Деплой на Railway (auto-deploy из GitHub main).

## Основные секции (порядок в файле):
1. **Imports + Config** (~строки 1-200): env vars, API keys, constants
2. **Database** (~200-400): PostgreSQL через asyncpg
3. **Exchange APIs** (~400-870): KuCoin + ByBit REST клиенты
4. **Earn Engine** (~870-1350): [[KuCoin Earn API требует три fallback endpoint пути]], [[ByBit Earn API категория FlexibleSaving пробовать три варианта]]
5. **Cross-Exchange Arbitrage** (~1350-1800): арбитраж между биржами
6. **AI Layer** (~1800-2300): [[DeepSeek единственный AI провайдер в торговом цикле]], [[MiroFish rule-based RSI fallback когда нет DeepSeek]]
7. **MiroFish Council** (~2300-3200): 15 AI-агентов, голосование
8. **Trading Logic** (~3200-4500): BUY/SELL routing, [[dual exchange routing KuCoin и ByBit выбор по USDT балансу]]
9. **Spot Monitor** (~4500-5500): основной цикл мониторинга позиций
10. **Telegram Bot** (~5500-6500): все /команды
11. **FastAPI endpoints** (~6500-7000): /api/*, health check
12. **Startup** (~7000+): asyncio tasks, uvicorn run

## Ключевые env vars:
- `KUCOIN_API_KEY/SECRET/PASSPHRASE` — KuCoin
- `BYBIT_API_KEY/SECRET` — ByBit
- `DEEPSEEK_API_KEY` — AI (единственный!)
- `EARN_ENABLED=true` — Earn Engine
- `VISION_ENABLED=false` — [[VISION_ENABLED false по умолчанию для экономии]]
- `DATABASE_URL` — PostgreSQL на Railway

## Версия: v10.1.0
