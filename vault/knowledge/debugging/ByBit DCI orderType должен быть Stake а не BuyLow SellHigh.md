---
tags: [bybit, dci, debugging, api, earn]
date: 2026-04-05
version: v10.9.23
severity: critical
---

# ByBit DCI: orderType должен быть "Stake", не "BuyLow"/"SellHigh"

## Проблема
ByBit Advanced Earn API (`POST /v5/earn/advance/place-order`) для DCI (DualAssets)
возвращал цепочку ошибок при неправильном формате тела запроса.

## Итеративный квест ошибок

| Попытка | Что попробовали | Ошибка ByBit |
|---|---|---|
| v10.9.19 | `orderType: "BuyLow"` или `"SellHigh"` | `Invalid parameter: order_type` |
| v10.9.21 | Убрали `orderType` полностью | `Invalid parameter: order_type` (required!) |
| v10.9.22 | `orderType: "Stake"` + `selectPrice` на верхнем уровне | `dual_assets_extra is required` |
| v10.9.23 | `orderType: "Stake"` + `dualAssetsExtra: {selectPrice, apyE8}` | ✅ |

## Правильная структура (v10.9.23)
```python
body = {
    "category": "DualAssets",
    "productId": str(product_id),
    "coin": coin,
    "amount": str(round(amount, 8)),
    "orderType": "Stake",           # ОБЯЗАТЕЛЬНО "Stake" для всех earn продуктов
    "accountType": "FUND",          # ОБЯЗАТЕЛЬНО (fallback: "UNIFIED")
    "orderLinkId": order_link_id,
    "dualAssetsExtra": {            # ОБЯЗАТЕЛЬНО nested object для DCI
        "selectPrice": str(select_price),
        "apyE8": str(apy_e8),
    },
}
```

## Ключевые инсайты
- `orderType` у ByBit earn = тип операции (Stake/Redeem), НЕ направление (BuyLow/SellHigh)
- Направление DCI кодируется в `selectPrice`: ниже рынка = BuyLow, выше = SellHigh
- `dualAssetsExtra` — обязательный nested объект, нельзя выносить поля на верхний уровень
- Fallback: если FUND не работает → retry с `accountType: "UNIFIED"`

## Применимо к Double Win тоже
Тот же паттерн: `orderType: "Stake"`, `accountType: "FUND"`, категория `"DoubleWin"`.

## Связанные заметки
- [[KuCoin DCI endpoint 400100 официально недоступен]]
