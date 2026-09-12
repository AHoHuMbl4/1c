# V2 — красная атака ПЛАНА flip (до исполнения)

Срез: 12.09.2026. Режим: атака плана, не подтверждение. Код/git/psql не
менялись. На окне — только чтение; повторные ssh с ключом deploy после
первого успешного `ls` блокировались средой (`~/.ssh`), поэтому **живые
md5 / `systemctl cat` / имена `ASK_*` в процессном env — не досняты**
(см. §1.1). Состав файлов прода снят; остальное — из дерева HEAD + якорь
прод=`14aec85` (activeContext) + сверка имён файлов.

План под атакой (из задания V2):

1. единственный код-дифф: `_bootstrap.py` — default = новый
   `z20_ask_main_http.py`; откат `ASK_LEGACY=1` →
   `z20_ask_main_http_legacy.py` + `_patch_z20_wiki_primary`;
2. выкат всего `ask/` scp → рестарт `1c-serene-ask@postgres` → health →
   контрольные → L67 на :8091.

Полигон (ASK_ONEPATH=1) L67 35/31/1/0 — **не** опровергает риски ниже:
полигон ≠ прод по набору файлов и по смыслу имени `z20_ask_main_http.py`.

---

## 0. Вердикт

| # | Риск | Вердикт |
|---|---|---|
| R1 | На проде нет `z20_ask_main_http_legacy.py`; имя `z20_ask_main_http.py` там = **старый** тракт эпохи 14aec85 | **блокер** |
| R2 | «Единственный дифф `_bootstrap`» врёт: с 14aec85 на HEAD ещё z01/z07/z16/z18 + новый z20 + legacy-файл | **блокер** (выкат ≠ один файл) |
| R3 | Откат `ASK_LEGACY=1` без предварительного выката legacy-файла = FileNotFound / старт мёртв | **блокер** |
| R4 | Текущий код знает `ASK_ONEPATH`, не `ASK_LEGACY`; план **инвертирует** семантику флага | **чинится в коммите flip** |
| R5 | Горячий `deploy-okna-serene-ask.sh` **не** возит `ask/` (только `serene_ask.py`+словари) | **блокер** процедуры |
| R6 | Порядок зон / `register_zone` / `apply_bindings` при смене z20-файла | **наблюдать** (позиция та же, последняя) |
| R7 | Env `ASK_ENTITY_FORM` / arbiter / fork / signal — на новом z20 **молчат** (0 чтений в новом файле) | **наблюдать** → при живом `=1` на проде = скрытая смена поведения |
| R8 | Замки `test_wiki_card_hybrid` / часть legacy-path замков — **не** краснеют от flip bootstrap, пока legacy+патч на диске | **наблюдать** (B7 — другое) |
| R9 | `test_zone_names_resolvable` следует `zone_paths()` / env — после инверсии флага без правки теста может грузить «не тот» z20 в CI | **чинится в коммите flip** (явный env в тесте или оба пути) |
| R10 | Рестарт: `decision_id` в памяти процесса → живые билеты умирают | **наблюдать** (ожидаемо; предупредить канал) |
| R11 | Журнал /health: файловый журнал продолжается; in-process кэш health сбрасывается | **наблюдать** |
| R12 | Без бэкапа прод-`ask/` перед scp откат «файлами» невозможен (новое имя затирает боевой z20) | **блокер** |

**Итог атаки:** план flip в текущей формулировке **не готов к исполнению**.
Минимум до слова «выкатывай»: (а) живая сверка md5 прод↔дерево,
(б) атомарный выкат **всего** изменившегося `ask/` + legacy под своим именем
+ новый bootstrap с явной семантикой флага, (в) bak прод-дерева, (г) 30-сек
откат проверен на полигоне с тем же набором файлов, что будет на проде.

---

## 1. Разница сред: прод `/opt/1c-mcp-reports/ask` vs дерево

### 1.1 Что удалось снять на окне

Команда (read-only): `ssh -p 2202 -i ~/.ssh/id_ed25519_deploy root@gpu-erw…`
→ `ls /opt/1c-mcp-reports/ask/*.py | xargs -n1 basename | sort`.

**На проде сейчас (имена):**

```
__init__.py  _bootstrap.py  _ctx.py  _imports.py  _wire.py
z01…z19, z21, z22, z20_ask_main_http.py
```

**Нет на проде:** `z20_ask_main_http_legacy.py`.

Повторные заходы (md5sum, `systemctl cat`, `grep ASK_` по env /proc) —
отклонены runtime-floor на чтение `~/.ssh`. Поэтому md5 в таблице ниже —
**ожидание по якорю 14aec85**, не живой замер. Перед flip оператор обязан
переснять.

### 1.2 Таблица отличий (прод-ожидание 14aec85 ↔ HEAD)

| Файл | Прод (ожидание 14aec85 md5) | HEAD md5 | Смысл |
|---|---|---|---|
| `_bootstrap.py` | `1eb61ace…` | `001284a9…` | 14aec85: жёстко `z20_ask_main_http.py` + патч на это имя. HEAD: `ASK_ONEPATH` → new / else legacy+патч |
| `z20_ask_main_http.py` | `aa1e7ecb…` (~5230 строк, **legacy-тракт**) | `9f27f617…` (~2962, **новый** один путь) | **коллизия имён**: scp HEAD **затрёт** боевой код новым трактом |
| `z20_ask_main_http_legacy.py` | **отсутствует** | `476c7484…` (~5103) | нужен для отката; ≠ байт-в-байт 14aec85 (докстринг БЫВШИЙ + вырезы люка W / `entity_locked`) |
| `z01_infra_trace_llm.py` | `aee7c256…` | `483cf2f4…` | DIFF (B5-хвост) |
| `z07_rrf_vectors.py` | `c13038e3…` | `059ad191…` | DIFF |
| `z16_veto_pick_entity.py` | `62ae1222…` | `51000020…` | DIFF (люк count_defer) |
| `z18_compose.py` | `45d5e48c…` | `f76476eb…` | DIFF |
| остальные `ask/*.py` (22 шт.) | = HEAD | = HEAD | без расхождений 14aec85↔HEAD |

`git diff --stat 14aec85..HEAD -- ubuntu/serenedb/ask/`: **7 файлов**,
+5849/−3083. «Только bootstrap» — ложь.

Файлов «только на проде, нет в дереве» по `ls` **не видно** (нет лишних
имён). Правки «поверх выката» без нового имени **этим ls не ловятся** —
нужен md5. Лишних не-`.py` в каталоге ask/ в первом заходе не смотрели
(повторный ssh заблокирован) → перед flip: `find ask -type f`.

### 1.3 Юнит (из дерева, не с прода)

Канон `ubuntu/serenedb/systemd/1c-serene-ask@.service`:

- `WorkingDirectory=/opt/1c-mcp-reports`
- `ExecStart=…/python /opt/1c-mcp-reports/serene_ask.py`
- EnvironmentFile порядок: `1c-mcp-reports.env` → `1c-embed.env` →
  `-1c-serene-ask.env` → `1c-serene-ask-%i.env`

Живой `systemctl cat 1c-serene-ask@postgres` — **не снят** (ssh). Перед
flip сверить, что overlay не подменяет `WorkingDirectory` / `ExecStart`.

### 1.4 Полигон vs прод

| | Полигон | Прод |
|---|---|---|
| Код | HEAD + `ASK_ONEPATH=1` | файлы эпохи ~14aec85, имя z20 = старый тракт |
| Legacy-файл | есть в дереве | **нет** |
| L67 | 35/31/1/0 на новом тракте | зелёный якорь на **legacy**-содержимом под именем new |

Успех полигона **не** доказывает, что scp HEAD на прод = тот же мир: на
проде сейчас другое содержимое того же пути `…/z20_ask_main_http.py`.

---

## 2. Порядок загрузки зон

Канон `_ZONE_FILES` (W1-X1 / `_bootstrap.py`):

```
z01→…→z19 → z21 → z22 → <Z20>
```

`<Z20>` = последний элемент в **обоих** режимах (new или legacy). Число
зон 23. Порядок остальных **не** меняется.

`_exec_zone` срезает `apply_bindings` / `register_zone` (W2-R1): в общий
`ns` уходит только тело. Оба файла регистрируются (на диске) как
`ask.z20_ask_main_http` — имя одно; при bootstrap это не исполняется, но
для замков/доков важно: **не два модуля**, а взаимоисключающий файл.

**Влияние на bindings:** нет сдвига позиции → нет нового перетирания имён
между z01–z22. Меняется **состав символов**, которые z20 кладёт поверх
общего `ns` (новый vs legacy `answer`/хвост). Это и есть flip поведения,
не баг порядка.

Патч `_patch_z20_wiki_primary` применяется **только** если
`path.name == z20_ask_main_http_legacy.py`. Новый z20 — без патча (net/
ef_gate уже на диске нового или сняты по дизайну B).

---

## 3. Env-флаги: new vs legacy

Прямые `ASK_*` в теле z20 (grep `os.environ` + имя):

| Флаг | legacy z20 | новый z20 | Риск при flip |
|---|---|---|---|
| `ASK_ENTITY_FORM` | да (гейт + патч → `entity_form_gate_open`) | **нет** | если на проде `=1` — ветка F исчезает молча |
| `ASK_ARBITER_*` / `ASK_SIGNAL_DISAGREE` / `ASK_NOT_FOR` | да | нет | arbiter/signal пути умирают |
| `ASK_FORK_OUTCOMES` (и fork через z08) | читается трактом legacy | новый не опирается на fork-судью | fork-env перестаёт рулить ответом |
| `ASK_SALES_RANK_CANON` | прямое в legacy | в z20 нет; остаётся через `period_readings` (z03) | частично живо |
| `ASK_CURRENCY_AXIS` / journal / health / slot / token / deadline | оба | оба | ок |
| `ASK_ONEPATH` | только `_bootstrap` | только `_bootstrap` | план хочет заменить на `ASK_LEGACY` с **инверсией default** |
| `ASK_LEGACY` | **не существует** | **не существует** | должен появиться в коммите flip |

Зоны z03/z05/z08 по-прежнему **читают** флаги при load (константы в
общем ns). Но call-site из нового `answer()` на entity_form/fork — по
картам W1/O1 — сняты или не используются. Итог: **включённый на проде
флаг legacy-only после flip не падает ошибкой — он просто ничего не
делает**. Это хуже явного краша.

**До исполнения:** снять с прода имена `ASK_*` из четырёх EnvironmentFile
и `/proc/<pid>/environ` (без значений секретов) и сверить с таблицей.

---

## 4. Замки после flip-коммита bootstrap

| Замок | Что держит | После смены default→new + наличия legacy на диске |
|---|---|---|
| `test_zone_names_resolvable` | `boot.zone_paths()` + патч **если** в списке legacy | При default=new грузит новый z20. Патч-ветка L57 не дергается. Сам замок **переживёт**, если новый z20 резолвится. **Риск:** CI без явного env после инверсии флага ≠ прежний «default=legacy». Чинить: в тесте зафиксировать оба режима или `ASK_LEGACY=1` для регрессии патча |
| `test_wiki_card_hybrid` | **жёстко** читает `z20_ask_main_http_legacy.py` + `_patch_z20_wiki_primary` | **не** краснеет от flip default, пока файл+функция живы. Краснеет при B7-сносе |
| `test_enough` / `test_final_stock_route_filters_absent` / `test_early_clarify_*` / `test_wiki_leader_not_overridden` / `test_no_pre_wiki_reorders` / … | path → legacy файл | живут до сноса legacy; flip их не ломает |
| `test_one_path` | контракт нового тракта | должен остаться зелёным; это замок **приёмки** flip, не жертва |

**В том же коммите flip обязательно:** правка `_bootstrap` (семантика
флага) + не оставлять «дырявый» default без выката файлов. Правка
`test_zone_names_resolvable` — если инверсия ломает локальный прогон без
env. Массовая чистка legacy-path замков — **не** этот коммит (это B7 /
W2 S1).

---

## 5. Здоровье / журнал / билеты при рестарте

| Артефакт | Где живёт | При `systemctl restart` |
|---|---|---|
| `decision_id` / `_DECISIONS` / clarify batches | память процесса (`z14`, комментарий: «рестарт → старые билеты неизвестны») | **теряются** |
| кэш `/health` gap | in-process TTL | сброс; первый GET пересчитает |
| журнал исходов | БД/файл через `_ask_journal_write` при `ASK_JOURNAL` | **продолжается** (новые строки; md5 кода в полях журнала сменится) |
| TRACE / rid | процесс + journald | новые rid; старые в journald остаются |
| memory shadow choice | процесс / внешнее по флагу | проверить `ASK_CHOICE_MEMORY`; process-часть сбрасывается |

Не блокер кода, но **операционный**: в момент flip не слать пользователям
clarify с кнопками «дорестартовые» decision_id.

---

## 6. Откат: дыры плана

### 6.1 Что план обещает

`ASK_LEGACY=1` → грузит `z20_ask_main_http_legacy.py` + патч.

### 6.2 Что сломает откат

1. **Файла legacy на проде нет** → флаг бесполезен, пока scp не довёз файл.
2. **Текущий код** откатывается через *снятие* `ASK_ONEPATH`, а не через
   `ASK_LEGACY`. План меняет контракт — полигон после flip-коммита должен
   гонять **новую** семантику, не старую.
3. HEAD-legacy **≠** прод-14aec85 z20 (люк W вырезан из legacy в дереве).
   Откат на HEAD-legacy ≠ бит-в-байт «как сейчас на проде». Для аварийного
   «вернуть ровно прод» нужен **bak файлов с прода**, не только ASK_LEGACY.
4. `deploy-okna-serene-ask.sh` / старый `rollback-okna-serene-ask.sh`
   крутят `serene_ask.py`, не дерево `ask/`.

### 6.3 Проверка за ≤30 с, если прод сломался

Предусловие: до рестарта сделан bak, например
`/opt/1c-mcp-reports/ask.bak-<ts>/` и известен путь.

```bash
# A. Быстрый откат флагом (только если legacy УЖЕ на диске и bootstrap умеет ASK_LEGACY)
# в /etc/1c-serene-ask-postgres.env (или overlay): ASK_LEGACY=1
systemctl restart 1c-serene-ask@postgres.service
sleep 3
curl -sS -m 5 http://127.0.0.1:8091/health
# один вопрос-маркер (тот, что на полигоне отличал тракты), смотреть kind/text

# B. Если флаг не спас / FileNotFound — откат файлами из bak (предпочтительно)
cp -a /opt/1c-mcp-reports/ask.bak-<ts>/. /opt/1c-mcp-reports/ask/
# снять ASK_LEGACY/ASK_ONEPATH если добавляли
systemctl restart 1c-serene-ask@postgres.service
sleep 3
curl -sS -m 5 http://127.0.0.1:8091/health
```

Критерий «откат жив»: health JSON без 5xx + контрольный вопрос даёт
прежний kind (не `unavailable` / не traceback в journalctl -n 50).

---

## 7. Чек-лист выката (после закрытия блокеров)

Только командами; **не исполнять**, пока владелец не сказал.

```bash
# 0) Живая сверка (то, что V2 не доснял)
ssh -p 2202 -i ~/.ssh/id_ed25519_deploy root@gpu-erw.timpul.pro \
  'md5sum /opt/1c-mcp-reports/ask/*.py | sort -k2;
   systemctl cat 1c-serene-ask@postgres.service;
   for f in /etc/1c-mcp-reports.env /etc/1c-embed.env /etc/1c-serene-ask.env /etc/1c-serene-ask-postgres.env; do
     echo "== $f"; grep -E "^ASK_" "$f" | cut -d= -f1; done;
   PID=$(systemctl show -p MainPID --value 1c-serene-ask@postgres);
   tr "\0" "\n" </proc/$PID/environ | grep -E "^ASK_" | cut -d= -f1 | sort'

# 1) Bak прода
ssh … 'ts=$(date +%Y%m%d-%H%M%S); cp -a /opt/1c-mcp-reports/ask /opt/1c-mcp-reports/ask.bak-$ts;
        cp -a /opt/1c-mcp-reports/serene_ask.py /opt/1c-mcp-reports/serene_ask.py.bak-$ts;
        echo BAK=ask.bak-$ts'

# 2) Выкат: НЕ deploy-okna-serene-ask.sh для зон.
#    Либо scp всего ubuntu/serenedb/ask/*.py (+ serene_ask.py если DIFF),
#    либо на машине с SERENE_SRC_DIR — deploy.sh (он копирует ask/).
#    Обязательно оба z20 + новый _bootstrap.

# 3) md5 бит-в-бит дерево↔/opt для всех DIFF-файлов из §1.2

# 4) Env: убрать ASK_ONEPATH если был; НЕ ставить ASK_LEGACY (default=new).
#    Зафиксировать снятый список ASK_* (снимок до/после).

# 5) systemctl restart 1c-serene-ask@postgres.service
# 6) sleep 5; curl health :8091
# 7) Контрольные вопросы (короткий набор) + L67 на 8091
# 8) journalctl -u 1c-serene-ask@postgres -n 100 — нет ImportError/FileNotFound
```

Коммит flip (когда разрешат): `_bootstrap` (default new / `ASK_LEGACY`) +
документы + при необходимости правка `test_zone_names_resolvable` под оба
режима. Выкат на прод — **отдельным** операторским шагом после коммита,
не «магией» git (на okna SERENE_SRC_DIR пуст).

---

## 8. Чек-лист отката

1. Есть bak `ask.bak-*` с **до**-flip содержимым? Если нет — только надежда на
   HEAD-legacy (поведение ≠ текущий прод).
2. `ASK_LEGACY=1` + restart → health OK?
3. Нет → `cp -a ask.bak-*/* ask/` + restart.
4. Снять экспериментальные флаги.
5. Один контрольный вопрос + `journalctl -n 50`.
6. Сообщить каналу: старые decision_id всё равно мертвы после любого
   рестарта.

---

## 9. Что план должен поправить до исполнения (сводка атаки)

1. **Не** называть flip «один файл bootstrap»: в выкат входят ≥7 путей ask/
   (+ bak + процедура не из `deploy-okna-serene-ask.sh`).
2. Явно: на проде сегодня `z20_ask_main_http.py` = legacy-содержимое;
   выкат **переименовывает смысл имени**.
3. Откат = bak **или** (legacy-файл с flip-scp + `ASK_LEGACY`); одного
   флага без файла недостаточно.
4. Инверсия `ASK_ONEPATH` → `ASK_LEGACY` — отдельный замер на полигоне с
   **прод-подобным** набором (сначала файлы как на проде, потом как после
   scp).
5. Доснятие md5/env/`systemctl cat` — предусловие, не «приятное дополнение».

---

## 10. Источники

- Живой `ls` прод ask/ (ssh 12.09, один успешный заход).
- `ubuntu/serenedb/ask/_bootstrap.py` (HEAD), `git show 14aec85:…/_bootstrap.py`.
- md5/diff `14aec85`↔HEAD по `ask/`; diff legacy↔14aec85 z20.
- `work/acceptance/deploy-okna-serene-ask.sh`, `ubuntu/serenedb/deploy.sh`,
  `systemd/1c-serene-ask@.service`.
- Замки: `test_zone_names_resolvable.py`, `test_wiki_card_hybrid.py`.
- Карты: W1-X1/X2, W2-R1, O5-locks; CHANGELOG 12.09 (3)(10); activeContext
  (прод=14aec85, e019cbb не выкачен).
