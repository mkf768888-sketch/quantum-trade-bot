# Security Rules — QuantumTrade AI
> Обязательные правила безопасности. AI-агент должен соблюдать всегда.

## Абсолютные запреты
- НИКОГДА не коммитить API ключи, токены, пароли в код
- НИКОГДА не логировать полные API ключи (только первые 4 символа)
- НИКОГДА не отключать auth на приватных эндпоинтах
- НИКОГДА не использовать eval() или exec() с пользовательским вводом
- НИКОГДА не доверять данным из Telegram callback без верификации

## Обязательные проверки
- Каждый POST/PUT/DELETE эндпоинт → Depends(verify_api_key)
- Пользовательский ввод в AI chat → escHtml() перед отображением
- Все fetch() в index.html → AbortSignal.timeout + .ok check
- Ордера на бирже → валидация symbol, side, size перед отправкой
- WebSocket → proper disconnect handling + try/finally close

## Перед каждым деплоем
1. grep -r "API_KEY\|SECRET\|TOKEN\|PASSWORD" --include="*.py" | grep -v "os.environ\|getenv\|Header\|verify_"
2. Убедиться что .gitignore содержит: __pycache__/, *.env, .env*, credentials*
3. python3 -c "import py_compile; py_compile.compile('server.py', doraise=True)"
4. Проверить что все новые эндпоинты имеют auth где нужно
