---
tags: [tools, design, github, plan]
date: 2026-04-03
status: не установлено
---
# GitHub репозитории для Claude Code супер-дизайнера

## Репозитории

### 1. Frontend Design Toolkit (Wilwaldon)
- URL: github.com/wilwaldon/Claude-Code-Frontend-Design-Toolkit
- 70+ инструментов, решает проблему "AI-слоп"
- Установка: `claude plugin add anthropic/frontend-design`

### 2. OhMySkills Design Styles
- URL: github.com/NakanoSanku/OhMySkills/tree/main/design-style
- 30+ готовых дизайн-систем: Neo-brutalism, Cyberpunk, Swiss, Claymorphism
- Для нашего проекта: **Cyberpunk** (неон на тёмном, глитч-эффекты)

### 3. UI/UX Pro Max
- 240+ стилей, 127 шрифтовых пар, 99 UX-гайдлайнов

### 4. Design Tokens Skill
- OKLCH математика — один --brand-hue меняет всю цветовую схему
- Уже частично в нашем [[design-system.md]] агенте

## Telegram-управление Claude Code

### Вариант 1: Claude Code Channels (официальный)
```bash
claude plugin install telegram@claude-plugins-official
claude --channels plugin:telegram@claude-plugins-official
```

### Вариант 2: @gonzih/cc-tg (продвинутый)
```bash
TELEGRAM_BOT_TOKEN=токен CLAUDE_CODE_TOKEN=токен npx @gonzih/cc-tg
```
- Голосовые, изображения, файлы, cron-задачи

### Вариант 3: telegram-ai-bridge (мульти-агент)
- Claude + Codex + Gemini из одного чата

### Вариант 4: instar (самый мощный)
```bash
npx instar
```
- Персистентная память, планировщик задач
- Связано с [[instar persistent agent с Telegram и scheduling]]

## Скрипт установки для MacBook
```bash
# 1. Claude Code (если не установлен)
npm install -g @anthropic-ai/claude-code

# 2. Перейти в проект
cd ~/quantum-trade-bot

# 3. Плагины
claude plugin add anthropic/frontend-design

# 4. OhMySkills (клонировать скиллы)
git clone https://github.com/NakanoSanku/OhMySkills.git /tmp/ohmyskills
cp -r /tmp/ohmyskills/design-style .claude/skills/design-style

# 5. Telegram (выбрать один)
# Вариант A: Официальный
claude plugin install telegram@claude-plugins-official
# Вариант B: gonzih
npm install -g @gonzih/cc-tg
# Вариант C: instar
npx instar
```

## Что уже применено в проекте
- design-system.md агент с OKLCH токенами ✅
- Cyberpunk + Glassmorphism концепция в CLAUDE.md ✅
- Реальная установка плагинов: ❌ (требует Claude Code CLI на MacBook)
