# Аудит T1-C3: безопасность векторов и целостность данных

Дата: 2026-09-02. Контекст нулевой. Серверы не трогались. Код/план не правились
(кроме этого отчёта). Источники: `docs/audit/TAKT_SPEED_PLAN_2026-09-02.md`,
`ubuntu/serenedb/{corpus_merge.sql,corpus_build.sql,build.sh}`, фон
`result-t1a3.md` / `result-t1a4.md` / `result-t1b3.md`, якоря v10 / FIX_PLAN этап 6.

Линза: **условие номер один — вектора не теряются**.

---

## 1. Пути потери векторов при исполнении плана

### 1.1 Смена `content_hash` / `row_key` (чанки+хвост vs монолит) → emb=NULL → GPU

**Механика по коду.** `content_hash = corpus_content_hash(doc)`, `row_key` из
keyed/`sha1(doc)` / `#`-суффиксов — в `p_doc` / `p_doc_finalize`
(`corpus_build.sql` ~1602–1762, 2084–2113). Селектор порции (`keyvals IN order`
или хвост) в формулу ключа/хеша **не входит** — план §2.6 верен; B1 п.5a это
подтверждал.

MERGE при том же `(src_table,row_key)` и **другом** `content_hash` делает
`emb=NULL` unless `corpus_bmap_common_eq` (`corpus_merge.sql:855`). Массовая
смена ключей → `unmatched_kill` / `hash_kill` в `tmp3_merge_vec_budget`
(:589–677) → гейт ДО записи (:688–714).

**Замок 2.5** — фикстура Python: multiset `(content_hash,row_key)` монолит ≡
чанки+хвост. Это доказательство **эквивалентности операторов**, не живого окна.

**Приёмка 3.4** сверяет md5 стейджа realiz / accum **в рамках такта №1**, но
текст не требует явной остановки **между** `corpus_build` и `corpus_merge`.
В `build.sh:296–337` шаги идут подряд: при расхождении multiset merge уже
может стартовать; спасает только `vector_loss_gate` (порог по умолчанию
**0.5%** ≈ до ~8k векторов до STOP — не «ноль»).

**Вердикт: ИСПРАВИТЬ.**

Правка в план:
1. Явно: **до первого MERGE** на окне — сверка multiset стейджа
   (`tmp3_corpus`) с эталоном `/tmp/takt-monolith-ref.txt` (или повторный
   монолитный прогон на копии); mismatch → **не звать** `corpus_merge.sql`.
2. Критерий приёмки: `vector_loss_gate` **и** `sum(векторов_умрёт)=0` (не
   «ниже tol»), плюс count(emb) ≥ baseline.
3. Замок 2.5 обязателен до выката, но **не** заменяет п.1.

Гарантии multiset «до применения merge к боевому» в текущем тексте плана —
**нет**.

---

### 1.2 Карта xfer / гейт vector_loss vs дифф этапа 1

**Этап 1** трогает только построение `tmp3_merge_unmatched` (резка по
`src_table` + `\gexec`, образец `:252–261`) и порядок
`edited_delta` **после** unmatched. Тело 6 анти-предикатов — без изменений
(план 1.1; B3: анти = **6**, не 7).

**Не в диффе этапа 1** (чтение кода):
- карта `tmp3_merge_emb_*` / `tmp3_merge_emb_xfer` — `:506–561`;
- бюджет / `MERGE_VECTOR_LOSS_*` / `tmp3_merge_vec_budget` — `:570–714`;
- MERGE/UPDATE пачки — `:739–882`;
- DELETE — `:887–898`;
- APPLY xfer — `:900–915`.

Эквивалентный UNION INSERT'ов unmatched = прежний SELECT → те же множества для
гварда, те же входы в rewrite_wave / xfer (xfer вообще scoped на
`tmp3_merge_rewrite_wave`, не на unmatched).

**Вердикт: ПРИНЯТЬ.** Этап 1 форму/гейт векторов записи не трогает. Замок M1
(множество unmatched == старой формуле) — обязателен как страховка
эквивалентности.

---

### 1.3 Порядок unmatched → edited_delta и «что удаляется»

**DELETE боевого корпуса** (`:887–890`) — анти-джойн
`search_corpus` ∉ `tmp3_corpus` по `(src_table,row_key)` для сущностей стейджа.
Список удаления **не читает** `tmp3_merge_unmatched`.

`edited_delta` / unmatched влияют на **`уйдёт`** в `tmp3_merge_ent_guard`
(`:201–219`: `уйдёт = unmatched − правок`) и на STOP частичной потери
(`:364–372`, порог 0.1%). Сейчас `edited_delta` строится **до** CREATE
unmatched (`:154–160` vs `:162`) — на повторном прогоне считает **вчерашний**
unmatched (A3/B3). Завышение «правок» → занижение `уйдёт` → **ложный пропуск**
STOP → DELETE по анти-джойну стейджа идёт при недооценённой потере. Занижение
правок → ложный STOP (для векторов безопасно).

План 1.2 переносит `edited_delta` после свежего unmatched — чинит именно этот
класс. На множество ключей DELETE это не влияет напрямую; на **разрешение**
записи — влияет.

**Вердикт: ПРИНЯТЬ** (фикс обязателен для безопасности гварда). Уточнение в
план одной фразой: DELETE keyed по стейджу; порядок чинит гвард «уйдёт/правки»,
не формулу DELETE.

---

### 1.4 Такт №2 сразу за №1 — лишний DELETE?

`SKIP_BUILD` (`build.sh:274–288`): корпус непуст ∧ `corpus_built_ts` >
`mart_changed_ts` ∧ `build_sql_hash` = md5(`corpus_build.sql`+`poc_load_entity.py`)
∧ на месте `tmp3_cls|ent|src|corpus` → **пропуск и build, и merge** — DELETE не
зовётся.

После зелёного такта №1 `corpus_built_ts` пишется только после удачного merge
(`:339–342`). При apply.timer стопнутом (план 3.3/3.6) `mart_changed_ts` не
растёт → такт №2 с тем же SQL → SKIP → доказательство «минуты / 0 изменений».

Если SKIP не сработал (FORCE / смена SQL / нет tmp3_*): полная пересборка
сущностей в `tmp3_build`; DELETE снова только ключи, которых нет в новом
стейдже. При эквивалентном multiset — удалений 0; emb при том же
content_hash+row_key не трогается (`:855`).

Оговорка: `SQL_HASH` **не включает** `corpus_merge.sql`. Выкат **только**
этапа 1 без правки build мог бы оставить SKIP=1 и не прогнать новый merge —
в пакете есть этап 2 (build) → хеш сдвинется на такте №1. Зафиксировать в
плане: первый такт после выката обязан идти с изменившимся `build_sql_hash`
или явным не-SKIP.

«Второй прогон считает корпус старым» — отдельной ветки нет: unmatched =
сироты относительно **текущего** стейджа, не «возраст» корпуса. Защита от
лишнего merge — `SKIP_BUILD`/`built_ts`, не семантика unmatched.

**Вердикт: ПРИНЯТЬ** с пометкой про состав `SQL_HASH` и стоп apply до конца
приёмки (уже в §3.3).

---

## 2. Приёмка §3.4 — достаточно ли контроля?

Сейчас: count(*) / count(emb), 2× md5 стейджа (realiz + accum),
`vector_loss_gate=0`, шаги 2–8, health.

**Дыры:**
- нет явного **pre-merge** стопа по md5 стейджа (см. 1.1);
- нет md5 множества **`row_key`** (в activeContext / v10 уже фигурировал
  keys-md5 — дешёвый ортогональный сигнал к паре hash\|key);
- нет сверки «дыры относительно бэкапа»:
  `LEFT JOIN backup … WHERE sc.emb IS NULL AND b.emb IS NOT NULL` → 0
  (образец `result-tf1-4.md`);
- `vector_loss_gate` в `search_quality` — число; лучше явно
  `sum(векторов_умрёт)=0` из `tmp3_merge_vec_budget` в журнал приёмки;
- search_quality smoke (`entity_emb_xfer:*`, tick) — дёшево, не заменяет
  multiset.

Полный L20 / search_quality регрессии — дорого; для **этого** пакета
достаточно дешёвых SQL выше. L20 — §3.7, после двух тактов — ок.

**Вердикт: ИСПРАВИТЬ.** Добавить в §3.4:
1. pre-merge md5 стейджа (или отдельный ручной барьер build→merge на такте №1);
2. md5 `string_agg(row_key ORDER BY row_key)` по realiz (и желательно accum);
3. anti-join к свежему бэкапу emb → 0 дыр;
4. `векторов_умрёт=0` (не только «gate в журнале»).

---

## 3. Рестарт / аборт посреди нового такта (чанки / хвост / merge)

**Что уже есть.** `tmp3_*` обычные, переживают рестарт (`corpus_merge.sql:19–21`).
Resume чанков: `tmp3_pdoc_progress` (`:1409`), окно 6 ч (`:1536–1538`), сброс
при смене formula (`:1444–1452`). `corpus_built_ts` не пишется при падении
build/merge — следующий такт не считает аварию успехом.

**Дыра A — хвост + finalize (новая).** Сейчас dup-сущности выкидываются из
chunks/formula (`:1531–1534`) → монолит без progress. План 2.1 **оставляет**
чанки и добавляет `p_doc_tail`. Диспетчер сегодня финализирует, когда
`rid_hi >= nrows` и `done_rows = nrows` по **диапазонам** порций (`:2198–2209`),
не по факту «хвост вставлен». Сценарий:
1. порции уникальной части дописаны, progress полный;
2. abort **до** `p_doc_tail`;
3. resume: порции пропускаются; finalize зовётся со stage без хвоста;
4. non-fold: `stage_gate` (`:2070–2077`) ловит `stage_rows <> nrows` — хорошо;
5. но хвост **сам** при resume может **не перезапуститься**, если нет маркера
   «tail done» / условия «stage не покрывает tail keys» → сущность зависает
   (plain запрещён при непустом progress/stage — v10 A.6 / `:2221–2226`).

Fold: `stage_gate` **не** сверяет stage_rows с nrows (`:2074–2077`) — план 2.4
усиливает; для векторов это **обязательный**, не опциональный пункт.

**Дыра B — частичный stage + финализация.** План 2.4 частично закрывает. Нужно
явно: finalize только если `stage_rows` покрывает unique∪tail (или
`done_rows` включает хвост **и** tail-маркер); иначе error, merge не звать
(свежесть `tmp3_run` — уже есть).

**Дыра C — аборт в merge после записи.** Сейчас OOM на unmatched **до** MERGE →
корпус/emb целы. Успех этапа 1 **впервые** доводит такт до MERGE/DELETE/xfer.
Порядок сейчас: DELETE (`:887`) **затем** APPLY xfer (`:900–915`) — окно K8 /
FIX_PLAN этап 6. План §8 BYPASS запрещает, но **xfer-before-DELETE не вносит**.
Mid-abort после DELETE до xfer = потеря векторов, которые карта уже «спасла» в
бюджете. Этап 6 FIX_PLAN отложен «после двух зелёных» — при **первом** зелёном
слиянии этого пакета окно открыто.

Рестарт движка между шагами план правильно не требует (B3: снос TEMPORARY
SECRET).

**Вердикт: ИСПРАВИТЬ.**
1. Спека resume для `p_doc_tail`: идемпотентный повтор, пока stage не содержит
   все keyvals хвоста; запрет finalize без хвоста.
2. §2.4 — must-have для всех путей, включая fold.
3. Перед первым боевым merge после этапа 1: либо interim
   MERGE→xfer→DELETE / pending (как FIX_PLAN 6 / activeContext), либо явное
   принятие риска + **свежий бэкап + отработанный restore** (п.4) + запрет
   kill/restart mid-merge.

---

## 4. Бэкапы

Существующие `backup_corpus_emb_20260902_1430` (src_table,row_key,emb) и
`backup_corpus_emb2_20260902_1500` (+content_hash), по 1 657 724 — снимок
**до** текущего/нового merge. Для отката emb по неизменным `(src_table,row_key)`
после неудачного merge (NULL emb) — пригодны. **Недостаточны** как единственная
страховка после **успешного частичного** merge, который уже записал новые
строки / снёс ключи / переложил emb: UPDATE-from-backup не вернёт удалённые
строки; INSERT из бэкапа в план не входит.

Свежий бэкап **непосредственно перед выкатом / первым merge** нового кода —
дешёвая обязательная страховка (векторы не пересчитывать).

**Вердикт: ИСПРАВИТЬ.** В §3.2–3.3 добавить шаг бэкапа. Образец SQL:

```sql
-- Свежий снимок emb перед выкатом плана C (имя с меткой времени).
CREATE OR REPLACE TABLE backup_corpus_emb_20260902_pre_takt_speed AS
SELECT src_table, row_key, content_hash, emb
FROM search_corpus
WHERE emb IS NOT NULL;

-- Контроль: должно совпасть с baseline окна.
SELECT count(*) AS n_emb FROM backup_corpus_emb_20260902_pre_takt_speed;
-- ожидание: >= 1657724

-- Restore-drill (только дыры, строго по ключу — НЕ по content_hash группам):
UPDATE search_corpus AS c
SET emb = b.emb
FROM backup_corpus_emb_20260902_pre_takt_speed AS b
WHERE c.src_table = b.src_table
  AND c.row_key = b.row_key
  AND c.emb IS NULL
  AND b.emb IS NOT NULL;

-- Проверка дыр относительно бэкапа:
SELECT count(*) AS holes
FROM backup_corpus_emb_20260902_pre_takt_speed b
LEFT JOIN search_corpus c
  ON c.src_table = b.src_table AND c.row_key = b.row_key
WHERE b.emb IS NOT NULL
  AND (c.row_key IS NULL OR c.emb IS NULL);
-- цель приёмки: 0
```

Старые ×2 держать до двух зелёных тактов (как activeContext); новый —
основной rollback этого выката. Fallback restore **только** по
`(src_table,row_key)`; по `content_hash` без `HAVING count(*)=1 AND
count(DISTINCT row_key)=1` — запрещён (v10 / tf2).

---

## Сводка вердиктов

| # | Тема | Вердикт |
|---|---|---|
| 1.1 | Multiset до merge / смена hash | **ИСПРАВИТЬ** |
| 1.2 | Этап 1 vs xfer/vector_loss | **ПРИНЯТЬ** |
| 1.3 | Порядок unmatched→edited_delta | **ПРИНЯТЬ** (с уточнением) |
| 1.4 | Такт №2 / SKIP_BUILD / DELETE | **ПРИНЯТЬ** (SQL_HASH) |
| 2 | Приёмка §3.4 | **ИСПРАВИТЬ** |
| 3 | Resume / stage_gate / mid-merge | **ИСПРАВИТЬ** |
| 4 | Бэкапы | **ИСПРАВИТЬ** |

Ни одного **ОТКЛОНИТЬ** по архитектуре V5-гибрида / резки unmatched: направление
верное, дыры — в барьерах до записи и в resume/хвосте/окне DELETE→xfer.

---

## Итог

**Вектора в этом плане защищены — НЕТ**

(нет pre-merge барьера multiset; resume хвоста недоспецифицирован; успех этапа 1
открывает существующее окно DELETE→xfer без FIX_PLAN-6; бэкап перед выкатом не
задан.)

**План готов к исполнению — НЕТ**

Готов после правок: §1.1 pre-merge, §2.3–2.4 resume/tail+stage_gate, §3.4
усиление приёмки, §3.x свежий бэкап+restore-drill, явное решение по окну
DELETE→xfer на первом боевом merge.
