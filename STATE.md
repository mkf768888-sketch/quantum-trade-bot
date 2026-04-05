# STATE.md — Память между сессиями
> Обновлять после каждой значимой сессии. AI-агент читает это первым.
> Последнее обновление: 2026-04-05
> Архитектура: GSD v2 Wave Execution

## Текущее состояние бота
- **Версия:** 10.12.0 (deployed на Railway)
- **Автопилот:** включён, Q≥77 (динамический через self-learning)
- **Арбитраж:** ARB_EXEC_ENABLED=False (hardcoded off — баланс <$500), уведомления работают
- **Биржи:** KuCoin Spot + ByBit Spot (dual-exchange routing)
- **Фьючерсы:** неактивны (малый баланс)
- **MAX_OPEN_POSITIONS:** 2

## Параметры безопасности (v10.11.5+)
- ADMIN_CHAT_IDS: настроен в Railway Variables ✅
- AUTHORIZED_CHAT_IDS: работает, неавторизованные молча отклоняются
- Webhook auth: использует RAILWAY_PUBLIC_DOMAIN, не Host header
- /sell all + /reset_stats: требуют подтверждения inline keyboard

## Wave Execution Status (GSD v2)
```
Completed: Wave 1A (Earn Engine), Wave 1A+ (DCI ByBit), Security Audit, Wave 2A (Smart Filters)
Current Wave: v10.12.0 — Wave 2A deployed + H-fixes (arb lock, fee)
Next Wave: Wave 2B (backtesting + /winrate) → Wave 3A (CCXT) → Wave 5 (Design)
Blocked: Binance/OKX API keys (Wave 3A multi-exchange)
```

## Earn Engine (v10.11+)
- KuCoin FlexSaving: работает, пробует 3 endpoint'а (DEMAND/SAVING/без фильтра)
- ByBit Earn: Flexible Savings работает
- DCI (Dual Currency Investment): исправлен precision error (round 8→2), исправлен auto-transfer ($41 в Funding)
- Smart Money Router: авто-редим перед BUY, авто-инвест после SELL

## Торговая логика v10.12.0
- **Фильтры BUY** (в порядке применения):
  1. Q-Score ≥ MIN_Q_SCORE (динамический, self-learning)
  2. TA confirmations ≥ 2 (MACD/BB/Stoch/ADX/OBV)
  3. Volume filter: vol_ratio ≥ 0.65 (объём не упал >35%) ← NEW v10.12
  4. 4h trend: EMA7 > EMA14 на 4h свечах (30min кэш) ← NEW v10.12
  5. Per-symbol cooldown: 4h между покупками одного символа
  6. F&G ≥ 8 (contrarian mode, блок при Extreme Fear)
  7. MiroFish veto: <75% агентов SELL
  8. Opus Gate: сделки >$15
- **Выходы:**
  - Partial Exit TP1: продаём 50% при первом TP (4%), трейлим остаток ← NEW v10.12
  - TP2: 6% (после partial exit)
  - Trail: TRAIL_TRIGGER=2%, TRAIL_PCT=1%
  - SL: 2%, MaxLoss: 5%, Stale: 12h/48h
- **Арбитраж:** asyncio.Lock (было bool, H-06 fix), FEE=0.999 (KC taker 0.1%, H-07 fix)
- **ARB_MIN_PROFIT_PCT:** 0.35% (выше 3×fee=0.3%)

## Railway Variables актуальные
```
KUCOIN_API_KEY / KUCOIN_SECRET / KUCOIN_PASSPHRASE
BYBIT_API_KEY / BYBIT_API_SECRET
BOT_TOKEN / API_SECRET / ANTHROPIC_API_KEY / DEEPSEEK_API_KEY
RAILWAY_PUBLIC_DOMAIN / TG_WEBHOOK_SECRET
ADMIN_CHAT_IDS=<твой_chat_id>
RISK_PER_TRADE=0.08 / MIN_Q_SCORE=77 / MAX_OPEN_POSITIONS=2
ARB_RESERVE_USDT=3 / SPOT_BUY_MIN_USDT=5
DOUBLE_WIN_ENABLED=? (рекомендую включить после проверки DCI)
```

## Активные направления
| Направление | Статус | Версия |
|------------|--------|--------|
| Dual-Exchange торговля | ✅ Активно | v10.0+ |
| Smart Trading v2 (фильтры) | ✅ Deployed | v10.12.0 |
| Earn Engine (KC+BB) | ✅ Активно | v10.11+ |
| DCI ByBit | ✅ Исправлен (precision, auto-transfer) | v10.11.4 |
| Security Hardening | ✅ Complete (11 критических) | v10.11.5 |
| Wave 3A CCXT | 🔒 Заблокировано (нет Binance keys) | — |
| Wave 5 Design | ⏳ Ожидает | — |

## Ближайшие задачи
1. Проверить DCI placing (/dciplace — есть $41 в Funding)
2. Включить DOUBLE_WIN_ENABLED=true в Railway
3. Мониторить vol_ratio + 4h фильтры в логах (первые несколько часов)
4. Wave 2B: backtesting + /winrate команда
5. Wave 3A когда появятся API ключи Binance/OKX

## Obsidian vault
- Vault: vault/ — 20+ заметок, wiki-ссылки
- Текущие приоритеты: vault/00-home/текущие приоритеты.md
- Решения: vault/knowledge/decisions/
