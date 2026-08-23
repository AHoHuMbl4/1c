# Root-задания dev-хоста (Ф3, Ф4, Ф3.5, Ф7.5)

Подготовлено 23.08.2026 сессией `claudedev` (read-only разведка). **Запускать только от root**
на dev-машине `/srv/1c`. Скрипты идемпотентны: повторный прогон безопасен.

Источник: `docs/PLAN_UPGRADE_NATIVE.md` (Ф3, Ф4, Ф7), CHANGELOG 22–23.08.

---

## Разведка (снимок на момент подготовки)

| Область | Факт |
|---|---|
| `/etc/1c-embed.env` | права `640 root:1c-secrets`; модель **`Qwen3-Embedding-8B`** (канон — **4B**); хосты **`gpu-erw.timpul.pro`** (канон — vSwitch `10.3.1.11` / `10.3.1.12`); `EMBED_DIM=1024`; `EMBED_BATCH_CHARS=12000` (канон — **60000**) |
| okna (ожидание) | по CHANGELOG/NETWORK 23.08 уже на 4B + vSwitch; сверка — команда ниже |
| PostgreSQL dev | пакеты `postgresql-16`, `postgresql-16-pgvector`, `postgresql-client-16`; **`127.0.0.1:5432` слушает** (`postgresql@16-main` active); соединений к :5432 нет |
| SereneDB | **`127.0.0.1:7890`**, юнит `serenedb.service`, бинарь `/usr/local/bin/serened` — **не** пакет postgres |
| `CLAUDE.md` / `AGENTS.md` | один инод (`806516`, 2 hardlink); абзац про обход WebFetch для `read_section` **ещё не снят** |

SSH на okna из сессии исполнителя заблокирован (runtime floor). Владелец сверяет okna вручную:

```bash
ssh -i ~/.ssh/id_ed25519_deploy -p 2202 root@gpu-erw.timpul.pro \
  'grep -v -i "key\|token\|pass" /etc/1c-embed.env | grep -E "^(EMBED_|BUILD_|RERANK_)"'
```

Ожидаемые не-секретные значения (канон 23.08, `docs/NETWORK.md` §2.1):

- `EMBED_MODEL=Qwen3-Embedding-4B`
- `EMBED_DIM=1024`
- `EMBED_HOSTS` — оба: `http://10.3.1.11:8000|…`, `http://10.3.1.12:8002|…` (ключ тот же)
- `EMBED_BASE_URL=http://10.3.1.11:8000`
- `EMBED_HEALTH_URL=http://10.3.1.11:8001/health`
- `RERANK_URL=http://10.3.1.11:8005/rerank`
- `EMBED_BATCH_CHARS=60000`

---

## Порядок выполнения

### 0. Перейти в каталог

```bash
cd /srv/1c/work/root-tasks
chmod +x 01-embed-env.sh 02-purge-pg.sh
```

### 1. EMBED 4B на dev — `01-embed-env.sh`

**Не перезапускает юниты** — только правит `/etc/1c-embed.env` (бэкап + sed, секреты не трогает).

```bash
./01-embed-env.sh
```

**Проверка после:**

```bash
grep -v -iE 'key|token|pass|secret' /etc/1c-embed.env | grep -E '^(EMBED_|BUILD_|RERANK_)'
# EMBED_MODEL=Qwen3-Embedding-4B, EMBED_DIM=1024, vSwitch-хосты, BATCH_CHARS=60000

# Живость эндпоинтов (ключ из env, не печатать):
set -a; source /etc/1c-embed.env; set +a
curl -sS -m 5 -H "Authorization: Bearer ${EMBED_API_KEY:-$EMBED_API_KEYS}" \
  "${EMBED_BASE_URL%/}/v1/models" | head -c 200; echo
curl -sS -m 5 "${EMBED_HEALTH_URL}" | head -c 200; echo
```

**Рестарт юнитов** (отдельно, после проверки env):

```bash
# Читают EnvironmentFile=/etc/1c-embed.env (установленные юниты dev):
systemctl restart \
  '1c-serene-ask@postgres' \
  '1c-serene-ask@ut_test' \
  '1c-serene-pipeline@postgres' \
  '1c-serene-index' \
  '1c-branch-alias' \
  '1c-wiki-alias'

# Проверка:
systemctl is-active '1c-serene-ask@postgres' '1c-serene-ask@ut_test' serenedb.service
curl -sS -m 5 http://127.0.0.1:8091/health | head -c 300; echo
```

`1c-mcp-ask@*` embed env **не** подключает напрямую — при необходимости рестарт после смены ключей в `1c-mcp-reports.env`.

Пересчёт векторов 4B (`EMBED_RESET=1`) — **отдельный заход**, не часть этого скрипта.

---

### 2. Снос PostgreSQL 16 — подготовка + `02-purge-pg.sh`

PostgreSQL на dev — наследие braine, **не** SereneDB. SereneDB на `:7890` не трогаем.

**Сначала остановить кластер** (иначе `02-purge-pg.sh` выйдет с ошибкой):

```bash
systemctl stop postgresql@16-main postgresql
systemctl disable postgresql@16-main postgresql
ss -ltn | grep 5432 || echo "OK: 5432 не слушает"
```

**Затем purge:**

```bash
./02-purge-pg.sh
```

**Проверка после:**

```bash
dpkg -l | grep -i postgres || echo "OK: пакетов postgres нет"
ss -ltn | grep -E '5432|7890'
systemctl is-active serenedb.service
/usr/local/bin/serened --version 2>/dev/null || ls -la /usr/local/bin/serened
psql -h 127.0.0.1 -p 7890 -c "SELECT version();" 2>/dev/null | head -1
```

---

### 3. owner-memory (Ф3.5)

Файл `memory_bank/owner-memory/` — root-only.

```bash
cp -a /srv/1c/memory_bank/owner-memory/project-architecture-pg-windows-attach.md \
      /srv/1c/memory_bank/owner-memory/project-architecture-pg-windows-attach.md.bak-$(date +%Y%m%d-%H%M%S)

cp /srv/1c/work/root-tasks/03-owner-memory/project-architecture-pg-windows-attach.md \
   /srv/1c/memory_bank/owner-memory/project-architecture-pg-windows-attach.md

# Права как у соседей:
chown root:root /srv/1c/memory_bank/owner-memory/project-architecture-pg-windows-attach.md
chmod 644 /srv/1c/memory_bank/owner-memory/project-architecture-pg-windows-attach.md
```

---

### 4. CLAUDE.md — снять обход WebFetch (Ф7.5)

`CLAUDE.md` и `AGENTS.md` — **один инод** (hardlink). Править содержимое, не пересоздавать файл.

```bash
stat -c '%i %h %n' /srv/1c/CLAUDE.md /srv/1c/AGENTS.md
# оба должны показать один inode и links=2

cd /srv/1c
patch -p0 --backup --suffix=.bak-root-$(date +%Y%m%d) \
  < work/root-tasks/04-claude-md/claude-md.patch

# inode не должен измениться:
stat -c '%i %n' /srv/1c/CLAUDE.md
grep 'read_section' /srv/1c/CLAUDE.md | head -1
```

Если patch ответит «already applied» — шаг не нужен (текст уже обновлён).

---

## Откат

| Шаг | Откат |
|---|---|
| 01 | `cp /etc/1c-embed.env.bak-* /etc/1c-embed.env` (последний бэкап из вывода скрипта) + рестарт юнитов |
| 02 | `apt install postgresql-16 postgresql-client-16` — только если понадобился PG; иначе не восстанавливать |
| 03 | восстановить `.bak-*` owner-memory |
| 04 | `cp CLAUDE.md.bak-root-* CLAUDE.md` |
