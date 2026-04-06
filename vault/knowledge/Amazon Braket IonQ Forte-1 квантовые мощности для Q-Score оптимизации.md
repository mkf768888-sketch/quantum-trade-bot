---
tags: [quantum, braket, ionq, q-score, decision, future]
date: 2026-04-07
version: v10.18.2
status: исследование
---
# Amazon Braket IonQ Forte-1 — квантовые мощности для Q-Score

## Контекст
- AWS аккаунт: AlexITCompany (594677690580)
- Support кейс: #177528072800782 "Request IonQ Forte-1 QPU Access for Algorithmic Trading"
- Подан: 2026-04-04 05:32 UTC
- Статус: Reopened (AWS ответил)
- QuantumTrade AI уже содержит QAOA CPU-симулятор (заглушка)

## Что такое IonQ Forte-1
- Квантовый процессор IonQ на Amazon Braket
- 36 высококачественных кубитов (ion-trap технология)
- Лучшая точность среди публично доступных QPU
- Цена: ~$0.00035 за 1 квантовый гейт, ~$0.9 за задачу (минимум)
- Доступен через boto3 + amazon-braket-sdk

## Идея интеграции в QuantumTrade AI

### Текущий QAOA в проекте
```python
# server.py — CPU симулятор (строки ~900)
# QAOA = Quantum Approximate Optimization Algorithm
# Используется для оптимизации весов Q-Score
# Сейчас: заглушка на numpy, не реальный квантовый
```

### Что можно улучшить с реальным QPU

**Задача 1: QAOA Portfolio Optimization**
- Оптимальное распределение USDT между 8 passive продуктами
- Задача: максимизировать APY с учётом ограничений (лимиты, риски)
- QUBO формulation: каждая монета/продукт = кубит (0 = не инвестировать, 1 = инвестировать)
- 8 продуктов = 8 кубитов → идеально для IonQ Forte-1

**Задача 2: Q-Score Weight Optimization**
- Текущие веса Q-Score: Indicators 25%, Context 20%, Whale 10%, F&G 10%, Vision 35%
- QAOA может найти оптимальные веса на основе исторических trades из PostgreSQL
- Обучение: maximize(win_rate × avg_profit) с весами как переменными

**Задача 3: Multi-Exchange Arbitrage Path**
- Треугольный арбитраж — задача поиска оптимального пути
- 3+ биржи × 10+ пар = комбинаторная оптимизация
- QPU ускоряет поиск при масштабировании

### Архитектура интеграции

```python
# Новый модуль: quantum_optimizer.py
import boto3
from braket.aws import AwsDevice
from braket.circuits import Circuit

BRAKET_DEVICE_ARN = "arn:aws:braket:us-east-1::device/qpu/ionq/Forte-1"
BRAKET_S3_BUCKET = "quantum-trade-results"

async def quantum_portfolio_optimize(products: list[dict]) -> dict:
    """
    Запускает QAOA на IonQ Forte-1 для оптимизации распределения.
    Fallback: CPU симулятор если QPU недоступен / дорого.
    """
    if not BRAKET_ENABLED or len(products) > 20:
        return cpu_qaoa_fallback(products)

    # Строим QUBO матрицу
    # Запускаем задачу (async, результат ~30 мин)
    # Сохраняем в PostgreSQL
    # Применяем при следующем Yield Router цикле
```

### Стоимость
| Режим | Частота | Стоимость |
|-------|---------|-----------|
| Portfolio optimization | 1×/день | ~$0.01-0.05 |
| Q-Score weight tune | 1×/неделю | ~$0.10 |
| Arb path finding | per trade | ~$0.001 |
| **Итого** | | **~$0.15-0.50/день** |

Для сравнения: DeepSeek = $0.01-0.05/день. QPU добавляет ~$0.10-0.50/день.

### Когда включать
- При капитале $1000+ (стоимость QPU окупается улучшением стратегии)
- После получения доступа от AWS (кейс #177528072800782)
- После верификации аккаунта (CloudShell → boto3 работает)

## Ограничения
- Latency: IonQ задача выполняется ~10-30 минут → нельзя использовать в real-time торговле
- Стоимость растёт экспоненциально с числом кубитов
- Noise: реальный QPU шумнее симулятора
- Решение: QPU только для оффлайн оптимизации, результаты применяются в следующем цикле

## Railway Variables (будущие)
```
BRAKET_ENABLED=false  # включить после получения доступа
BRAKET_DEVICE=ionq-forte-1  # или ionq-harmony (дешевле)
BRAKET_S3_BUCKET=quantum-trade-results
AWS_ACCESS_KEY_ID=...  # через Railway Secrets
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
BRAKET_MAX_COST_USD=0.50  # лимит в день
```

## Связанные заметки
- [[QAOA CPU симулятор уже в server.py]]
- [[Yield Router v2 сравнение 7 продуктов с режим-коэффициентами]]
- [[2026-04-07 v10.17-v10.18.2 duet channel gate.io quantum]]
