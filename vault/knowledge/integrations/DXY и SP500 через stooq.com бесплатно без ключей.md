---
tags: [macro, dxy, sp500, stooq, free-api, mirofish, v10.10]
date: 2026-04-05
version: v10.10.0
---

# DXY и S&P500 через stooq.com — бесплатно, без API ключей

## Зачем
Агент `"Макро-стратег"` в MiroFish описан как "смотрит на DXY, ставки ФРС, корреляция с S&P500",
но до v10.10 реальных данных не получал — летел вслепую.

## API
```
DXY:   https://stooq.com/q/l/?s=dxy.fx&f=sd2t2ohlcv&h&e=csv
S&P500: https://stooq.com/q/l/?s=%5Espx&f=sd2t2ohlcv&h&e=csv
```

## Формат ответа (CSV)
```
Symbol,Date,Time,Open,High,Low,Close,Volume
DXY.FX,2026-04-05,00:00:00,104.21,104.45,103.98,104.32,0
```
Берём `Close` = 5-й столбец (индекс 4) из первой строки данных.

## Реализация в fetch_macro_context()
```python
r_dxy = await s.get("https://stooq.com/q/l/?s=dxy.fx&f=sd2t2ohlcv&h&e=csv",
                     timeout=aiohttp.ClientTimeout(total=6))
csv_text = await r_dxy.text()
vals = csv_text.strip().split("\n")[1].split(",")
dxy_val = round(float(vals[4]), 2)
result["dxy"] = dxy_val
result["dxy_signal"] = "bearish_usd" if dxy_val < 100 else "neutral" if dxy_val < 104 else "strong_usd"
```

## Сигнал DXY
| Значение | Сигнал | Значение для крипто |
|---|---|---|
| < 100 | `bearish_usd` | Доллар слабый → крипто бычий |
| 100–104 | `neutral` | Нейтрально |
| ≥ 104 | `strong_usd` | Доллар сильный → крипто медвежий |

## Где используется
1. `market_ctx` в `mirofish_simulate()` — агенты видят: `DXY=104.32 (strong_usd), S&P500=5421.03`
2. `/health` команда: `🌍 Macro: DXY=104.32 | S&P=5421.03`
3. `db.save_macro_snapshot()` extra dict

## Кэш
15 минут (общий с остальным macro context).

## Fallback
```python
except Exception as e_dxy:
    log_activity(f"[macro] stooq DXY timeout: {e_dxy}")
    result["dxy"] = None  # никогда не крашит основную функцию
```

## Лог в норме
```
[macro] BTC dom=56.2% MCap=$3.1T ETH/BTC=0.039 DXY=104.32 S&P=5421.03
```
