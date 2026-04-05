---
tags: [q-score, auto-tune, self-learning, trading, v10.10]
date: 2026-04-05
version: v10.10.0
---

# Q-Score Auto-tune — еженедельная самонастройка порога входа

## Проблема
`MIN_Q_SCORE = 77` захардкожен. `/analyze` собирает win rate по Q-диапазонам,
но бот не использует эти данные для самонастройки.

## Решение (v10.10.0)
Новая функция `auto_tune_q_threshold()` + DB запрос `get_best_q_threshold()`.

## Алгоритм
1. Получить win rate по каждому Q-диапазону (последние 30 дней)
2. Найти лучший диапазон: `total ≥ 10` И `win_rate > 55%` И `avg_pnl > 0`
3. Применить `q_min` из лучшего диапазона как новый порог
4. Safety check: `new_q = max(72, min(new_q, 90))`
5. Только если `|new_q - MIN_Q_SCORE| > 2` — иначе не трогать
6. Сдвинуть per-pair пороги пропорционально: `PAIR_Q_THRESHOLDS[pair] += delta`
7. Отправить Telegram уведомление

## Q-диапазоны в SQL
```sql
CASE
  WHEN q_score >= 85 THEN '85+' (q_min=85)
  WHEN q_score >= 80 THEN '80-84' (q_min=80)
  WHEN q_score >= 77 THEN '77-79' (q_min=77)
  WHEN q_score >= 74 THEN '74-76' (q_min=74)
  WHEN q_score >= 70 THEN '70-73' (q_min=70)
  ELSE '<70' (q_min=65)
```

## Триггер
```python
# В earn_monitor_loop, каждые 672 цикла (~7 дней)
# 4 цикла/час × 24ч × 7д = 672
if _earn_stats.get("_dci_cycle", 0) % 672 == 1:
    await auto_tune_q_threshold()
```

## Границы безопасности
- Никогда ниже **72** (was: hardcoded 77)
- Никогда выше **90**
- Требуется минимум 10 сделок в диапазоне
- WR > 55% обязательно
- Изменение только если дельта > 2 пункта

## Telegram уведомление
```
🎯 Q-Score автонастройка

77 → 80 (+3)

Данные за 30 дней:
  Диапазон: 80-84
  Win Rate: 67% (16/24 сделок)
  Средний PnL: $0.0234

Per-pair пороги сдвинуты на +3
```

## Лог
```
[autotune] ✅ Q_THRESHOLD: 77 → 80 (range=80-84 WR=67% n=24 avg_pnl=$0.0234)
[autotune] best range 77-79 (WR=52%, n=12) — delta ≤ 2, keeping Q=77
[autotune] no statistically valid range found — keeping Q=77
```

## Важно
- Изменение `MIN_Q_SCORE` происходит в памяти (global), при рестарте Railway — сбросится
- Сохранение в DB не реализовано (v10.11 backlog)
- Per-pair `PAIR_Q_THRESHOLDS` тоже только в памяти

## Связанные заметки
- [[earn monitor loop фоновая задача каждые 15 минут]]
