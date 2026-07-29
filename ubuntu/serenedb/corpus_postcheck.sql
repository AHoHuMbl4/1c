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
                  -- «Было без вектора» — чтобы судить по СДВИГУ, а не по остатку.
                  max(v) FILTER (WHERE k = 'before_noemb') AS b_noemb,
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
  -- 🔴 СУДИМ ПО СДВИГУ, А НЕ ПО ОСТАТКУ. Прежнее условие («без вектора больше двадцатой
  -- части — эмбеддер молчал») исходило из того, что за один такт векторизуется ВСЁ. Это
  -- верно на маленькой базе и неверно на большой: [замер 29.07, УТ] первая загрузка —
  -- 632 683 строки, за такт считается около 87 000, то есть нужно несколько тактов. Такт
  -- падал с «эмбеддер не отработал», хотя эмбеддер отработал и посчитал 86 896 строк.
  --
  -- Для автономности это дефект, а не мелочь: на любой крупной базе клиента первый такт
  -- всегда падал бы, а если его перезапускает таймер — падал бы бесконечно, при том что
  -- работа идёт. И настоящий отказ эмбеддера утонул бы в этом шуме.
  --
  -- Правильный признак молчания: остаток НЕ УМЕНЬШИЛСЯ. Строки, которым вектор невозможен
  -- (слишком длинные), из ожидания вычитаются — они не уменьшатся никогда.
  WHEN a_noemb > coalesce(b_noemb, 0) AND a_noemb > 0
       THEN error(printf('без вектора стало БОЛЬШЕ: было %d, стало %d — эмбеддер не отработал',
                         coalesce(b_noemb, 0), a_noemb))
  WHEN a_noemb > 0 AND a_noemb = coalesce(b_noemb, -1)
       THEN error(printf('без вектора %d строк, и за такт не убавилось ни одной — эмбеддер молчал',
                         a_noemb))
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
UNION ALL   SELECT 'build_res',   (SELECT count(*) FROM resolver_index),         'значений резолвера'
-- 🔴 ОТПЕЧАТОК КОДА СБОРКИ. По нему следующий такт понимает, можно ли пропустить
-- пересборку корпуса: если ни данные не менялись, ни сам `corpus_build.sql`, собирать
-- заново нечего. Хранится в `note`, потому что это строка, а не число.
UNION ALL   SELECT 'build_sql_hash', 0, :'build_sql_hash';

-- Итог — ДЕЛЬТОЙ, а не абсолютом.
SELECT printf('корпус %d -> %d (%+d), сущностей %d -> %d, без вектора %d; резолвер %d -> %d',
              b_rows, a_rows, a_rows - b_rows, b_src, a_src, a_noemb, b_res, a_res) AS итог
FROM (SELECT max(v) FILTER (WHERE k = 'before_rows') AS b_rows, max(v) FILTER (WHERE k = 'after_rows') AS a_rows,
             max(v) FILTER (WHERE k = 'before_src')  AS b_src,  max(v) FILTER (WHERE k = 'after_src')  AS a_src,
             max(v) FILTER (WHERE k = 'after_noemb') AS a_noemb,
             max(v) FILTER (WHERE k = 'before_res')  AS b_res,  max(v) FILTER (WHERE k = 'after_res')  AS a_res
      FROM build_state);
