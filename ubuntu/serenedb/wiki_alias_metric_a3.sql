-- Метрика A3 (одна таблица словаря; прогнать для alias_okna_c5 и alias_sandbox).
-- Методика docs/audit/dict-audit/A3-вопросы-словарь.md: топ-100 формулировок за 30 дней;
-- значимые стемы вопроса; корзины по числу сущностей, покрывающих стем своими
-- стемами aliases||best_used_for. Доки: ts_lexize (Text); str_split; len (List).
WITH top100 AS (
  SELECT t.q_text, count(*) AS freq
  FROM ask_journal j JOIN ask_journal_text t ON t.id = j.id
  WHERE j.ts > now() - INTERVAL '30 day'
    AND coalesce(t.q_text,'') <> ''
  GROUP BY t.q_text
  ORDER BY freq DESC, t.q_text
  LIMIT 100
),
qwords AS (
  SELECT DISTINCT w AS word
  FROM top100 q,
       unnest(str_split(trim(regexp_replace(lower(q.q_text), '[^a-zа-яё0-9 ]', ' ', 'g')), ' ')) AS w
  WHERE len(w) >= 3
    AND w NOT IN ('сколько','покажи','дай','нас','всего','уже','реально','отдельно','каждый',
                  'месяц','неделя','вчера','воскресенье','понедельник','вторник','среда',
                  'четверг','пятница','суббота','сегодня','год','квартал','день','дня','дней',
                  'был','было','были','есть','будет','наш','наши','мой','какой','какая','какие',
                  'чему','чего','там','все','еще','при','для','это','такой','такая','прошлой')
),
qstems AS (
  SELECT word, coalesce(ts_lexize('search_dict_stem', word), ARRAY[word]) AS stems
  FROM qwords
),
dstems AS (
  SELECT a.src_table, coalesce(ts_lexize('search_dict_stem', w), ARRAY[w]) AS stems
  FROM :dict_table a,
       unnest(str_split(regexp_replace(lower(coalesce(a.aliases,'') || ' ' || coalesce(a.best_used_for,'')), '[^a-zа-яё0-9 ]', ' ', 'g'), ' ')) AS w
  WHERE len(w) >= 3
),
cover AS (
  SELECT q.word,
         (SELECT count(DISTINCT d.src_table) FROM dstems d
           WHERE EXISTS (SELECT 1 FROM unnest(d.stems) ds
                          WHERE ds = ANY (q.stems))) AS n
  FROM qstems q
)
SELECT bucket, count(*) AS n FROM (
  SELECT CASE WHEN n = 0 THEN 'ПРОБЕЛ' WHEN n <= 2 THEN 'ОК' ELSE 'КАША' END AS bucket FROM cover
) x GROUP BY bucket ORDER BY bucket;
