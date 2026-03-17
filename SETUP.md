# QuantumTrade AI — Setup Guide

## Структура проекта

```
quantum-crypto-bot/
├── index.html          # Telegram Mini App (фронтенд)
├── backend/
│   ├── server.py       # FastAPI backend
│   ├── kucoin.py       # KuCoin API интеграция
│   ├── quantum.py      # Origin QC интеграция
│   ├── whale.py        # On-chain whale tracker
│   └── ml_engine.py    # Самообучающаяся модель
├── bot/
│   └── telegram_bot.py # Telegram Bot
└── SETUP.md
```

## 1. Telegram Bot

1. Создайте бота у @BotFather
2. Получите BOT_TOKEN
3. Настройте Mini App: /newapp → укажите URL хостинга

```bash
pip install python-telegram-bot aiohttp
```

```python
BOT_TOKEN = "YOUR_BOT_TOKEN"
MINI_APP_URL = "https://your-domain.com/index.html"
```

## 2. KuCoin API

Получите ключи на: https://www.kucoin.com/account/api

```python
KUCOIN_API_KEY = "your_api_key"
KUCOIN_SECRET = "your_secret"
KUCOIN_PASSPHRASE = "your_passphrase"
```

Эндпоинты:
- Spot: https://api.kucoin.com
- Futures: https://api-futures.kucoin.com

## 3. Origin QC API

URL: https://console.originqc.com.cn/en/apikey

```python
ORIGIN_QC_KEY = "your_quantum_key"
ORIGIN_QC_URL = "https://api.originqc.com.cn/v1"
```

Квантовые алгоритмы для анализа:
- QAOA для оптимизации портфеля
- VQE для анализа корреляций
- Quantum Random Walk для прогнозирования

## 4. Запуск backend

```bash
pip install fastapi uvicorn kucoin-python pandas numpy scikit-learn
uvicorn backend.server:app --host 0.0.0.0 --port 8000
```

## 5. Хостинг Mini App

Варианты деплоя:
- Vercel (рекомендуется): `vercel deploy`
- Nginx + SSL на VPS
- Cloudflare Pages

Mini App должен быть доступен по HTTPS!

## 6. Конфигурация переменных окружения

```env
BOT_TOKEN=
KUCOIN_API_KEY=
KUCOIN_SECRET=
KUCOIN_PASSPHRASE=
ORIGIN_QC_KEY=
WEBHOOK_URL=https://your-domain.com/webhook
RISK_PER_TRADE=0.02
MAX_LEVERAGE=10
```

## Архитектура потока данных

```
KuCoin API (цены, ордера)
         ↓
Origin QC (квантовый анализ) ← On-chain данные (whale tracker)
         ↓
ML Engine (самообучение) ← Исторические результаты
         ↓
Signal Generator (BUY/SELL/SHORT + confidence)
         ↓
Autopilot (автоисполнение через KuCoin API)
         ↓
Telegram Mini App (UI/уведомления)
```
