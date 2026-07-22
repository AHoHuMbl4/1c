# Windows-стенд (10.8.0.58)

Тестовая машина для 1С-части «второго мозга». Раскладка на машине:

```
C:\1c\
  repo\      — клон этого репозитория (git pull для обновления скриптов)
  bases\     — файловые базы 1С (тестовые)
  backups\   — zip-бэкапы баз (ротация, последние 14)
  distr\     — дистрибутивы (платформа 1С и т.п.)
  logs\      — логи скриптов
```

## Правила
- **Перед любым изменением базы/конфигурации — бэкап**: `powershell -NoProfile -File C:\1c\repo\windows\scripts\backup-1c.ps1 -BasePath C:\1c\bases\<база>`.
- Скрипты живут в репозитории (`windows/scripts/`), на машину попадают через `git pull` в `C:\1c\repo`.
- Доступ Claude: `ssh unde@10.8.0.58` (ключ `claude-1c` в `administrators_authorized_keys`). Длинные команды — через `powershell -EncodedCommand` (base64 UTF-16LE).
