# R4 — адвокат дьявола: дифф `ubuntu/serenedb/` (X1+X2)

Дата: 02.09.2026. Контекст нулевой. Серверы не трогались. Правки — только этот отчёт.

## Что реально проверяют замки

### `test_corpus_merge_unmatched_split.py` (M1)
- **Текст-греп:** empty CTAS, PREPARE, `$1`, NOT IN wave, `\gexec`, 6 anti-join, memory_limit/`\gset` без литерала GiB, порядок prepare < edited_delta < ent_guard.
- **Живой движок:** эквивалентность резки unmatched эталонному монолитному SELECT; wave→0; uniqueness; edited_delta свежесть; формула 0.55 memory_limit; пустая база.
- **Не ловит:** corpus_build / V5 / p_doc_tail / порядок wipe↔INSERT tail / атомарный `\gexec`-батч.

### `test_pdoc_tail_equivalence.py` (M2)
- **Текст-греп:** наличие PREPARE/таблиц, строка `BEGIN TRANSACTION; EXECUTE p_doc_tail(`, гейт `count(order)+collision_rows`, stage_gate без fold-исключения, lifecycle-иголки, ≥3 DELETE done.
- **Живой движок:** V5 multiset≡mono (есть уникальный остаток), fold stage_rows, incomplete→mono, oversize→mono, resume «маркер не раздувает» (но **не** боевой атомарный батч), fresh/formula wipe маркеров, без коллизий chunk≡mono.
- **Критический пробел:** живые прогоны зовут `EXECUTE` и `INSERT …tail_done` **раздельными** statements / отдельными строками `\gexec`. Боевая одна строка `BEGIN…;EXECUTE…;INSERT…;COMMIT` **никогда не исполняется**. Последовательность **INSERT tail → fresh-wipe (NOT on_) → dispatch** в боевом порядке файла **не прогоняется**. Кейс «все строки в коллизиях / order пуст» нет.

---

## Баги, которые замки не ловят

### BUG-1 (критично, корректность+живучесть): fresh-wipe стирает только что построенный `tmp3_pdoc_tail`

**file:line:** `ubuntu/serenedb/corpus_build.sql:1585-1593` (INSERT V5-хвоста) → затем `:1667-1669` (DELETE tail при `NOT on_`).

**Сценарий:**
1. Обычный «свежий такт»: `tmp3_pdoc_progress` пуст → `tmp3_resume_pdoc.on_ = false` (`:1617-1619`: нужно ещё и `progress>0`).
2. Блок решения пишет план в `tmp3_pdoc_tail` (`:1585+`), пишет `search_quality` `pdoc_tail:… path=v5` (`:1637+`).
3. Сразу после — lifecycle «как у stage»:  
   `DELETE FROM tmp3_pdoc_tail t WHERE EXISTS (chunks) AND NOT (SELECT on_ FROM tmp3_resume_pdoc);`
4. План хвоста уничтожен. Порции чанков читают только оставшийся `order` (уникальные keyvals). Диспетчер хвоста (`:2542-2548`) видит пустой `tmp3_pdoc_tail` → 0 вызовов.
5. `p_doc_finalize`: `stage_rows <> nrows` (`:2410-2412`) и/или неполный stage. При `ON_ERROR_STOP on` вокруг finalize — **падает весь `corpus_build.sql`**, не только сущность.

Категориальная ошибка: `tmp3_pdoc_stage`/`progress` — накопители рантайма (их fresh-wipe перед dispatch корректен); `tmp3_pdoc_tail` — **артефакт плана** (как chunks/order), его нельзя стирать тем же шагом после INSERT плана.

**Почему замок не ловит:** M2 `test_resume_and_fresh` зовёт wipe-SQL **изолированно** и радуется, что маркеры обнулились; не делает `decide → wipe(NOT on_) → chunk+tail+finalize`. Offline-греп даже **требует** needle fresh-wipe для tail.

**Фикс:** убрать `DELETE FROM tmp3_pdoc_tail` из блока `:1667-1669` (оставить wipe только `tmp3_pdoc_tail_done` + stage/progress). Сброс **устаревшего** плана — уже есть: formula-wipe `:1457-1460`, pre-decide `:1539`, mono-каскад `:1576`, post-finalize `:2569-2572`. Альтернатива: перенести INSERT в tail **после** fresh-wipe (после `:1672`), тогда wipe stage/done остаётся, план пишется один раз перед PREPARE/dispatch.

---

### BUG-2 (высокий риск живучести): атомарный `\gexec`-батч с явным `BEGIN/COMMIT` не проверен; при отказе — дыра идемпотентности

**file:line:** `corpus_build.sql:2542-2548`

**Сценарий:**
- Доки SereneDB (`Sql › Statements › Transaction Management › Multi-Statement Transactions`): несколько statements в одной посылке уже = **одна неявная транзакция**; ошибка откатывает батч.
- Явный `BEGIN TRANSACTION; …; COMMIT;` внутри такого батча либо избыточен, либо (типичный класс ошибок движков) даёт «cannot start a transaction within a transaction» → весь хвост падает на каждой V5-сущности.
- Если батч «молча» исполняет только первый statement / не атомарно (другая ветка протокола): stage получает хвост, маркера нет → при повторе повторный `p_doc_tail` дублирует stage → снова `stage_rows <> nrows`.

`quote_literal(t.tbl)` для имён 1С надёжен (совместимость `quote_literal` — да; кавычка в имени удваивается). Риск не в кавычках, а в модели транзакции батча.

**Почему замок не ловит:** M2 только грепает подстроку `BEGIN TRANSACTION; EXECUTE p_doc_tail(`; живые тесты шлют EXECUTE и INSERT **отдельно** (см. `_run_chunk_tail_finalize`).

**Фикс:** боевая строка = `EXECUTE p_doc_tail(…); INSERT INTO tmp3_pdoc_tail_done VALUES (…);` **без** BEGIN/COMMIT (атомарность — неявный multi-statement). Замок: один `\gexec`/`psql -c` с **той же** строкой, что в файле; плюс негатив «обрыв после EXECUTE» не оставляет stage без done. Живая проба BEGIN-варианта на 26.07.3 до выката.

---

### BUG-3 (средний, resume): pre-decide чистит `tail`, но не `tail_done`

**file:line:** `corpus_build.sql:1539` vs отсутствие симметричного DELETE done.

**Сценарий:** resume (`on_=true`), прошлый заход поставил `tail_done`, stage ещё жив, finalize не дошёл. `:1539` сносит ключи tail, V5 пишет их заново, done остаётся → диспетчер хвоста скипает (`:2545`). При целом stage — finalize ок. Если stage потерян иным путём (ручной DELETE, частичный сбой вне formula-wipe), а done жив — tail_gate/`stage_rows` ломают сущность навсегда до ручного сброса done.

**Почему замок не ловит:** resume-тест не комбинирует «done=1 + stage очищен + on_=true + полный decide из файла».

**Фикс:** при `:1539` (или в начале decide) для тех же `tbl` делать `DELETE FROM tmp3_pdoc_tail_done WHERE tbl IN (…)`, **либо** не трогать tail на resume, если formula/chunks не менялись. Согласовать с идемпотентностью маркера.

---

## Проверка минимума-кандидатов (не баги / ложные тревоги)

| # | Вердикт |
|---|---|
| 2. `tmp3_pdoc_collision` / JOIN `coll_keys` | **ОК.** `count(*)` по строкам order после JOIN по `IS NOT DISTINCT FROM`; не группы. Синтаксис `FROM tmp3_pdoc_order o` ×2 (keys + rows) корректен. |
| 3. Сущность вся в tail (order пуст) | **Не зависает.** `done_rows` = сумма **ширин** чанков (`:2553`), не вставок; progress доходит до nrows; tail кладёт все строки; finalize по `rid_hi/done_rows` срабатывает. Замок кейс не гоняет — регрессия желательна, но это не блокер. |
| 4. tail есть, chunks нет | При штатном каскаде mono/formula/finalize — симметрия DELETE. Guard `EXISTS(chunks)` на диспетчере ок. Отдельный баг — только если план/маркер разъедутся (см. BUG-1/3). |
| 5. `INSERT search_quality … UNION ALL` | **ОК.** Обе ветки с FROM; валидный SELECT. |
| 6. `cfg.chunk_cells >= e.ncols` | **ОК.** Оба места (`:1445`, `:1475`) согласованы. |

---

## Прочее (ниже порога «НЕТ», но зафиксировать)

- **M1 / merge:** резка unmatched и порядок edited_delta выглядят согласованными с эталоном замка; отдельных багов корректности в диффе merge не видно (memory_limit 0.55 — ортогонально V5).
- **Зеркало p_doc:** монолит по-прежнему без keyvals-UNPIVOT (все строки) — для mono-пути норма; INCLUDE NULLS добавлен в order/chunk/tail согласованно для ключа сортировки.

---

## Итог

**Дифф принять — НЕТ**

Причина: **BUG-1** на любом свежем такте с хотя бы одной V5-сущностью уничтожает план хвоста до dispatch → неполный stage / падение finalize / останов сборки. Пока wipe tail на `NOT on_` стоит после INSERT плана (или INSERT не перенесён ниже wipe) — выкат недопустим.

Минимум до повторного R: фикс BUG-1 + замок на боевой порядок `decide→(fresh wipe)→dispatch` с `on_=false` и ненулевым V5-хвостом; отдельно — живой прогон реальной строки диспетчера хвоста (BUG-2).
