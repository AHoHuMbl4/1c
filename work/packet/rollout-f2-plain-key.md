# Выкат F2: p_doc_plain — порядковый суффикс ключа (§3.77)

Рабочий артефакт, **не коммитить отдельно от репо**. Выкатывает оркестратор —
сессия-исполнитель сама на юниты не лезет.

Цель на юните: `/opt/1c-mcp-reports/corpus_build.sql`
(канон — `ubuntu/serenedb/corpus_build.sql` в git после коммита F2).

**На okna** файл уже совпадал с репо до правки plain; выкат = HEAD с F2.
**На klient-1** `/opt/corpus_build.sql` **старше репо** (md5 `43050f46f3c7…`, нет
§3.77 и refs_map/refs_own) — выкат **одним файлом** HEAD+F2, промежуточный «просто
HEAD» не нужен.

Юниты сборки: `1c-serene-index@…` / ручной такт по `PLAN_ORCHESTRATOR.md` A2.
После выката — перезапуск/продолжение сборки klient-1; приёмка: слияние проходит,
`build_failed=0`, дублей ключа 0 (было 37 522).

---

## Что меняет F2

В `PREPARE p_doc_plain` (`corpus_build.sql:831-862`): зеркало полного пути
(строки 731-736). Строки с одинаковым `(src_table, row_key)` получают
`'#' || row_number()` по детерминированному порядку `(doc, doc_hash)`; где дубля
нет — ключ не меняется (сохранение векторов).

---

## Перед любой командой

```bash
md5sum /opt/1c-mcp-reports/corpus_build.sql
```

| живой md5 | действие |
|---|---|
| `bffaa2ab1ef2ec7f453afbcbbe7d56a7` | уже F2 — **ничего не класть** |
| `a2fb7ff48a08…` (репо pre-F2, okna) | выкат F2 — инструкция ниже |
| `43050f46f3c7…` (klient-1 старый) | выкат F2 — один scp, не два шага |
| иное | СТОП, сверить с git log |

Эталон md5 после коммита F2: **`bffaa2ab1ef2ec7f453afbcbbe7d56a7`**
(уточнить по `md5sum ubuntu/serenedb/corpus_build.sql` в HEAD, если коммит
новее).

---

## okna (`167.233.249.110`) — scp + md5

С машины, где есть репозиторий:

```bash
WANT=bffaa2ab1ef2ec7f453afbcbbe7d56a7
SRC=/srv/1c/ubuntu/serenedb/corpus_build.sql
test "$(md5sum "$SRC" | awk '{print $1}')" = "$WANT"

ssh root@167.233.249.110 'md5sum /opt/1c-mcp-reports/corpus_build.sql'

scp "$SRC" root@167.233.249.110:/tmp/corpus_build.sql.f2
ssh root@167.233.249.110 'bash -s' <<EOF
set -euo pipefail
DST=/opt/1c-mcp-reports/corpus_build.sql
WANT=$WANT
test "\$(md5sum /tmp/corpus_build.sql.f2 | awk '{print \$1}')" = "\$WANT"
cp -a "\$DST" "/opt/1c-mcp-reports/corpus_build.sql.bak-\$(date -u +%Y%m%d-%H%M%S)"
install -m 644 /tmp/corpus_build.sql.f2 "\$DST.\$WANT.new"
mv -f "\$DST.\$WANT.new" "\$DST"
test "\$(md5sum "\$DST" | awk '{print \$1}')" = "\$WANT"
rm -f /tmp/corpus_build.sql.f2
echo "okna corpus_build.sql F2: \$WANT"
EOF
```

Приёмка okna: md5 совпал; следующий такт сборки не регрессирует (первая база
не затронута, если такт только на okna-витрине).

---

## klient-1 (`10.1.1.7`, через релей) — scp + ProxyCommand

Цепочка: `ssh -A root@89.23.101.22` → `ssh root@10.1.1.7`
(агент: `eval $(ssh-agent -s) && ssh-add ~/.ssh/id_ed25519_deploy`).

```bash
WANT=bffaa2ab1ef2ec7f453afbcbbe7d56a7
SRC=/srv/1c/ubuntu/serenedb/corpus_build.sql

scp -o ProxyCommand='ssh -A -W %h:%p root@89.23.101.22' \
  "$SRC" root@10.1.1.7:/tmp/corpus_build.sql.f2

ssh -A root@89.23.101.22 'ssh root@10.1.1.7 bash -s' <<EOF
set -euo pipefail
DST=/opt/1c-mcp-reports/corpus_build.sql
WANT=$WANT
echo "до: \$(md5sum "\$DST")"
test "\$(md5sum /tmp/corpus_build.sql.f2 | awk '{print \$1}')" = "\$WANT"
cp -a "\$DST" "/opt/1c-mcp-reports/corpus_build.sql.bak-\$(date -u +%Y%m%d-%H%M%S)"
install -m 644 /tmp/corpus_build.sql.f2 "\$DST.\$WANT.new"
mv -f "\$DST.\$WANT.new" "\$DST"
test "\$(md5sum "\$DST" | awk '{print \$1}')" = "\$WANT"
rm -f /tmp/corpus_build.sql.f2
echo "klient-1 corpus_build.sql F2: \$WANT"
EOF
```

Приёмка klient-1 (оркестратор): продолжить/перезапустить сборку A2;
`corpus_merge` не останавливается на «дублей ключа»; `build_failed=0`;
деградация plain-путём — числом в `search_quality.build_degraded`.

Откат: последний `corpus_build.sql.bak-*` → `/opt/1c-mcp-reports/corpus_build.sql`.

---

## Проверки на деве (до выката)

- `python3 ubuntu/serenedb/test_corpus_plain_key.py` — **8/8** PASS (PGPASSWORD).
- Оффлайн регресс первой базы: test_gate 130, test_fork_detector 23, test_delta — зелёные.
- `[замер]` проба plain: 5 строк, **0** дублей `(src_table, row_key)`; klient-1
  блокер был **37 522** дублей → ожидается **0** после полного такта на выкаченном файле.
