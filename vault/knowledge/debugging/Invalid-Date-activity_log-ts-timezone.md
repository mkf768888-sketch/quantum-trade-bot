---
date: 2026-04-06
tags: [bug, fix, frontend, timezone, date]
---

# Invalid Date — activity_log.ts timezone/string handling

## Баг (v10.16.2)
- Python server отправляет `activity_log.ts` как ISO string: `"2026-04-06T12:30:45.123Z"`
- Frontend делает `new Date(e.ts * 1000)` → NaN (потому что string * 1000 = NaN)
- Результат: "Invalid Date" в таблице activity log

## Фикс (v10.16.3)
```javascript
const parseTs = (e) => {
  if (typeof e === 'string') return new Date(e);
  if (typeof e === 'number') return new Date(e * 1000);
  return new Date();
};

// Использование:
renderActivityLog() {
  activities.map(e => ({
    ...e,
    displayTime: parseTs(e.ts).toLocaleString()
  }))
}
```

## Причина
- Python `datetime.isoformat()` → строка ISO 8601
- Frontend предполагал number (UNIX timestamp)
- Type mismatch при передаче через JSON

## Уроки
- Всегда документировать timestamp формат в API контракте
- Backend: либо всегда string, либо всегда number, не смешивать
- Frontend: проверить type перед использованием

## Файлы затронутые
- `server.py` — убедиться что `activity_log` отправляется как ISO string
- `quantum-control-center.html` — parseTs() helper
