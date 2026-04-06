# STATE.md — Память между сессиями
> Обновлять после каждой значимой сессии. AI-агент читает это первым.
> Последнее обновление: 2026-04-06
> Архитектура: GSD v2 Wave Execution

## Текущее состояние бота
- **Версия:** 10.12.6 (deployed на Railway)
- **Автопилот:** включён, Q≥77 (динамический через self-learning)
- **Арбитраж:** ARB_EXEC_ENABLED=False (hardcoded off — баланс <$500)
- **Биржи:** KuCoin Spot + ByBit Spot (dual-exchange routing)
- **DCI:** ✅ РАБОТАЕТ — auto-reinvest + VIP-fallback + capital check
- **Double Win:** ✅ ENABLED в Railway
- **Funding Rate Arb:** ✅ КОД ГОТОВ — FUNDING_ARB_ENABLED=false (ждёт капитала)

## Стратегический фокус (изменён 2026-04-06)
**Приоритет #1 — Пассивный доход** (DCI → Funding Arb → Lending)
При ~$310 капитала DCI даёт в 3x больше чем spot trading.
Торговля остаётся, но уступает место passive income до роста капитала до $1000+.

## Параметры безопасности (v10.11.5+)
- ADMIN_CHAT_IDS: настроен в Railway Variables ✅
- AUTHORIZED_CHAT_IDS: работает, неавторизованные молча отклоняются
- Webhook auth: использует RAILWAY_PUBLIC_DOMAIN
- /sell all + /reset_stats: требуют подтверждения inline keyboard

## Wave Execution Status (GSD v2)
```
Completed: Wave 1A (Earn Engine), Wave 1A+ (DCI ByBit full), Security Audit,
           Wave 2A (Smart Filters), DCI fix chain v10.12.2-v10.12.6
Current:   Passive Income Focus — DCI auto-reinvest + Funding Rate Arb
Next:      KuCoin Lending Pro (Wave 1B) → Funding Arb live test → CCXT (Wave 3A)
Blocked:   Binance/OKX API keys (Wave 3A multi-exchange)
```

## Passive Income Engine (v10.12.6)
| Продукт | Статус | APY | Railway var |
|---------|--------|-----|-------------|
| DCI ByBit BuyLow/SellHigh | ✅ Активен, auto-reinvest | 450-850% | DCI_ENABLED=true |
| Double Win ByBit | ✅ Активен | 200-500% | DOUBLE_WIN_ENABLED=true |
| Funding Rate Arb | ✅ Код готов | 10-150% | FUNDING_ARB_ENABLED=false |
| Flex Savings KC+BB | ✅ Fallback | 1-10% | EARN_ENABLED=true |
| KuCoin Lending Pro | ⏳ Не реализован | 20-50% пики | — |

## DCI fix история (важно для отладки)
- "Invalid select price" → re-fetch quote перед placement (v10.12.2)
- "User not VIP" → VIP-fallback loop топ-5 кандидатов (v10.12.3)
- "Amount out of range" → capital sufficiency check + active position guard (v10.12.4)
- Auto-reinvest: `dci_check_settlements()` → 15с sleep → `dci_auto_place_idle()` (v10.12.5)
- Yield Router: порог редима из Flex повышен $5→$20 (v10.12.5)

## Торговая логика v10.12.0 (вторичный приоритет)
- **Фильтры BUY:** Q-Score ≥ 77, TA ≥ 2, vol_ratio ≥ 0.65, 4h EMA trend, cooldown 4h, F&G ≥ 8, MiroFish veto, Opus Gate >$15
- **Выходы:** Partial Exit 50% at TP1(4%), trail TP2(6%), SL 2%, stale 12h/48h
- **ARB:** asyncio.Lock, FEE=0.999 (KC taker 0.1%)

## Railway Variables актуальные
```
KUCOIN_API_KEY / KUCOIN_SECRET / KUCOIN_PASSPHRASE
BYBIT_API_KEY / BYBIT_API_SECRET
BOT_TOKEN / API_SECRET / ANTHROPIC_API_KEY / DEEPSEEK_API_KEY
RAILWAY_PUBLIC_DOMAIN / ADMIN_CHAT_IDS / ALERT_CHAT_ID
RISK_PER_TRADE=0.08 / MIN_Q_SCORE=77 / MAX_OPEN_POSITIONS=2
DCI_ENABLED=true / DCI_DIRECTION=Auto / DCI_MIN_APY_PCT=15 / DCI_MAX_INVEST_USDT=20
DOUBLE_WIN_ENABLED=true / DOUBLE_WIN_MIN_INVEST=5 / DOUBLE_WIN_MAX_INVEST=20
FUNDING_ARB_ENABLED=false → включить при $10+ свободных на ByBit
FUNDING_ARB_MIN_RATE=0.0001 / FUNDING_ARB_MAX_USDT=30
EARN_ENABLED=true / ARB_RESERVE_USDT=3 / SPOT_BUY_MIN_USDT=5
```

## Новые Telegram команды (v10.12.5-v10.12.6)
- `/winrate` — win rate по монетам из PostgreSQL с топ-5 лучших/худших
- `/fundarb` — сканер funding rates + статус открытых позиций
- POST `/api/telegram/notify` — внешние уведомления (quantum-bot-monitor)

## Ближайшие задачи (приоритет)
1. ✅ Проверить ♻️ авто-реинвест DCI в Telegram (после расчёта 07:59 UTC)
2. Включить `FUNDING_ARB_ENABLED=true` когда $10+ свободных на ByBit
3. `/fundarb` — проверить live ставки BTC/ETH/SOL
4. KuCoin Lending Pro — реализовать `kucoin_lending_auto_place()` (Wave 1B)
5. Wave 3A когда появятся API ключи Binance/OKX

## Obsidian vault
- Vault: vault/ — 25+ заметок
- Текущие приоритеты: vault/00-home/текущие приоритеты.md
- Последняя сессия: vault/sessions/2026-04-06 v10.12.2-v10.12.6...
