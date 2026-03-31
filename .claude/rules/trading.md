# Trading Rules — QuantumTrade AI
> Правила торговой логики. AI-агент должен учитывать при изменении стратегий.
> Обновлено: v10.0.0 · 2026-03-31

## Параметры риска
- RISK_PER_TRADE: 0.08 (8% депо) — НЕ повышать выше 0.15
- MAX_LEVERAGE: 3x — НЕ повышать выше 5x
- MIN_Q_SCORE: 77 — НЕ опускать ниже 65
- COOLDOWN: 600 секунд — НЕ опускать ниже 300
- MAX_OPEN_POSITIONS: 2 — НЕ повышать выше 4 при балансе <$100

## Параметры малого счёта (v10.0, баланс <$50)
- ARB_RESERVE_USDT: $3 (минимум для арбитража)
- SPOT_BUY_MIN_USDT: $5 (минимальная сделка)
- TP_PCT: 0.04 (4%) — быстрая фиксация прибыли
- SL_PCT: 0.02 (2%) — тайтовый стоп
- TRAIL_TRIGGER: 0.02 (2%) — начало трейлинга
- TRAIL_PCT: 0.01 (1%) — шаг трейлинга
- Smart sizing: при <$50 risk до 35%, минимум $2 на сделку
- Stale auto-sell: 12 часов без движения >1.5% → освободить капитал

## Dual-Exchange (v10.0)
- BUY: маршрутизация на биржу с большим доступным USDT
- Fallback: если основная биржа ошибка → попытка на второй
- Account tracking: "spot" (KuCoin) или "bybit_spot" (ByBit)
- ByBit market buy: marketUnit=quoteCoin (qty в USDT, не в base coin)
- Мониторинг: spot_monitor_loop проверяет обе биржи параллельно

## Самообучение
- Порог Q-Score повышается при серии проигрышей (streak <= -3)
- Порог снижается при серии побед (streak >= 5, max -2)
- Per-symbol корректировка: winrate < 30% → +5, winrate > 70% → -2
- Минимум 5 сделок перед активацией корректировки
- Avoid list: символы с winrate <25% автоматически блокируются

## Защитные механизмы
- Fear & Greed < 15 → бот НЕ покупает (Extreme Fear block)
- MiroFish veto: если >=75% агентов против → отмена сделки
- Opus Gate: сделки >$15 подтверждаются Claude Opus
- При 3+ проигрышах подряд → автоповышение порога
- Whale dump signal → осторожность на LONG позициях
- Emergency: loss >5% → принудительное закрытие

## KuCoin специфика
- Фьючерсы: contractQty в лотах (не USDT!)
- Спот: minSize зависит от пары (проверять через API)
- Rate limits: 30 req/3s на приватные, 60 req/3s на публичные

## ByBit специфика
- V5 API: /v5/order/create (category=spot)
- Символы без дефиса: BTC-USDT → BTCUSDT
- Подпись: HMAC-SHA256, другой формат чем KuCoin
- bybit_sell_spot() возвращает {"success": bool, "error": str}
