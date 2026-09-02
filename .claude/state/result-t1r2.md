# Красная команда R2 — дифф этапа 2 (`corpus_build.sql`) vs план v4 §4

Дата: 2026-09-02. Материал: `git diff ubuntu/serenedb/corpus_build.sql`, план
`docs/audit/TAKT_SPEED_PLAN_2026-09-02.md` §4, `git show HEAD:…/corpus_build.sql`,
замок `ubuntu/serenedb/test_pdoc_tail_equivalence.py`. Серверы не трогались; правки
только этот отчёт.

## 1. Таблица: пункт плана → в диффе → верно/нет

| Пункт | В диффе (file:line) | Верно? |
|---|---|---|
| **2.1** порядок гейтов: (в) неполный order → mono | `1541-1546`: `count(order)<>nrows` → `tmp3_pdoc_mono` **до** collision | **да** |
| **2.1** иначе collision_rows (не DISTINCT) | `1548-1568`: `coll_keys` HAVING count>1; `coll_rows` = `count(*)` строк order по `IS NOT DISTINCT FROM` | **да** |
| **2.1** (б) `tail_rows×ncols > chunk_cells` → mono + oversize | `1564-1573` + `1634-1636` `pdoc_tail_oversize` | **да** |
| **2.1** (а) V5: keep chunks/formula/entity; DELETE order только коллизии; tail DISTINCT keyvals | `1575-1599` (mono-каскад снимает чанкование; V5 INSERT+частичный DELETE) | **да** |
| **2.1** mono = полный каскад → диспетчер `p_doc` | `1575-1581` DELETE order/chunks/formula/entity (+tail/_done); mono вне chunks → `:2516-2520` | **да** |
| **2.1** visibility `tail_rows/nrows/ncols` при любом исходе | `1637-1649` mono_incomplete / mono_oversize / v5 | **да** |
| **2.1** coverage до диспетчера: `count(order)+collision_rows==nrows`; DISTINCT-форма запрещена | `1601-1612`; в гейте нет `count(DISTINCT …)` | **да** |
| **2.2** `PREPARE p_doc_tail` = зеркало chunk, фильтр только на tail | vs **нового** `p_doc_chunk`: после нормализации фильтра дифф **0 строк**; фильтр `2213-2216`. vs **старого** chunk: ещё `UNPIVOT INCLUDE NULLS` (автономное, см. §2) | **да*** |
| **2.3** tail `\gexec` после порций, до finalize | `2538-2550` → `2551-2561` | **да** |
| **2.3** одна строка `BEGIN…; EXECUTE p_doc_tail; INSERT done; COMMIT` | `2542-2543` | **да** |
| **2.3** lifecycle = progress/stage: formula / fresh / post-finalize | `1456-1464`, `1667-1672`, `2569-2572` | **да** |
| **2.3** finalize: tail без маркера → error | `tail_gate` `2415-2420` + `CROSS JOIN` `2454` | **да** |
| **2.4** stage_gate fold = nrows (без `NOT fold`) | `2406-2413`: всегда `stage_rows <> nrows` → error; снято исключение fold из HEAD | **да** |
| done_rows не тронут (порции) | finalize-диспетчер `2553-2560` как прежде | **да** |

\*Зеркало §2.2 выполнено относительно **текущего** chunk (арность `$1` vs `$1,$2,$3` — ожидаемо). Отклонение от буквы «только фильтр vs HEAD-chunk» = автономный UNPIVOT.

## 2. Оценка автономных решений X2

### (а) `UNPIVOT` → `UNPIVOT INCLUDE NULLS` (order-build + chunk/tail pre-pass)

**Где:** order `:1496`; `p_doc_chunk`/`p_doc_tail` `sort_cells` `:1956`/`:2186`.

**Контент корпуса (keyed/doc/content_hash):** путь `cells AS (… UNPIVOT …)` в `p_doc` / chunk / tail **остался прежним** (без INCLUDE NULLS) — `:1704`, `:1989`, `:2219`. Селектор порции не входит в row_key/doc/content_hash (план §2.6). **Контент не меняется этим решением.**

**Порционирование:** CASE `NULL→∅` в `string_agg` keyvals **без** INCLUDE NULLS почти мёртв (обычный UNPIVOT роняет NULL) → дыры в order / ложные коллизии / неполный order→mono. INCLUDE NULLS делает keyvals полной ширины ключа; order и chunk/tail pre-pass согласованы. Для **уникальных** keyvals фильтр `IN` по-прежнему 1:1 (одна группа → множество строк с тем же ключом только у коллизий, а они уходят в V5-хвост и вычищаются из order через `IS NOT DISTINCT FROM`). Задвоения chunk∩tail при штатном V5 нет.

**Вердикт:** принять. Это не «косметика», а выравнивание выражения keyvals с уже написанным `∅`; риск — смена множества mono/V5 vs старого UNPIVOT (больше полноты order), не порча cells-контента.

### (б) `cfg.chunk_cells >= e.ncols` вместо `floor(…/…)::BIGINT >= 1`

**Где:** `:1445`, `:1475` (оба места согласованы). `chunk_rows` по-прежнему `floor(chunk_cells/ncols)`.

**Эквивалентность:** для целых `chunk_cells≥1`, `ncols≥1` (есть `ncols>0`) — `floor(a/b)≥1 ⟺ a≥b` (проверка перебором 1..199: 0 расхождений). Комментарий про баг движка на `floor` в том же AND с `nrows*ncols` — правдоподобная мотивация.

**Следствия:** множество чанкуемых сущностей и `chunk_rows` те же; formula-строка не зависит от формы предиката. **Принять.**

## 3. Совместимость dup / resume

| Тема | Находка |
|---|---|
| `tmp3_pdoc_dup` | Теперь алиас mono `:1614-1615`. **Продакшен-читателей** `tmp3_pdoc_dup` вне этого файла нет (только аудит/state/промты). Согласовано. |
| `tmp3_resume_pdoc` / progress | Логика on_ / wipe stage/progress сохранена; добавлены зеркальные wipe tail/_done. Диспетчер порций и done_rows не ломались. |
| Пересборка tail на каждом прогоне | `:1539` стирает `tmp3_pdoc_tail` по order, **не** стирает `tmp3_pdoc_tail_done`. При `on_=true` и живом stage это согласовано с lifecycle (skip tail по маркеру). Отдельного wipe stage без done в файле нет → дыра узкая. |
| Formula id | Остаётся `v8b\|key_order\|cells\|ncols` — **не бампнут** под V5/INCLUDE NULLS. Resume через выкат при живом progress теоретически смешает старый stage с новым решением (операционный сброс §3.8 плана снимает; дисциплина «бамп при правке тела» — нет). |

## 4. Замок M2 — достаточно ли кейсов?

Покрыто живо/оффлайн по смыслу §2.5: V5+NULL→∅ vs mono multiset; coverage без count(tail); incomplete→mono; oversize+запись; stage==nrows (в т.ч. fold-попытка); resume не раздувает stage; fresh/formula wipe; unique без хвоста == mono; оффлайн-греп BEGIN/stage_gate/lifecycle.

**Дыры замка (против найденных рисков):**

1. Атомарность `BEGIN…COMMIT` **только грепается**; live-resume гоняет `EXECUTE` и `INSERT done` **раздельными** `\gexec` — обрыв «stage есть, маркера нет» замком не доказан.
2. Нет кейса keyvals класса «`|`» (пустые строки, не NULL).
3. Нет негатива: coverage-гейт обязан **упасть** при сломанном DELETE.
4. Нет явной проверки, что `cells`-UNPIVOT остался без INCLUDE NULLS / что INCLUDE NULLS не меняет multiset vs mono при тех же данных (косвенно есть через V5==mono).
5. Нет бампа/сброса formula на выкате V5; нет кейса «маркер есть, stage потерян».
6. incomplete-тест **переигрывает** гейт вручную после полного decide — не полный каскад продукта.

**Вердикт по M2:** на дыры п.13/скорости основные пути закрыты; **атомарность и `|`-класс — недостаточно**. Не блокер принятия **диффа кода**, но замок нельзя считать «зелёным закрытием §2.5» без доработки.

## 5. Найденные дефекты

| # | Место | Severity | Суть |
|---|---|---|---|
| D1 | `corpus_build.sql:1438` / formula `v8b` | **medium** | Семантика keyvals (INCLUDE NULLS) и ветка V5 меняют порционирование, formula id не бампнут → mid-resume через выкат без сброса progress/stage/tail рискован. План §3.8/дисциплина бампа частично закрывают операционно. |
| D2 | `corpus_build.sql:1539` vs `tail_done` | **low** | При пересборке tail не сбрасывается `tmp3_pdoc_tail_done`. Безопасно при синхронном lifecycle stage↔done; хрупко, если stage исчезнет иначе. |
| D3 | `test_pdoc_tail_equivalence.py` resume/atomic | **medium (замок)** | Не исполняет боевую BEGIN-строку; атомарность из §2.3/§2.5 не замерена. |
| D4 | тот же замок | **low (замок)** | Нет кейса `|` / негатива coverage / явного cells-UNPIVOT. |

Блокирующих дефектов реализации §2.1–2.4 в диффе **не найдено**. Автономные (а)(б) — корректны.

## 6. Итог

**Дифф этапа 2 принять — ДА**

(с сопроводительными D1–D2 к исполнителю/следующему кругу; M2 доработать по D3 до объявления замка зелёным по §2.5.)
