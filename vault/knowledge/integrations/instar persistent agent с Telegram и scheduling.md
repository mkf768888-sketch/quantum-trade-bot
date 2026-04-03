---
tags: [integration, telegram, autonomy, planned]
date: 2026-04-02
---
# Instar: persistent Claude Code agent с Telegram и scheduling

## Что это:
GitHub: JKHeadley/instar
Persistent Claude Code agent — memory выживает между сессиями, Telegram интеграция, job scheduling.

## Зачем нам:
- Управлять QuantumTrade через Telegram → Claude Code → git → Railway
- Автодиагностика каждые 6ч
- Crash recovery через Telegram
- Self-improvement loop

## Setup:
```bash
npx instar
```
Далее: настройка Telegram бота, привязка к проекту.

## Альтернативы:
- CCGram (jsayubi) — проще, но без memory
- Claude Code Telegram Plugin (official) — базовый
- Claudegram, Teleforge — community

## Статус: ЗАПЛАНИРОВАНО (Wave 3A)
## Стоимость: $0

Связано: [[текущие приоритеты]]
