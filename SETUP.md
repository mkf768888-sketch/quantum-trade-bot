# QuantumTrade AI Bot — Setup Guide

## Версия: v7.1.2

Торговый бот на FastAPI с Q-Score, квантовой оптимизацией (Wukong 180), Polymarket, Claude Vision и треугольным арбитражем.

---

## 🚀 Деплой на Railway

1. Форкни/загрузи репо на GitHub
2. Зайди на [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
3. Выбери репо `quantum-trade-bot`
4. Добавь все переменные окружения (см. ниже)
5. Railway сам запустит бота через `Procfile`

---

## ⚙️ Переменные окружения (Environment Variables)

### KuCoin API
| Переменная | Описание |
|---|---|
| `KUCOIN_API_KEY` | API ключ KuCoin |
| `KUCOIN_API_SECRET` | Секрет KuCoin |
| `KUCOIN_API_PASSPHRASE` | Пасфраза KuCoin |

### Telegram
| Переменная | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен Telegram-бота |
| `TELEGRAM_CHAT_ID` | ID чата для уведомлений |

### Anthropic (Claude Vision)
| Переменная | Описание |
|---|---|
| `ANTHROPIC_API_KEY` | API ключ Anthropic (для Claude Vision) |

### Origin QC (Wukong 180)
| Переменная | Описание |
|---|---|
| `ORIGIN_QC_TOKEN` | Токен для реального квантового чипа Wukong 180 (опционально) |

### Торговые параметры (опционально, есть дефолты)
| Переменная | Дефолт | Описание |
|---|---|---|
| `TEST_MODE` | `false` | `true` = бумажная торговля без реальных ордеров |
| `MIN_Q_SCORE` | `65` | Минимальный Q-Score для входа (глобальный) |
| `COOLDOWN` | `600` | Пауза между сделками по одной паре (секунды) |
| `LEVERAGE` | `5` | Плечо для фьючерсов |
| `RISK_PCT` | `0.25` | Доля баланса на одну сделку (0.25 = 25%) |
| `TP_PCT` | `0.05` | Take Profit (0.05 = 5%) |
| `SL_PCT` | `0.025` | Stop Loss (0.025 = 2.5%) |
| `CYCLE_INTERVAL` | `60` | Интервал торгового цикла (секунды) |

---

## 📊 Торгуемые пары

`BTC-USDT` · `ETH-USDT` · `SOL-USDT` · `BNB-USDT` · `XRP-USDT` · `AVAX-USDT`

### Per-pair Q-пороги (v7.1.2)
| Пара | Min Q-Score |
|---|---|
| BTC-USDT | 64 |
| ETH-USDT | 66 |
| SOL/BNB/XRP/AVAX | 65 |

---

## 🧠 Фичи

### Q-Score (квантовый скоринг)
Агрегирует сигналы из 30+ источников:
- Fear & Greed Index
- Polymarket (7 тематик, предиктивные рынки)
- Whale Alert (BTC, ETH, SOL, XRP, BNB)
- Claude Vision (AI-анализ графиков)
- Cross-ticker корреляции
- Origin QC Wukong 180 (квантовая оптимизация)

### Стратегии
- **Strategy A** — консервативная
- **Strategy B** — сбалансированная
- **Strategy C** — агрессивная (дефолт, оптимальна для медвежьего рынка)

### Треугольный арбитраж (v7.1.0)
Мониторинг 6 путей `USDT→ETH→BTC→USDT` на KuCoin.
Endpoint: `GET /api/arb/triangle`

---

## 🔗 API Endpoints

| Endpoint | Описание |
|---|---|
| `GET /api/positions` | Открытые позиции |
| `GET /api/bot-stats` | Статистика бота |
| `GET /api/logs` | Последние логи |
| `GET /api/settings` | Текущие настройки |
| `GET /api/arb/triangle` | Треугольный арбитраж |
| `POST /api/start` | Запустить бота |
| `POST /api/stop` | Остановить бота |

---

## 📁 Структура репо

```
quantum-trade-bot/
├── server.py          # Основной файл бота
├── requirements.txt   # Зависимости Python
├── Procfile           # Команда запуска для Railway
└── SETUP.md           # Этот файл
```

---

## 🔄 История версий

| Версия | Что нового |
|---|---|
| v7.1.2 | Per-pair Q-пороги, динамический баланс, Whale Alert → SOL/XRP/BNB |
| v7.1.1 | Фикс poly_events UnboundLocalError, get_cross_ticker NoneType |
| v7.1.0 | Треугольный арбитраж (6 путей, KuCoin, Telegram alerts) |
| v7.0.0 | Polymarket Q-Score v7.0 (7 тем, 30 сигналов, ±8 бонус) |
| v6.9.0 | Strategy C дефолт (5x leverage, TP 5%, SL 2.5%) |
| v6.8.0 | Фикс PnL, rich TG уведомления, cooldown 600s |
| v6.7.0 | MIN_Q_SCORE 78→65, эндпоинт настроек |
