\set ON_ERROR_STOP on

-- ПРОВЕРКИ ПОСЛЕ ТАКТА. Их код возврата и есть код всей сборки: если здесь ошибка,
-- такт считается неудавшимся, и systemd это видит.
--
-- Зачем. Прежде такт печатал абсолютные числа, и «корпус: 0 строк» выглядело в журнале
-- так же спокойно, как «корпус: 97 965 строк». Сравнивать надо с тем, что было ДО —
-- отпечаток снят `corpus_precheck.sql` и лежит в базе, а не в переменной оболочки:
-- он переживает рестарт движка посреди прогона.

DELETE FROM build_state WHERE k LIKE 'after_%';
INSERT INTO build_state
            SELECT now(), 'after_rows',  count(*)                            FROM search_corpus
UNION ALL   SELECT now(), 'after_src',   count(DISTINCT src_table)           FROM search_corpus
UNION ALL   SELECT now(), 'after_noemb', count(*) FILTER (WHERE emb IS NULL) FROM search_corpus
UNION ALL   SELECT now(), 'after_res',   count(*)                            FROM resolver_index;

WITH s AS (SELECT max(v) FILTER (WHERE k = 'before_rows')  AS b_rows,
                  max(v) FILTER (WHERE k = 'after_rows')   AS a_rows,
                  max(v) FILTER (WHERE k = 'before_src')   AS b_src,
                  max(v) FILTER (WHERE k = 'after_src')    AS a_src,
                  max(v) FILTER (WHERE k = 'after_noemb')  AS a_noemb,
                  max(v) FILTER (WHERE k = 'before_res')   AS b_res,
                  max(v) FILTER (WHERE k = 'after_res')    AS a_res
           FROM build_state)
SELECT CASE
  WHEN a_rows = 0
       THEN error('после такта корпус ПУСТ — восстанавливать из копии')
  -- «Пропала сущность» — это когда живой ИСТОЧНИК не доехал до корпуса, а не когда
  -- число сущностей просто уменьшилось. Отсев теней регистров (`_recordtype`) уменьшает
  -- счётчик законно, и сравнение before/after ловило бы это ложной тревогой. Считаем по
  -- контракту: каждый источник из `search_sources` обязан быть в корпусе.
  WHEN (SELECT count(*) FROM search_sources s
        WHERE NOT EXISTS (SELECT 1 FROM search_corpus c WHERE c.src_table = s.src_table)) > 0
       THEN error('источник не доехал до корпуса: ' ||
                  (SELECT string_agg(s.src_table, ', ') FROM search_sources s
                   WHERE NOT EXISTS (SELECT 1 FROM search_corpus c WHERE c.src_table = s.src_table)))
  WHEN a_rows * 10 < b_rows * 9
       THEN error(printf('корпус усох больше чем на десятую: было %d, стало %d', b_rows, a_rows))
  -- Векторов не хватает больше чем у двадцатой части строк — значит эмбеддер молчал
  -- (например, секрет умер при рестарте движка), а не «часть не успела».
  WHEN a_noemb * 20 > a_rows
       THEN error(printf('без вектора %d строк из %d — эмбеддер не отработал', a_noemb, a_rows))
  WHEN b_res > 0 AND a_res * 10 < b_res * 9
       THEN error(printf('резолвер усох: было %d, стало %d', b_res, a_res))
  END
FROM s;

-- След такта в БАЗЕ, а не только в журнале: по нему отвечающий сервис может судить о
-- свежести данных (п. 17), а владелец — о том, что вообще происходило в последнем такте.
DELETE FROM search_quality WHERE k LIKE 'build_%';
INSERT INTO search_quality
            SELECT 'build_ts',    epoch(now())::BIGINT,                          'время конца такта'
UNION ALL   SELECT 'build_rows',  count(*),                                      'строк корпуса' FROM search_corpus
UNION ALL   SELECT 'build_noemb', count(*) FILTER (WHERE emb IS NULL),           'строк без вектора' FROM search_corpus
UNION ALL   SELECT 'build_res',   (SELECT count(*) FROM resolver_index),         'значений резолвера';

-- Итог — ДЕЛЬТОЙ, а не абсолютом.
SELECT printf('корпус %d -> %d (%+d), сущностей %d -> %d, без вектора %d; резолвер %d -> %d',
              b_rows, a_rows, a_rows - b_rows, b_src, a_src, a_noemb, b_res, a_res) AS итог
FROM (SELECT max(v) FILTER (WHERE k = 'before_rows') AS b_rows, max(v) FILTER (WHERE k = 'after_rows') AS a_rows,
             max(v) FILTER (WHERE k = 'before_src')  AS b_src,  max(v) FILTER (WHERE k = 'after_src')  AS a_src,
             max(v) FILTER (WHERE k = 'after_noemb') AS a_noemb,
             max(v) FILTER (WHERE k = 'before_res')  AS b_res,  max(v) FILTER (WHERE k = 'after_res')  AS a_res
      FROM build_state);
