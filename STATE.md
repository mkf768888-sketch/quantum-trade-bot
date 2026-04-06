# STATE.md — Память между сессиями
> Обновлять после каждой значимой сессии. AI-агент читает это первым.
> Последнее обновление: 2026-04-07 (ночная сессия v10.19.x)
> Архитектура: GSD v2 Wave Execution

## Текущее состояние бота
- **Версия:** 10.19.3 (задеплоена, АКТИВНА)
- **Автопилот:** включён, Q≥77 (динамический через self-learning)
- **Биржи:** KuCoin Spot + ByBit Spot (dual-exchange routing)
- **DCI:** ✅ РАБОТАЕТ — auto-reinvest + VIP-fallback + capital check + FUND fix
- **KuCoin Lending:** ✅ КОД ГОТОВ v10.17.2 — LENDING_ENABLED=true (проверить Railway!)
- **Gate.io Lending:** ✅ КОД ГОТОВ v10.18.0 — ждёт API ключей (см. чеклист)
- **Snowball:** ✅ КОД ГОТОВ v10.14.0 — SNOWBALL_ENABLED=false (включить при F&G 30-65)
- **Funding Rate Arb:** ✅ КОД ГОТОВ v10.12.7 — FUNDING_ARB_ENABLED=false (ждёт капитала $30+)
- **Yield Router v2:** ✅ РАБОТАЕТ — каждый час + /yrouter команда
- **Telegram канал:** ✅ Duet формат — whale alerts, BUY сигналы, образовательные посты

## 🎉 Подтверждённые результаты
- **DCI +20.1267 USDT** (2026-04-05 21:06 → 2026-04-06 10:14) — ETH/USDT BuyLow
- **Earn Flex $107.35** активно работает — $0.0074/день
- **ByBit Earn $20.03** — tracked via yield estimation (v10.19.2 fix)
- **ByBit FUND $20.50** — теперь виден в /health и /router (v10.19.0 fix)
- Канал: 3 подписчика, Duet формат, whale alerts работают
- **Общий ByBit: ~$60.35** = UNIFIED $19.82 + FUND $20.50 + Earn $20.03

## Что сделано сегодня (2026-04-07, ночная сессия v10.19)
### Баги исправлены
- ByBit FUND $20.50 не виден в /router: добавлен `bybit_fund_usdt` в /health, /earn/status, /router (v10.19.0)
- ByBit Earn $20 показывал $0: fallback yield-based estimation (yesterdayYield × 365 / 2.06%) (v10.19.2)
- ByBit Earn API bug — `amount: "0"` для активных позиций: исправлен через yield estimation (v10.19.2)
- DCI "Amount out of range, min: 20": v10.19.3 — два исправления:
  1. `usdt_free = fund_usdt` в else-branch Step 3.6 → DCI использует FUND баланс ($20.50)
  2. `f"{amount:.2f}"` вместо `str(round(amount, 2))` → "20.00" а не "20.0"

### Новые фичи
- Новый эндпоинт `/api/bybit/balance` — полный breakdown FUND+UNIFIED+Earn+DCI (v10.19.0)
- `_bybit_fund_balance` глобал — кеш FUND баланса для portfolio display (v10.19.0)
- Версия правильно показывает 10.19.3 везде (было 10.9.4) (v10.19.0)

## Стратегический фокус
**Приоритет #1 — Пассивный доход** (DCI → Lending → Snowball → Funding Arb → Gate.io)
- Текущий капитал ~$60 ByBit + ~$250+ KuCoin, Earn Flex $107.35 в работе
- DCI настроен на Auto режим — BuyLow при F&G<60, SellHigh при F&G≥60
- DCI работает даже при F&G=13 (market-neutral, не блокируется Extreme Fear)
- Следующий DCI авто-цикл через ~60 мин после деплоя v10.19.3

## Чеклист действий для пользователя
```
[ ] Gate.io API ключи → Railway Variables (GATE_API_KEY, GATE_SECRET, GATE_LENDING_ENABLED=true)
[ ] Проверить LENDING_ENABLED=true в Railway Variables
[ ] Проверить DCI_MAX_INVEST_USDT=20 в Railway Variables (уже есть по дефолту)
[x] v10.19.3 задеплоен → проверить /health — version должна быть 10.19.3
[x] Проверить /router — должен показывать ByBit FUND $20.50
[ ] Подождать ~60 мин → DCI авто-цикл должен сработать — проверить /dci
```

## Passive Income Engine (v10.19.3)
| Продукт | Статус | APY | Railway var |
|---------|--------|-----|-------------|
| DCI ByBit BuyLow/SellHigh | ✅ Fixed, auto-reinvest | 100-900% | DCI_ENABLED=true |
| Double Win ByBit | ✅ Код + Railway var | 5-30% | DOUBLE_WIN_ENABLED=true |
| KuCoin Lending Pro | ✅ Код исправлен v10.17.2 | 10-50% APR | LENDING_ENABLED=true |
| Gate.io Lending | ✅ Новый v10.18.0 | 8-50% APR | GATE_LENDING_ENABLED=true + ключи |
| Funding Rate Arb | ✅ Код готов v10.12.7 | 10-150% | FUNDING_ARB_ENABLED=false |
| ByBit Snowball | ✅ Код готов v10.14.0 | 10-50% | SNOWBALL_ENABLED=false |
| Flex Savings KC+BB | ✅ Работает | 1-10% | EARN_ENABLED=true |
| Yield Router v2 | ✅ Активен (8 продуктов) | — | авто-каждый час |

## Wave Execution Status (GSD v2)
```
Completed: Wave 1A-1C (Earn+DCI+Lending+Snowball+FundingArb+YieldRouter)
           Wave 2A (Smart Filters+Security)
           Wave 2B partial (Whale Alerts + Duet Channel + News Engine)
           Wave 3A partial (Gate.io integration — 3я биржа!)
           Wave 3B (ByBit balance visibility + DCI capital fix — v10.19.x)
Current:   DCI работает корректно — ждём авто-цикл для подтверждения
Next:      Sub-accounts (KC+BB) → Binance integration → ATR trailing stop
Blocked:   Binance API ключи (нужно зарегистрировать)
           Gate.io API ключи (пользователь добавить в Railway)
```

## Масштабирование (следующие шаги)
```
Сейчас (~$60 BB + $250 KC):  DCI + Earn Flex + KC Lending
+Gate.io ключи:              +Gate.io Lending (8-50% APR)
+Sub-accounts:               КС sub1 + BB sub1 → ×2 прибыль, без нового кода
+Binance:                    4я биржа, Dual Investment аналог DCI
При $500+:                   Funding Rate Arb активен
При $1000+:                  Full CCXT multi-exchange routing
```

## Railway Variables актуальные
```
KUCOIN_API_KEY / KUCOIN_SECRET / KUCOIN_PASSPHRASE
BYBIT_API_KEY / BYBIT_API_SECRET
BOT_TOKEN / API_SECRET / ANTHROPIC_API_KEY / DEEPSEEK_API_KEY
RAILWAY_PUBLIC_DOMAIN / ADMIN_CHAT_IDS / ALERT_CHAT_ID
WHALE_CHANNEL_ID / DIGEST_CHANNEL_ID / DIGEST_ENABLED=true
RISK_PER_TRADE=0.08 / MIN_Q_SCORE=77 / MAX_OPEN_POSITIONS=2
DCI_ENABLED=true / DCI_DIRECTION=Auto / DCI_MIN_APY_PCT=15 / DCI_MAX_INVEST_USDT=20
DOUBLE_WIN_ENABLED=true / DOUBLE_WIN_MIN_INVEST=5 / DOUBLE_WIN_MAX_INVEST=20
FUNDING_ARB_ENABLED=false → при $30+ USDT на ByBit UNIFIED
LENDING_ENABLED=true / LENDING_MIN_APR=10.0 / LENDING_MAX_USDT=30 / LENDING_TERM_DAYS=7
SNOWBALL_ENABLED=false → при F&G 30-65
GATE_API_KEY= / GATE_SECRET= / GATE_LENDING_ENABLED=true ← ДОБАВИТЬ!
GATE_LENDING_MIN_APR=8.0 / GATE_LENDING_MAX_USDT=50 / GATE_LENDING_DAYS=10
```

## Telegram команды (полный список v10.19)
- `/balance` — балансы KC + BB FUND + BB UNIFIED + Earn + DCI (обновлено!)
- `/router` — Yield Router + BB FUND/UNIFIED разбивка
- `/gate` — Gate.io Lending статус + ставки
- `/dci`, `/dciplace` — DCI позиции + ручной запуск
- `/lending` — KuCoin Lending статус + ставки
- `/snowball` — ByBit Snowball позиции
- `/yrouter` — Yield Router v2: топ-8 продуктов с APY
- `/fundarb` — Funding Rate Arb сканер
- `/earn`, `/earnplace` — Flex Savings
- `/health` — полный system check (включает bybit_fund_usdt)
- `/digest` — ручной запуск дайджеста (для теста)

## Obsidian vault
- Vault: vault/ — 37+ заметок
- Последняя сессия: vault/sessions/2026-04-07 v10.19.x ByBit balance DCI fix.md
