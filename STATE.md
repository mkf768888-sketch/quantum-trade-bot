# STATE.md — Память между сессиями
> Обновлять после каждой значимой сессии. AI-агент читает это первым.
> Последнее обновление: 2026-03-31

## Текущее состояние бота
- **Версия:** 10.0.0 (deployed, dual-exchange trading live)
- **Автопилот:** включён, Q>77 (динамический порог через self-learning)
- **Арбитраж:** межбиржевой KuCoin↔ByBit включён, треугольный включён
- **Портфель:** ~$45.5 (KuCoin ~$7.5 спот + ByBit ~$38 спот)
- **Фьючерсы:** неактивны (малый баланс)
- **MAX_OPEN_POSITIONS:** 2 (защита от drain)
- **Fear & Greed:** мониторится в реальном времени, блок при <15

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

## Ключевые решения (не менять без обсуждения)
1. **Один файл server.py** — сознательное решение, не дробить на модули
2. **Q-Score порог 77** — высокий, self-learning корректирует ±5
3. **MAX_OPEN_POSITIONS=2** — защита от drain всего USDT в монеты
4. **RISK_PER_TRADE=0.08** — smart sizing для малых счетов (<$50: до 35%)
5. **CORS: ["*"]** — упрощено после проблем с middleware (v10.0)
6. **Без TG_WEBHOOK_SECRET** — удалён, блокировал все сообщения

## История версий (краткая)
| Версия | Дата | Ключевые изменения |
|--------|------|---------------------|
| 10.0.0 | 31.03 | ByBit spot orders, dual-exchange routing, small-account algo |
| 9.2.0 | 30.03 | MiroFish v3, cross-exchange arb, copy-trading, self-learning v2 |
| 9.0.0 | 30.03 | 15 MiroFish agents, sentiment pipeline, macro dashboard |
| 8.3.4 | 29.03 | Opus Gate, advanced TA, Reddit/LunarCrush sentiment |
| 7.5.2 | 29.03 | Security hardening, XSS fix, auth on debug endpoints |

## Известные проблемы
- Trade log в /tmp/ — теряется при редеплое (нужен Railway Volume на /data/)
- DeepSeek V3 API: 402 (бесплатный тир исчерпан), авто-fallback на Haiku
- DeepSeek V3.2 вышел — платежи не проходят (нужен PayPal)
- CORS: ["*"] — работает но не идеально для продакшена

## Блокеры
- Нет критических. Бот торгует на обеих биржах.

## Следующие задачи (ROADMAP)
1. Наблюдение за dual-exchange trading — анализ первых результатов
2. Multi-exchange через CCXT (Binance, OKX, Gate.io)
3. Polymarket программная торговля (ставки на крипто-события)
4. Railway Volume для персистентного trade_log
5. DeepSeek V3.2 интеграция (когда PayPal будет)
6. Бэктестинг на исторических данных

## Заметки для AI-агента
- При Fear & Greed < 15 бот НЕ ДОЛЖЕН торговать — это правильно
- Не понижать MIN_Q_SCORE ниже 65 — иначе будут убыточные сделки
- ByBit: marketUnit=quoteCoin для market buy (USDT, не base coin)
- bybit_sell_spot() возвращает {"success": bool, "error": str}
- sell_spot_to_usdt() возвращает {"success": bool, "msg": str}
- POST /api/setup-webhook (не GET!) — обновляет кнопку Mini App
