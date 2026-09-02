# R1: дифф этапа 1 (`corpus_merge.sql`) vs план v4 §3

Дата: 2026-09-02. Аудитор: красная команда R1 (только чтение `/srv/1c` + MCP docs; серверы не трогались; правки кроме этого файла — нет).

Материал: `git diff ubuntu/serenedb/corpus_merge.sql` (не закоммичен), `docs/audit/TAKT_SPEED_PLAN_2026-09-02.md` §3, HEAD `git show HEAD:ubuntu/serenedb/corpus_merge.sql`, `ubuntu/serenedb/test_corpus_merge_unmatched_split.py` (untracked), MCP `serenedb-docs` (limits / pragmas#memory-limit / oom / utility).

---

## Таблица: пункт плана → в диффе → верно/нет

| Пункт | Требование плана | В диффе | Верно? |
|---|---|---|---|
| **1.1 каркас** | `CREATE OR REPLACE TABLE tmp3_merge_unmatched AS SELECT c.src_table, c.row_key FROM search_corpus c WHERE false;` | `:209-210` дословно | **да** |
| **1.1 PREPARE** | `PREPARE … AS INSERT … SELECT`, предикаты :162-199 дословно, `src_table = $1` вместо `IN`, `NOT IN wave` в теле | `:212-247`; от `AND c.src_table NOT IN (wave)` до конца 6-го `NOT EXISTS` — **байт-в-байт** с HEAD; единственная замена — `IN (DISTINCT tmp3)` → `= $1` | **да** (сигнатура без `(tbl)` — косметика, см. дефекты) |
| **1.1 6 анти** | все 6 `NOT EXISTS` без потери/изменения | count=6; `FROM WAVE EQUAL: True` (сверка скриптом HEAD vs PREPARE) | **да** |
| **1.1 диспетчер** | `SELECT DISTINCT 'EXECUTE p_merge_unmatched('\|\|quote_literal(src_table)\|\|');' FROM (SELECT DISTINCT src_table FROM tmp3_corpus WHERE src_table NOT IN (wave)) t \gexec` | `:249-252` дословно | **да** |
| **1.1 fail mid-loop** | `ON_ERROR_STOP` → неполный unmatched не доходит до гвардов | файл уже `\set ON_ERROR_STOP on` на `:2`; после `\gexec` сразу `edited_delta`/`ent_guard` | **да** (механизм файла, не новый в диффе) |
| **1.2 порядок** | `edited_delta` после заполнения unmatched; читатели позже | unmatched→`\gexec`→`edited_delta` `:257`→`ent_guard` `:265`→`collapse_rec` `:300`→`delta_rec` `:343`→`key_deleted_delta`/STOP≈`:411-436`→`search_quality` edited `:438-442` | **да** |
| **1.3 memory_limit** | `current_setting` → CASE единиц → `floor(*0.55)` → та же единица → `\gset` → `SET memory_limit = :'ml';`; без литералов/box_tune; threads не трогать | `:8-58`; threads нет; литерала в SET нет | **да** на формате живого `current_setting` (`N.N GiB`); см. дефект D2 про `%` |
| **1.4 замок M1** | файл-тест по чеклисту §1.4 | `test_corpus_merge_unmatched_split.py` есть (??), покрывает ядро; дыры — ниже | **частично** (не блокер диффа SQL, но замок неполон) |

---

## Эквивалентность множества (п.2 аудита)

**Вывод: множество строк `(src_table, row_key)` совпадает** с монолитным HEAD-SELECT при том же состоянии таблиц.

| Кейс | Старый SELECT | Новый (диспетчер ∪ INSERT) | |
|---|---|---|---|
| сущность ∈ `tmp3_corpus` ∖ wave | попадает в `IN (DISTINCT tmp3)` + antis | EXECUTE на неё + те же antis | равно |
| сущность ∈ wave (и в tmp3) | `NOT IN wave` отсекает | нет в диспетчере; fail-safe в теле | равно |
| сущность только в `search_corpus`, не в tmp3 | нет в `IN` | нет в диспетчере | равно |
| `NULL src_table` в tmp3 | `IN`/`=` с NULL → строка не отбирается | `NULL NOT IN (wave)` = UNKNOWN → не в диспетчере | равно |
| дубли EXECUTE | — | `DISTINCT` в диспетчере | ок |

UNION INSERT'ов по сущностям ≡ фильтр `src_table ∈ (tmp3 ∖ wave)` плюс те же 6 анти-джойнов. Семантика «строка search_corpus orphan относительно tmp3» не менялась.

---

## Порядок читателей (п.3)

Все потребители `edited_delta` / `unmatched` ниже по файлу идут **после** нового `edited_delta` (`:257`):

- `ent_guard` `:265` (JOIN `ed`)
- `collapse_rec` `:300` ← `unmatched`
- `delta_rec` `:343` ← `unmatched`
- блок ≈старого `:411` (`key_deleted_delta` / STOP частичной потери / `entity_edited_delta` в `search_quality`) — `:405-442`

Порядок Д5 закрыт.

---

## memory_limit / psql / доки (п.4)

**SET/\gset:** `SELECT (…) AS ml \gset` + `SET memory_limit = :'ml';` — валидный psql: `:'ml'` подставляет строковый литерал (в т.ч. с пробелом: `'27 GiB'`).

**Доки (MCP):**

- `configuration/limits`: default memory use — «80% of RAM» (описание лимита, не формат строки).
- `pragmas#memory-limit` / `set#examples`: `SET memory_limit = '1GB'` / `'10GB'` — абсолютный размер.
- `cookbook/performance/oom`: для 50–60% нужен **абсолютный** размер; «percentage literal such as `'60%'` is not accepted» (для рекомендуемого SET-обхода OOM).
- `current_setting` — «return the current value»; формат строки для memory_limit в доках **не зафиксирован**.

**Живой зонд (локальный `serened shell`, не прод-сервер):**  
`current_setting('memory_limit')` → `50.0 GiB`; после `SET '10GB'` → `9.3 GiB`; после `SET '80%'` → снова абсолют `… GiB`. Процент в SET резолвится; **чтение — всегда с единицей GiB/абсолют**.

**Симуляция формулы на чужих строках:** `80%` → `44B` (ELSE); `6500MB` → `3575MB`; `50.0 GiB` → `27 GiB`. На реальном формате движка — ок; на литерале `%` — катастрофа (см. D2).

---

## Замок M1 (п.5)

Покрывает из §1.4:

| Требование | В тесте |
|---|---|
| множество == эталонной формуле (6 antis в ref SELECT) | `eq_ref` FULL OUTER JOIN |
| диспетчер == DISTINCT tmp3 ∖ wave | `dispatch == ent_a,ent_b` |
| wave → 0 | `wave0` |
| уникальность `(src_table,row_key)` | `uniq` |
| edited_delta от свежего unmatched | `ed1`/`ed2` после DELETE |
| пустая база не падает | `empty_ok\|0/0` |
| структурно: CTAS / PREPARE / `$1` / wave / `\gexec` / порядок / ml `\gset` | текстовые `t(...)` |

**Что добавить (рекомендации, не стоп SQL-диффа):**

1. Кейсы 6-го анти (Period + хвост Recorder) на сущности **вне** wave — сейчас `Period` только у `ent_wave`.
2. Кейсы hash/`#`/split_part `|` anti-match (не только orphan + edited-pair).
3. Прогон формулы ml на вход `'80%'` / неизвестный суффикс → ожидание `error` или явный отказ (сейчас только regex «есть единица»).
4. Реальный `SET memory_limit` + `current_setting` после SET (не только SELECT формулы).
5. Извлекать ml-SQL из файла, как PREPARE/edited — сейчас формула **продублирована** в тесте (дрейф).
6. Сверка текста PREPARE с `git show HEAD:…` (или снимок эталона) — сейчас эталон захардкожен; двойной дрейф HEAD↔тест↔PREPARE теоретически возможен согласованно.
7. `NULL src_table` в tmp3/search_corpus.

---

## Найденные дефекты

| ID | file:line | Суть | severity |
|---|---|---|---|
| D1 | `corpus_merge.sql:212` | План пишет `PREPARE p_merge_unmatched(tbl) AS`; в диффе без списка параметров. На SereneDB/`$1` работает; отклонение от буквы плана, не от семантики. | low |
| D2 | `corpus_merge.sql:20-49` | Неизвестный суффикс / `%` → ELSE считает число **байтами** и клеит `'B'` (`80%`→`44B`). На живом `current_setting` (GiB) не стреляет; доки описывают default как 80% RAM — латентный подрыв сессии при смене формата. Нет `error()` на bad unit. | **medium** |
| D3 | `test_corpus_merge_unmatched_split.py:239-287` | Формула ml скопирована, не извлечена из merge; нет негатива на `%`; Period-анти не упражняется. Замок §1.4 формально «есть», покрытие неполное. | low |
| D4 | — | `DEALLOCATE` перед PREPARE нет. Повтор merge в **той же** сессии упадёт на PREPARE. Такт обычно новый psql — риск низкий. | low |

**Не найдено:** потеря/изменение любого из 6 анти-предикатов; сдвиг `edited_delta` до unmatched; литерал GiB в SET; правка `threads`; расхождение множества unmatched vs HEAD-формула; читатели до нового edited_delta.

---

## Итог

**Дифф этапа 1 принять — ДА**

Обоснование: §1.1–1.3 воплощены по существу (каркас, дословные 6 анти, диспетчер ∖ wave, порядок edited_delta, session ml 0.55 через `\gset` без литералов). Эквивалентность множества с HEAD-SELECT держится. D2 — усиление на `%`/unknown unit желательно до выката, но на формате `current_setting` этой сборки (абсолют `N.N GiB`, подтверждено зондом) дифф не ломает такт. M1 закрывает чеклист плана с оговорёнными доработками замка.
