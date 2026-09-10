# ПЛАН 1∥3 «Полной B» v2 (волна 1 ×4 + волна 2 ×4 + контрольный круг ×4)

Дата: 10.09. Статус: ГОТОВ К ВНЕДРЕНИЮ после одобрения владельца.
Источники: fullb1-audit-a1/a2/a3/a4.md, fullb1-plan-audit-p1/p2/p3/p4.md,
fullb1-check-p1/p2/p3/p4.md (контрольный круг: P3 сошёлся сразу; остатки
P1/P2/P4 внесены в v2 дословно). Решение оркестратора — Q2: VALUES×1000
(temp — запасной; P4 предпочёл temp, P1/P2/P3 — VALUES; выбор — одна форма
с живым _apply_gone, минимальный дифф).

## ИТОГ АУДИТА (кратко)

- Этапы 0a-e/2/3d — УЖЕ в дереве (DDL+UNIQUE+дедуп pipeline-restore, мост bridge_*).
- 0f (mode) — НЕТ; сторож A и merge-ветвление ждут 0f (один выкат со Speed-II-2).
- Этап 3: 3a/3b/3c — 0%, 3d — готово. Пакет A = писатели.
- Вектора в пакете A не участвуют (merge/build SQL не трогаем); поведение
  маркерных гейтов МЕНЯЕТСЯ ПРЕДСКАЗУЕМО (это цель, не побочка — P4-атака 1).

## ПАКЕТ 1∥3-A «Писатели маркеров» — сейчас; flip=0

🔴 ФАЙЛЫ: poc_load_entity.py, serene_sync.py, packet_apply.py + 3 замка.
🔴 corpus_merge.sql и corpus_build.sql — НЕ ТРОГАТЬ ВООБЩЕ (path-spec без них;
  repost→bridge — пакет B; «заодно унифицировать» — запрещено исполнителю).

### A1. 3a HTTP-писатель (poc_load_entity.py)
1. Хелпер `_upsert_changed_rows(table, keys, op, batch=1000)` (~15 строк): VALUES
   пачки через `_psql_exec` stdin (образец — _apply_gone :816-828); upsert
   ON CONFLICT (src_table,key_text,op) DO UPDATE SET ts=EXCLUDED.ts; пустой
   список — no-op; перед первым upsert CREATE TABLE IF NOT EXISTS (форма
   pipeline.sh:53) — зависимость от pipeline не предполагать (P3).
2. load_entity_delta: точная точка — ПОСЛЕ обоих DML витрины (upsert changed
   :796-804 И delete gone :805-810), ДО `n = _psql_rows` :811. 🔴 ПОРЯДОК СВЯЩЕНЕН
   (P4-атака 2): маркеры строго ПОСЛЕ применения к витрине; persist-до-DELETE
   запрещён замком.
   - delta_keys = [k for k in changed if k not in set(gone)] (404-ключи остаются
     в changed — исключить, P3) → op='delta'
   - gone (финальный, с 404-пополнением) → op='deleted_gone'
   - 🔴 Persist ⊆ applied keys: писать ТОЛЬКО реально применённые ключи; «на
     всякий» — запрещено (P2 §1а; анти-§3.113).
3. load_entity (full-rewrite): после успеха DROP+CREATE (:925-927), до return
   (:939-940): `_upsert_changed_rows(table, ["*"], "full")` — ОДИН маркер. При
   same=True и rows==0 — ничего. 3b v1 = СУЖЕНИЕ КАНОНА (P1): на любом
   full-rewrite — только сентинель; однопроходная проекция differing (канон
   3b :192-193) — ВНЕ СКОУПА A (второй EXCEPT по-прежнему запрещён §3;
   порог доли differing не вводим — R8).
4. Словарь (P1): op='full' ∧ key_text='*' ≡ глоссарий table_full (FULLB §0:28,
   3a:190). `*` = сигнал БУДУЩЕГО mode=full, НЕ объяснение rehash.

### A2. 3c одна tx + A3 3b (packet_apply.py)
1. row_markers: list[tuple(table,key,op)] на стеке apply_package (:1088+).
   - delta: УБРАТЬ changed_rows_sql из _delta_sql (:770-800; TEMP d_* не живёт
     между _psql — «SELECT FROM d_ в contract_tx» ЗАПРЕЩЁН, P3); ключи собрать
     в Python из CSV-чанка тем же kc-выражением, что _key_text_expr (хелпер
     ~20 строк; НЕ SELECT из базы — п.20).
   - full-ветка: точка = apply_package ПОСЛЕ _psql(_full_sql(...)) (:1124-1125),
     НЕ тело _full_sql (P3): row_markers.append((table, "*", "full")).
   - _apply_gone: сигнатура +row_markers; DELETE витрины оставить по ходу;
     INSERT маркеров заменить на row_markers.append((table,k,"deleted_gone")).
2. _contract_tx: параметры +row_markers; внутри существующего BEGIN...COMMIT —
   INSERT ... SELECT ... FROM (VALUES пачки×1000) ON CONFLICT DO UPDATE ts.
3. _plan (:1055-1056): после переноса текст становится правдой — сверить
   дословно (не «поправить на фактический без rows», а наоборот, P3).
4. Retry/quarantine: state-machine retry НЕ доказательство идемпотентности DML
   (P4-атака 3) — добавить приёмку: gone-маркеры появляются ТОЛЬКО при успехе tx;
   attempts_exhausted на пакете с gone = видимый дефект quality, не тишина
   (блокер flip-готовности, вне скоупа A-кода: пометка в плане B-предусловий).

### A4. Замки (три файла)
1. test_changed_rows_lock.py (+25-45 строк): читать poc_load_entity.py и
   serene_sync.py (сейчас не читает); ветки: HTTP delta/gone upsert+ON CONFLICT;
   full = ровно одна строка ('*','full'); ОТДЕЛЬНАЯ ветка «persist ⊆ applied
   keys» (после успешного delta с N gone — count(deleted_gone) по таблице = N;
   grep-порядок: INSERT deleted_gone не выше DELETE витрины по коду — P4);
   serene_sync err → '*' ОТДЕЛЬНОЙ веткой (L7 — закрытие FULLB §5:274-275);
   _contract_tx содержит INSERT rows; существующие apply-asserts сохранить
   (подстрока ON CONFLICT...ts, не привязка к функции).
2. test_hash_kill_gate.py (+6-12): 🔴 БЛОКЕР приёмки: фикстура mass hash_kill +
   только (e,'*','full') свежий → все unexplained → STOP; grep: op='full'/
   table_full НЕ упоминаются в die_hash_unexplained; bridge_row_matches('*')
   =false на нормальных ключах; 🔴 ПАТОЛОГИЯ отдельно (P2/P4): row_key ∈ {'*',
   '*|…', '*#…', '*|1'} — вторая фикстура FAIL-closed «патологический ключ не
   используем как row_key/не объясняем» (ветка 3 моста формально жива при
   n_seg>1 — замок обязателен, не избыточен).
3. test_corpus_bridge_lock.py: инвертировать assert РАЗДЕЛЬНО build (вызова нет)
   / merge (вызов ЕСТЬ, list_slice-копии НЕТ) — докстринг :8-11 предписывает;
   семантические тесты моста :57-106 не трогать.
4. test_packet_apply_retry: без изменений — регрессия «не сломали retry».

### Приёмка пакета A (P4-атака 1 + P2 §1в)
- Замки: расширенные PASS (rows-lock c ветками persist⊆/L7/патологии, hash_kill
  +ветка '*' и патология, bridge 28/0, retry ок, vector_budget 63/0 и key_form
  93/0 НЕ тронуты — прогон до/после); закрытие L7 (FULLB §5 :274-275 —
  HTTP/table_full писатели, fail-closed + quality-отметка) фиксируется
  расширенным rows-lock; + DML-фикстура packet (P4-атака 3):
  apply → kill перед _contract_tx → retry → витрина≡чанку, markers≡ожидаемому,
  sources полны (не state-machine — реальный обрыв).
- Обрыв HTTP-писателя (P4-атака 2, приёмка): kill после DELETE gone до persist
  → ЛИБО retry догоняет маркеры, ЛИБО видимый quality/STOP «HTTP delta
  incomplete markers» — не тишина (п.13).
- Инвариант порядка: к моменту merge epoch(marker.ts) > corpus_built_ts —
  свойство pipeline (sync→build→merge→штамп), НЕ отдельный SQL (P2).
- Живое (только после одобрения владельца): stop timer → inactive → scp
  (poc_load_entity.py, packet_apply.py, serene_sync.py) → md5 бит-в-бит →
  start timer → контрольный такт.
- Замеры до/после (не «такт зелёный и всё»): (1) HTTP-дельта N ключей → N
  строк delta/gone в search_changed_rows; (2) hash_kill по этим ключам не
  STOPит; (3) контрольный необъяснённый hash_kill вне маркеров → STOP как
  прежде; (4) count STOP-классов в quality до/после; (5) repost: движения при
  HTTP-delta маркере → класс entity_repost_delta, не transport-STOP.
- 🔴 Ожидаемо и НЕ дефект: крупный легитимный full-rewrite с массовой сменой
  текста остаётся STOP по rehash до отдельной правки (FIX §1d) + 6a0 — так
  задумано (P2/P4).
- Бэкап emb parquet перед выкатом — несмотря на «вектора не участвуют» (свято).

## ПАКЕТ 1∥3-B «Merge по mode» — после Speed-II-2+0f (отдельное окно)

0f одним выкатом с концом Speed-II-2 → сторож A → 1a/1b/1c/1d. Артефакты связаны
md5 в одном окне (build с mode + merge с A вместе, A4-чеклист п.3).

1. 🔴 R6-правка канона 0f (P1 §2): при :partial_rebuild=0 CTAS tmp3_build пишет
   mode='full' ВСЕМ (сторож A иначе STOP на честном partial — зелёный прод
   ломается порядком). Честный расчёт по мосту — только при flip=1. Прежняя
   формула F3 «interim до этапа 2» снята: мост есть, риск инвертирован. Это
   отклонение от буквы канона — внести в FULLB_PLAN тем же коммитом.
2. 1a: \if :partial_rebuild ветвление DELETE (anti-join только mode=full;
   partial — gone∪expand по op='deleted_gone' ТОЛЬКО, P2 §3.3); else = текущий
   merge байт-в-байт.
3. 1b: сужение empty-build/unmatched/rewrite-wave/count-equivalence по mode.
4. 1c с R1-комплектом (P2 §3 — НЕОБХОДИМО И ДОСТАТОЧНО): gone_expand вычитается
   ТОЛЬКО при: предок-маркер op='deleted_gone' ∧ fanout-cap per-marker из
   витрины (COUNT строк под предком, НЕ константа — R8) ∧ пересечение со
   свидетелем витрины; n_seg=0/без key_cols → expand запрещён (mode=full);
   cap+⊆ проверка ДО DELETE, не после; фикстуры: «один Ref → expand >K%
   сущности → STOP до записи» ∧ «строка expand БЕЗ предка-маркера → STOP до
   записи» ∧ «PASS только при fanout = COUNT(mart rows под предком)»;
   grep-замок «unexpected без cap-CTE в том же файле». Само-объяснение
   (множество DELETE оправдывает бюджет) — запрещено.
5. L-mid (P2 §5, R3): (1) после обрыва count(emb IS NULL) вне свежих маркеров
   = 0 ЛИБО явный STOP/quality до следующего такта — запрет тихого resume с
   дырами; (2) повторный такт: нет второго anti-join вне gone∪expand; (3)
   gone-маркеры живы. Фикстура обрыва после N COMMIT пачек — риск есть уже на
   текущем full (:1347-1365), не только после flip.
6. 1d: замки L0 (сторож A), L2, L4(а)(б); repost :588-595 starts_with →
   bridge_row_matches (сюда, P1/P2/P3/P4).
7. Flip (этап 6 канона): 6a0 свято (бэкап+сверка+drill); BYPASS только one-shot
   по RUNBOOK §10.9-bis.

## Чего НЕ делаем (консолидировано, P4 + §3 канона + R-линии)
1. corpus_merge.sql / corpus_build.sql в пакете A — никакие правки, включая
   repost и «унификацию заодно».
2. Не учить die_hash_unexplained/rehash понимать op='full'/'*' в выкате A
   (отмена намёка FIX_PLAN:38-42 до отдельного решения владельца).
3. Не писать HTTP-маркеры до успешного DML витрины; не писать ключи вне
   применённого changed/gone.
4. Не считать test_packet_apply_retry доказательством идемпотентности DML.
5. Не принимать выкат критерием «поведение такта не изменилось» (оно меняется
   предсказуемо — замерять).
6. Не второй EXCEPT; не порог differing с числами okna; не N маркеров вместо
   '*'; не SELECT из базы для сборки маркеров (п.20).
7. Не flip/row-фильтр/1a в окне A. Не BYPASS после появления HTTP-маркеров.
8. Не scp на running merge; не рестарт без stop timer.

## Контрольный круг (волна 2-бис) — перед показом владельцу
v1 сверить с p1-p4 чеклистами: все ли правки внесены дословно.
