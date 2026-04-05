---
tags: [bybit, dci, api, debugging, fix]
date: 2026-04-05
version: v10.10.1
---
# ByBit DCI: orderDirection обязателен в теле запроса

## Проблема
`POST /v5/earn/advance/place-order` возвращал:
```
Invalid parameter: order_direction
```
Тело запроса было корректным по остальным полям (orderType="Stake", dualAssetsExtra, accountType="FUND"),
но поле `orderDirection` отсутствовало.

## Причина
Функция `bybit_dci_place_order(direction="BuyLow", ...)` принимала параметр `direction`,
но **никогда не клала его в тело запроса**. Логировала в success-сообщение — но в API не отправляла.

## Финальная структура тела запроса (рабочая)
```json
{
  "category": "DualAssets",
  "productId": "127734",
  "coin": "ETH",
  "amount": "8.80288",
  "orderType": "Stake",
  "orderDirection": "BuyLow",
  "accountType": "FUND",
  "orderLinkId": "dci_abc123",
  "dualAssetsExtra": {
    "selectPrice": "2037.35",
    "apyE8": "321275344"
  }
}
```

## Эволюция API (хронология квеста)
| Версия | Что добавили | Ошибка до |
|--------|-------------|-----------|
| v10.9.19 | Убрали dualAssetsExtra обёртку | Invalid parameter: order_type |
| v10.9.22 | orderType="Stake" + accountType="FUND" | dual_assets_extra is required |
| v10.9.23 | dualAssetsExtra nested object | (деплой) |
| v10.10.1 | orderDirection="BuyLow"/"SellHigh" | Invalid parameter: order_direction |

## Итоговые обязательные поля
- `category` = "DualAssets"
- `productId` = строка из get_quote
- `coin` = базовая монета (ETH, BTC и т.д.)
- `amount` = строка, USDT для BuyLow / монеты для SellHigh
- `orderType` = "Stake" (константа, не направление!)
- `orderDirection` = "BuyLow" или "SellHigh" (направление сделки)
- `accountType` = "FUND" (с fallback на UNIFIED)
- `orderLinkId` = уникальный идентификатор
- `dualAssetsExtra.selectPrice` = цена страйка из get_quote
- `dualAssetsExtra.apyE8` = APY*10^8 из get_quote

## Паттерн: два разных поля для разных вещей
- `orderType` = **тип операции** (Stake = разместить, как в FlexibleSaving)
- `orderDirection` = **направление DCI** (BuyLow = откупить дешевле, SellHigh = продать дороже)
Ранняя ошибка: думали orderType это и есть направление. Нет — это разные поля.
