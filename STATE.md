# STATE.md — Память между сессиями
> Обновлять после каждой значимой сессии. AI-агент читает это первым.
> Последнее обновление: 2026-04-01
> Архитектура: GSD v2 Wave Execution

## Текущее состояние бота
- **Версия:** 10.0.0 (deployed, dual-exchange trading live)
- **Автопилот:** включён, Q>77 (динамический порог через self-learning)
- **Арбитраж:** межбиржевой KuCoin↔ByBit включён, треугольный включён
- **Портфель:** ~$45.5 (KuCoin ~$7.5 спот + ByBit ~$38 спот)
- **Фьючерсы:** неактивны (малый баланс)
- **MAX_OPEN_POSITIONS:** 2 (защита от drain)
- **Fear & Greed:** мониторится в реальном времени, блок при <15

## Wave Execution Status (GSD v2)
```
Current Wave: 1 (Earn Engine — v10.1)
Wave Phase: PLANNING → ready to execute
In Progress: none
Blocked: none
Next Wave: 2 (Multi-Exchange CCXT)
Last Wave Completed: 0 (Foundation v10.0)
```

## Dual-Exchange Trading (v10.0)
- BUY: маршрутизация на биржу с большим USDT (ByBit или KuCoin)
- SELL: автоматическое определение биржи по account (spot / bybit_spot)
- Monitor: spot_monitor_loop проверяет обе биржи для TP/SL/Trail/Stale
- Fallback: если основная биржа даёт ошибку — автопереключение на вторую

## Параметры малого счёта (v10.0)
- ARB_RESERVE_USDT: $3 (было $15)
- SPOT_BUY_MIN_USDT: $5 (было $20)
- TP_PCT: 4% (было 6%)
- SL_PCT: 2%
- TRAIL_TRIGGER: 2% (было 2.5%)
- TRAIL_PCT: 1% (было 1.5%)
- Stale auto-sell: 12 часов без движения >1.5%

## Активные направления (v10.1+)
| Направление | Статус | Агент | Волна |
|------------|--------|-------|-------|
| Earn Engine | Планирование | earn-strategist | Wave 1 |
| Multi-Exchange | Ожидание API ключей | wave-orchestrator | Wave 2 |
| Polymarket | Исследование | polymarket-trader | Wave 3 |
| Design System | Готов к внедрению | design-system | Wave 4 |
| AI/ML | Будущее | wave-orchestrator | Wave 4-5 |

## Ключевые решения (не менять без обсуждения)
1. **Один файл server.py** — сознательное решение, не дробить на модули
2. **Q-Score порог 77** — высокий, self-learning корректирует ±5
3. **MAX_OPEN_POSITIONS=2** — защита от drain всего USDT в монеты
4. **RISK_PER_TRADE=0.08** — smart sizing для малых счетов (<$50: до 35%)
5. **CORS: ["*"]** — упрощено после проблем с middleware (v10.0)
6. **Без TG_WEBHOOK_SECRET** — удалён, блокировал все сообщения
7. **GSD Wave Execution** — волновая модель, state on disk, crash recovery

## История версий (краткая)
| Версия | Дата | Ключевые изменения |
|--------|------|---------------------|
| 10.0.0 | 31.03 | ByBit spot orders, dual-exchange routing, small-account algo |
| 10.0.1 | 01.04 | GSD v2 architecture, 8 agents, 4 commands, ROADMAP.md, HOWTO.md |
| 9.2.0 | 30.03 | MiroFish v3, cross-exchange arb, copy-trading, self-learning v2 |
| 9.0.0 | 30.03 | 15 MiroFish agents, sentiment pipeline, macro dashboard |
| 8.3.4 | 29.03 | Opus Gate, advanced TA, Reddit/LunarCrush sentiment |
| 7.5.2 | 29.03 | Security hardening, XSS fix, auth on debug endpoints |

## Известные проблемы
- Trade log в /tmp/ — теряется при редеплое (нужен Railway Volume на /data/)
- DeepSeek V3 API: 402 (бесплатный тир исчерпан), авто-fallback на Haiku
- DeepSeek V3.2 вышел — платежи не проходят (нужен PayPal)
- CORS: ["*"] — работает но не идеально для продакшена
- CoinGecko API — periodic errors in autodiag

## Блокеры
- Binance/OKX API ключи — нужны для Wave 2
- PayPal — нужен для DeepSeek V3.2
- Polygon wallet — нужен для Polymarket (Wave 3)

## Пользователь
- Закинет ~$100 для тестов (ожидается)
- Есть монеты на KuCoin: BTC, ETH (холд), мелочь продана
- Хочет видеть работающую прибыльную систему перед масштабированием

## Заметки для AI-агента
- При Fear & Greed < 15 бот НЕ ДОЛЖЕН торговать — это правильно
- Не понижать MIN_Q_SCORE ниже 65 — иначе будут убыточные сделки
- ByBit: marketUnit=quoteCoin для market buy (USDT, не base coin)
- bybit_sell_spot() возвращает {"success": bool, "error": str}
- sell_spot_to_usdt() возвращает {"success": bool, "msg": str}
- POST /api/setup-webhook (не GET!) — обновляет кнопку Mini App
- Волна 1 (Earn) не требует участия пользователя — можно начинать
