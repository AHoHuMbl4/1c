# ПЛАН: скорость и живучесть такта (Задание 1) — v4 (ФИНАЛ-КАНДИДАТ)

Дата: 2026-09-02. Статус: v4 — правки круга 3 (E1/E2/E4 «НЕТ» с адресными правками,
E3 «ДА»; все закрыты, спор об эталоне решён ДВУМЯ независимыми замерами).
Круги: A×4, B×4, C×4, D×4, E×4. Волна F — узкая сверка дельты v4.

## 0. Контракт

1. **Минуты** относятся к: (а) сборке сущности с коллизиями ключей (сейчас 5 ч);
   (б) регулярному такту при 0 изменений (такт №2). Первый такт после выката —
   SKIP_BUILD=0 (build.sh:253-288), scope = `tmp3_build` по инкремент-правилам
   (corpus_build.sql:1004-1013, 1336-1347), на окне ~30 сущностей, НЕ «все 351».
   **Предусловие (оркестратор, до сухого №0): сущности с коллизиями ∈ tmp3_build**
   — проверить отметки search_changed_sources (merge их не потреблял, :1003 не дошёл).
   «≲1 ч» — ОРИЕНТИР с разложением (пятёрка ~6 мин замер; V5-сущность ≈ минуты по
   аналогии; мелкие — десятки минут tf1; merge минуты; embed секунды при том же
   content_hash). Превышение → разбор по журналу. «До зелёного» ≈ две сборки
   (сухой №0 + юнит №1).
2. **Из коробки** (п.0): ни ручных шагов в продукте, ни env-флагов, ни литералов,
   ни имён сущностей в коде. Приёмка оркестратора — процедура проверки, не продукт.
3. **Вектора не теряются** — условие №1. row_key/content_hash существующих строк не
   меняются (v10 №1). Финальный допуск: 0 дырок на живых ключах (см. §3.5).
4. Молчаливая потеря строк = дефект (п.13). Считает база (п.19/20).

## 1. Диагноз (A+B подтверждают)

Д1 монолит p_doc (UNPIVOT 9.45M ячеек, 1 поток <122 880 row-group, unspillable
string_agg) · Д2 dup-гейт роняет сущность в монолит из-за коллизий keyvals · Д3 OOM:
6 анти-джойнов в одном CTAS unmatched · Д4 MERGE_CHUNK_ROWS не режет гвард · Д5
edited_delta до unmatched · Д6 продукт закрыт честным staleness-гейтом · Д7 апгрейд
движка класс не лечит.

## 2. Решение по движку

Не обновляем в этом пакете (Д7; B2). Вопрос владельцу после зелёного такта.

## 3. Этап 1 — починить слияние (OOM, Д3-Д5)

`ubuntu/serenedb/corpus_merge.sql`:

1.1 **Резка unmatched по сущностям**:
- `CREATE OR REPLACE TABLE tmp3_merge_unmatched AS SELECT c.src_table, c.row_key FROM
  search_corpus c WHERE false;` (схема из SELECT, пустой старт; приём уже в дереве —
  embed_missing.sql:108);
- `PREPARE p_merge_unmatched(tbl) AS INSERT … SELECT` — предикатная часть SELECT
  дословно из :162-199 (все 6 анти), `src_table = $1` вместо IN, фильтр rewrite_wave
  сохранён в теле (fail-safe);
- диспетчер: `SELECT DISTINCT 'EXECUTE p_merge_unmatched('||quote_literal(src_table)||');'
  FROM (SELECT DISTINCT src_table FROM tmp3_corpus WHERE src_table NOT IN (SELECT
  src_table FROM tmp3_merge_rewrite_wave)) t \gexec`;
- ошибка mid-loop валит такт (ON_ERROR_STOP) — неполный unmatched до гвардов не доходит.

1.2 **Порядок**: edited_delta — после заполнения unmatched (читатели :216/:218/:378 позже).

1.3 **memory_limit сессии merge**: `SET memory_limit = '<значение>'` — **строкой с той
же единицей, что вернул current_setting('memory_limit')**, масштаб 0.55 (доки
cookbook/performance/oom «50-60%»; раздел — в «Доки:» коммита). Снятие и пересчёт —
SQL CASE по суффиксу единицы, через \gset. Источник только current_setting;
box_tune.sh и литералы запрещены. threads не трогаем.

1.4 **Замок M1** `test_corpus_merge_unmatched_split.py`: множество == эталонной формуле
(:162-199 целиком в тесте); список сущностей диспетчера == DISTINCT tmp3_corpus ∖ wave
(пропуск ловится); wave → 0 строк; уникальность (src_table,row_key); edited_delta от
свежего unmatched; пустая база без tmp3_* не падает. Python — фикстура и сверки
запросами; строки корпуса вне SQL не идут.

## 4. Этап 2 — вернуть чанкование (скорость, Д1-Д2)

`ubuntu/serenedb/corpus_build.sql`:

2.1 **Перепись dup-блока (:1522-1534) — явная спецификация** (E4-Д1):
- **порядок гейтов**: (в) неполный order (`count(order) ≠ nrows`) → **mono**;
  иначе посчитать коллизионное множество и `collision_rows`; (б) `tail_rows × ncols >
  chunk_cells` → **mono** + `pdoc_tail_oversize` в search_quality; иначе (а) **V5**;
- **mono** = нынешний полный каскад: DELETE из order/chunks/formula/entity для
  сущности, диспетчер — `EXECUTE p_doc`;
- **V5** = сущность ОСТАЁТСЯ в chunks/formula/entity; из order удаляются ТОЛЬКО
  строки с keyvals ∈ коллизионному множеству; `tmp3_pdoc_tail(tbl, keyvals DISTINCT)`;
- при любом исходе — `tail_rows/nrows/ncols` в search_quality (видимость кейса
  «хвост 40%»);
- **гейт покрытия до диспетчера**: `collision_rows` считается ДО DELETE; после
  DELETE `count(order) + collision_rows == nrows`, иначе error(). Форма
  `count(order)+count(DISTINCT tail)` ЗАПРЕЩЕНА (класс "|" даёт nrows−2776+1).

2.2 **PREPARE p_doc_tail(tbl)** — тело p_doc_chunk (:1820-2044), фильтр порции заменён
на `kv.keyvals IN (SELECT DISTINCT keyvals FROM tmp3_pdoc_tail WHERE tbl=$1)`;
INSERT в tmp3_pdoc_stage; все строки группы — один батч.

2.3 **Диспетчер/идемпотентность**:
- done_rows не меняется; tail — отдельный \gexec-список ПОСЛЕ порций и ДО finalize;
- **хвост+маркер атомарны**: одна строка \gexec
  `'BEGIN TRANSACTION; EXECUTE p_doc_tail(…); INSERT INTO tmp3_pdoc_tail_done …; COMMIT'`
  (канон по докам Multi-Statement Transactions; обрыв откатывает оба, повтор чист);
  окно «stage есть, маркёра нет» закрыто;
- **жизненный цикл tmp3_pdoc_tail/_done = у progress/stage**: fresh (NOT on_,
  :1561-1567), смена formula (:1445-1452), после успешного finalize (:2211-2216);
  правка тела tail в будущем сопровождается бампом formula (дисциплина);
- finalize при непустом tail без маркёра → error().

2.4 **stage_gate** (:2070-2077): fold усилить до `stage_rows = nrows` (как non-fold).
done_rows остаётся проверкой порций в диспетчере. (Для chunk/tail-пути fold-QUALIFY
живёт в finalize :2112-2113 — равенство достижимо.)

2.5 **Замок M2** `test_pdoc_tail_equivalence.py` (фикстуры в движке): коллизии обычные
+ пустой keyvals («|», NULL→«∅»); дыры pos — полное покрытие; гейт покрытия в форме
§2.1г (collision_rows, не count(tail)); multiset (content_hash,row_key) финального
tmp3_corpus ПОСЛЕ finalize == монолитному p_doc; stage_rows == nrows; неполный
order → mono; oversize-хвост → mono + запись; resume не раздувает stage (атомарность);
сброс маркёров на fresh/formula; сущность без коллизий — байт-в-байт как до правки.

2.6 Семантика ключей не меняется (селектор не входит в row_key/doc/content_hash).

## 5. Этап 3 — выкат и приёмка

3.1 Красная команда на дифф → правки → замки локально зелёные.
3.2 Выкат serenedb-файлов в /opt/1c-mcp-reports, md5-сверка.
3.3 **Бэкап векторов до выката**: `CREATE OR REPLACE TABLE backup_corpus_emb_<дата>_
pre_takt AS SELECT src_table,row_key,content_hash,emb FROM search_corpus WHERE emb IS
NOT NULL;` контроль count ≥ 1 657 724. Restore-drill только по (src_table,row_key).
3.4 **Такт №0 (сухой)**: предусловие (коллизии ∈ tmp3_build, отметки стоят) →
`psql -f corpus_build.sql` → сверка multiset финального tmp3_corpus (после finalize)
с эталоном монолита:
- **document_реализациятмц: 74 982 / 57ad85decc6bd7405bde5f42d1fe68ec;
  accumulationregister_реализациятмц: 78 733 / bf9de8a65cd5023325c0f34bb6c64d5f.**
- **Обоснование эталона (два независимых замера, совпали)**: монолит завершился
  19:35:13 UTC 02.09 (журнал: «сборка завершена 1441514»), такт умер ПОЗЖЕ на
  merge-гварде, tmp3_corpus никто не трогал; замеры 20:04 и 20:26:30 UTC дали
  идентичные md5. tmp3_corpus монолита = вывод ПОСЛЕ внутреннего QUALIFY
  (:1815-1817 внутри INSERT) — 74 982 == витрина: для этой сущности fold-QUALIFY
  не сокращает (факт данных, не отмена QUALIFY; совпадение с витриной — свойство
  этой сущности, см. дрейф ниже). Контроль сравнимости: count витрины
  document_реализациятмц == 74 982 до и после (apply стопнут).
- **Дрейф «до»-корпуса (замер 20:26 UTC)**: doc — 637 ключей выбыло (перепроведения:
  row_key=sha1(doc) сменился), 0 смен content_hash при живом ключе; acc — 10 выбыло,
  554 смены content_hash при живом ключе. Ожидаемое поведение merge: 647 «законно
  умрёт» (пересчитает/заменит step 5), 554 обновится с emb→NULL→досчёт.
- **mismatch → merge не зовём**, разбор (M2 обязан поймать раньше).
- «До»-отпечаток корпуса: 74 785 / 71947efe… (takt-baseline.txt) — контроль перехода.
- multiset не включает emb.
3.5 **Такт №1** (юнит): критерии:
- corpus count(*) ≥ 1 665 427;
- multiset двух сущностей в финальном search_corpus == §3.4; keys-md5 в отчёт;
- **векторные критерии (переопределены по E2)**: (а) `векторов_умрёт` из
  tmp3_merge_vec_budget — ОТЧЁТНАЯ величина merge-фазы, ожидание ≈ 647±554-класс
  законного дрейфа, НЕ критерий зелёного; (б) **дырка = ключ бэкапа §3.3,
  присутствующий в финальном search_corpus, с emb IS NULL → 0** (после полного такта
  incl. шаг 5); чтение «только ключ» запрещено; (в) count(emb) ≥ 1 657 724; (г)
  departed-ключи (бэкап ∩ отсутствие в корпусе) — отчёт, ожидание ≈ 647, сверх —
  разбор (гварды ent_guard/STOP их ограничивают сами);
- шаги 2-8 зелёные, health tick ok; запрет kill/restart движка во время merge
  (окно DELETE→xfer K8 — принятый риск, лечит этап 6 FIX_PLAN; откат — бэкап §3.3).
3.6 **Такт №2**: минуты при ~0 изменений (SKIP_BUILD=1). SKIP не сработал → разбор
до таймеров.
3.7 **Таймеры**: включать ТОЛЬКО после зелёного №2; apply не включать между №1 и №2.
3.8 После сорванного №0: сброс tmp3_pdoc_progress/stage/tail/_done перед №1.
3.9 L20-ретейк (база «до» Задания 2).
3.10 Документы одним коммитом: CHANGELOG, activeContext, SCALE_BLOCKERS (OOM-merge
закрыт; новый пункт: pre-pass порций квадратичен — на 10-30× нужна полная B),
techContext (ловушка dup-гейта, V5-хвост, session memory_limit), RUNBOOK_DEPLOY
(unmatched режется по сущностям; MemoryMax не ставим).

## 6. Этап 4 — следующий пакет (НЕ в этом)

Полная B (row-level дельта, скелёт A4) + V3 (материализация keyvals). После зелёного
такта + L20, со своей армией.

## 7. Почему V5-гибрид, а не V1-pos

V1 требует детерминированного тай-брейкера коллизий между EXECUTE'ами порций
(row_number() OVER () :1844 ≠ order :1479; B1-№8) — без него п.13. V5 даёт полноту
существующими механизмами.

## 8. Чего НЕ делаем

- «Только этап 2» / «только этап 1» / «только memory_limit» (разобрано в C2/D2).
- V1-pos; рестарт движка между шагами; MemoryMax; MERGE_VECTOR_LOSS_BYPASS; апгрейд
  движка; V3/полная B в этом пакете.
- env-флаги, литералы под базу, имена сущностей в коде (числа §3.4/3.5 — только
  приёмочные артефакты оркестратора).
