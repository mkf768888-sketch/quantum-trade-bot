---
tags: [bug, dependencies, railway, fixed]
date: 2026-04-03
---
# pandas-ta не ставится на Python 3.11 — нужен pandas-ta-classic

## Проблема
Railway использует Python 3.11. Оригинальный `pandas-ta` заброшен и не имеет колеса для 3.11+.
`pip install pandas-ta` → `ERROR: No matching distribution found`.

## Решение (v10.2.1)
Заменили на `pandas-ta-classic` (форк, поддерживает 3.11/3.12/3.13).
```python
try:
    import pandas_ta_classic as ta  # v10.2.1: Python 3.11+ compatible
except ImportError:
    import pandas_ta as ta  # fallback
```
В requirements.txt: `pandas-ta-classic` вместо `pandas-ta`.

## Дополнительно
- `ta.VERBOSE = False` — убирает спам "[X] Series has N rows..."
- Для MACD нужно >=26 свечей → запрашиваем 72ч (было 24ч, давало только 24 свечи)
