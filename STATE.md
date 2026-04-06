# STATE.md — Память между сессиями
> Обновлять после каждой значимой сессии. AI-агент читает это первым.
> Последнее обновление: 2026-04-06
> Архитектура: GSD v2 Wave Execution

## Текущее состояние бота
- **Версия:** 10.16.5 (deployed на Railway)
- **Автопилот:** включён, Q≥77 (динамический через self-learning)
- **Арбитраж:** ARB_EXEC_ENABLED=False (hardcoded off — баланс <$500)
- **Биржи:** KuCoin Spot + ByBit Spot (dual-exchange routing)
- **DCI:** ✅ РАБОТАЕТ — auto-reinvest + VIP-fallback + capital check
- **Double Win:** ✅ ENABLED в Railway
- **Funding Rate Arb:** ✅ КОД ГОТОВ v10.12.7 — FUNDING_ARB_ENABLED=false (ждёт капитала)
- **KuCoin Lending:** ✅ КОД ГОТОВ v10.13.0 — LENDING_ENABLED=false (включить!)
- **Snowball:** ✅ КОД ГОТОВ v10.14.0 — SNOWBALL_ENABLED=false (включить при F&G 30-65)
- **Yield Router v2:** ✅ РАБОТАЕТ — каждый час логирует лучший продукт, /yrouter команда

## 🎉 Подтверждённые результаты
- **DCI +20.1267 USDT** (2026-04-05 21:06 → 2026-04-06 10:14) — ETH/USDT BuyLow
  Бот работает автономно, авто-реинвест активен

## Стратегический фокус
**Приоритет #1 — Пассивный доход** (DCI → Lending → Snowball → Funding Arb)
При ~$310 капитала DCI даёт в 3x больше чем spot trading.
Passive Income Suite полностью реализован (v10.13-v10.14).
Включить Lending + Snowball в ближайшие дни.

## Параметры безопасности (v10.11.5+)
- ADMIN_CHAT_IDS: настроен в Railway Variables ✅
- AUTHORIZED_CHAT_IDS: работает, неавторизованные молча отклоняются
- Webhook auth: использует RAILWAY_PUBLIC_DOMAIN
- /sell all + /reset_stats: требуют подтверждения inline keyboard

## Wave Execution Status (GSD v2)
```
Completed: Wave 1A (Earn Engine), Wave 1A+ (DCI ByBit full), Security Audit,
           Wave 2A (Smart Filters), DCI fix chain v10.12.2-v10.12.6,
           Wave 1B (KuCoin Lending Pro), Wave 1C (Snowball + Yield Router v2),
           Wave 2A Audit (v10.16 fixes + UI)
Current:   Wave 2B — ATR trailing stop + 30% coin allocation + Whale Alerts
Next:      Whale Alerts интеграция в Telegram, Balance $0 debug
Blocked:   Binance/OKX API keys (Wave 3A multi-exchange)
```

## Passive Income Engine (v10.14.0)
| Продукт | Статус | APY | Railway var |
|---------|--------|-----|-------------|
| DCI ByBit BuyLow/SellHigh | ✅ Активен, auto-reinvest | 100-900% | DCI_ENABLED=true |
| Double Win ByBit | ✅ Активен | 5-30% | DOUBLE_WIN_ENABLED=true |
| Funding Rate Arb | ✅ Код готов v10.12.7 | 10-150% | FUNDING_ARB_ENABLED=false |
| KuCoin Lending Pro | ✅ Код готов v10.13.0 | 10-50% APR | LENDING_ENABLED=false → включить |
| ByBit Snowball | ✅ Код готов v10.14.0 | 10-50% | SNOWBALL_ENABLED=false → при F&G 30-65 |
| Flex Savings KC+BB | ✅ Fallback | 1-10% | EARN_ENABLED=true |
| Yield Router v2 | ✅ Активен (скан) | — | авто-каждый час |

## DCI fix история (важно для отладки)
- "Invalid select price" → re-fetch quote перед placement (v10.12.2)
- "User not VIP" → VIP-fallback loop топ-5 кандидатов (v10.12.3)
- "Amount out of range" → capital sufficiency check + active position guard (v10.12.4)
- Auto-reinvest: `dci_check_settlements()` → 15с sleep → `dci_auto_place_idle()` (v10.12.5)
- Yield Router: порог редима из Flex повышен $5→$20 (v10.12.5)

## Funding Arb fix история (v10.12.7)
- Qty precision: `_round_perp_qty()` с `_BYBIT_PERP_QTY_STEPS` (ETH=0.01, BTC=0.001)
- Rollback: измеряем баланс ДО/ПОСЛЕ spot buy → продаём точное кол-во
- Persistence: `funding_arb_positions` table в PostgreSQL (переживает Railway restart)
- Funding tracking: ByBit `/v5/account/transaction-log` type=SETTLEMENT

## Snowball логика (важно!)
- category=Snowball в `/v5/earn/advance/product` (тот же паттерн что DCI/DoubleWin)
- Авто-место ТОЛЬКО при F&G 25-70 (sideways рынок)
- F&G < 25 или > 70 → пропуск (режим-зависимая защита)
- Principal-protected: USDT всегда возвращается

## Торговая логика v10.12.0 (вторичный приоритет)
- **Фильтры BUY:** Q-Score ≥ 77, TA ≥ 2, vol_ratio ≥ 0.65, 4h EMA trend, cooldown 4h, F&G ≥ 8, MiroFish veto, Opus Gate >$15
- **Выходы:** Partial Exit 50% at TP1(4%), trail TP2(6%), SL 2%, stale 12h/48h

## Railway Variables актуальные
```
KUCOIN_API_KEY / KUCOIN_SECRET / KUCOIN_PASSPHRASE
BYBIT_API_KEY / BYBIT_API_SECRET
BOT_TOKEN / API_SECRET / ANTHROPIC_API_KEY / DEEPSEEK_API_KEY
RAILWAY_PUBLIC_DOMAIN / ADMIN_CHAT_IDS / ALERT_CHAT_ID
RISK_PER_TRADE=0.08 / MIN_Q_SCORE=77 / MAX_OPEN_POSITIONS=2
DCI_ENABLED=true / DCI_DIRECTION=Auto / DCI_MIN_APY_PCT=15 / DCI_MAX_INVEST_USDT=20
DOUBLE_WIN_ENABLED=true / DOUBLE_WIN_MIN_INVEST=5 / DOUBLE_WIN_MAX_INVEST=20
FUNDING_ARB_ENABLED=false → включить при $30+ свободных на ByBit UNIFIED
FUNDING_ARB_MIN_RATE=0.0001 / FUNDING_ARB_MAX_USDT=30
LENDING_ENABLED=false → ВКЛЮЧИТЬ (готово v10.13.0)
LENDING_MIN_APR=10.0 / LENDING_MAX_USDT=30 / LENDING_TERM_DAYS=7
SNOWBALL_ENABLED=false → включить при F&G 30-65
SNOWBALL_MIN_APY=15.0 / SNOWBALL_MAX_USDT=20 / SNOWBALL_MIN_USDT=5
EARN_ENABLED=true / ARB_RESERVE_USDT=3 / SPOT_BUY_MIN_USDT=5
```

## Telegram команды (полный список v10.14.0)
- `/dci` — статус DCI позиций + авто-реинвест
- `/dciplace` — ручной запуск DCI placement
- `/lending` — KuCoin Lending статус + ставки
- `/snowball` — ByBit Snowball статус + позиции
- `/yrouter` — **Yield Router v2**: топ-7 продуктов с APY рейтингом
- `/fundarb` — Funding Rate Arb сканер
- `/earn`, `/earnplace` — Flex Savings
- `/health` — полный system check
- `/router` — Smart Money Router статус
- `/winrate` — win rate по монетам из PostgreSQL
- `/balance` — балансы KuCoin + ByBit + Earn + DCI

## Ближайшие задачи (Wave 2B, следующая сессия)
1. ATR trailing stop — динамический trail по волатильности (не фиксированный 1%)
2. Max portfolio allocation — не более 30% в одну монету, guard в spot_monitor_loop
3. Whale Alerts → Telegram канал (telegram_whale_detector_jobs)
4. Balance $0 debug — KuCoin/ByBit показывает $0 в overview но корректно в portfolio
5. Авто-ротация капитала в Yield Router v2 (не только скан, но и переложение)

## Obsidian vault
- Vault: vault/ — 35+ заметок
- Текущие приоритеты: vault/00-home/текущие приоритеты.md
- Последняя сессия: vault/sessions/2026-04-06-v10.16-audit-ui.md
- Новые знания:
  - vault/knowledge/decisions/2026-04-06-APR-normalization-KuCoin.md
  - vault/knowledge/debugging/Invalid-Date-activity_log-ts-timezone.md
