# Аудит P3

Срез: 10.09.2026. Линза P3: план пакета B v1 — секции **4. B4**, **5. B5**, **6. B6**.
Объект: `docs/audit/FULLB2_PLAN_2026-09-10.md` (v1).
Предшественник: `docs/audit/fullb2-audit-b3.md` (сверка дословно по 9 пробелам + вердикту).
Живые якоря: `corpus_merge.sql` repost `:597-604`, transport-STOP `:612-618`,
COMMIT-пачки `:1290-1366`, emb_xfer `:1393-1399`, зазор `:1366`→`:1371`;
мост `corpus_init.sql:129-150`; замки-образцы `test_hash_kill_gate.py`,
`test_corpus_bridge_lock.py`, `test_changed_rows_lock.py`.
Режим: **только чтение**; БД не трогалась, код не менялся, коммитов нет.
Проверка формулы — python-модель макроса (зеркало `test_corpus_bridge_lock.py`).

---

## B4 формула

### Вызов (направление — верно)

План: `bridge_row_matches(k.key_text, t.rec, n_seg_eff)` вместо
`(k.key_text = t.rec OR starts_with(k.key_text, t.rec || '|'))`.

Совпадает с b3: `row_key` = витринный `key_text` маркера, `marker` = `t.rec`
(Ref документа из `tmp3_merge_transport_defect`). Инверсия аргументов
(`bridge(t.rec, k.key_text, …)`) ломает line/hash-кейсы (проверено моделью).

### `n_seg_eff = greatest(len(key_cols), len(split(k.key_text,'|')))`

Сверка с ветками макроса `bridge_row_matches` (`corpus_init.sql:129-150`):

| Кейс | key_text | rec | key_cols | n_seg_eff | Ветка макроса | Результат |
|---|---|---|---|---|---|---|
| **(а)** line при fold | `guid\|4` | `guid` | 1 | `greatest(1,2)=2` | 3) `len(segs(marker))=1 < 2` → `starts_with(…, rec\|\|'\|')` | **true** (нужная) |
| (а) naive без greatest | то же | то же | 1 | 1 | 3 не срабатывает (`1 < 1` false) → ELSE | **false** — регресс vs сегодняшний `starts_with` |
| **(б)** объект при n_seg=2 | `guid` | `guid` | 2 | 2 | 1) точное `row_key = marker` | **true** |
| **(в)** `guid#sha` | `guid#sha` | `guid` | 1 или 2 | 1 или 2 | 1) `starts_with(row_key, marker\|\|'#')` | **true** (сегодня `starts_with(…\|\|'\|')` **терял**) |
| **(г)** точное | `guid` / `guid\|4` | = key_text | любой | ≥1 | 1) равенство | **true** |

**Вердикт по формуле:** семантика `greatest(…)` **верна** для (а)–(г); без
`greatest` fold+line ломается ровно как в b3. Исправление формулы **не**
требуется; требуется **дописать SQL-источник** `key_cols` и имя функции.

Дословно в EXISTS (стиль rehash `:945-946`, `:1021-1023`):

```sql
AND bridge_row_matches(
      k.key_text,
      t.rec,
      greatest(
        coalesce((SELECT len(kk.key_cols) FROM tmp3_key kk
                  WHERE kk.entity = lower(k.src_table)), 0),
        len(string_split(k.key_text, '|'))
      ))
```

Замечания к тексту плана B4:
- писать `string_split`, не `split` (живой SQL/макрос);
- `len(key_cols)` без JOIN/`tmp3_key` в EXISTS — исполнителю неоткуда взять;
- `op='delta'` и `k.src_table = t.doc_tbl` остаются как сейчас (`:602-603`).

Упрощение (эквивалентно на типичном `rec`=односегментный GUID): одного
`len(string_split(k.key_text,'|'))` хватает для (а)/(в)/(г); `greatest` с
`key_cols` не вредит и закрывает краевые `n_seg`>длины маркера — **оставить**.

### Регистр / `lower()`

Мост и нынешний `starts_with` — **case-sensitive** (b3 риск «регистр»).
`lower()` вокруг `key_text`/`rec` в repost **не нужен**: (1) та же поверхность,
что у текущего фильтра; (2) выравнивание регистра — контур apply/`meta_canon`,
не мост; (3) `lower()` только в repost разошёлся бы с rehash
(`bridge_row_matches(d.row_key, m.key_text, d.n_seg)` без lower).
Фикстура замка B6.5: пара `Guid` vs `guid` → false (как сейчас) — достаточно.

Сентинель `('*','full')`: фильтр `op='delta'` + `bridge(*, …)`/`bridge(нормальный,'*',n)` —
как в плане; transport-STOP задуман. OK.

---

## B5 SQL-формы

### B5.1 — гейт `merge_emb_holes` между `:1366` и `:1371`

Сейчас между `\gexec` и DELETE — только комментарий (b3 подтверждён).

**Мост-вызов (как rehash, не как repost):** корпусный ключ ↔ маркер:
`bridge_row_matches(c.row_key, m.key_text, n_seg)`.
**Окно свежести:** то же, что rehash `:1024-1026` —
`epoch(m.ts)::BIGINT > coalesce((SELECT v FROM search_quality WHERE k='corpus_built_ts' LIMIT 1), 0)`.

**Точная форма в стиле файла** (с обязательным сужением скоупа — см. атаку 3):

```sql
-- 🔴 L-mid (R3.1): после COMMIT-пачек, до anti-join. Тихий resume с
-- необъяснёнными дырами emb запрещён. Скоуп — только ключи ЭТОГО merge,
-- у которых пачка могла обнулить emb (hash_kill: content_hash сменился
-- относительно снимка до записи). Легитимные исторические NULL и чистые
-- INSERT с emb=NULL под шаг 5 / xfer — не STOP.
CREATE OR REPLACE TABLE tmp3_merge_emb_holes AS
WITH built AS (
  SELECT coalesce((SELECT v FROM search_quality
                   WHERE k = 'corpus_built_ts' LIMIT 1), 0)::BIGINT AS ts
),
nseg AS (
  SELECT entity, len(key_cols) AS n_seg FROM tmp3_key
),
fresh AS (
  SELECT m.src_table, m.key_text,
         coalesce(n.n_seg, 0) AS n_seg
  FROM search_changed_rows m
  CROSS JOIN built b
  LEFT JOIN nseg n ON n.entity = lower(m.src_table)
  WHERE epoch(m.ts)::BIGINT > b.ts
),
-- снимок «был emb» обязан быть снят ДО \gexec пачек (см. ниже); иначе
-- после MERGE отличить hash_kill-дыру от старого NULL нельзя.
killed AS (
  SELECT p.src_table, p.row_key
  FROM tmp3_merge_pre_emb p
  INNER JOIN tmp3_corpus t
          ON t.src_table = p.src_table AND t.row_key = p.row_key
  WHERE p.had_emb
    AND t.content_hash IS DISTINCT FROM p.old_content_hash
)
SELECT c.src_table, c.row_key
FROM search_corpus c
INNER JOIN killed k ON k.src_table = c.src_table AND k.row_key = c.row_key
WHERE c.emb IS NULL
  AND NOT EXISTS (
    SELECT 1 FROM fresh m
    WHERE m.src_table = c.src_table
      AND bridge_row_matches(c.row_key, m.key_text, m.n_seg)
  );

SELECT CASE WHEN count(*) > 0
       THEN error('corpus_merge: merge_emb_holes=' || count(*)
                  || ' (emb=NULL после пачек вне свежих маркеров; L-mid/R3.1): '
                  || string_agg(src_table || ':' || row_key, ', '
                                ORDER BY src_table, row_key))
       END
FROM (SELECT src_table, row_key FROM tmp3_merge_emb_holes LIMIT 20) x;
```

Снимок **до** генератора пачек (`:1290`):

```sql
CREATE OR REPLACE TABLE tmp3_merge_pre_emb AS
SELECT c.src_table, c.row_key,
       (c.emb IS NOT NULL) AS had_emb,
       c.content_hash AS old_content_hash
FROM search_corpus c
WHERE c.src_table IN (SELECT DISTINCT src_table FROM tmp3_corpus);
```

План v1 («count(emb IS NULL вне свежих маркеров)») **без** `killed`/`pre_emb` —
неполон: см. «Атаки» §3. Это блокер спецификации B5.1, не мелочь.

**Стоимость на полном такте.** Скоуп `emb IS NULL ∩ killed` (не весь корпус):
на okna сейчас ~7703 NULL всего; `killed` ≪ этого на тихом такте (0 изменений)
и ограничен hash_kill этого прогона. `NOT EXISTS` + bridge по маркерам окна —
тот же класс, что `die_hash_unexplained` (уже живёт до записи). Полный seq-scan
1.67M **не** нужен, если гейт идёт от `killed`/`tmp3`, а не от
`FROM search_corpus WHERE emb IS NULL` без фильтра.

### B5.2 — обёртка emb_xfer в BEGIN/COMMIT

**Сейчас (`:1389-1399`):** одна нумерация `tmp3_merge_emb_xfer_n`, затем `\gexec`
генерирует **только** UPDATE по 1000 строк — **без** BEGIN/COMMIT:

```1393:1399:ubuntu/serenedb/corpus_merge.sql
SELECT 'UPDATE search_corpus SET emb = x.emb FROM tmp3_merge_emb_xfer_n x '
       || 'WHERE search_corpus.src_table = x.src_table AND search_corpus.row_key = x.row_key '
       || 'AND search_corpus.emb IS NULL AND x.n >= ' || (b * 1000)
       || ' AND x.n < ' || ((b + 1) * 1000) || ';'
FROM (SELECT i AS b FROM range(0, (SELECT ceil(count(*) / 1000.0)::BIGINT
                                   FROM tmp3_merge_emb_xfer_n)) t(i)) z
\gexec
```

**Как обернуть (ord-схема как `:1290-1366`, не «пачка=одна строка с тремя `;`»):**

```sql
SELECT stmt FROM (
  SELECT b AS job_id, 0 AS ord, 'BEGIN;' AS stmt
  FROM (SELECT i AS b FROM range(0, (SELECT ceil(count(*) / 1000.0)::BIGINT
                                     FROM tmp3_merge_emb_xfer_n)) t(i)) z
  UNION ALL
  SELECT b, 1,
         'UPDATE search_corpus SET emb = x.emb FROM tmp3_merge_emb_xfer_n x '
         || 'WHERE search_corpus.src_table = x.src_table AND search_corpus.row_key = x.row_key '
         || 'AND search_corpus.emb IS NULL AND x.n >= ' || (b * 1000)
         || ' AND x.n < ' || ((b + 1) * 1000) || ';'
  FROM (SELECT i AS b FROM range(0, (SELECT ceil(count(*) / 1000.0)::BIGINT
                                     FROM tmp3_merge_emb_xfer_n)) t(i)) z
  UNION ALL
  SELECT b, 90, 'COMMIT;' AS stmt
  FROM (SELECT i AS b FROM range(0, (SELECT ceil(count(*) / 1000.0)::BIGINT
                                     FROM tmp3_merge_emb_xfer_n)) t(i)) z
) q ORDER BY job_id, ord
\gexec
```

«Просто пачки по 1000 в tx» = то же самое; ord-схема обязательна, потому что
живой `\gexec` так уже доказан на MERGE (multi-statement через отдельные stmt).
Checkpoint после xfer (`:1401`) можно оставить одним снаружи, как сейчас.

---

## B6 замки

| # | Имя (план) | Grep-якоря | Семантические ветки | Конфликт с существующими? |
|---|---|---|---|---|
| 1 | `test_changed_rows_lock.py` | заменить assert `:131-133` (`\if` запрещён в build∧merge) → merge: есть `\if :partial_rebuild` ∧ между `\else`…`\endif` anti-join байт-в-байт `:1371-1374`; **build** по-прежнему `\if` нет | dual `\set`, сторож A, L4(б), writers A — **не трогать** | Нет, если правка точечная. Риск: оставить запрет на build+merge одной строкой — сломает B1 |
| 2 | НОВЫЙ `test_merge_mode_lock.py` | сторож A до `tmp3_merge_vec_budget`; `\else`-anti-join; anti-pattern «корпус⊃tmp3» как L0 | L0: mode=partial∧flip=0→STOP; все full→PASS; L4(а): урезанный стейдж full→STOP; мёртвость partial-тел при flip=0 | Имя ≠ b3 (`…_mode_guard_…`) — OK. L0-каркас остаётся в changed_rows; семантика — здесь. Не дублировать противоречащий запрет `\if` |
| 3 | НОВЫЙ `test_merge_gone_expand_lock.py` | CTE-имена `gone_markers`/`gone_expand_raw`/`fanout_cap`/`gone_expand`; `error(` до MERGE; EXCEPT не COUNT | F1–F7 (b2); патология `*`; n_seg=0→пусто; само-объяснение FAIL | С `test_hash_kill_gate` / `test_corpus_merge_gone_register` — смежно, не конфликт; не копировать rehash-окна впустую |
| 4 | НОВЫЙ `test_merge_mid_abort_lock.py` | `BEGIN;`+`COMMIT;` в генераторе `:1290+`; якорь `merge_emb_holes`/`error(` между `\gexec` пачек и `DELETE FROM search_corpus`; после B1 — mode в anti-join | R3.1–3: J0..J4, committed={J0..J2}; дыры вне маркеров→STOP; retry∉gone∪expand; gone живы | Модель должна зеркалить **`ORDER BY job_id, ord`** (см. атаку 4), не «все BEGIN подряд» |
| 5 | `test_corpus_bridge_lock.py` | в блоке `tmp3_merge_repost_delta`: есть `bridge_row_matches(`, нет `starts_with(k.key_text` | guid / guid\|N / guid#sha / fold+n_seg_eff / `'*'`+op delta не классифицирует | Существующие ветки макроса не ломать; grep **скоупить** блоком repost (в init `starts_with` останется) |

**`test_changed_rows_lock` после правки `\if`-assert.** Файл читает целиком merge/build;
единственный assert про `\if` — строки 131–133 (+ комментарии 7–8, 111–113).
Остальные ветки (DDL rows, pipeline snapshot, dual `\set`, сторож A порядок,
L4(б), env-замок, poc/sync writers) от `\if` **не зависят**. Ломает другие ветки
только кривая замена вроде «разрешить `\if` везде» или удаление dual-`\set`.
Правильная замена: **build** — по-прежнему forbid; **merge** — structural B1.3;
обновить комментарий «CASE, не `\if`» → «merge: `\if` только вокруг DELETE».

**«14 замков»** в плане — размыто: в дереве `test_*_lock.py` в serenedb немного;
рядом живут `test_hash_kill_gate`, `test_*_merge_*`, `test_vector_budget_gate`.
Имеется в виду «прогон suite FULLB/merge до/после» — уточнить списком файлов
в B7, иначе исполнителю нечего гонять.

**Дыра vs b3:** отдельный **L2** (`test_merge_emb_delta_lock.py` — emb вне
маркеры∪tmp3∪gone_expand не трогать при partial) в таблице B6 **отсутствует**.
Частично пересекается с B6.4, но b3 требовал L2 отдельно от L-mid.

---

## Атаки

### 1. Мост в repost матчит слишком широко (префикс без `|`)

Макрос ветка 3: только `row_key = marker` ∨ `starts_with(…, marker||'|')` ∨
`starts_with(…, marker||'#')`. Строковый префикс `ab`↛`abc|…` отсечён
(замок bridge уже: «ложный СТРОКОВЫЙ префикс»). Модель:
`bridge('guidX|1','guid',2)=false`. **Атака закрыта макросом**; план B4 её не
открывает. Риск расширения — только если исполнитель подставит голый
`starts_with(key_text, rec)` без разделителя.

### 2. emb_xfer в tx — deadlock / долги

Порядок живой: MERGE-пачки → DELETE → xfer. Конкурентов-писателей корпуса на
такте нет (flock pipeline). Пачка 1000 emb-UPDATE в короткой tx — те же замки
строк, что сейчас без tx; deadlock маловероятен. Долг: обрыв **между**
COMMIT-пачками xfer → часть emb уже возвращена, часть NULL — идемпотентно
(`emb IS NULL` в UPDATE), шаг 5 досчитает; **хуже не становится**. Обёртка
полезна против обрыва mid-statement (редко) и единообразия с MERGE; не против
межпачечного abort (и не должна).

### 3. Гейт дыр на первом такте после выката B (легитимные NULL)

Прод: ~7703 `emb IS NULL` (activeContext), `rehash_gate=0`. Наивный
`count(emb IS NULL ∧ ¬bridge(свежие))` → **ложный STOP на каждом полном такте**,
включая первый после scp B (маркеров дельты нет / `'*'` мост не объясняет).
Также ловит легитимные INSERT с `emb=NULL` до xfer/шага 5.

**Как отличить свежие дыры от старых NULL:**
- снимок `tmp3_merge_pre_emb` до пачек (had_emb ∧ смена content_hash) → только
  hash_kill этого merge; **или**
- quality-флаг `merge_incomplete` в начале `\gexec`, снятие после успешного
  DELETE (+ опционально xfer); resume при флаге → STOP без счёта NULL.

План B5.1 обязан выбрать один скоуп до кода. Иначе B7 «count NULL ≡ базе»
конфликтует с гейтом, который сам же краснеет на базе.

### 4. Замок B6.4: модель обрыва vs реальный `\gexec` порядок

Живой генератор: `ORDER BY job_id, ord` → для каждого job: `0 BEGIN` → `1 emb=NULL`
→ `2 MERGE` → `3 maps` → `90 COMMIT` → `95 checkpoint`, затем следующий job.
Модель `committed={J0,J1,J2}` при kill перед J3 **верна**, только если симулирует
**целиком завершённые** job_id, а не «три COMMIT из перемешанных ord».
Ловушка: kill между `COMMIT` (90) и `checkpoint` (95) — данные уже стойки;
модель не должна требовать checkpoint для «committed».
Ловушка: после B5.1 гейт дыр стоит **после всех** job; mid-abort внутри `\gexec`
гейт **не** успевает — замок обязан различать (а) «в SQL есть якорь STOP до
следующего такта / на старте resume» и (б) «гейт после полного `\gexec`» —
второе ловит только completed-gexec с дырами, не kill mid-gexec (это приёмка
выката, как сказал b3 §9).

---

## Внесено/упущено из b3

Сверка 9 пробелов + 5 пунктов вердикта `fullb2-audit-b3.md`:

| # | b3 | В v1? | Где / комментарий |
|---|---|---|---|
| П1 | якоря `:597-604`, `:1290-1366` | **да** | шапка + B4/B5 |
| П2 | формула bridge + n_seg fold+line | **да** | B4 `n_seg_eff=greatest…`; не хватает SQL-источника `key_cols`/`string_split` |
| П3 | L4(а) runtime/критерий | **частично** | B6.2 замок есть; **SQL-якоря runtime L4(а) в секциях B1–B5 нет** (как в b3 — «только текст») |
| П4 | L0 семантика отдельно | **да** | B6.2 |
| П5 | L2 + L-mid якорь | **частично** | L-mid = B5.1+B6.4; **L2-замок выпал** |
| П6 | L3 gone / кто несёт mid-abort | **частично** | B6.4 п.3 «gone живы»; отдельный контур gone_register не уточнён |
| П7 | emb_xfer без tx | **да** | B5.2 |
| П8 | сентинель full / transport-STOP | **да** | B4 |
| П9 | замок ≠ живой kill | **частично** | B6=оффлайн; B7 не говорит «живой mid-gexec — только приёмка» |
| В1 | якорь правки 602-604 + формула | **да** | B4 |
| В2 | новые замки L0/L2/L4(а)/repost/L-mid | **почти** | нет L2; L4(а) только в замке |
| В3 | L-mid межпачечный + нет гейта сейчас | **да** | B5.1; скоуп SQL дырявый |
| В4 | оффлайн-модель N COMMIT | **да** | B6.4 |
| В5 | обновить номера + формулу до кода | **да** | v1 |

**Упущенное списком:**
1. Замок **L2** (`test_merge_emb_delta_lock.py` / секция) — нет в B6.
2. **Runtime SQL L4(а)** («урезанный стейдж у mode=full → STOP») — нет в B1–B5 (только замок).
3. B5.1: **скоуп дыр** (`pre_emb` / merge_incomplete) — не специфицирован; наивный count ломает прод с 7703 NULL.
4. B4: дописать **`tmp3_key` + `string_split`** в формуле (не только math `greatest`).
5. B6/B7: явный список suite «14 замков» + фраза «живой kill mid-`gexec` ≠ замок».
6. Усиление L4(б) «непустой tmp3 без mode» (b3) — в B6 не упомянуто (каркас уже в changed_rows).

---

## Вердикт

1. **B4:** формула `n_seg_eff = greatest(len(key_cols), len(split(key_text,'|')))`
   семантически **верна** для (а)–(г); `lower()` не нужен. Довести до
   copy-paste SQL с `tmp3_key`/`string_split`/направлением `(key_text, rec, …)`.
2. **B5.1:** место гейта верное; текст «count NULL вне маркеров» **опасен** —
   без скоупа hash_kill/`pre_emb` первый же такт после выката даст ложный STOP
   на легитимных NULL. Нужна SQL-форма со снимком до пачек (выше).
3. **B5.2:** ord-обёртка emb_xfer по образцу `:1290-1366` — верный путь;
   deadlock не блокер.
4. **B6:** таблица в целом стыкуется с b3; правка `\if` в changed_rows **не**
   ломает соседние ветки при точечной замене; **дырка — L2**; B6.4 обязан
   кодировать реальный `ORDER BY job_id, ord`.
5. **Готовность линзы P3 к показу владельцу:** B4 — почти (добить SQL-якорь);
   B5 — **нет**, пока не зафиксирован скоуп дыр; B6 — **нет**, пока нет L2 и
   уточнения L4(а) runtime vs только-замок.

**Блокер этой линзы:** не формула n_seg_eff (она сходится с макросом), а
неспецифицированный скоуп `merge_emb_holes` на корпусе с тысячами легитимных
`emb IS NULL`.
