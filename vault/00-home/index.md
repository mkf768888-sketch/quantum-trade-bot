---
tags: [home, index]
date: 2026-04-07
version: v10.19.3
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
- [[ByBit Double Win structured earn product]] ← NEW v10.10
- [[DXY и SP500 через stooq.com бесплатно без ключей]] ← NEW v10.10
- [[instar persistent agent с Telegram и scheduling]]
- [[GitHub репозитории для Claude Code супер-дизайнера]]

## Ключевые решения
- [[убрали все Claude fallback из торговли чтобы не платить $20 в день]]
- [[MiroFish rule-based RSI fallback когда нет DeepSeek]]
- [[Opus Gate автоодобряет сделки до $50 без AI вызова]]
- [[small account algorithm ARB_RESERVE $3 TP 4% SL 2%]]
- [[earn auto-place после SELL свободный USDT уходит в Flexible Savings]]
- [[earn redeem автоматический перед BUY если есть позиции в Earn]]
- [[Smart Money Router автоматическое распределение средств]]
- [[ByBit Earn subscribe пробовать UNIFIED потом FUND]]
- [[Earn поиск продуктов без coin фильтра как fallback]]
- [[DeepSeek оплата через PayPal с помощью товарища]]
- [[2026-04-06-APR-normalization-KuCoin]] ← v10.16.3

## Баги и фиксы
- [[LunarCrush 429 death spiral кеш никогда не заполняется при rate limit]]
- [[pandas-ta не ставится на Python 3.11 нужен pandas-ta-classic]]
- [[KuCoin Earn 0% APR возможно нет permissions на API ключе]]
- [[DeepSeek 402 вызывал fallback на Claude Haiku и стоил $20 в день]]
- [[VISION_ENABLED false по умолчанию для экономии]]
- [[Smart Money Router двойное резервирование tradeable=0]]
- [[ByBit DCI orderType должен быть Stake а не BuyLow SellHigh]] ← v10.9.23
- [[KuCoin DCI endpoint 400100 официально недоступен]] ← v10.9.22
- [[ByBit DCI orderDirection обязателен в теле запроса]] ← v10.10.1
- [[Invalid-Date-activity_log-ts-timezone]] ← v10.16.3

## Паттерны
- [[earn monitor loop фоновая задача каждые 15 минут]]
- [[Q-Score auto-tune еженедельная самонастройка порога]] ← NEW v10.10

## Пассивный доход
- [[DCI стратегия фокус на пассивный доход при малом капитале]]
- [[Funding Rate Arb дельта-нейтральная стратегия сбора ставок]]
- [[VIP-only DCI продукты надо пропускать по ошибке]]
- [[KuCoin Lending margin lending 10-50% APR авто-размещение]] ← v10.13.0
- [[ByBit Snowball range-bound product только при боковом рынке F&G 25-70]] ← v10.14.0
- [[Yield Router v2 сравнение 7 продуктов с режим-коэффициентами]] ← v10.14.0
- [[Gate.io 3-я биржа HMAC-SHA512 lending auto-place]] ← NEW v10.18.0

## Квантовые технологии
- [[Amazon Braket IonQ Forte-1 квантовые мощности для Q-Score оптимизации]] ← NEW v10.18.2

## Telegram Channel
- [[Duet Channel формат новичок и про блоки Whale Alerts BUY сигналы]] ← NEW v10.17.0
- [[News Engine RSS CoinDesk CoinTelegraph Decrypt Polymarket дайджест]] ← NEW v10.18.2

## Баги и фиксы
- [[LunarCrush 429 death spiral кеш никогда не заполняется при rate limit]]
- [[pandas-ta не ставится на Python 3.11 нужен pandas-ta-classic]]
- [[KuCoin Earn 0% APR возможно нет permissions на API ключе]]
- [[DeepSeek 402 вызывал fallback на Claude Haiku и стоил $20 в день]]
- [[VISION_ENABLED false по умолчанию для экономии]]
- [[Smart Money Router двойное резервирование tradeable=0]]
- [[ByBit DCI orderType должен быть Stake а не BuyLow SellHigh]] ← v10.9.23
- [[KuCoin DCI endpoint 400100 официально недоступен]] ← v10.9.22
- [[ByBit DCI orderDirection обязателен в теле запроса]] ← v10.10.1
- [[Invalid-Date-activity_log-ts-timezone]] ← v10.16.3
- [[FUND UNIFIED ping-pong earn_monitor_loop 4ч кулдаун фикс]] ← NEW v10.17.1
- [[Risk агент total_usdt вместо available_usdt неверный ключ]] ← NEW v10.17.3
- [[KuCoin Lending ищет только main надо main+trade аккаунты]] ← NEW v10.17.2
- [[ByBit Earn amount всегда 0 в API yield estimation workaround]] ← NEW v10.19.2
- [[DCI capital должен быть из FUND а не UNIFIED account]] ← NEW v10.19.3

## Сессии
- [[2026-04-01 earn engine и cost protection]]
- [[2026-04-02 obsidian vault и roadmap update]]
- [[2026-04-03 v10.2.2 LunarCrush backoff и Earn debug]]
- [[2026-04-03 v10.9.4 command center и двойное резервирование]]
- [[2026-04-05 v10.9-v10.10 DCI финализация и три апгрейда]]
- [[2026-04-06 v10.12.2-v10.12.6 DCI fix chain и passive income focus]]
- [[2026-04-06 v10.13-v10.14 passive income suite завершён]]
- [[2026-04-06-v10.16-audit-ui]] — v10.16.x аудит и UI апгрейд
- [[2026-04-07 v10.17-v10.18.2 duet channel gate.io quantum]]
- [[2026-04-07 v10.19.x ByBit balance DCI fix]] ← NEW v10.19.3

## Текущие приоритеты
→ см. [[текущие приоритеты]]
