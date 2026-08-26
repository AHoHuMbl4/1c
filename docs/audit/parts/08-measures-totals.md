# 08. measures-totals

Участок: `ubuntu/serenedb/serene_ask.py:3730–3935`.

## Зачем участок нужен

На строках 3730–3740 — `_shares_chars`: структурная проверка «слово и значение делят буквы» (подстрока или пересечение буквенных триграмм). На 3746–3857 — чтение модульных констант из окружения (алиасы, карточки, RRF, IVF, вето и бюджеты кандидатов). На 3861–3932 — три функции величин сущности: список имён числовых колонок корпуса (`measures_of`), словарь алиасов величин (`measure_aliases_of`), агрегаты sum/count/max/min по каждой величине (`totals_of`).

## Входы

| Символ | Входы |
|---|---|
| `_shares_chars(term, value)` | две строки; пустые после очистки → `False` (`3730–3738`) |
| `measures_of(src_table)` | имя сущности (`src_table`); SQL к `CORPUS` (`3869–3872`) |
| `measure_aliases_of(src_table)` | `src_table`; SQL к `search_measure_alias` (`3880–3883`) |
| `totals_of(src_table, match, preds, measures)` | сущность; SQL-фрагмент `match`; список предикатов `preds`; список имён величин `measures` (`3889–3903`) |

Константы блока читают `os.environ` при загрузке модуля (`3746–3857`). Внутри трёх функций величин env не читается. Используются модульные `CORPUS`, `INDEX` (вне участка: `"search_corpus"`, `"search_idx"`, `:77`), `lit`, `psql`, `_num` (`:8336`), `_ngrams` (`:3723`), `PICK_BUDGET` (`:92`) — только в формуле `MEANING_TOP`.

## Порядок работы

1. `_shares_chars`: очистка `term`/`value` от не-букв/цифр, lower; пусто → `False`; подстрока → `True`; иначе пересечение `_ngrams` (`3734–3740`).
2. При импорте: `ALIAS_TOP` … `MEANING_TOP` из env (`3746–3857`). `MEANING_TOP`: `ASK_MEANING_TOP` или `max(1, PICK_BUDGET // 40 // 4)` если env дал `0`/пусто (`3856–3857`).
3. `measures_of`: `SELECT DISTINCT` ключей `map_keys(nums)` из `CORPUS` по `src_table`, `nums IS NOT NULL`, `ORDER BY 1`; `RuntimeError` → `[]` (`3869–3874`).
4. `measure_aliases_of`: `SELECT measure, aliases FROM search_measure_alias` где `src_table` и `aliases` не пусты; словарь `measure → aliases`; ошибка → `{}` (`3880–3886`).
5. `totals_of`: пустой `measures` → `[]` (`3900–3901`). `where` = непустые из `[match] + preds + [src_table=…]` (`3902`). Источник: `INDEX` если `match` truthy, иначе `CORPUS` (`3903`). На каждую величину — `sum`/`count`/`max`/`min` через `TRY_CAST(… AS DECIMAL(38,10))` с `FILTER (NOT coalesce(map_extract_value(flags,'IsFolder'), false))` (`3913–3919`). Один `SELECT`; ошибка/`пустой ряд` → `[]` (`3920–3925`). В `out` только величины с `count > 0`: кортеж `(имя, sum, max, min)` через `_num` (`3928–3931`).

## Выходы

| Функция | Возврат | Потребители в том же файле (вне участка) |
|---|---|---|
| `_shares_chars` | `bool` | фильтр резолва значений `:3715` |
| `measures_of` | `list[str]` | выбор/проверка величины, промт, уточнения (`:8131`, `:8327`, `:11284`, `:13883`, `:13903`, `:13962`, `:13969`, `:13983`, `:13998`, `:14062`, `:14100`, `:14150`, `:14249`, `:14255` и др.) |
| `measure_aliases_of` | `dict` | подписи/выбор меры (`:4668`, `:8037`, `:8134`, `:9268`, `:13904`, `:13922`, `:13985`, `:13999`, `:14087`, `:14100`, `:14135`, `:14249`, `:14292`) |
| `totals_of` | `list[(name, sum, max, min)]` | живые альтернативы и контекст модели (`:13926`, `:13976`, `:14062`, `:14121`, `:14150`, `:14280`); обёртки `:7975`, `:7985` |

Константы `3746–3857` — модульные глобалы для других участков файла; сами `measures_of` / `measure_aliases_of` / `totals_of` их не читают.

## Обращения наружу

| Место | Что | Назначение |
|---|---|---|
| `3869–3872` | SQL `psql` → `CORPUS`, `unnest(map_keys(nums))` | имена величин сущности |
| `3880–3883` | SQL `psql` → `search_measure_alias` | алиасы величин |
| `3921` | SQL `psql` → `INDEX` или `CORPUS`, агрегаты по `nums` | итоги/max/min по величинам |

HTTP и вызов языковой модели в этом диапазоне: нет.

## Переключатели

Все читаются при загрузке модуля (`3746–3857`). На `measures_of` / `measure_aliases_of` / `totals_of` не влияют.

| Env | Умолчание | Место |
|---|---|---|
| `ASK_ALIAS_TOP` | `8` | `3746` |
| `ASK_ALIAS_INDEX` | `alias_idx` | `3749` |
| `ASK_CARD_INDEX` | `entity_card_idx` | `3754` |
| `ASK_RRF_K` | `60` | `3759` |
| `ASK_SQL_RRF` | `'0'` → выкл (`== '1'`) | `3762` |
| `ASK_CORPUS_IVF_IDX` | `corpus_ivf_idx` | `3763` |
| `ASK_RESOLVER_IVF` | `'0'` → выкл | `3768` |
| `ASK_RESOLVER_IVF_IDX` | `resolver_ivf_idx` | `3769` |
| `ASK_ALIAS_VETO` | `'1'` → вкл | `3782` |
| `ASK_PROBE` | `'0'` → выкл | `3789` |
| `ASK_SKIP_SERVICE_RIVALS` | `'1'` → вкл | `3793` |
| `ASK_ALIAS_BY_CONCEPTS` | `'0'` → выкл | `3805` |
| `ASK_VETO_NEEDS_RANK` | `'0'` → выкл | `3820` |
| `ASK_VETO_HEAD_WINS` | `'1'` → вкл | `3830` |
| `ASK_MEANING_TOP` | `0` → fallback от `PICK_BUDGET` | `3856–3857` |

`CARD_FIELDS` — кортеж литералов, не env (`3755`). Кэши `_CORPUS_IVF_CACHE`, `_RESOLVER_IVF_CACHE` — пустые dict (`3764`, `3770`).

## Развилки

- `_shares_chars`: пустые строки / подстрока / триграммы (`3737–3740`).
- `measures_of` / `measure_aliases_of`: успех SQL vs `RuntimeError` → `[]` / `{}` (`3873–3874`, `3885–3886`).
- `totals_of`: нет `measures` → `[]` (`3900–3901`); `match` задаёт `INDEX` vs `CORPUS` (`3903`); ошибка/`пустой ряд` → `[]` (`3922–3925`); величина с `count==0` в `out` не попадает (`3930–3931`).

## Чего здесь нет

- `signal_terms`, `clarify_text`, `refuse_text` — вне диапазона (`:3408`, `:3454`, `:3482`); в 3730–3935 нет.
- Выбор одной величины, реранк, гейт ответа, HTTP, LLM — нет.
- Чтение env внутри трёх функций величин — нет.
- Использование констант `ALIAS_*` / `ASK_SQL_RRF` / вето внутри `measures_of`/`measure_aliases_of`/`totals_of` — нет.
- С 3935 начинается комментарий «детектор развилки»; тело детектора в этот диапазон не входит.
