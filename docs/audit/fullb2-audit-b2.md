# Аудит B2 (1c)

Срез: 10.09.2026. Линза 2: R1-комплект формулы
`unexpected = unmatched − gone_expand − xfer`.
Режим: **только чтение** кода/планов/замков; БД не трогалась, прогонов нет,
код не менялся.

Канон: `FULLB_1PAR3_PLAN_2026-09-10.md` пакет B п.4; `FULLB_PLAN_2026-09-03.md`
§1 п.7 (сторож A/B), этап 1c, §5; урок `HOW_NOT_TO.md` §3.113; живой код
`ubuntu/serenedb/corpus_merge.sql` (1497 строк), мост `corpus_init.sql`,
замок `test_hash_kill_gate.py`.

**Терминология (важно).** В живом merge «unexpected» **как идентификатор
отсутствует**. Ближайший аналог — колонка `векторов_умрёт` (= CTE
`die_unexplained`) гейта `vector_loss_gate`. Гейт `rehash_gate` /
`hash_kill_unexplained` — **ортогонален** (смена текста при живом row_key);
1c его не переписывает. Путаница «бюджет rehash = unexpected» в постановке
задачи — ложная: R1 бьёт в **vector-budget / unmatched**, не в rehash.

---

## Якоря

### 1. Где сейчас считается unmatched / «умрёт» / xfer

| Что | Где | Сейчас |
|---|---|---|
| `tmp3_merge_unmatched` (диагностика «уйдёт») | `:223-329` | anti-join корпус⊖стейдж; **не** формула бюджета |
| `tmp3_merge_emb_xfer` | `:844-855` | карта переноса emb по ch / refs+bmap |
| Vec-budget блок | `:864-1162` | STOP **до** MERGE/DELETE |
| `die_unmatched` | `:954-960` | `unmatched_kill` = emb-строки old без пары row_key в new |
| `die_unexplained` → `векторов_умрёт` | `:975-1011`, SELECT `:1047` | необъяснённый unmatched; **нет** `gone_expand` |
| `xfer` CTE | `:923-926` | считает `векторов_спасено_картой`; **не вычитается** из `векторов_умрёт` напрямую |
| `die_hash` / `die_hash_unexplained` | `:928-953`, `:1017-1028` | rehash; маркеры через `bridge_row_matches`; **не** 1c |
| Гейт 0.5% loss | `:1075-1110` | `sum(векторов_умрёт) / emb_total > tol` → `error()` |
| Гейт rehash | `:1118-1162` | отдельно; §3.113 |

Цитата — ядро бюджета (сейчас **нет** имён `unexpected` / `gone_expand`):

```954:1011:ubuntu/serenedb/corpus_merge.sql
die_unmatched AS (
  SELECT o.src_table, count(*)::BIGINT AS unmatched_kill
  FROM old_full o
  WHERE o.emb IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM new_full n
                    WHERE n.src_table = o.src_table AND n.row_key = o.row_key)
  GROUP BY 1
),
-- ...
die_unexplained AS (
  SELECT o.src_table, count(*)::BIGINT AS n
  FROM old_full o
  WHERE o.emb IS NOT NULL
    AND NOT EXISTS (... new_full по row_key ...)
    AND NOT EXISTS (... ch-баланс ...)
    AND NOT EXISTS (SELECT 1 FROM tmp3_merge_key_deleted_delta d ...)
    AND NOT EXISTS (SELECT 1 FROM tmp3_merge_key_collapse c ...)
    AND NOT EXISTS (SELECT 1 FROM tmp3_merge_rewrite_wave rw ...)
    AND NOT EXISTS (SELECT 1 FROM tmp3_merge_shrink s ...)
    AND NOT EXISTS (SELECT 1 FROM tmp3_merge_repost_delta r ...)
  GROUP BY 1
)
```

Объяснения сегодня — **свидетели сущности/класса** (membership в
`key_deleted_delta` / shrink / repost / collapse / rewrite + ch-баланс),
не row-level `gone_expand` по маркерам `deleted_gone`.

`grep gone_expand\|unexpected` по `corpus_merge.sql` → **0** (кроме
комментария `:526` про будущий свидетель `deleted_gone`).

### 2. Где DELETE (потеря emb вместе со строкой)

```1371:1382:ubuntu/serenedb/corpus_merge.sql
DELETE FROM search_corpus c
WHERE c.src_table IN (SELECT DISTINCT src_table FROM tmp3_corpus)
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table AND t.row_key = c.row_key);

DELETE FROM search_corpus c
WHERE NOT EXISTS (SELECT 1 FROM search_sources s WHERE s.src_table = c.src_table);
```

Сейчас: anti-join по **полному** стейджу сущности (mode-ветвления 1a **нет**).
`partial_rebuild=0` (`:4-6`); сторож A уже жив (`:123-130`).

До DELETE — обнуление emb при hash_kill внутри пачек MERGE (`:1311-1317`):
строка **жива**, emb=NULL → не «unexpected», а очередь embed; rehash-гейт
ловит необъяснённое **до** записи.

### 3. Gone / expand сегодня

- Мост `bridge_row_matches` / `bridge_norm`: `corpus_init.sql:123-150`
  (ветки точный / enriched LineNumber / объектный префикс).
- В merge мост зовётся **только** в `die_hash_unexplained` (`:1021-1023`).
- Механики `gone_expand` (множество row_key по предкам `op='deleted_gone'`)
  **нет**. Комментарий-намёк: `:523-527` («полный второй свидетель —
  search_changed_rows op='deleted_gone'»).
- `repost_delta` (`:597-604`) читает маркеры `op='delta'` + `starts_with`,
  **не** мост и **не** `deleted_gone` — соседний путь, не expand.

### 4. Куда вставлять cap-CTE (точка внедрения 1c)

Порядок канона: **cap + ⊆ проверка ДО DELETE**, в одном файле с формулой
unexpected (grep-замок).

Рекомендуемый блок — **внутри / сразу после** `CREATE … tmp3_merge_vec_budget`
(`:890-1073`), **до** `DELETE search_corpus` (`:1371`):

1. CTE `gone_markers` — свежие `search_changed_rows` где `op='deleted_gone'`
   и `epoch(ts) > corpus_built_ts` (то же окно, что rehash).
2. CTE `gone_expand_raw` — `old_full` ⋈ мост к маркерам; **запрет** при
   `n_seg = 0` / нет `key_cols` (тогда expand∅, сущность остаётся mode=full
   по 1a/2b — не здесь чинить mode, но вычитание = 0).
3. CTE `fanout_cap` — per-marker
   `COUNT(mart rows под предком)` через `query_table` / витринный ключ
   (НЕ константа, R8); строка expand допускается только если
   `|expand(m)| ≤ fanout(m)`.
4. CTE `gone_expand` = raw ∩ (есть предок) ∩ (cap OK) ∩ (пересечение со
   свидетелем витрины — row-level аналог `key_deleted_delta` / «строки нет
   в mart»).
5. Переписать `векторов_умрёт` /
   `unexpected = count(unmatched_kill_rows − gone_expand − xfer_explained)`
   как **множество** (EXCEPT), не три независимых COUNT (иначе двойное
   вычитание).
6. Отдельный `SELECT CASE … error(...)` на нарушения cap/⊆ — **до** первого
   MERGE (`:1290+`) и тем более до DELETE `:1371` (сейчас гейты loss/rehash
   уже стоят в `:1075-1162` — рядом).

`xfer_explained` уже материализован как `tmp3_merge_emb_xfer` / CTE `xfer`;
привязка к unmatched — только строки, чей **старый** ключ в unmatched и чей
контент уехал на новый ключ карты (не «все строки карты»).

### 5. Замок hash_kill (A4) — что уже ловит, чего нет для 1c

`test_hash_kill_gate.py`: модель `die_hash_unexplained` + окно ts; R4
`('*','full')` не объясняет; pathology `*|1` / `*#` — FAIL-closed на уровне
**модели замка**, не SQL-STOP в merge. **Нет** веток fanout / gone_expand /
unexpected / cap-CTE — расширение только пакетом B.

---

## Атаки

Минимум R1; каждая — путь «уменьшить unexpected → пропустить wipe».

### A1. Маркер-фальшивка + раздутый fanout (классика R1)

**Как.** В `search_changed_rows` свежий `(tbl, key_text=короткий_префикс,
op='deleted_gone')`. Ветка 3 моста (`len(split)<n_seg`) даёт
`starts_with(row_key, marker||'|')` → сотни/тысячи строк ТЧ/движений в
expand. DELETE (1a partial) снимает их с emb. То же множество вычитается
из `unmatched_kill` → `unexpected≈0` → гейт 0.5% PASS.

**Обход fanout-cap, если cap — константа/доля okna:** подобрать K маркеров
или один «широкий» GUID-префикс так, чтобы `|expand| ≤ K_const`, но ≫
реальной ТЧ. **Канон R1:** cap = `COUNT(mart rows под предком)` —
фальшивка без строк в витрине даёт cap=0 → любой expand >0 = STOP.

### A2. Предок-маркер есть, строк витрины под предком нет

**Как.** Gone уже применён к витрине (писатели A: persist ⊆ applied) →
маркер `deleted_gone` жив, `query_table` по Ref пуст → fanout=0. Если
expand строить из **корпуса** по мосту (а не из mart), получим ненулевой
expand при cap=0.

**Требование.** Cap+⊆ до DELETE: при fanout=0 expand обязан быть ∅;
ненулевой expand без mart-строк под предком → STOP. Пересечение со
свидетелем витрины (строка корпуса отсутствует в mart) — обязательный
AND, не OR с cap (P2 §3 п.1).

### A3. Двойное вычитание (строка ∈ gone_expand ∩ xfer)

**Как.** При наивной формуле
`count(unmatched) − count(gone) − count(xfer)` одна и та же физическая
потеря (или пара ключей) уменьшает бюджет дважды → `unexpected` занижен,
вплоть до отрицательного clamp в 0.

**Когда пересечение реально.** Редко на чистом gone (строка исчезла, xfer
обычно кормит *новый* ключ). Опасно при rewrite/key-form: old unmatched
объяснён и ch-картой, и ошибочно попал в expand (широкий маркер).

**Защита.** Множественная разность row_key (EXCEPT), не арифметика трёх
COUNT; замок: `gone_expand ∩ xfer_old_keys = ∅` или явный приоритет одного
класса.

### A4. Патологические row_key `*`, `*|1`, `*#…` в merge-контуре 1c

**Hash_kill (A4):** `bridge_row_matches('*|1','*',2)=true` — замок
`test_hash_kill_gate.py:211-218` фиксирует опасность ветки 3; продукт
не должен иметь такие row_key. SQL `die_hash_unexplained` патологии
**не** режет явно.

**В 1c / gone_expand:** если когда-либо появится `deleted_gone` с
`key_text='*'` или корпусный ключ `*|…`:
- сентинель `*` как предок → объектная ветка при n_seg>1 матчит `*|…`;
- expand может «объяснить» wipe; либо наоборот — ложный STOP.

**Требование.** В cap/expand CTE: `key_text`/`row_key` ∈ {`*`, префикс `*|`,
`*#`} → не expand, не вычитание (FAIL-closed), плюс grep/фикстура рядом с
hash_kill pathology.

### A5. Само-объяснение (запрещено каноном)

**Как.** Множество DELETE := gone∪expand; budget вычитает то же множество
как `gone_expand` без независимого свидетеля mart. Тогда любой успешный
DELETE «оправдан» собой → гейт 08.09 (ужесточённый unexplained) регрессирует
ровно в сценарий a4-R1.

**Канон.** Вычитание только при
`предок deleted_gone ∧ fanout-cap из витрины ∧ пересечение со свидетелем`;
множество DELETE **само** бюджет не кормит.

### A6. n_seg=0 / нет key_cols

`die_hash_rows` уже пишет `coalesce(len(key_cols),0)` (`:945-946`). При
n_seg=0 объектная ветка моста почти не открывается, но «expand запрещён,
mode=full» — правило **плана**, в SQL expand ещё нет. Внедрение 1c без
явного `WHERE n_seg > 0` в expand-CTE = дыра при пустом declared key.

---

## Пути потери векторов и STOP-точки

Инвариант: **любой путь, где unexpected уменьшается оправданием DELETE →
строка уходит из корпуса → emb пропадает навсегда** (не hash_kill: там
row_key жив).

| # | Путь | Где код | Emb | STOP до записи сейчас? |
|---|---|---|---|---|
| P1 | Anti-join DELETE unmatched (full стейдж) | `:1371-1374` | удалена со строкой | Да, если `die_unexplained` > tol (`:1084-1110`). Объяснённый deleted/shrink/repost — PASS намеренно |
| P2 | DELETE сирот источников | `:1381-1382` | удалена | Нет отдельного vec-budget на этот DELETE (сущность выбыла из sources) |
| P3 | Будущий 1a: DELETE gone∪expand при partial | ещё нет | удалена | Должен: cap+⊆ + unexpected-гейт **до** DELETE; иначе R1 |
| P4 | MERGE-пачка: UPDATE emb=NULL (hash_kill) | `:1311-1317` | NULL, строка жива | `rehash_gate` `:1131-1162` до MERGE; не unexpected |
| P5 | Тихий wipe через 1c без cap | будущего CTE | удалена | **Сейчас невозможно** (gone_expand нет). После 1c без R1 — дыра |

Порядок живых STOP до записи в `search_corpus`:

1. Сторож A mode (`:123-130`)
2. Дубли / масштаб / transport / ent_guard (раньше по файлу)
3. **Vec-budget** `векторов_умрёт` (`:1084-1110`)
4. **Rehash** `hash_kill_unexplained` (`:1131-1162`)
5. Затем MERGE-пачки → DELETE unmatched

§3.113: массовая смена **текста** (P4) ≠ wipe (P1). Само-объяснение wipe
через expand — тот же класс «бюджет врёт, вектора уже нет», что и обход
rehash full-сентинелем; поэтому R1 держит **свидетеля витрины**, а не
множество DELETE.

---

## Фикстуры

Целевой файл расширения: `ubuntu/serenedb/test_hash_kill_gate.py`
**(и/или `test_vector_budget_gate.py`)** — ниже **вход/ожидание**, не код.
Имена условные; семантика — R1 + 1PAR3 п.4.

### F1. Один Ref → expand > K% сущности → STOP до записи

- **Вход:** сущность `e`, N=1000 emb-строк корпуса; стейдж partial без этих
  строк (они «уйдут» unmatched); один маркер
  `(e, 'REF0', 'deleted_gone', ts>built)`; мост матчит M строк, M/N > K
  (K — порог фикстуры, напр. доля или просто M > fanout_mart);
  витрина под `REF0`: `fanout_mart = COUNT = 3` (три строки ТЧ), а expand
  моста дал M=400 (кривой/широкий match **в модели теста**).
- **Ожидание:** cap-проверка FAIL → STOP (модель `gate_fires` / аналог
  `error()`); в бюджет `gone_expand` **не** вычитается; `unexpected ≥ M`
  (или весь необъяснённый unmatched); запись корпуса не моделируется
  (STOP до).

### F2. Строка expand без предка-маркера → STOP до записи

- **Вход:** в кандидат-множестве «expand» есть `row_key=R` без
  `bridge_row_matches(R, m.key_text, n_seg)` ни к одному свежему
  `deleted_gone`; либо предок есть, но `op='delta'` / `op='full'`.
- **Ожидание:** ⊆-проверка FAIL → STOP; вычитания нет. PASS запрещён.

### F3. PASS только при fanout = COUNT(mart rows под предком)

- **Вход A (PASS):** маркер `(e,'REF0','deleted_gone')`; mart: ровно 5 строк
  с ключом/префиксом REF0; expand ровно эти 5 corpus row_key; все 5
  отсутствуют в стейдже; свидетель «нет в mart» согласован.
- **Ожидание A:** `gone_expand=5`; `unexpected = unmatched − 5 − xfer_set`;
  при остальном нуле — гейт не STOPит.
- **Вход B (FAIL):** те же 5 в expand, но `COUNT(mart)=4` или cap посчитан
  константой 999.
- **Ожидание B:** STOP / не вычитать.

### F4. Grep-замок «unexpected без cap-CTE в том же файле»

- **Вход:** текст `corpus_merge.sql`.
- **Ожидание:** если в файле есть идентификатор/комментарий-якорь
  вычитания `gone_expand` / колонка/`AS unexpected` / пересчёт
  `векторов_умрёт` через expand — в **том же файле** есть CTE/таблица
  cap (имя с `fanout`/`cap`/`gone_expand_cap`) и `error(` на нарушение
  cap/⊆ **выше** по тексту, чем `DELETE FROM search_corpus`. Отсутствие
  cap при наличии вычитания → FAIL замка.

### F5. Само-объяснение запрещено

- **Вход:** модель, где `delete_set == gone_expand_set`, но mart-свидетель
  пуст и/или fanout не считался из витрины.
- **Ожидание:** unexplained остаётся полным; STOP при превышении tol.
  Нельзя получить PASS только из равенства DELETE≡expand.

### F6. Pathology в expand (стык с A4)

- **Вход:** `row_key='*|1'` или маркер `key_text='*'` с `op='deleted_gone'`.
- **Ожидание:** не входит в `gone_expand`; не уменьшает unexpected; либо
  явный FAIL-closed до записи (согласовано с pathology hash_kill).

### F7. n_seg=0

- **Вход:** сущность без `key_cols` / `n_seg=0`, свежий `deleted_gone`.
- **Ожидание:** expand∅; вычитание 0; mode-full путь не маскируется
  «успешным» gone_expand.

---

## Пробелы

1. **Имени `unexpected` в коде нет** — канон 1c говорит на языке плана;
   живой столбец `векторов_умрёт`. При внедрении нужно явно: либо
   переименовать/добавить алиас в quality, либо закрепить в доке, что
   unexpected ≡ этот столбец после вычитаний.
2. **`gone_expand` полностью отсутствует** — только комментарий `:526`.
3. **Вычитание xfer из unmatched** в живом SQL **не** формулы 1c: xfer
   учитывается косвенно (ch-баланс / rewrite_wave reason), COUNT xfer не
   вычитается из `du.n`. Наивная арифметика 1c ≠ текущий `die_unexplained`.
4. **Свидетели сегодня entity-level** (`NOT EXISTS … key_deleted_delta` по
   `src_table`), R1 требует **row-level** ∩ mart. Перенос «сущность в
   deleted_delta ⇒ все unmatched объяснены» шире, чем gone_expand — при
   1c нельзя слепо удалить старые NOT EXISTS, не доказав покрытие.
5. **Порядок 1a ↔ 1c:** вычитание gone_expand осмысленно при DELETE
   gone∪expand; при текущем full anti-join и `partial_rebuild=0` введение
   только 1c без 1a меняет бюджет, не меняя множество DELETE — риск
   «бюджет зелёный, семантика partial ещё нет» / наоборот. Канон: 0f+A →
   1a/1b/1c вместе по смыслу.
6. **`repost` всё ещё `starts_with`, не `bridge_row_matches`** (`:600-604`) —
   пакет B п.6 (1d) обещает замену; до замены expand и repost — два
   разных мира матчинга.
7. **Порог K% в фикстуре F1** в каноне 1PAR3 сформулирован как «>K%
   сущности», но R8 запрещает константы с okna для **cap**. K% — только
   оффлайн-фикстура «раздутый expand», не runtime-порог вместо mart-COUNT.
8. **Grep-замок** не специфицирован до имени CTE — исполнителю нужно
   зафиксировать каноническое имя (`gone_expand_cap` / `fanout_cap`) в
   плане до кода.
9. **Двойное вычитание / EXCEPT** в плане 1c записано арифметикой COUNT —
   пробел формализма множеств (атака A3).
10. **`test_hash_kill_gate` vs vector_budget:** 1c по смыслу — vector-budget;
    расширение только hash_kill-файла без `test_vector_budget_gate.py`
    оставляет 63 ассерта бюджета слепыми к gone_expand (P2 уже сказал:
    расширять vector_budget в B).
11. **Окно ts для deleted_gone** в 1c каноне 1PAR3 не повторено явно
    (есть у rehash). Пробел: свежесть маркера для expand должна =
    `epoch(ts) > corpus_built_ts`, иначе старый gone объяснит новый wipe.
12. **Не смешивать с обучением rehash понимать `op='full'`** — прямо в
    «Чего НЕ делаем» 1PAR3 п.2; 1c не должен открывать этот люк «заодно».

---

## Вердикт

**Семантика 1c с R1-комплектом ещё не воплощена в коде.** Живой бюджет
потери — `die_unexplained` → `векторов_умрёт` со свидетелями
deleted/shrink/repost/collapse/rewrite/ch-баланс; `gone_expand` = 0
вхождений; формула `unexpected = unmatched − gone_expand − xfer` не
собрана. Rehash (`die_hash_unexplained`) ортогонален и ужесточён после
§3.113; 1c его не заменяет.

**Внедрять 1c безопасно только если одновременно:**

1. cap per-marker = `COUNT(mart)` (не константа);
2. вычитание только при `deleted_gone` ∧ cap ∧ свидетель витрины (AND);
3. cap+⊆ `error()` до DELETE (рядом с vec-budget, файл один);
4. запрет само-объяснения + фикстуры F1–F7 + grep;
5. разность множеств, не три COUNT;
6. n_seg=0 / pathology `*` → expand запрещён;
7. не трогать объяснение `op='full'` в rehash.

Без п.1–4 пакет B 1c = регрессия ужесточённого гейта 08.09 (a4-R1 /
plan-audit-p2 §3) — тихий wipe под нулевым unexpected.

**Статус к выкату 1c:** НЕ ГОТОВ (ожидаемо: код ещё full-B0 + писатели A;
якорные точки для вставки ясны — `:890-1073` + STOP до `:1371`).
