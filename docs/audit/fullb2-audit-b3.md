# Аудит B3 (замки/L-mid/repost)

Дата: 10.09.2026. Линза 3: замки и устойчивость к обрывам (пункты 5–6 пакета 1∥3-B).
Режим: только чтение кода/канона. БД не трогалась, прогоны не запускались, код не правился.

Канон: `docs/audit/FULLB_1PAR3_PLAN_2026-09-10.md` (пакет B п.5–6), `docs/audit/FULLB_PLAN_2026-09-03.md` §5 / §1.7.
HEAD-дерево: `corpus_merge.sql` 1497 строк; `corpus_build.sql` 2985.

---

## Якоря

| Тема | файл:строка | Цитата / суть |
|---|---|---|
| repost delta (текущий) | `corpus_merge.sql:597-604` | `starts_with(k.key_text, t.rec \|\| '\|')` — канон звал `:588-595`, блок съехал |
| transport STOP без маркера | `corpus_merge.sql:612-618` | error «дефект транспорта», если rec не в `tmp3_merge_repost_delta` |
| сторож A (L0 runtime) | `corpus_merge.sql:123-129` | `:partial_rebuild=0` ∧ `mode IS DISTINCT FROM 'full'` → `error(...)` |
| L4(б) runtime | `corpus_build.sql:1541-1546` | `mode IS NULL OR mode NOT IN ('full','partial')` → error |
| CTAS mode (R6) | `corpus_build.sql:1485-1489` | `WHEN :partial_rebuild = 0 THEN 'full'` |
| COMMIT-пачки emb/MERGE | `corpus_merge.sql:1236-1366` | `BEGIN` ord=0 → UPDATE emb=NULL ord=1 → MERGE ord=2 → maps ord=3 → `COMMIT` ord=90 → checkpoint 95 |
| anti-join wipe (полный) | `corpus_merge.sql:1371-1374` | `DELETE … IN (tmp3_corpus) AND NOT EXISTS tmp3` — без ветвления по mode |
| emb_xfer пачки | `corpus_merge.sql:1393-1399` | UPDATE emb из карты ×1000 **без** BEGIN/COMMIT на пачку |
| мост | `corpus_init.sql:129-150` | `MACRO bridge_row_matches(row_key, marker, n_seg)` |
| вызов моста (rehash) | `corpus_merge.sql:1021-1023` | `bridge_row_matches(d.row_key, m.key_text, d.n_seg)` |
| каркас L0/L4(б) в замке | `test_changed_rows_lock.py:111-158` | dual `\set`, сторож A порядок, L4(б) после CTAS |
| модель моста + `*` | `test_hash_kill_gate.py:30-44,186-217` | `bridge('*')` false на нормальных ключах; патология `*\|1` |
| форма замков | `test_*_lock.py` | python3, читают файлы, `t()` → `PASS N FAIL M`, exit 1 |

### repost :604 — текущий код (6 строк)

```597:604:ubuntu/serenedb/corpus_merge.sql
CREATE OR REPLACE TABLE tmp3_merge_repost_delta AS
SELECT t.src_table, t.rec, t.n
FROM tmp3_merge_transport_defect t
WHERE EXISTS (
  SELECT 1 FROM search_changed_rows k
  WHERE k.op = 'delta'
    AND k.src_table = t.doc_tbl
    AND (k.key_text = t.rec OR starts_with(k.key_text, t.rec || '|')));
```

### COMMIT-пачки — текущее место (канон :1347-1365 → сейчас :1290-1366)

```1290:1366:ubuntu/serenedb/corpus_merge.sql
SELECT stmt FROM (
  -- 🔴 ПАЧКА В ТРАНЗАКЦИИ: BEGIN … COMMIT (ord=90)
  SELECT job_id, 0 AS ord, 'BEGIN;' AS stmt
  ...
  SELECT job_id, 1 AS ord, 'UPDATE search_corpus c SET emb = NULL ...'
  ...
  SELECT job_id, 2, 'MERGE INTO search_corpus ...'
  ...
  SELECT job_id, 90, 'COMMIT;' AS stmt
  ...
  SELECT job_id, 95, 'SELECT checkpoint();' AS stmt
) z ORDER BY job_id, ord
\gexec
```

Внутри пачки смешанное «emb=NULL + старый контент» откатывается (`ON_ERROR_STOP` рвёт незакрытую tx). **Между пачками** уже закоммиченное остаётся — это и есть поверхность тихого resume.

---

## 1. repost: `starts_with` → `bridge_row_matches`

### Что менять

Фильтр сейчас: маркер **длиннее/равен** `rec` (`key_text = rec` ∨ `starts_with(key_text, rec||'|')`). Мост принимает `(row_key, marker, n_seg)` и смотрит «корпусный ключ ↔ маркер».

Корректная подстановка (направление важно):

```sql
bridge_row_matches(k.key_text, t.rec, <n_seg>)
```

т.е. `row_key` = витринный `key_text` маркера, `marker` = `t.rec` (Ref документа). Тогда объектная ветка моста (`len(segs(marker)) < n_seg`) даёт `key_text = rec` ∨ `starts_with(key_text, rec||'|')` ∨ `starts_with(key_text, rec||'#')` — плюс точный/enriched пути.

`#`-потомки (`guid#sha`) текущий `starts_with(…, rec||'|')` **не** ловит; мост ловит — улучшение, не регресс.

### Риски

| Риск | Факт | Следствие |
|---|---|---|
| `n_seg=1` (fold / `[Ref_Key]`) | `bridge_row_matches('guid\|4', 'guid', 1)` = **false** (объектная ветка только при `len(segs)<n_seg`) | Наивный `n_seg = len(key_cols)` на fold-документе **ломает** line-маркеры, которые сегодня PASS через `starts_with`. Нужен `n_seg ≥ len(split(key_text,'\|'))` либо явный `greatest(len(key_cols), …)`. |
| нет `key_cols` / n_seg=0 | ветки 2–3 моста не срабатывают; остаётся только точное равенство | `guid\|4` vs `guid` → false → transport-STOP вместо `entity_repost_delta`. Fail-closed OK, но нужен явный fallback в каноне. |
| сентинель `('*','full')` | фильтр `op='delta'` — full не участвует; `bridge_row_matches(нормальный, '*', n)` = false (как в R4 hash_kill) | full-rewrite **не** классифицирует repost; остаётся transport-STOP — задумано (не дыра). |
| патология `*\|…` | ветка 3 моста матчит `*\|1` vs маркер `*` при n_seg>1 | На `rec` из движений маловероятно; замок патологии hash_kill уже есть — для repost достаточно не брать `rec='*'`. |
| регистр | и `starts_with`, и макрос — case-sensitive | Расхождение регистра маркера vs `rec` из `row_key` → ложный transport-STOP (та же поверхность, что у meta_canon; не новая, но при смене формулы проверить фикстурой). |
| `op='delta'` only | gone/full не объясняют | OK для семантики repost; замок должен grep'ать `op = 'delta'` + `bridge_row_matches(`. |

### Вердикт по формуле

Нельзя тупо заменить `starts_with` на `bridge_row_matches(t.rec, k.key_text, len(key_cols))` — **аргументы и n_seg** обязаны быть в каноне B одним SQL-предложением. Рекомендуемый якорь правки: строки **602-604** (EXISTS-тело).

---

## Замки: что нового нужно

Форма как у существующих: `ubuntu/serenedb/test_<имя>_lock.py`, читает SQL/py текстом + python-модель семантики, `PASS/FAIL`, без pytest и без живой БД.

### Уже есть (каркас, не полный 1d)

| Замок | Что покрывает | Чего не хватает для 1d |
|---|---|---|
| `test_changed_rows_lock.py` | dual `\set`, запрет `\if`, grep сторожа A (после empty-entity, до vec_budget), L4(б) после CTAS | нет фикстуры «mode=partial при partial_rebuild=0 → STOP»; нет L4(а); нет L2; нет L-mid |
| `test_corpus_bridge_lock.py` | семантика моста + «merge зовёт, build не копирует» | нет ветки **repost→bridge** |
| `test_hash_kill_gate.py` | `bridge('*')=false`, патология `*` | не про repost |

### НОВЫЕ / расширения под пакет B (1a/1b/1c + 1d)

| ID | Файл-замок | Grep / ветки | Привязка к коду B |
|---|---|---|---|
| **L0** | расширить `test_changed_rows_lock.py` **или** новый `test_merge_mode_guard_lock.py` | (1) `mode IS DISTINCT FROM 'full'` + `partial_rebuild=0` + `error(` в merge **до** `tmp3_merge_vec_budget`; (2) python-фикстура: `partial_rebuild=0`, одна сущность `mode='partial'`/`NULL` → STOP; все `full` → PASS; (3) запрет предиката «корпус⊃tmp3» как L0 (grep anti-pattern рядом со сторожем A) | runtime уже есть `:123-129`; полный L0 = каркас + семантическая фикстура (FULLB §0e→1d) |
| **L2** | **новый** `test_merge_emb_delta_lock.py` | модель: emb ключей ∉ (свежие маркеры∪tmp3∪gone_expand) бит-в-бит до/после merge-partial; FAIL если UPDATE/MERGE трогает emb вне скоупа; grep: при `mode=partial` нет голого `SET emb = NULL` по всей сущности без фильтра моста | код появится с 1a/1b; до ветвления — замок RED или skip-до-якоря |
| **L4(а)** | **новый** `test_merge_full_stage_lock.py` (или секция в mode-guard) | «урезанный tmp3 у `mode=full` → STOP до MERGE/DELETE»; grep runtime `error(` с текстом про partial stage / full mode; **запрещён** предикат «корпус⊃tmp3» как единственный критерий (§1.7) — нужен явный счёт стейджа vs ожидание full | runtime **сейчас НЕТ** (поиск `L4(а)` / «частичный стейдж» в serenedb — пусто) |
| **L4(б)** | уже в `test_changed_rows_lock.py:151-158` | усилить: ветка «непустой tmp3 без строки mode → STOP»; grep `corpus_build: L4(б)` | runtime `:1541-1546` есть |
| **repost→bridge** | расширить `test_corpus_bridge_lock.py` **или** `test_merge_repost_bridge_lock.py` | grep: в блоке `tmp3_merge_repost_delta` есть `bridge_row_matches(`, **нет** `starts_with(k.key_text`; семантика: `guid`/`guid\|N`/`guid#sha` vs `rec`; `n_seg` fold+line; `op='delta'`; `'*'`/`full` не классифицируют | правка `:602-604` |
| **L-mid (R3)** | **новый** `test_merge_mid_abort_lock.py` | см. секции ниже | якорь COMMIT `:1290-1366` + anti-join `:1371` |
| **1c cap** (смежно 1d) | канон B п.4 — отдельный замок | grep `unexpected` без cap-CTE; фикстуры fanout | не путать с L0/L2/L4 |

**L3 gone** в FULLB §5/1d упомянут, в 1∥3-B п.6 — нет; держать в `test_corpus_merge_gone_register.py` (уже есть контур), не плодить дубль в B3-скоупе.

---

## L-mid: где тихий resume

Канон R3 (три пункта):

1. после обрыва `count(emb IS NULL)` вне свежих маркеров = 0 **ИЛИ** явный STOP/quality до следующего такта;
2. повторный такт: нет второго anti-join вне `gone∪expand`;
3. gone-маркеры живы.

### Где сейчас тихий resume

| Место | Поведение при kill | Почему «тихо» |
|---|---|---|
| **COMMIT-пачки `:1290-1366`** | пачки 1..N закоммичены (контент новый, emb часто NULL на hash_kill); пачка N+1 откатилась | нет `search_quality` «merge_incomplete»; следующий такт просто стартует снова |
| **anti-join `:1371-1374`** | если обрыв **после** части COMMIT, но **до** DELETE — корпус частично новый; следующий full-такт пересоберёт и снова сделает полный anti-join по всем `tmp3_corpus` | при будущем `mode=partial` это и есть «второй wipe» вне gone∪expand (R3.2) — сейчас ветвления нет, риск уже в полном пути при неполном стейдже (§1 диагноз) |
| **emb_xfer `:1393-1399`** | UPDATE×1000 без обёртки tx на пачку | частичный добор emb; дыры вне маркеров остаются NULL → шаг 5 досчитает **молча** (нет STOP) |

Внутри одной пачки защита уже есть (комментарий `:1356-1358`): без BEGIN/COMMIT ошибка MERGE после обнуления emb оставляла бы дыру; **межпачечный** обрыв этой защитой не покрыт.

### Якорь для правки L-mid

1. **Сразу после** `\gexec` пачек записи (`:1366`) и **до** anti-join DELETE (`:1371`): гейт/quality  
   `merge_emb_holes` = `count(emb IS NULL)` по строкам вне окна свежих маркеров (через `bridge_row_matches`) → `error(...)` или запись в `search_quality` + STOP такта.
2. **Ветвление DELETE** (1a): заменить `:1371-1374` на anti-join только `mode=full`; partial — только `deleted_gone∪expand` (закрывает R3.2).
3. Gone: писатели A уже в tx; L-mid-замок проверяет, что retry/новый такт не `DELETE FROM search_changed_rows` по gone до успешного merge (grep pipeline/apply).

Сейчас между `:1366` и `:1371` — только комментарий; **вставки гейта нет**.

---

## Фикстуры

### Фикстура обрыва после N COMMIT-пачек (замок, не живой прогон)

**Файл:** `test_merge_mid_abort_lock.py`  
**Форма:** python-модель пачек + grep SQL (как `test_hash_kill_gate.py`).

**Вход модели:**

```text
jobs = [J0..J4]           # 5 пачек
committed = {J0, J1, J2}  # N=3 успели COMMIT
# для строк пачек J0..J2: content новый, emb=NULL на hash_change
# маркеры: только ключи дельты D; строки вне D с emb=NULL = «дыры»
holes_outside_markers = count(emb IS NULL ∧ ¬bridge_match(маркеры))
```

**Ожидание R3:**

| Проверка | PASS | FAIL (текущее дерево) |
|---|---|---|
| (1) дыры | `holes==0` **или** в merge есть `error(`/`search_quality` якорь `merge_incomplete`/`emb_holes` **до** следующего такта | дыры >0 и нет STOP/quality-якоря в SQL |
| (2) anti-join | при модели `mode=partial` повторный DELETE не трогает ключи ∉ gone∪expand | grep `:1371` без `\if`/CASE по mode — FAIL до 1a |
| (3) gone | маркеры `deleted_gone` остаются в модели state после abort | если модель «очистили rows» — FAIL |

**Grep-минимум (статическая часть, без движка):**

- `BEGIN;` + `COMMIT;` в генераторе пачек merge;
- отсутствие resume-флага сейчас → ветка «должен появиться» (после внедрения — assert на подстроку);
- anti-join и `mode` в одном файле после 1a.

Живой kill mid-`gexec` — **приёмка выката**, не замок коммита (как DML-фикстура packet в плане A).

### Фикстуры L0 / L4(а)(б) (кратко)

- **L0:** таблица `tmp3_build(mode)` + флаг `partial_rebuild` → ожидаемый STOP/PASS (зеркало SQL `:126-129`).
- **L4(а):** `mode=full`, `|tmp3| << |corpus∩entity|` (или явный expected_full_count) → STOP; полный стейдж → PASS.
- **L4(б):** `mode=NULL` при непустом наборе → STOP (уже близко к runtime build).

---

## Пробелы

1. **Нумерация канона:** repost `:588-595` → факт `:597-604`; COMMIT `:1347-1365` → факт `:1290-1366` (ord=90 на `:1360`). Обновить 1∥3-B п.5–6.
2. **Формула repost→bridge не специфицирована:** направление аргументов, выбор `n_seg` при fold (`n_seg=1` ломает `guid|N`), поведение без `key_cols`. Без этого исполнитель сделает наивный swap и получит ложные transport-STOP.
3. **L4(а) — только текст плана:** runtime STOP «частичный стейдж у mode=full» в дереве отсутствует; критерий «неполный стейдж» без запрещённого «корпус⊃tmp3» не зафиксирован SQL-ом.
4. **L0 «полный»:** каркас в `test_changed_rows_lock` есть; семантическая фикстура STOP (FULLB 0e→1d) — нет отдельным артефактом.
5. **L2 / L-mid:** замков нет; R3.1 не имеет SQL-якоря между `\gexec` пачек и DELETE.
6. **L3 в 1d канона FULLB vs урезанный список 1∥3-B п.6 (L0,L2,L4):** кто несёт gone-фикстуры mid-abort — не сказано.
7. **emb_xfer `:1393+`:** канон L-mid говорит про COMMIT-пачки merge; xfer — вторая поверхность дыр без tx; в п.5 1∥3-B не упомянута.
8. **Сентинель full и repost:** ожидаемо не объясняет; канон не говорит, нужен ли отдельный класс quality при full+пропажа движений (сейчас — transport-STOP).
9. **Приёмка vs замок:** «фикстура обрыва после N COMMIT» в каноне смешивает живой kill и оффлайн-замок — развести (как A: замок grep + живая приёмка отдельно).

---

## Вердикт

1. **repost:** якорь правки `corpus_merge.sql:602-604`; замена на `bridge_row_matches` обязательна по канону B, но **только** с явной формулой `(key_text, rec, n_seg)` и правилом n_seg для fold+line; иначе регресс классификации.
2. **Замки 1d:** L0 runtime + каркас grep — **есть**; L4(б) runtime + каркас — **есть**; **новые обязательны:** L0-семантика, L2, L4(а), repost-bridge, L-mid. Форма — существующие `test_*_lock.py`.
3. **L-mid:** тихий resume — **межпачечный COMMIT** `:1290-1366` (главный якорь) + полный anti-join `:1371` (R3.2 после 1a) + опционально emb_xfer. Гейта дыр после `\gexec` **нет**.
4. **Фикстура обрыва:** оффлайн-модель N COMMIT + assert R3.1–3 + grep будущих якорей; живой kill — только приёмка выката.
5. **Канон:** обновить номера строк; дописать формулу bridge для repost и SQL-критерий L4(а)/L-mid до кода пакета B.

**Блокер внедрения B по этой линзе:** не сторож A (уже зелёный), а спецификация `n_seg` для repost и отсутствие L-mid/L4(а) якорей в SQL — иначе замки не к чему привязать или привяжут ломающий diff.
