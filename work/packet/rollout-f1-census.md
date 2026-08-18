# Выкат F1: census в packet-режиме (okna + klient-1)

Рабочий артефакт, **не коммитить отдельно от кода** (копии лежат в
`work/packet/rollout-f1-census/`). Из сессии на юниты **не выкатывать** —
команды для владельца.

Цель: убрать «синк: частичные ошибки» из-за `ValueError: unknown url type`
в `odata_census.py`, когда `ETL_ODATA_BASE=/var/lib/serenedb/packet-meta/<base>`.

Файлы на юните: `/opt/1c-mcp-reports/odata_census.py`,
`/opt/1c-mcp-reports/poc_load_entity.py` (раскладка через `deploy.sh` или
`install` ниже).

| файл | md5 (HEAD F1) |
|---|---|
| `odata_census.py` | `5e21f5ed3c69e4e8dbd8970905a019ab` |
| `poc_load_entity.py` | `a68c0b7af02d96b2eb17e440e2d54807` |

Канон для `scp`: `ubuntu/serenedb/odata_census.py` и
`ubuntu/serenedb/poc_load_entity.py` (или копии ниже).

---

## Перед любой командой

```bash
md5sum /opt/1c-mcp-reports/odata_census.py /opt/1c-mcp-reports/poc_load_entity.py
```

| md5 odata_census | действие |
|---|---|
| `5e21f5ed3c69e4e8dbd8970905a019ab` | уже F1, **ничего не класть** |
| иное | выкат ниже |

---

## okna (`167.233.249.110`) — файл + bash

С машины владельца, где есть репозиторий:

```bash
# 1) живые md5 — если оба F1, дальше не идти
ssh root@167.233.249.110 'md5sum /opt/1c-mcp-reports/odata_census.py /opt/1c-mcp-reports/poc_load_entity.py'

# 2) бэкап + атомарная подмена (как deploy.sh: install + mv)
for f in odata_census.py poc_load_entity.py; do
  scp /srv/1c/ubuntu/serenedb/"$f" \
      root@167.233.249.110:/tmp/"$f".f1
done
ssh root@167.233.249.110 'bash -s' <<'EOF'
set -euo pipefail
DST=/opt/1c-mcp-reports
stamp=$(date -u +%Y%m%d-%H%M%S)
for f in odata_census.py poc_load_entity.py; do
  src=/tmp/"$f".f1
  dst="$DST/$f"
  case "$f" in
    odata_census.py) want=5e21f5ed3c69e4e8dbd8970905a019ab ;;
    poc_load_entity.py) want=a68c0b7af02d96b2eb17e440e2d54807 ;;
  esac
  test "$(md5sum "$src" | awk "{print \$1}")" = "$want"
  cp -a "$dst" "$dst.bak-$stamp"
  install -m 644 "$src" "$dst.new"
  mv -f "$dst.new" "$dst"
  echo "$f -> $(md5sum "$dst")"
  rm -f "$src"
done
EOF
```

Приёмка okna (следующий такт pipeline или ручной синк):

```bash
ssh root@167.233.249.110 'journalctl -u 1c-serene-pipeline@okna-1 -n 80 --no-pager | grep -E "перепись|частичные|ValueError|unknown url" || true'
```

Ожидание: строка «перепись схемы…» или «перепись свежая» **без**
`unknown url type` и без census-ошибки в «частичные ошибки».

---

## klient-1 (`10.1.1.7`, только через релей) — те же два файла

Цепочка: `ssh -A root@89.23.101.22` → `ssh root@10.1.1.7`
(агент: `eval $(ssh-agent -s) && ssh-add ~/.ssh/id_ed25519_deploy`).

```bash
# на релее или с jump-хоста, где доступен 10.1.1.7
for f in odata_census.py poc_load_entity.py; do
  scp /srv/1c/ubuntu/serenedb/"$f" root@10.1.1.7:/tmp/"$f".f1
done
ssh root@10.1.1.7 'bash -s' <<'EOF'
set -euo pipefail
DST=/opt/1c-mcp-reports
stamp=$(date -u +%Y%m%d-%H%M%S)
for f in odata_census.py poc_load_entity.py; do
  src=/tmp/"$f".f1
  dst="$DST/$f"
  case "$f" in
    odata_census.py) want=5e21f5ed3c69e4e8dbd8970905a019ab ;;
    poc_load_entity.py) want=a68c0b7af02d96b2eb17e440e2d54807 ;;
  esac
  test "$(md5sum "$src" | awk "{print \$1}")" = "$want"
  cp -a "$dst" "$dst.bak-$stamp"
  install -m 644 "$src" "$dst.new"
  mv -f "$dst.new" "$dst"
  echo "$f -> $(md5sum "$dst")"
  rm -f "$src"
done
EOF
```

Приёмка klient-1:

```bash
ssh root@10.1.1.7 'journalctl -u 1c-serene-pipeline@klient-1 -n 80 --no-pager | grep -E "перепись|частичные|ValueError|unknown url" || true'
```

---

## Проверки на деве до выката (17/17 + регресс)

```bash
python3 ubuntu/serenedb/test_odata_census.py   # OK 17/17
python3 ubuntu/serenedb/test_delta.py            # проба дельты зелёная
```

Откат: последние `*.bak-<stamp>` обратно в `/opt/1c-mcp-reports/`.
