\set ON_ERROR_STOP on

-- СТРАНИЦЫ ВИКИ OPENCLAW — СОБИРАЕТ БАЗА, А НЕ СКРИПТ.
--
-- Зачем вики. Замер 30.07: из 11 провалов приёмки 8-10 — выбрана НЕ ТА сущность. Переход на
-- модель посильнее (`v4 pro`) этого не починил: плохих исходов 11 против 11. Дело не в силе
-- рассуждения, а в том, что из НАЗВАНИЯ «Отчёт о розничных продажах» против «Реализация
-- Товаров Услуг» неоткуда узнать, какое отвечает на «на какую сумму мы продали». Это знание
-- о конкретной базе, и его надо дать, а не ждать от модели. Замысел владельца 30.07:
-- «нельзя надеяться на ллм, у него мало контекста чтобы правильно сделать; Wiki тут поможет».
--
-- 🔴 ПОЧЕМУ ЭТО SQL, А НЕ ПИТОН. Сборка текста идёт по данным всей базы: имена величин,
-- родство шапка↔строки, класс сущности. Вычитывать это наружу и склеивать у себя — прямой
-- запрет п. 20. Тела остаются во VIEW `wiki_pages` (Э7 б1): штатный COPY TO умеет писать
-- файлы, но не раскладку memory-wiki `entities/<page_id>.md` + purge — поэтому файловый
-- dump из такта снят; перефраз сущностей — таблицы алиасов в движке.
--
-- 🔴 УНИВЕРСАЛЬНОСТЬ. Ни одного имени сущности, величины или слова конкретной базы здесь нет.
-- Тип сущности — ПРЕФИКС имени от платформы 1С (`Catalog_`, `Document_`, …): берётся как есть
-- и НЕ переводится, перевод был бы привязкой к языку. Каркас страницы по-английски, иначе на
-- английской базе вики оказалась бы русской; данные при этом на языке базы.
--
-- 🔴 ЧЕГО НА СТРАНИЦЕ НЕТ: счётов, сумм, диапазонов дат. Страница попадает в промт при поиске,
-- а «249 документов» — это готовый ответ; устарев, он стал бы неверным ответом в обход базы
-- (п. 19: ни одна цифра в ответе не вычислена моделью). Сколько сейчас подошло — считает база
-- на каждом вопросе.

CREATE OR REPLACE VIEW wiki_entity_facts AS
SELECT t.src_table, t.label, coalesce(t.parent, '') AS parent,
       coalesce(pl.label, '')                       AS parent_label,
       coalesce(ec.cls, 'unknown')                  AS cls,
       (SELECT string_agg(DISTINCT k, ', ' ORDER BY k)
          FROM (SELECT unnest(map_keys(c2.nums)) AS k FROM search_corpus c2
                WHERE c2.src_table = t.src_table AND c2.nums IS NOT NULL)) AS measures,
       (SELECT string_agg(ch.label, ', ' ORDER BY ch.label)
          FROM search_tables ch WHERE ch.parent = t.src_table)             AS children
FROM search_tables t
LEFT JOIN search_tables pl       ON pl.src_table = t.parent
LEFT JOIN search_entity_class ec ON ec.src_table = t.src_table;

-- Человеческие слова к сущности лежат в `search_entity_alias` — их кладёт `wiki_alias.sh`
-- штатным агентом OpenClaw один раз при установке. Нет их — страница всё равно собирается,
-- просто без этого слоя: вики улучшает выбор, но не является условием работы.

-- Текст страницы целиком. Одна строка результата = один файл.
-- Служебные сущности пропускаются: по решению владельца 29.07 они не нужны даже в векторе,
-- и в основу для выбора сущности им тем более не место.
CREATE OR REPLACE VIEW wiki_pages AS
SELECT f.src_table AS page_id,
       '---' || chr(10)
    || 'pageType: entity' || chr(10)
    || 'entityType: ' || coalesce(nullif(lower(regexp_extract(f.src_table, '^([a-z]+)_', 1)), ''), 'record') || chr(10)
    || 'id: entity.' || f.src_table || chr(10)
    || 'canonicalId: ' || f.src_table || chr(10)
    || 'title: ' || f.label || chr(10)
    || coalesce((SELECT chr(10) || 'aliases:' || string_agg(chr(10) || '  - ' || trim(x.v), '')
                   FROM unnest(str_split(a.aliases, ',')) AS x(v)
                  WHERE a.aliases IS NOT NULL AND trim(x.v) <> ''), chr(10) || 'aliases: []')
    || coalesce((SELECT chr(10) || 'bestUsedFor:' || string_agg(chr(10) || '  - ' || trim(x.v), '')
                   FROM unnest(str_split(a.best_used_for, ',')) AS x(v)
                  WHERE a.best_used_for IS NOT NULL AND trim(x.v) <> ''), chr(10) || 'bestUsedFor: []')
    || coalesce((SELECT chr(10) || 'notEnoughFor:' || string_agg(chr(10) || '  - ' || trim(x.v), '')
                   FROM unnest(str_split(a.not_enough_for, ',')) AS x(v)
                  WHERE a.not_enough_for IS NOT NULL AND trim(x.v) <> ''), chr(10) || 'notEnoughFor: []')
    || chr(10)
    || CASE WHEN f.parent <> '' OR f.children IS NOT NULL THEN 'relationships:' || chr(10) ELSE '' END
    || CASE WHEN f.parent <> '' THEN
         '  - targetId: entity.' || f.parent || chr(10)
      || '    targetTitle: ' || f.parent_label || chr(10)
      || '    kind: line-items-of' || chr(10) ELSE '' END
    || coalesce((SELECT string_agg('  - targetId: entity.' || ch.src_table || chr(10)
                                || '    targetTitle: ' || ch.label || chr(10)
                                || '    kind: has-line-items', chr(10) ORDER BY ch.label)
                   || chr(10)
                 FROM search_tables ch WHERE ch.parent = f.src_table), '')
    || '---' || chr(10) || chr(10)
    || '# ' || f.label || chr(10) || chr(10)
    || 'Record type in this 1C database. Platform entity set: `' || f.src_table || '`.'
    || chr(10) || chr(10)
    -- 🔴 СЛОВА ДУБЛИРУЮТСЯ В ТЕЛО СТРАНИЦЫ, А НЕ ТОЛЬКО В ЗАГОЛОВОК. [замер 30.07] поиск по
    -- вики ищет по ТЕКСТУ: с алиасами только во frontmatter запрос «сколько мы заработали» не
    -- находил ничего, хотя ровно эти слова там стояли.
    || coalesce('## Asked about with these words' || chr(10) || chr(10)
                || nullif(a.aliases, '') || chr(10) || chr(10), '')
    || coalesce('## Answers questions about' || chr(10) || chr(10)
                || nullif(a.best_used_for, '') || chr(10) || chr(10), '')
    -- 🔴 «НЕ ОТВЕЧАЕТ» В ИСКОМЫЙ ТЕКСТ НЕ ИДЁТ. [замер 30.07] запрос «розничные продажи»
    -- нашёл регистр выручки именно по строке «розничные продажи в детализации» из раздела
    -- «не годится» — то есть отрицание сработало как совпадение, ровно наоборот смыслу.
    -- Поле остаётся во frontmatter: модель прочитает его через `wiki_get`, а поиск — не увидит.
    || CASE WHEN f.measures IS NOT NULL THEN
         '## Quantities recorded on this record' || chr(10) || chr(10)
      || 'Use one of these names verbatim when a question asks for a value:' || chr(10) || chr(10)
      || (SELECT string_agg('- `' || m || '`', chr(10))
            FROM (SELECT trim(u.m) AS m FROM unnest(str_split(f.measures, ',')) AS u(m)))
      || chr(10) || chr(10)
       ELSE
         '## Quantities' || chr(10) || chr(10)
      || 'This record type carries no numeric quantity. A question about an amount or about a '
      || 'number of units cannot be answered from it.' || chr(10) || chr(10)
       END
    || CASE WHEN f.parent <> '' THEN
         '## Position' || chr(10) || chr(10)
      || 'These are the line items inside `' || f.parent || '` (' || f.parent_label || '). '
      || 'A question about a document total belongs to the owning record, not to its lines.'
      || chr(10) || chr(10) ELSE '' END
    || CASE WHEN f.children IS NOT NULL THEN
         '## Line items' || chr(10) || chr(10)
      || (SELECT string_agg('- ' || trim(u.c), chr(10))
            FROM unnest(str_split(f.children, ',')) AS u(c))
      || chr(10) ELSE '' END AS body
FROM wiki_entity_facts f
LEFT JOIN search_entity_alias a ON a.src_table = f.src_table
WHERE f.cls <> 'service';

SELECT printf('вики: страниц к публикации %d', count(*)) AS итог FROM wiki_pages;
