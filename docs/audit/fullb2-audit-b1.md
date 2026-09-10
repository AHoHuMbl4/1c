# Аудит B1 (1a/1b)

Линза 1: семантика DELETE и гварды. Режим: только чтение. Дата: 10.09.2026.
Канон: `FULLB_1PAR3_PLAN` пакет B п.2–3; `FULLB_PLAN` §1.7 / этап 1 / §5.
Живой код: `ubuntu/serenedb/corpus_merge.sql` (1497 строк), `corpus_build.sql` (mode CTAS).
HEAD-контекст сессии: пакет A + Speed-II-2+0f+сторож A уже в дереве; `partial_rebuild=0`.

**Краткий вердикт:** цель 1a/1b ясна; якоря в коде найдены; **к детализации плана не готово** — канон не фиксирует формулу count-equivalence при partial, владельца множества gone∪expand (1a vs 1c) и судьбу текущего orphan-пути `tmp3_merge_deleted_delta_rows` при ветвлении. Плюс конфликт: канон требует `\if :partial_rebuild`, замок `test_changed_rows_lock.py` сейчас запрещает `\if` в merge/build.

---

## Якоря в живом коде

Нумерация канона устарела: DELETE был «:1250+» → сейчас **:1371–1374**; repost «:588–595» → **:597–604**; сторож A живёт **:123–130** (не «до vec-budget» абстрактно — конкретно после empty-build :117–121, до ent_counts :189).

| Правка | Файл:строка | Цитата (контекст) |
|---|---|---|
| 1a — рубильник (else = байт-в-байт) | `corpus_merge.sql:4–6` | `\set partial_rebuild 0` + комментарий «удаления по списку — будущая B» |
| 1a — anti-join DELETE (wipe неизменившихся) | `corpus_merge.sql:1371–1374` | `DELETE FROM search_corpus c WHERE c.src_table IN (…tmp3_corpus) AND NOT EXISTS (…tmp3_corpus…row_key)` |
| 1a — DELETE сирот источников | `corpus_merge.sql:1381–1382` | `DELETE … WHERE NOT EXISTS (SELECT 1 FROM search_sources s …)` — вне mode; не путать с anti-join |
| 1a — текущий «gone»-свидетель (НЕ маркеры) | `corpus_merge.sql:577–582` | `tmp3_merge_deleted_delta_rows` ← orphan_rec × doc_alive (витрина), **не** `op='deleted_gone'` |
| 1a — JOIN кандидата deleted_delta | `corpus_merge.sql:620–625` | `tmp3_merge_key_deleted_delta` ← `collapse_cand INNER JOIN deleted_delta_rows` |
| 1a — маркеры deleted_gone ещё не кормят DELETE | `corpus_merge.sql:525–527` | комментарий: полный свидетель `op='deleted_gone'` — «пакет полная B» |
| 1a — единственное чтение `:partial_rebuild` сегодня | `corpus_merge.sql:126–129` | сторож A: `WHEN :partial_rebuild = 0 AND EXISTS (… mode IS DISTINCT FROM 'full')` |
| 1a — `\if` отсутствует; замок запрещает | `test_changed_rows_lock.py:131–133` | assert `"\\if :partial_rebuild" not in merge` (CASE, не `\if`) |
| 1b — empty-build | `corpus_merge.sql:117–121` | `tmp3_build` без строк в `tmp3_corpus` → `error('…собрались пустыми…')` |
| 1b — rewrite-wave | `corpus_merge.sql:209–214` | `было>0 AND стало>=было AND (было-matched_exact)/было≥0.9 AND \|Δ\|/было≤0.05` |
| 1b — unmatched (anti-join корпус⊖стейдж) | `corpus_merge.sql:223–333` | `p_merge_unmatched` / `_period`: `NOT EXISTS`×5(+Period) по `tmp3_corpus` |
| 1b — гвард «удаление снесло бы >10%» | `corpus_merge.sql:688–709` | count(`tmp3_merge_unmatched`) минус key_form/wave/collapse/deleted_delta/shrink/repost |
| 1b — count-equivalence (после записи) | `corpus_merge.sql:1470–1478` | `в_корпусе <> собрано` по каждой `src_table` из `tmp3_corpus` |
| 1b — ent_counts (было/стало/matched) | `corpus_merge.sql:189–207` | база для wave/unmatched/guard; скоуп = сущности стейджа |
| mode CTAS (вход в merge) | `corpus_build.sql:1485–1528` | `WHEN :partial_rebuild = 0 THEN 'full'` … иначе bridge→`partial`/`full` |
| L4(б) | `corpus_build.sql:1541–1546` | `mode IS NULL OR mode NOT IN ('full','partial')` → STOP |
| Вектора: hash_kill → emb=NULL | `corpus_merge.sql:1311–1317` | `UPDATE … SET emb = NULL … content_hash IS DISTINCT …` (только ключи в пачке стейджа) |
| Вектора: rehash_gate | `corpus_merge.sql:1118–1146` | необъяснённый `hash_kill` vs `rehash_tol`; объяснение — `search_changed_rows`+`bridge_row_matches` (:1017–1028) |
| Вектора: die_unmatched (бюджет) | `corpus_merge.sql:954–960` | emb IS NOT NULL ∧ ключ ∉ `new_full` — сейчас = весь anti-join стейджа |
| Мост (для будущего expand) | `corpus_init.sql:129–149` | `bridge_row_matches(row_key, marker, n_seg)` — уже есть; DELETE им не пользуется |
| Repost (1d, не 1a/1b) | `corpus_merge.sql:597–604` | `op='delta'` + `key_text=rec OR starts_with(…\|)` — канон B п.6: → `bridge_row_matches` |

---

## Атаки и риски

### 1a — DELETE / mode

1. **Классический wipe (лишнее удаление).** Если при `mode=partial` anti-join `:1371–1374` останется включённым (баг ветвления, забытый entity в списке full, JOIN по `tmp3_corpus` вместо `tmp3_build.mode`), то все ключи сущности вне узкого стейджа уйдут из `search_corpus` вместе с `emb`. Это ровно диагноз FULLB_PLAN §1 п.2 (`merge УДАЛЯЕТ неизменившиеся`). Сторож A при `partial_rebuild=0` это не ловит — он только запрещает `mode≠full`, а не форму DELETE.

2. **Потеря строк (недоудаление / не тот мир ключей).** Канон 1a: partial-DELETE = gone∪expand строго по `op='deleted_gone'`. Маркеры — мир B (`key_text`); корпус — мир C (`row_key`). Без expand (канон относит fanout/⊆ к **1c**) наивный `row_key=key_text` или голый `starts_with` либо не снимет `#N`/ТЧ-потомков (мусор в корпусе), либо снимет чужие префиксы. **1a без спецификации множества DELETE = дыра:** либо 1a обязан включить минимальный expand-контракт, либо DELETE-ветка partial откладывается до 1c в том же выкате.

3. **Смешанный mode в одном такте.** CTAS уже умеет per-tbl `full|partial` (`corpus_build.sql:1488–1528`). Anti-join только full / gone∪expand только partial — два разных множества DELETE в одной сессии. Атаки: (а) родитель `full`, дочерняя ТЧ `partial` — anti-join шапки не трогает детей, gone-маркер только на Ref родителя без expand → сироты в корпусе; (б) наоборот — full-anti-join ТЧ при partial-шапке. Канон 1a не фиксирует порядок/один vs два DELETE и связь parent/child mode.

4. **Два «gone»-пути.** Живой `tmp3_merge_deleted_delta_rows` (:577+) — свидетель витрины (Recorder/Ref мёртв). Маркерный путь — `search_changed_rows`. При partial: если orphan-путь продолжает наполнять `key_deleted_delta` / исключать из «снесло бы», а фактический DELETE идёт только по маркерам — **гварды и DELETE расходятся** (PASS гварда + лишние строки, или STOP гварда при пустом marker-DELETE). Канон не говорит: orphan-путь при partial отключить / оставить только для full / объединить в одно множество.

5. **SKIP-такты (103–397 с) при текущем flip=0.** Else-ветка «текущий merge байт-в-байт» + сторож A (`mode` все `full` из R6) → путь `:1371–1374` и гварды без изменений. **SKIP зелёный сохраняется**, если правки 1a/1b строго внутри `\if :partial_rebuild` (или эквивалентного CASE) и не двигают else. Любая правка unmatched/wave «заодно» вне ветки ломает SKIP.

6. **Первый `flip=1` (`\set partial_rebuild 1`) без этапа 4.** CTAS начнёт писать честный `partial` (мост есть), а row-фильтр p_doc ещё нет → стейдж сущности часто **полный**, DELETE — только gone∪expand. Вектора соседей живут (недоудаление gone без маркеров — отдельный дефект полноты). Опаснее обратное: включить row-фильтр (этап 4) раньше ветвления DELETE — тогда partial-стейдж + старый anti-join = wipe. Канон пакета B порядок 1a→…→4→6 верный, но **явного предусловия «1a+1b зелёные оффлайн до любого flip»** в п.2–3 нет.

### 1b — гварды / mode

1. **count-equivalence `:1470–1478` убивает любой честный partial.** После gone∪expand + MERGE среза `|корпус(entity)| ≠ |tmp3_corpus(entity)|` почти всегда (соседи остаются). Без сужения предиката до `mode=full` (или до `markers∪tmp3`) **каждый partial-такт STOPит после записи**. Это блокер №1 для 1a: ветвить DELETE без 1b count-eq = зелёный путь недостижим. Канон 1b говорит «сузить по mode», но **не даёт SQL-предикат**.

2. **unmatched без сужения → ложный STOP «снесло бы» / ложная rewrite-wave.** `p_merge_unmatched` (:226+) для partial-стейджа объявит «уйдёт» почти все живые ключи. Гейт `:688–709` (>10% корпуса) или ent_guard порог 0.1% — STOP. Wave (`:209–214`) при `стало≪было` обычно **не** сработает (`стало >= было` ложно) → путь в STOP, не в wave. Если же ошибочно сузить wave-условия «под partial», можно получить rewrite-семантику (уйдёт:=было) на урезанном стейдже.

3. **empty-build `:117–121` при delete-only дельте.** Сущность в `tmp3_build` с только `deleted_gone` и пустым `tmp3_corpus` — сегодня STOP «собрались пустыми». При partial это может быть легитимно (удалили всё затронутое, вставлять нечего). Если гвард не сузить — partial-gone-only невозможен; если снять для всех partial без замены — тихий пропуск сбойной сборки (нет стейджа и нет маркеров). Канон: «scope = маркеры∪tmp3» — для empty не расписан.

4. **Смешанный mode и глобальный 10%-гейт.** Гейт `:688–709` считает unmatched **по всему корпусу**, не per-mode. Одна крупная partial-сущность с несокращённым unmatched заливает долю >0.1 и стопит соседние full. Сужение unmatched per-entity по mode обязательно до агрегата.

5. **SKIP / flip=0.** При `partial_rebuild=0` все `mode=full` → гварды должны остаться семантически теми же. Риск: «сужение по mode» через JOIN `tmp3_build` меняет план/NULL-mode край и ломает байт-поведение else (например entity в стейдже без строки mode — L4(б) в build ловит, merge полагается на это).

6. **Vec-budget `die_unmatched` (:954–960) — сосед 1b/1c.** Даже если DELETE верный, бюджет увидит «смерть» всех emb вне partial-стейджа. Канон относит unexpected/gone_expand к **1c**, но 1b unmatched и die_unmatched — один антипаттерн: оба требуют одного и того же scope. Детализация 1b без стыка с 1c даст ложный STOP до записи.

---

## Вектора

**Святое:** при `mode=partial` строки с живым `emb`, чьих ключей нет в gone∪expand, не должны попадать в DELETE из `search_corpus`.

Доказательство по текущему коду (что именно угрожает):

| Путь | Строки | Что делает с emb | Влияние mode сегодня |
|---|---|---|---|
| Anti-join DELETE | :1371–1374 | Удаляет **строку целиком** (emb уходит) для ключей стейдж-сущности ∉ `tmp3_corpus` | Нет ветвления — при partial-стейдже это wipe |
| Sources-orphan DELETE | :1381–1382 | Удаляет строки источников вне `search_sources` | Не про mode; 1a не должен сюда лезть |
| `SET emb=NULL` до MERGE | :1311–1317 | Обнуляет emb при смене content_hash/bmap на **совпавшем** row_key | Только ключи в пачке `tmp3_corpus` — вне дельты не трогает |
| rehash_gate / die_hash_unexplained | :1017–1146 | STOP до записи при массовой смене текста без свежего маркера | Маркеры уже объясняют hash_kill; DELETE не нужен |
| die_unmatched в vec-budget | :954–960 | Считает «смерть» emb ключей ∉ стейджа | Без 1c/сужения — ложный бюджет на partial |
| emb_xfer | :1389–1399 | Возвращает emb после смены ключа | Не удаляет; на partial не опасен сам по себе |

Инвариант для 1a (проверка детализации): partial-ветка DELETE = `search_corpus` ⋉ (expand(`deleted_gone`) ∩ entity), **без** `NOT EXISTS tmp3_corpus`. Пока anti-join в partial жив — святое нарушено. Else при `partial_rebuild=0` сохраняет текущий full-anti-join (легитимные gone 1С через витринный orphan-путь + anti-join).

`hash_kill` / `rehash_gate` — **не** DELETE: строка жива, emb пересчитает embed_bulk. Режим partial на них влияет косвенно (меньше ключей в `new_full` → меньше hash_kill, больше ложный unmatched_kill).

---

## Уже в дереве

Повторно внедрять в пакете B (1a/1b) **не нужно**:

1. **0f + R6:** колонка `mode` в CTAS `tmp3_build` (`corpus_build.sql:1485–1528`), interim `full` при `:partial_rebuild=0`.
2. **L4(б)** сразу после CTAS (`:1541–1546`).
3. **Сторож A** в merge (`:123–130`) до vec-budget.
4. **Dual `\set partial_rebuild 0`** в build+merge + потребление через CASE (не «мёртвая константа» из старого FULLB_PLAN §1 п.2 — устарело на 10.09).
5. **Speed-II-2:** `tmp3_infra_scope`, numhint-кэш, wipe-гард, фазовые метки (см. `SPEED2_0F_PLAN`) — зоны не пересекаются с DELETE-ветвлением.
6. **Пакет A «Писатели»:** `poc_load_entity._upsert_changed_rows` → `delta` / `deleted_gone` / `full` (`*`); packet/sync-контур пишет rows (маркеры копятся; merge DELETE их ещё не ест — `:5`, `:525–527`).
7. **Мост `bridge_row_matches` / `bridge_norm`** в `corpus_init.sql` — для 1c/1d и объяснения hash_kill; не дублировать.
8. **rehash_gate / die_hash_rows** — защита от массовой смены канона; 1a не заменяет.

---

## Пробелы

Явные дыры канона именно для 1a/1b (не «хотелки»):

1. **Формула count-equivalence при partial** — не задана (какие множества равны: корпус vs tmp3? vs markers∪tmp3? только mode=full?). Без неё 1b не детализируется.
2. **Владелец множества DELETE gone∪expand:** 1a требует DELETE по нему; 1c (fanout-cap, ⊆ витрина, STOP до записи) определяет его. Нужна явная норма: «1a+1c одним выкатом» или «1a partial-DELETE = stub STOP until 1c».
3. **Судьба `tmp3_merge_deleted_delta_rows` / orphan-витринного пути** при `\if partial` — отключить / только full / merge в одно множество с маркерами.
4. **empty-build при delete-only** — легитимный partial или STOP; замена-предикат.
5. **Конфликт `\if` vs замок** (`test_changed_rows_lock.py:131–133` + SPEED2: «`\if` — пакету B/1a»). Детализация обязана снять/ослабить assert тем же коммитом, что вводит `\if` (или отказаться от `\if` в пользу CASE — тогда править текст FULLB_1PAR3 п.2).
6. **Смешанный mode parent/child** и число DELETE-statement’ов — не специфицировано.
7. **Предусловия выката 1a/1b:** оффлайн-фикстуры (partial стейдж + anti-join выключен → соседи с emb бит-в-байт; count-eq не STOP; empty+gone-only; mixed full/partial) **до** любого scp; связь с этапом 4/6a0 при flip — в п.2–3 пакета B не повторена.
8. **Замеры приёмки 1a/1b** отдельно от M1–M8 полного flip: канон пакета B даёт замеры для A, для B — нет чеклиста «1a/1b без flip».
9. **Устаревшие номера строк** в FULLB_1PAR3 (`:1250+`, `:588–595`, «частичный `\set` мёртв») — править при следующей правке плана, иначе исполнители сядут не туда.
10. **Стык 1b unmatched ↔ 1c die_unmatched** — один scope; иначе 1b «зелёный», vec-budget красный.

---

## Вердикт: не готово к детализации плана

Семантика цели 1a/1b (anti-join только `mode=full`; partial — DELETE только gone∪expand; гварды сузить по mode; else байт-в-байт) **согласована** с живым кодом и с диагнозом FULLB_PLAN §1.7. Якоря сдвинуты и зафиксированы выше.

**Блокер детализации:** пока в каноне нет (1) предиката count-equivalence для partial, (2) владельца/контракта множества gone∪expand относительно 1c, (3) правила для orphan-`deleted_delta` vs маркеры, (4) решения `\if` vs замок — писать пошаговый SQL-план опасно: получится либо wipe, либо вечный STOP на `:1470–1478` / unmatched / vec-budget.

Следующий шаг оркестратора: дописать канон B по пробелам 1–4 (короткая правка FULLB_1PAR3 / FULLB_PLAN), затем отдельная линза/детализация 1a+1b(+минимальный стык 1c для DELETE-множества) с оффлайн-фикстурами до выката.
