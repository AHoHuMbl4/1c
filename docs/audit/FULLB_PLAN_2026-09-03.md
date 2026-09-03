# ПЛАН «Полная B» v4: row-level дельта такта (обязательный пакет, решение владельца №14 от 03.09)

v4.1 — микрокруг G (G1 ДА, G2 НЕТ, G3 НЕТ, result-g1..g3.md): секции этапов
переставлены в порядок исполнения 0→2→(1∥3); NULL-mode разведён по
ответственным (L4(б) всегда / A-L0 при flip=0); 0f — одним выкатом с Speed-II-2
(общий файл), сторож A только после 0f; артефакты 0b/0e-каркас; сторож B —
явный шаг 4e. v4 — финальный круг (F1 ДА, F2 НЕТ, F3 НЕТ, result-f1..f3.md): порядок
0→2→(1∥3)→4 (мост раньше merge-ветвления — №10); артефакт сдачи 0a; interim
mode='full' до моста (0f); определения gone_expand/xfer_explained по CTE (1c);
сторож B — целиком в 4d (1d); L4 переписан без запрещённого предиката; отчёт
режима — этап 1/M8, не 0e. v3 — правки по кругу 2 (P5 ДА, P7 ДА, P6 НЕТ + P8 НЕТ, result-p5..p8.md): сторож A
переписан через режимы (голый EXISTS был ложноположителен на легитимном gone —
поймали две линзы независимо); mode = один источник истины; формула unexpected;
барьер Speed-II-2 сужен до этапа 4; словарь mode един. v2 — правки по кругу P1-P4
(result-p1..p4.md, 4×НЕТ, сходимость правок подтверждена
перекрёстно). Открытие исполнения — ПОСЛЕ зелёного такта №2, выката этапов 4+3
Скорости-II (cb2d262) и L20-базы; этап 4 этого плана — дополнительно после
Speed-II-2 (§2).

## 0. Контракт и глоссарий

- п.0 по сути: большие таблицы меняются часто, монолитов на чужой базе десятки; такт
  пересобирает ТОЛЬКО изменённые строки. Вектора — условие №1: вне дельты emb не
  трогаем вовсе, в дельте — по content_hash.
- **Глоссарий (единые ярлыки, P4-§3):** `mode=full` — сущность в этом такте собрана
  ЦЕЛИКОМ (query_table без среза; merge — anti-join разрешён); `mode=partial` —
  собрана срезом по маркерам (merge — DELETE только gone∪expand); `entity-level` =
  mode=full. `table_full` — сентинель маркера «таблица целиком» ⇒ mode=full.
- **Рубильник — ОДНА форма: SQL-константа `\set partial_rebuild` в выкате**
  (стиль B0; откат = выкат файла, как обычный откат такта). Строка search_quality
  как выключатель — ЗАПРЕЩЕНА в этом пакете (два канала = рассинхрон, К1 по духу).
  Замок: единственный источник `:partial_rebuild`; в unit EnvironmentFile нет
  PARTIAL_*/MERGE_*.
- **Per-entity режим — обязательный сигнал build→merge (P2-§2, P4-§3):** таблица
  **колонка `mode` в самой `tmp3_build`** (единый CTAS — членство и режим атомарны
  в одном statement; отдельная таблица `tmp3_rebuild_mode` ЗАПРЕЩЕНА: два CTAS =
  окно рассинхрона — P10-§2): `partial` ТОЛЬКО если у таблицы есть разрешённые
  мостом ключи И она НЕ в tmp3_lag / rename>200 / child-of-lag / table_full /
  HTTP-без-rows; иначе `full`. **Один источник истины (P6/P8 круг 2):** mode —
  функция от (членство tmp3_build + маркеры + мост), вычисляется и пишется ТЕМ ЖЕ
  statement/tx, что tmp3_build (не «те же условия» вторым WHERE — это разные
  вопросы: «кого собирать» vs «как»; дубль условий = дрейф). **Отсутствие строки
  mode при непустом tmp3 сущности → STOP** (mid-abort build не оставляет
  неопределённый режим); инварианты замка: `mode=full ⇒ anti-join on, полный
  стейдж`; `mode=partial ⇒ стейдж только по ключам, DELETE только gone∪expand`;
  частичный стейдж у tbl с mode=full — STOP.
- **Introspection-чеклист (норматив, из AA4 §2.4, не ссылка):** Ref_Key+DataVersion
  без mix версий → HTTP-дельта, маркеры документные + expand; нет версий/дельта
  None → full + EXCEPT-проекция ключей или table_full; packet key_cols (+LineNumber
  enrich) → маркеры мир B уже пишутся; declared_key пуст/мешок → только table_full;
  `#` в row_key → мост обязан `= k OR starts_with(k||'#')`; таблицы rows нет →
  все сущности mode=full. Проба — SQL/код по $metadata, без имён базы и без рук.
  **Вердикт режима виден запросом (п.13):** после такта `search_quality` / отчёт
  merge несёт per-src `rebuild_mode ∈ {partial, full}` **теми же ярлыками глоссария**
  + причину (`row-keys` | `table_full` | `entity-scope`) — тихий
  «entity навсегда из-за ключей» невозможен (P3-§5; словарь один — P8-§2.4).
- Никакой подстройки под okna; DDL маркеров — в corpus_init.sql (fail-closed:
  таблицы нет → все mode=full, такт не падает).

## 1. Диагноз (B1-B4 + AA1-AA4, подтверждено кодом)

1. Четыре схлоппа гранулярности: HTTP знает changed/gone КЛЮЧИ и выбрасывает
   (poc_load_entity:741-742 → :812-814); наружу — список таблиц; tmp3_changed/
   tmp3_build — ТАБЛИЦЫ (corpus_build:1004-1013, 1336-1347); p_doc/order/chunk/
   tail/plain читают query_table ЦЕЛИКОМ (:1701, :1955, :2185, :2487, order
   :1488-1532); merge ждёт ПОЛНЫЙ снимок сущности от стейджа.
2. Критический факт: при частичном tmp3_corpus merge УДАЛЯЕТ неизменившиеся строки
   (corpus_merge:950-953), счёт :1049-1057 падает ПОСЛЕ DELETE, vec-budget :654-740
   считает смертью все unmatched. **Оговорка (AA1): пустой-entity guard :111-115
   НЕ защита — он ловит только пустую сущность; при ≥1 строке неполного стейджа
   wipe делают DELETE+count. Ветвить DELETE/count, не усиливать guard.**
   `\set partial_rebuild 0` (:4-6) мёртв — нигде не читается.
3. Три мира ключей: A (Ref_Key, HTTP-дельта/gone) ≠ B (витринный key_text `|`-join,
   packet_apply:608-618 — уже пишется в search_changed_rows) ≠ C (корпусный row_key:
   fold, `#sha1`, `#N`, sha1(doc)). Мост B→C обязателен; join «row_key=key_text
   вслепую» запрещён. **Gone-путь только для сущностей с колонкой Ref_Key**
   (AA2.7); регистр без Ref_Key → delta/table_full, не gone.
4. Чанкуемый путь: N×полный raw на порции + order на всю сущность + finalize-гейт
   stage==nrows (:2416-2418). Фильтр после полного raw = дороже entity.
5. SKIP↔маркеры: build.sh SKIP не смотрит rows; маркеры пишутся ВНЕ contract_tx
   (packet_apply:706-708, :745-750 против :899-940) — падение до contract_tx даёт
   SKIP при живых маркерах; pipeline.sh:59-62 не восстанавливает rows-снимок.
   **Текст `_plan` (:956-957) врёт, что rows в контрактной tx — синхронизировать
   с фактическим `_contract_tx` (AA2.8).**
6. Движка-CDC нет (AA3 подтвердил MCP: Triggers No, no MATERIALIZED VIEW, нет
   change-feed); своя таблица — штатный путь (п.20). RETURNING на ATTACH PG запрещён
   (источник — строка бинарника/CHECK2, НЕ доки; цитировать CHECK2 — AA3).
7. Замок-сторож против наивного flip (P2-§1, P6/P8 круг 2 — семантика исправлена,
   место/форма — P10 круг 3):
   **A (runtime, merge, блок §0 «проверки до записи» — ДО vec-budget И до любого
   MERGE/DELETE в search_corpus; раньше vec-budget, чтобы STOP нёс свою причину,
   а не «вектор-бюджет»):** при `:partial_rebuild=0` — STOP, если у ХОТЯ БЫ ОДНОЙ
   сущности в tmp3_build `mode <> 'full'` (включая NULL = mode отсутствует).
   Один SQL (образец error() + ON_ERROR_STOP):
   `SELECT CASE WHEN :partial_rebuild = 0 AND EXISTS (SELECT 1 FROM tmp3_build b
   WHERE b.mode IS DISTINCT FROM 'full') THEN error('corpus_merge:
   partial_rebuild=0, но mode≠full') END;`
   **НЕ EXISTS-предикат «строка корпуса без row_key в tmp3»** — он
   ложноположителен на ЛЕГИТИМНОМ gone при полном стейдже (mode=full) и остановил
   бы каждый живой такт; исчезнувшие из 1С строки при mode=full удаляет штатный
   anti-join как сегодня. Стоимость A = O(числа сущностей) по tmp3_build,
   БЕЗ нового anti-join (не коррелированный EXISTS — урок corpus_merge :866,
   21 ГиБ tmp). Проводка `\if/:partial_rebuild` в шапке merge обязательна —
   сейчас константа мертва (corpus_merge:4-6 не читается).
   **B (оффлайн):** фикстура «режим partial при `\set partial_rebuild 0` → STOP
   до записи»; фикстура «урезанный tmp3 у mode=full → STOP (L4/guard)»; статическая
   связь «в corpus_build есть путь row-фильтра ⇒ в corpus_merge есть ветвление с
   anti-join только при mode=full»; flip=1 разрешён замком только после зелёных
   L0-L4. Без A+B порядок этапов — промт-правило (запрещено 03.08).

## 2. Порядок: 0 → 2 → (1∥3) → 4 → 5 → 6 (F3-№10: мост РАНЬШЕ merge-ветвления —
expand gone и scope «маркеры∪tmp3» требуют B→C; держать 1 раньше 2 значило бы
плодить заглушки без выигрыша в безопасности)

**Глобальный порядок со Скоростью-II (P4-§2; барьер сужен кругом 2 — P8-§2.3):**
Speed-II-этап-2 — барьер ТОЛЬКО перед этапом 4 этого плана (общий файл
corpus_build.sql). До этапа 4 параллельны Speed-II-2 все шаги КРОМЕ 0f: 0a-e
(контракт/DDL/замки), 2 (мост — отдельный файл), 1∥3 (merge/писатели — другие
файлы); исключение — 0f (колонка mode правит corpus_build.sql): одним выкатом
с завершением Speed-II-2, сторож A — только после 0f (см. 0f).
Секции этапов ниже идут в порядке исполнения: 0 → 2 → (1∥3) → 4.
Глобальная цепочка:
**Speed-II-2 → B-4 → Speed-II-1A/1B** (1A остаётся для full-fallback путей и
стоп-замера M3; на happy-path малой дельты выигрыш B поглощает 1A — «однопорционный
путь» 4b не зовёт N×raw; mart-slice — критерий 1B, не отговорка).

### Этап 0 — контракт и предохранители (оффлайн)
- 0a. Миры ключей A/B/C; expand gone через витрину (не голый starts_with); базовый
  маркер закрывает все `#`-потомки; порядок сегментов = tmp3_key.key_cols.
  **Артефакт сдачи этапа 0 (F3):** правки файлов 0c/0d + оффлайн-замки (расширения
  key_form/gone_register, каркас-замок L0) + сам текст контракта §0/§1 — новых
  прод-механизмов на этапе 0 не появляется.
- 0b. Инварианты: SKIP_BUILD=0 при nonempty rows с ts>corpus_built_ts; потребление
  rows только после успешного merge; SKIP rows не стирает. **Артефакт (G3):**
  текст инвариантов здесь + каркас-строки в test_changed_sources_lock (статическая
  проверка по build.sh; оживает с этапом 5b); прод-код — этап 5.
- 0c. DDL search_changed_rows → corpus_init.sql (+ UNIQUE или код-эквивалент
  идемпотентности на (src_table,key_text,op) — AA2.6); fail-closed → mode=full.
- 0d. pipeline.sh: restore tmp_changed_rows_keep симметрично sources.
- 0e. Оффлайн-замки контракта: расширение key_form/gone_register; **каркас L0
  (G3: состав — статический assert «сторож A присутствует в corpus_merge»
  текстовой проверкой; полный L0 на движке-фикстуре — этап 1d)**; дедуп записи
  (граница с 3d: 0e — замок формы записи, 3d — писатели). Отражение режима в
  отчёте — НЕ здесь: вводится merge-ветвлением этапа 1 и приёмкой M8 (F3).
- 0f. Колонка `mode` в `tmp3_build` (единый CTE: членство + маркеры + мост —
  см. §0 per-entity режим); NULL-mode при непустом tmp3 сущности → STOP
  **L4(б) при ЛЮБОМ flip; при flip=0 дублируется сторожем A/L0** (G2: без
  склейки «A/L4» в одну ответственность); отдельная таблица режима не заводится
  (P10). **Interim до этапа 2 (F3):** моста нет ⇒ introspection честно даёт
  `mode='full'` всем сущностям; после этапа 2 — по мосту. Заглушек-режимов
  не заводим. **Исполнение 0f (G3):** правит corpus_build.sql — общий файл со
  Speed-II-2 ⇒ 0f идёт ОДНИМ выкатом с завершением Speed-II-2 (не параллельно
  ему); сторож A (читает колонку) вводится только после 0f. До того 0a верен:
  прод-механизмы этапа 0 — только 0c/0d.

### Этап 2 — мост key_text → row_key (P4-§4: контракт размера p_doc, не «SQL на вечер»)
- 2a. Чеклист форм: база `|`-join по key_cols; fold (маркер=одна строка корпуса);
  `#sha1` при коллизии не-fold; `#N` у дублей; пустой ключ → sha1(doc); expand
  Ref_Key→строки ТЧ/движений (через витрину); регистр Recorder(+Type)|LineNumber.
  Каждая форма — в замке L6. Мост живёт ОТДЕЛЬНЫМ SQL-файлом/макросом (владелец
  L6 — этап 2; build и merge зовут один источник, не две копии логики).
- 2b. Miss моста → mode=full (fail-closed, не дыра, не отказ).

### Этап 1 — семантика merge при partial (блокер №1)
- 1a. Реальное ветвление по `:partial_rebuild` × **колонке mode в tmp3_build**:
  anti-join DELETE — только mode=full; DELETE по op=deleted_gone∪expand —
  mode=partial (gone при full тоже исполняется, anti-join обязан).
- 1b. Count-equivalence / empty-build / unmatched / rewrite-wave — сузить по
  mode (scope = маркеры∪tmp3 для partial; вся сущность для full).
- 1c. Vec-budget (P2-§3): `unmatched_kill` вне (маркеры∪tmp3∪gone-expand) = 0,
  иначе STOP; `hash_kill` (легитимная смена content в дельте) — ожидаемый сброс,
  в гейт катастрофы НЕ входит, учитывается очередью embed/отчётом; гейт 0.5% —
  на **`unexpected = unmatched_kill − gone_expand − xfer_explained`**, где
  **`gone_expand`** = множество row_key, полученное expand'ом маркеров
  `deleted_gone` мостом этапа 2; **`xfer_explained`** = emb, спасённые ШТАТНОЙ
  картой переноса `tmp3_merge_emb_xfer` (corpus_merge.sql:968+) — множества
  привязаны к существующим CTE, не только алгебра (F3). BYPASS не решение.
  Способ вычисления множеств — hash anti-join планом DELETE или reuse уже
  считаемого vec-budget CTE (не второй проход — урок :866).
- 1d. Замки L0, L2, L3, L4 + фикстуры сторожа A (§1.7); **статическая часть
  сторожа B (связь «row-фильтр в build ⇒ ветвление в merge») вводится в 4e
  вместе с самим фильтром — до этапа 4 связывать нечего (F3)**; фикстуры L3/L6
  используют готовые row_key тест-данных (мост слит в дереве с этапа 2 —
  порядок 0→2→(1∥3)); **L1 (pdoc-половина,
  multiset инкремент≡полный) — НЕ здесь: в этапе 4** (P4-§1: finalize/order —
  тот же контур, что test_pdoc_tail_equivalence).

### Этап 3 ∥ — писатели маркеров (параллельно 1; flip ещё off)
- 3a. HTTP: persist changed/gone из poc_load_entity ДО return; serene_sync err →
  table_full ('*'). **Полный rewrite (changed:n = кардинальность таблицы) →
  table_full, не N маркеров «как будто EXCEPT» (AA2.5).**
- 3b. Full/EXCEPT: ключи differing тем же проходом (проекция key_cols или
  hash-пары), НЕ второй полный проход; мешок/без ключа → table_full. Порог
  «ключи vs table_full» — по доле differing (зафиксировать числом при исполнении
  замером, не вслепую).
- 3c. **ОДНА форма (P3/P4): rows пишутся в ТОЙ ЖЕ tx, что sources+mart_changed_ts**
  (закрыть дыру «SKIP при живых маркерах» у корня; SKIP-предикат по max(ts) НЕ
  заводим). Поправить текст `_plan` (§1.5).
- 3d. Дедуп накопления (src_table,key_text,op).

### Этап 4 — сборка: срез витрины ДО UNPIVOT (смысл M2)
- 4a. Таблицу не убирать из tmp3_build; сузить СТРОКИ query_table по мосту —
  один фильтр во всех путях: mono p_doc + order + chunk + tail + plain; row-фильтр
  разрешён ТОЛЬКО при mode=partial этой tbl.
- 4b. Finalize: не требовать stage==nrows при partial; малая дельта → однопорционный
  путь (без N×raw и без полного order-build).
- 4c. lag / rename>200 / child-of-lag / table_full / HTTP-без-rows / miss моста →
  mode=full, полный p_doc; **при полном проходе (NOT on_) политика refmap
  остаётся полной перестройкой карты — row-level её не сужает (AA1); p_ref и
  tmp3_entity_rows — без row-фильтра (полный count nrows; О(N)-count признан
  допустимым членом такта — P4-§6.7; оптимизация — вне скоупа B).**
- 4d. Замок L1 (multiset инкремент≡полный) — здесь, рядом с
  test_pdoc_tail_equivalence, вместе с ослаблением finalize-гейта.
- 4e. **Статический сторож B** (из §1.7/1d): связь «row-фильтр в corpus_build ⇒
  ветвление anti-join в corpus_merge по mode» — вводится здесь, вместе с самим
  фильтром 4a; до этапа 4 связывать нечего, после — замок обязателен к коммиту
  4 (G3: указатель закрыт).

### Этап 5 — потребление + SKIP-инвариант
- 5a. DELETE rows: при mode=partial — только потреблённые ключи (не вся таблица
  маркеров — сохранить накопление соседей); при mode=full — table_full+ключи
  таблицы; рядом с sources (:1066).
- 5b. build.sh: маркеры новее corpus_built_ts ⇒ SKIP_BUILD=0 (согласовано с
  SKIP-каноном резолвера: SKIP=1 ⇒ витрина не менялась — маркеры того же такта
  пусты; замок L5).
- 5c. Правка только merge (flip) не инвалидирует build_sql_hash — не полагаться
  на инвалидацию SKIP через hash; держать 5b (P1).

### Этап 6 — flip и приёмка
- 6a0. **Предусловие flip (P2-§4): свежий бэкап emb по канону (src_table,row_key),
  сверка count(emb) с боевым, сухой restore-drill на выборке — иначе STOP.**
- 6a. `\set partial_rebuild 1` выкатом SQL-файла; откат = выкат 0. НЕ env.
- 6b. Приёмка: метрики §4; после — Скорость-II-1A на full-fallback путях.

### Этап 7 — вне скоупа (ссылки): резолвер row-delta (теперь SKIP-канон Скорости-II-3);
wiki/card/coverage — инварианты merge + чеклист регрессии (counts после
partial-такта); MERGE RETURNING в apply (после живой пробы, native-таблицы);
Скорость-II-1B (mart-slice — критерий стыка).

## 3. Чего НЕ делаем

Env-флаги PARTIAL_*/MERGE_* в /etc (К1) · рубильник через search_quality (в этом
пакете) · второй полный EXCEPT «для ключей» · фильтр после полного raw на порции ·
BYPASS как решение · свой CDC · словари сущностей/имён базы · join
row_key=key_text без `#`/fold/expand · «MERGE NOT MATCHED BY SOURCE бережёт» ·
усиление пустого-guard вместо ветвления DELETE · «повысить tol» вместо
разведения hash_kill/unexpected ·gone-маркер у сущностей без Ref_Key.

## 4. Метрики (замер; сценарий: малая дельта K≪N на крупной сущности, тот же снимок)

M1 wall partial≪full (цифру после сухого нуля) · **M2 протокол (P4-§5): EXPLAIN
ANALYZE — actual rows по операторам на query_table/сыром CTE, ИЛИ прокси
«порций=1 ∧ stage_rows≤K≪N»; wall в одиночку M2 не доказывает; члены
count/order-сканов учитываются явно (4c)** · M3 unexpected-потери emb=0 вне
дельты (M3 переформулирован: hash_kill в дельте — ожидаем, см. 1c) · M4 emb вне
дельты бит-в-бит · M5 multiset(content_hash‖row_key) partial-merge ≡ full · M6
gone исчезают, соседи живы · M7 SKIP↔markers · M8 L20 Δmatch≥0 Δwrong≤0,
coverage без дыр, rebuild_mode-отчёт заполнен. Не успех: «маркеры записались»,
«гейт не упал благодаря bypass», «wall меньше» без M2.

## 5. Замки

L0 STOP: при `partial_rebuild=0` — mode≠full (вкл. NULL) у сущности tmp3_build
(runtime-сторож A §1.7, до vec-budget и MERGE/DELETE; НЕ anti-join «корпус⊃tmp3») ·
L1 multiset инкремент≡полный (этап 4) · L2 emb вне дельты бит-в-бит · L3 gone ·
L4 STOP: (а) частичный стейдж у mode=full; (б) NULL-mode при ЛЮБОМ flip (нет
режима у сущности с непустым tmp3). Предикат «неполный tmp3» (корпус⊃tmp3) НЕ
используется — запрещён §1.7; покрытие дельты держит vec-budget 1c (F2-круг-финал) ·
L5 SKIP↔markers (маркеры⇒SKIP=0; SKIP не стирает) · L6 мост ключей: все формы
(fold/#sha1/#N/sha1(doc)/expand/Recorder), miss→mode=full · **L7 HTTP/table_full:
писатели контура; fail-closed + quality-отметка** · **L-mid: обрыв merge
посреди partial → повторный такт с накопленными маркерами: emb вне дельты
бит-в-бит, gone остаются, второго wipe нет** · статическая связь build-фильтр ↔
merge-ветвление (замок B) · расширить key_form (ветвление+UNIQUE), gone_register
(expand, только Ref_Key), changed_sources_lock (restore rows).

## 6. Документы (тем же коммитом)

CHANGELOG (M1-M8 до/после) · activeContext · граф MCP (corpus_build/corpus_merge/
packet_apply/poc_load_entity/pipeline.sh + замки) · SCALE_BLOCKERS · techContext
(ловушки: «partial без ветвления merge», «guard ≠ защита», «hash_kill ≠ гейт»)
· RUNBOOK §10 · SERENEDB.md (CDC-отрицание + RETURNING attach по CHECK2) ·
CHECKLIST_SEARCH_FIX при выкате.
