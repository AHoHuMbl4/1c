# Ф6.3 — фактура: `solr_synonyms` на SereneDB 26.08.1

Снято 24.08 на **локальном sandbox** (`psql :7895`,
`/srv/1c/work/sandbox-26081`, SereneDB **26.08.1**). Код `serene_ask.py` не
менялся. База: `CREATE`/`DROP` только пробных словарей `f6_syn_*` + `SELECT
ts_lexize` (основной индекс не трогали). Боевой локальный `:7890` в момент
пробы **не отвечал** (timeout) — как у Ф6.4. Запасной listen `:17890` —
та же сборка 26.08.1, `SELECT version()` ок; DDL словарей гоняли на `:7895`.

Соседние образцы формата: `docs/F6_HYBRID_FACTS.md`, `docs/F6_FRESHNESS_FACTS.md`.

## 1. Что сейчас в коде (alias-слой, не движок)

Самодельный контур синонимов — **таблица + inverted + джойны/veto в питоне**,
не `solr_synonyms`.

| Слой | Где | Роль |
|---|---|---|
| Таблица `search_entity_alias` | `corpus_init.sql`, пишет `wiki_alias.sh` (`ALIAS_TABLE`, умолч. то же имя) | `src_table`, `aliases` (CSV-строка), `best_used_for`, `not_enough_for`, `seen_at` |
| Таблица `search_measure_alias` | тот же init / тот же генератор | человеческие имена величин к полю |
| Индекс `alias_idx` | `corpus_init.sql`: `USING inverted(aliases search_dict, src_table)` | ранжирование соперников `@@` + scorer (`bm25`/`tfidf`) |
| Поверхность кандидатов | `serene_ask.alias_hits` | `FROM alias_idx WHERE aliases @@ …` → RRF вместе с corpus/card/… |
| Подтверждение выбора | `_alias_verdict` + `ASK_ALIAS_VETO` | `unnest(str_split(aliases,','))` + `ts_lexize(STEM_DICT,…)` vs вопрос; лидер по `alias_idx` |
| Родство словоформ | `same_concept_groups` / куча мест | только `ts_lexize(STEM_DICT=search_dict_stem)` — **стемминг**, не синонимы классов |
| Генератор | `wiki_alias.sh` + `wiki_alias_parse.py`, юнит `1c-wiki-alias` | штатный агент OpenClaw; **Ф6.3 генератор (24.08):** `--local` вместо gateway |

Env уже есть: `ASK_ALIAS_INDEX`, `ASK_ALIAS_TOP`, `ASK_ALIAS_VETO`,
`ASK_ALIAS_BY_CONCEPTS`, `ASK_STEM_DICT`. Отдельного флага «native solr
synonyms» **нет**.

На sandbox `:7895` живой снимок: `search_entity_alias` = **178** строк;
`alias_idx` в `duckdb_indexes()` **нет** (только `search_idx`) — полный
контур alias на этой БД не собран; для фактуры словаря это не блокер.

## 2. Что говорят доки (штатные средства)

| Раздел | URL | Суть |
|---|---|---|
| CREATE TEXT SEARCH DICTIONARY | https://docs.serenedb.com/sql/statements/create_text_search_dictionary | словарь = анализатор индекса **и** запроса; шаблоны в т.ч. `solr_synonyms`, `pipeline`, `copy_from` |
| solr_synonyms | https://docs.serenedb.com/sql/statements/create_text_search_dictionary/solr-synonyms | Solr-формат inline: `a, b, c` двусторонне; `lhs => rhs` односторонне; без правила — passthrough |
| Options › SYNONYMS | https://docs.serenedb.com/sql/statements/create_text_search_dictionary/solr-synonyms#options | `SYNONYMS` string, **required**; «one rule per line»; **лимита объёма в доках нет** |
| Cookbook › Synonyms | https://docs.serenedb.com/cookbook/search/synonyms | типичный путь: `pipeline` = `text` → `solr_synonyms`; индекс колонкой с этим словарём; расширение на обеих сторонах |
| ts_lexize | https://docs.serenedb.com/sql/functions/search/full-text#ts_lexize | `ts_lexize(dictionary, text)` — что выдаёт анализатор (инспекция / query-side) |
| Cookbook › See what a word expands to | https://docs.serenedb.com/cookbook/search/synonyms#see-what-a-word-expands-to | двусторонняя группа → все члены; односторонняя → цель |

Каркас из cookbook (укороченно):

```sql
CREATE TEXT SEARCH DICTIONARY syn (
    template = 'pipeline',
    step1_template = 'text',
    step1_locale = 'en_US.UTF-8',
    step1_case = 'lower',
    step1_stemming = false,
    step2_template = 'solr_synonyms',
    step2_synonyms = 'tv, television, telly
laptop => notebook',
    frequency = true,
    position = true
);
-- индекс: CREATE INDEX … USING inverted (id, name syn);
SELECT ts_lexize('syn', 'telly');
```

План Ф6.3 уже фиксирует: обновление = **пересоздание** словаря (SYNONYMS —
inline строка), не ALTER карты.

## 3. Живые пробы 24.08

### 3.1 Отказ боевого локального `:7890`

```text
$ PGCONNECT_TIMEOUT=2 psql "host=127.0.0.1 port=7890 …" -c "SELECT version();"
psql: error: … port 7890 failed: timeout expired
```

### 3.2 Успех sandbox `:7895` (SereneDB 26.08.1)

**Bare `solr_synonyms`** (без tokenizer, как пример раздела solr-synonyms):

| Вход | Карта | `ts_lexize` |
|---|---|---|
| `остатки` | `остатки, склад, stoc, depozit` | `{depozit,stoc,остатки,склад}` |
| `stoc` | то же | тот же класс |
| `laptop` | `laptop => notebook` | `{notebook}` |
| `keyboard` | (нет правила) | `{keyboard}` |

**Pipeline `text` → `solr_synonyms`** (`step1_locale='ru_RU.UTF-8'`, stemming
off): одиночные слова — как выше; фраза `остатки на складе` →
`{depozit,stoc,остатки,склад,на,складе}` (слово `остатки` раскрыто,
`складе` не совпало с каноном `склад`).

**Пересоздание:** `DROP` + `CREATE` с новой картой — `foo` из `{bar,foo}`
становится `{baz,foo}`; старый член `bar` снова passthrough.  
`CREATE … IF NOT EXISTS` **не** обновляет карту (остаётся прежняя).

**Лимит inline SYNONYMS** (файл в psql `-f`, не argv):

| Строк правил | ≈ байт карты | CREATE + `ts_lexize` |
|---|---|---|
| 50 … 20 000 | ~1 КБ … ~400 КБ | ✅ все OK |
| 100 × длинные термы (~200 символов) | ~40 КБ | ✅ |

Жёсткого отказа движка в этом диапазоне **нет**. Практический потолок
раньше упирается в **argv** (`psql -c` → `Argument list too long` на
~10 к строк) — генератор обязан кормить SQL **файлом**, не аргументом
командной строки (тот же класс, что у `wiki_alias` / HOW_NOT_TO §0).

**Ловушка стемминга до синонимов** (одна карта `склад, остатки, stoc`):

| Pipeline | Вход | Результат |
|---|---|---|
| stemming **true** | `складе` / `склад` | оба → `{stoc,остатки,склад}` |
| stemming **false** | `складе` | `{складе}` (не в классе) |
| stemming **false** | `склад` | класс целиком |

Без стемминга (или без всех словоформ в карте) query-side раскрытие на
русском **молча дырявое**.

Пробные словари `f6_syn_*` после замера сняты `DROP`.

## 4. Сводка «средство → доки → 26.08.1 → путь ответа»

| Средство | В доках | На 26.08.1 (sandbox) | Query-side (без пересборки индекса) | Index-side (пересборка) |
|---|---|---|---|---|
| `CREATE … template='solr_synonyms'` | ✅ | ✅ | да — словарь для `ts_lexize` / анализа запроса | да, если словарь в `CREATE INDEX` |
| `pipeline` text→solr | ✅ cookbook | ✅ | да | да |
| `ts_lexize(dict, text)` | ✅ | ✅ на пробных dict | **главный кандидат Ф6.3** (как STEM_DICT) | инспекция |
| Inline `SYNONYMS` до ~400 КБ / 20 к правил | лимита нет | ✅ | да | да |
| Обновление карты | пересоздать dict | DROP+CREATE ✅; IF NOT EXISTS не обновляет | такт: rebuild dict | + REINDEX / recreate index колонки |
| Текущий `search_entity_alias` + `alias_idx` | наш слой | таблица есть; idx на sandbox нет | сейчас весь путь | — |
| `search_dict` / `search_dict_stem` на корпусе | наш init | stem dict имя отвечает; полный alias-контур не эталон sandbox | стемминг уже query-side | корпусный индекс на `search_dict` **без** синонимов |

**Вывод для Ф6.3:** синтаксис и `ts_lexize` на 26.08.1 **не блокер**.
Первый безопасный врез — query-side словарь рядом со STEM_DICT, без смены
`search_idx`. Снятие alias-джойнов — только после A/B. Вшивание в индекс
корпуса = отдельный шаг (пересборка + шум классов — риск плана §5).

## 5. Ловушки

1. **Стемминг до класса** — иначе `складе` ≠ `склад` (замер §3.2).
2. **IF NOT EXISTS** не меняет SYNONYMS — только DROP+CREATE.
3. **Карта файлом**, не `psql -c` / не argv юнита.
4. **Два слоя** не смешивать молча: CSV в `search_entity_alias` ≠ Solr-строка
   словаря; компиляция — отдельный шаг генератора/такта.
5. Cookbook вешает synonyms на индекс колонки — это **не** то же, что
   query-only `ts_lexize`; план Ф6.3 начинает с query-side.
6. Боевой okna / klient-1 в этом заходе **не мерялись** (без ssh).

## 6. Минимальный следующий кодовый шаг (без реализации)

Предложение для будущего PR (флаг, старое рядом до замера):

1. Env, напр. `ASK_SOLR_SYNONYMS_DICT` (имя словаря) + `ASK_SOLR_SYNONYMS=1`
   (умолч. `0`).
2. Такт/юнит: скомпилировать Solr-строку из `search_entity_alias` (+ кэш
   моста с пометкой источника) → `DROP`/`CREATE TEXT SEARCH DICTIONARY`
   **файлом**; GRANT по правилу грантов плана.
3. При флаге в пути ответа: там, где уже зовётся `ts_lexize(STEM_DICT, …)`
   для сопоставления/раскрытия вопроса — дополнительно (или pipeline)
   `ts_lexize(ASK_SOLR_SYNONYMS_DICT, …)`; **не** хардкодить списки слов.
4. Пока флаг выключен — `alias_hits` / `_alias_verdict` / `alias_idx`
   без изменений.
5. Снятие alias-джойнов — отдельный ворот после скорера / gold, не в том же
   PR, что первое включение dict.

Критерий: A/B на :8092 не хуже базлайна по вердиктам; латентность
`ts_lexize` на вопросе — в бюджете; красная линия Ф6 п.6 (нет языковых
списков в коде) соблюдена.
