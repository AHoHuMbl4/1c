# План: гейт «необъяснимый hash_kill» — v2 (после аудита ×3; на аудит)

Цель: массовая смена текста корпуса ВНЕ дельты 1С → STOP ДО записи в
corpus_merge. Штатный такт не задет (п.0). Закрывает кейс 09.09 (§3.113).

Аудит v1 (3 линзы, cursor-run-hk-plan-{a,b,c}.log) внёс блокеры — все учтены:
- A: die_hash уже GROUP BY → нужен ROW-LEVEL CTE; search_changed_rows хранит
  ВСЮ историю → окно свежести ts > corpus_built_ts, иначе ложный PASS (старые
  маркеры «объяснят» смену канона) или ложный STOP; full-маркера в tmp3_*
  НЕТ (tmp3_build=только tbl) — «пусто» несовместимо с защитой после B.
- B: объяснение full «если маркера нет — пусто» противоречит защите; наоборот,
  объяснять только писательский rewrite; RUNBOOK-чек-лист дополнить; порог
  зафиксировать фактом (зелёные такты: hash_kill≈0, ряд 14 дней замерен).
- C: BYPASS в persistent env = гейт выключен навсегда (прецедент LOSS 08.09) —
  только one-shot; замок дополнить ветками-запретами; приёмка — проверка
  bypass выключен после такта; соседей гонять циклом пофайлово.

## Правки

### 1. corpus_merge.sql
1a. tmp3_merge_cfg: + rehash_tol DOUBLE (default 0.005 = существующий
    vector_loss_tol — распространение утверждённого порога, НЕ новое число),
    rehash_bypass BOOLEAN (default false).
1b. НОВЫЙ ROW-LEVEL CTE die_hash_rows: тот же JOIN old_full×new_full, что
    :912-921, но БЕЗ GROUP BY и ТОЩЕЙ проекцией: только (src_table, row_key)
    [+ n_seg = len(tmp3_key.key_cols) для моста] — emb/doc/bmap в результат
    НЕ тянуть (пик памяти на массовом срабатывании; фильтр emb IS NOT NULL
    уже в old_full).
1c. НОВОЕ окно дельты: якорь — search_quality, k='corpus_built_ts'
    (v BIGINT, unix epoch; пишется после удачного merge: build.sh:363-366,
    :411-414; в corpus_build.sql метки НЕТ). Маркер объясняет строку только
    если epoch(маркер.ts) > corpus_built_ts.v (TIMESTAMP→BIGINT приведение
    явное). Старые маркеры истории НЕ объясняют (анти-ложный-PASS).
1d. die_hash_unexplained = die_hash_rows МИНУС строки, объяснённые ПОСТРОЧНО:
      * свежий маркер search_changed_rows, сопоставление ТОЛЬКО через
        bridge_row_matches(row_key, marker, n_seg) (corpus_init.sql:97-150;
        слепой row_key=key_text запрещён);
      * ДРУГИХ объяснений НЕТ: emb_xfer НЕ вычитать; full-пересборки НЕ
        объяснять (маркера не существует; писательский full-маркер появится
        в полной B этап 1∥3/3a — тогда отдельной правкой расширить
        объяснение, до тех пор плановая полная пересборка/смена канона =
        честный STOP + разовый BYPASS по RUNBOOK — операция обслуживания,
        не путь коробки).
    Затем GROUP BY src_table → колонка hash_kill_unexplained в бюджете.
1e. Отдельный SELECT CASE (после :1058, НЕ комбинировать с «векторов_умрёт»):
      WHEN sum(hash_kill_unexplained)/всего > rehash_tol AND NOT rehash_bypass
      THEN error('corpus_merge: массовая смена текста вне свежей дельты 1С —
        N из M (>X%): похоже на смену канона (§3.113). Бэкап emb по канону
        (src_table,row_key) + сверка + one-shot MERGE_VECTOR_REHASH_BYPASS=1
        по RUNBOOK; сущности: [...top]')
1f. Метка 'rehash_gate' в search_quality (сумма hash_kill_unexplained);
    'vector_loss_gate' не трогать.

### 2. build.sh (:393-409)
MERGE_VECTOR_REHASH_TOLERANCE (default 0.005, та же валидация),
MERGE_VECTOR_REHASH_BYPASS (default 0) → rehash-колонки В ТОТ ЖЕ оператор
CREATE OR REPLACE tmp3_merge_cfg (:404-407) — иначе defaults не доживут.

### 3. Замок ubuntu/serenedb/test_hash_kill_gate.py (оффлайн, стиль
test_corpus_merge_emb_transfer.py: модель+grep SQL, каркас t(), PASS|FAIL)
Сценарии веток:
  1) массовый hash_kill без свежих маркеров → STOP-условие срабатывает,
     error() содержит «RUNBOOK» и «§3.113»;
  2) hash_kill на строках со СВЕЖИМИ маркерами → вычтены (в SQL есть
     антисоединение через bridge_row_matches И окно ts > built_ts);
  3) СТАРЫЙ маркер (ts <= built_ts) НЕ объясняет → остаётся в unexplained;
  4) rehash_bypass → гейт тих;
  5) cfg/build.sh синхронны (rehash-колонки в том же CREATE; default 0.005/0).
Ветки-запреты (grep-отрицания):
  6) STOP rehash НЕ входит в условие «векторов_умрёт» (отдельный CASE);
  7) emb_xfer НЕ вычитается из die_hash_unexplained;
  8) die_hash_rows — row-level (нет GROUP BY до антисоединения);
  9) окно — ТОЛЬКО через search_quality k='corpus_built_ts' с epoch(ts)>v;
 10) слепое row_key = key_text БЕЗ bridge_row_matches — запрещено (grep
     отсутствия прямого сравнения).

### 4. Документы
- CHANGELOG [код]: числа кейса 09.09 + ряд зелёных тактов (hash_kill≈0,
  14 дней, n=194 — «изменённых строк 0»).
- RUNBOOK_DEPLOY: §«Обход rehash-гейта (разовая операция)»: (1) бэкап emb
  parquet по канону (src_table,row_key); (2) сверка count/len=1024;
  (3) one-shot FAIL-CLOSED: systemctl stop …timer;
  MERGE_VECTOR_REHASH_BYPASS=1 systemctl start 1c-serene-pipeline@…;
  systemctl unset-environment MERGE_VECTOR_REHASH_BYPASS; systemctl start
  …timer — при обрыве между start и unset BYPASS остаётся в manager env:
  ПОСЛЕ операции обязательно `systemctl show-environment` без следа
  MERGE_VECTOR_REHASH_BYPASS (это финальная проверка протокола; `show -p
  Environment` пуст — не годится); (4) 🔴 ЗАПРЕЩЕНО писать в
  /etc/1c-serene-pipeline-*.env (прецедент LOSS 08.09); (5) после такта:
  search_quality rehash_gate записан; cfg пересоздаётся из env каждый такт —
  cfg.rehash_bypass=false при следующем ШТАТНОМ старте без env (не проверять
  сразу после bypass-такта).
- FULLB_PLAN: примечание — M3 (hash_kill в дельте) объясним окном свежих
  маркеров; писательский full-маркер (этап 1∥3/3a) добавит объяснение
  отдельной правкой.

## Приёмка
1. Локально: cd ubuntu/serenedb && python3 test_hash_kill_gate.py — все PASS;
   цикл соседей: for t in test_corpus_merge_*.py test_embed_*.py
   test_vector_budget_gate.py; do python3 "$t" || break; done
   (имя уже с .py — без второго суффикса; CI нет, гоняем пофайлово).
2. На окне: выкат → такт под контролем: гейт молчит (hash_kill=0),
   search_quality rehash_gate=0; ПОСЛЕ такта: env не содержит
   MERGE_VECTOR_REHASH_BYPASS, cfg.rehash_bypass=false.
3. Красная логика — только оффлайн-замком (окно не поджигать).

## Чего НЕ делаем
- Не трогаем MERGE-механику и гейт «векторов_умрёт»; не вычитаем xfer;
- не объясняем full до появления писательского маркера (B 1∥3/3a);
- не пишем BYPASS в persistent env;
- порог не новый: 0.5% вектор-бюджета; окно дельты — по метке сборки.
