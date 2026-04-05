# Opus Prompt: Wave 4 — Telegram→Claude Code Setup
> Запустить: вставить этот промт в Claude (Opus модель) в Cowork или через claude CLI
> Цель: полная автоматическая установка Telegram→Claude Code за 5 минут

---

## Твоя роль

Ты — автономный инженер DevOps. Твоя задача: полностью настроить связку **Telegram → Claude Code** на этом MacBook, чтобы хозяин мог управлять QuantumTrade AI с телефона, пока ноутбук дома.

Работай последовательно. Каждый шаг проверяй перед следующим. Если что-то уже установлено — пропускай, не переустанавливай.

---

## Шаг 1: Диагностика окружения

Выполни эти команды и сообщи что нашёл:

```bash
# Проверка Node.js
node --version 2>/dev/null && echo "✅ Node OK" || echo "❌ Node отсутствует"

# Проверка npm
npm --version 2>/dev/null && echo "✅ npm OK" || echo "❌ npm отсутствует"

# Проверка Bun (ОБЯЗАТЕЛЬНО для Telegram плагина)
bun --version 2>/dev/null && echo "✅ Bun OK" || echo "❌ Bun отсутствует — нужно установить"

# Проверка Claude Code CLI
claude --version 2>/dev/null && echo "✅ Claude Code OK" || echo "❌ Claude Code отсутствует"

# Проверка проекта
ls ~/quantum-trade-bot/server.py 2>/dev/null && echo "✅ Проект найден" || echo "❌ Проект не найден по ~/quantum-trade-bot"

# Проверка git
cd ~/quantum-trade-bot && git log --oneline -3 2>/dev/null || echo "❌ git проблема"
```

---

## Шаг 2: Установка недостающего

### Если нет Bun:
```bash
curl -fsSL https://bun.sh/install | bash
# Перезагрузить shell
source ~/.zshrc 2>/dev/null || source ~/.bashrc 2>/dev/null
bun --version
```

### Если нет Claude Code CLI:
```bash
npm install -g @anthropic-ai/claude-code
claude --version
```

### Если нет Node.js (крайний случай):
Скажи пользователю: "Установи Node.js с nodejs.org, это единственный шаг который нужно сделать вручную"

---

## Шаг 3: Установка Telegram плагина

```bash
cd ~/quantum-trade-bot

# Создать конфиг директорию если нет
mkdir -p ~/.claude/channels/telegram

# Проверить наличие плагина
ls ~/.claude/plugins/ 2>/dev/null || echo "Плагины ещё не установлены"
```

Плагин устанавливается автоматически при первом запуске с флагом --channels.
Скажи пользователю: "Плагин установится сам на Шаге 5. Сначала создадим бота."

---

## Шаг 4: Создание файла конфигурации

Создай файл `~/quantum-trade-bot/start_telegram.sh`:

```bash
cat > ~/quantum-trade-bot/start_telegram.sh << 'EOF'
#!/bin/bash
# QuantumTrade AI — Telegram управление
# Запуск: ./start_telegram.sh
# После запуска — пиши боту в Telegram, он ответит через Claude Code

echo "🚀 Запуск QuantumTrade AI Telegram Bridge..."
echo "📱 Пиши своему боту в Telegram"
echo "⚡ Claude Code будет обрабатывать команды локально"
echo ""
echo "Для остановки: Ctrl+C"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd ~/quantum-trade-bot
claude --channels plugin:telegram@claude-plugins-official
EOF

chmod +x ~/quantum-trade-bot/start_telegram.sh
echo "✅ Создан ~/quantum-trade-bot/start_telegram.sh"
```

Создай также файл `~/quantum-trade-bot/TELEGRAM_SETUP.md` с инструкцией для пользователя:

```bash
cat > ~/quantum-trade-bot/TELEGRAM_SETUP.md << 'EOF'
# Telegram Setup — один раз

## Единственный ручной шаг: создать бота

1. Открой Telegram → найди @BotFather
2. Напиши /newbot
3. Имя: QuantumTrade AI
4. Username: придумай уникальный, например quantumtrade_yourname_bot
5. Скопируй токен: 123456789:AAHfiq...

## Настройка (в терминале):

```bash
# Запустить мост
./start_telegram.sh
```

При первом запуске плагин установится автоматически.

```
# В Claude Code ввести токен:
/telegram:configure ВАШ_ТОКЕН_ЗДЕСЬ

# Написать боту в Telegram → получишь 6-значный код
# В Claude Code:
/telegram:access pair КОД

# Заблокировать для посторонних:
/telegram:access policy allowlist
```

## Готово! Теперь пиши боту:

- "Покажи логи бота за последний час"
- "Проверь DCI статус"
- "Запуши фикс в server.py и задеплой"
- "Что с позициями сейчас?"

Claude Code работает локально, видит весь проект, может пушить в GitHub.
EOF

echo "✅ Создан ~/quantum-trade-bot/TELEGRAM_SETUP.md"
```

---

## Шаг 5: Установка OhMySkills дизайн-пакета (Wave 5)

```bash
# Создать директорию для skills если нет
mkdir -p ~/quantum-trade-bot/.claude/skills

# Клонировать OhMySkills
if [ ! -d "/tmp/ohmyskills" ]; then
    git clone https://github.com/NakanoSanku/OhMySkills.git /tmp/ohmyskills
    echo "✅ OhMySkills клонирован"
fi

# Скопировать дизайн-стили
if [ -d "/tmp/ohmyskills/design-style" ]; then
    cp -r /tmp/ohmyskills/design-style ~/quantum-trade-bot/.claude/skills/design-style
    echo "✅ Дизайн-стили установлены: $(ls ~/quantum-trade-bot/.claude/skills/design-style | wc -l) стилей"
    ls ~/quantum-trade-bot/.claude/skills/design-style
else
    echo "⚠️ Структура OhMySkills изменилась, проверь вручную"
    ls /tmp/ohmyskills/
fi
```

---

## Шаг 6: Финальный отчёт

Выполни проверку и выдай красивый итог:

```bash
echo "════════════════════════════════════"
echo "  QuantumTrade Wave 4+5 Setup Report"
echo "════════════════════════════════════"

echo ""
echo "📦 Зависимости:"
bun --version && echo "  ✅ Bun: $(bun --version)" || echo "  ❌ Bun"
claude --version && echo "  ✅ Claude Code" || echo "  ❌ Claude Code"

echo ""
echo "📁 Файлы проекта:"
ls ~/quantum-trade-bot/start_telegram.sh && echo "  ✅ start_telegram.sh" || echo "  ❌ start_telegram.sh"
ls ~/quantum-trade-bot/TELEGRAM_SETUP.md && echo "  ✅ TELEGRAM_SETUP.md" || echo "  ❌ TELEGRAM_SETUP.md"

echo ""
echo "🎨 Дизайн-скиллы:"
ls ~/quantum-trade-bot/.claude/skills/design-style 2>/dev/null | head -10 || echo "  ❌ не установлены"

echo ""
echo "════════════════════════════════════"
echo "✅ ГОТОВО! Следующий шаг:"
echo ""
echo "1. Создай бота через @BotFather в Telegram"
echo "2. Запусти: cd ~/quantum-trade-bot && ./start_telegram.sh"
echo "3. Следуй инструкции в TELEGRAM_SETUP.md"
echo "════════════════════════════════════"
```

---

## Важные ограничения

- **BotFather** — единственный шаг который нельзя автоматизировать (создание бота требует Telegram аккаунта)
- **Токен бота** — пользователь вводит сам через `/telegram:configure`
- **Pairing** — пользователь делает один раз через `/telegram:access pair КОД`
- После этого всё работает автоматически при запуске `./start_telegram.sh`

---

## Как это работает потом (с телефона)

```
Телефон → Telegram Bot → Claude Code (MacBook) → git push → Railway → бот обновлён
```

Примеры команд с телефона:
- "Посмотри последние логи Railway"
- "Добавь обработку ошибки X в server.py и запуши"
- "Покажи текущие открытые позиции из БД"
- "Обнови vault с сегодняшними изменениями"
