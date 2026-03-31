# /forensics — Диагностика и восстановление
> Как GSD `/gsd forensics` — полный аудит состояния системы

## Назначение
Глубокая диагностика при проблемах: что сломалось, почему, как починить.

## Протокол
### 1. State Audit
```bash
# Проверить целостность конфигов
cat STATE.md
cat ROADMAP.md
git log --oneline -20
git status
```

### 2. Runtime Diagnostics
```bash
# Если бот запущен — проверить здоровье
curl -s https://$RAILWAY_PUBLIC_DOMAIN/health | python3 -m json.tool
curl -s https://$RAILWAY_PUBLIC_DOMAIN/api/autodiag?secret=$API_SECRET | python3 -m json.tool
```

### 3. Code Integrity
```bash
python3 -c "import py_compile; py_compile.compile('server.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('db.py', doraise=True)"
```

### 4. Security Scan
- Запуск security-auditor агента
- Проверка секретов в коде
- Проверка .gitignore

### 5. Crash Recovery
При обнаружении проблем:
1. Последний рабочий коммит: `git log --oneline -10`
2. Diff с текущим: `git diff HEAD~1`
3. Опционально: откат к рабочей версии
4. Обновить STATE.md с причиной проблемы

## Формат отчёта
```
🔬 FORENSICS REPORT
━━━━━━━━━━━━━━━━━
✅ / ❌ State Files: [OK/CORRUPT]
✅ / ❌ Syntax: [OK/ERROR at line X]
✅ / ❌ Security: [OK/N issues]
✅ / ❌ Runtime: [OK/DOWN]
✅ / ❌ Git: [CLEAN/N uncommitted]

🔍 Issues Found: [список]
💊 Fix Plan: [план исправления]
```
