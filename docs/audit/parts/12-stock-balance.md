# 12. stock-balance

Участок: `ubuntu/serenedb/serene_ask.py:5901–6160` (кэш/маркеры сразу выше: `5892–5898`).

## Зачем участок нужен

Набор функций для пути «вопрос про остатки»: читает из БД список/карту баланс-источников, распознаёт вопрос по маркерам, отличает именованный товар от «темы» остатков, отсекает структурно непригодные и «продажные» кандидаты, собирает ответы `no_data` / `clarify`. Сам остаток (сумму/количество) участок не считает.

## Входы

| Что | Откуда |
|---|---|
| `question: str` | аргументы `question_asks_stock_balance`, `stock_asks_named_product`, `stock_balance_named_no_data`, `balance_bridge_clarify`, `filter_stock_balance_sales_noise` |
| `intent: dict` | `kind`, `measure`, `terms` — `stock_asks_named_product`, `_stock_scaffold_stems` (`6014–6039`) |
| `regs` | опционально в `balance_registers_with_goods`; иначе `balance_registers()` (`5964–5970`) |
| `cands` | списки `src_table` в `filter_balance_structural`, `filter_stock_balance_sales_noise` |
| `diag`, `cut`, `t0` | в ответы `stock_balance_named_no_data`, `balance_bridge_clarify` |
| `labels: dict` | опционально в `balance_bridge_clarify` (`6103–6105`) |
| `src: str` | `stock_balance_is_sales_noise` |
| `_STOCK_MARKERS` | кортеж подстрок (`5895–5898`) |
| `CORPUS`, `TABLES` | `"search_corpus"`, `"search_tables"` (`77`) |
| `STEM_DICT` | модуль, из `ASK_STEM_DICT` (`903`) |
| `NO_DATA_TEXT` | модуль, из `ASK_NO_DATA_TEXT` (`317`) |
| кэши `_BALANCE_REGS`, `_BALANCE_MAP` | `{"at", "set"/"rows"}` (`5892–5893`) |

Переменные окружения участок сам не читает; только константы модуля и `psql` (DSN снаружи).

## Порядок работы

1. **Метаданные источников**
   - `balance_registers()` — кэш 300 с; иначе `SELECT v FROM search_meta WHERE k='balance_registers'`, разбор CSV-строки в `frozenset` (`5901–5915`).
   - `balance_map_rows()` — кэш 300 с; иначе `SELECT … FROM search_balance_map`; при RuntimeError с «таблица не существует» → `[]`, иначе проброс (`5917–5940`).
   - `balance_capable_sources()` — `frozenset` всех `src_table` из карты (`5943–5945`).
   - `balance_capable_or_registers()` — карта, если непуста; иначе реестр (`5948–5953`).
   - `balance_registers_with_goods(regs)` — из `regs` только те `src_table`, где в корпусе `map_extract_value(refs_map,'ТМЦ') IS NOT NULL` (`5964–5977`).
2. **Триггер вопроса** — `question_asks_stock_balance`: lower+пробелы; `True`, если любая подстрока из `_STOCK_MARKERS` входит в текст (`5956–5961`).
3. **Именованный товар** — `_stems_of_text` → `ts_lexize(STEM_DICT,…)` или fallback `_intent_word` при сбое/пустоте, стемы длины ≥3 (`5980–5995`); `_stock_scaffold_stems` = стемы `intent.kind` + совпавших маркеров (`5998–6011`); `stock_asks_named_product`: при триггере остатков проверяет `measure` и элементы `terms` — терм «именованный», если его стемы не ⊆ scaffold и текст не совпадает с `kind` (`6014–6039`).
4. **Отсев кандидатов** — `filter_balance_structural`: карта по `src`; кандидаты вне карты не трогает; для тех, что в карте — SQL «есть `nums`», плюс `has_period` и (`has_rt` ∨ `has_dk` ∨ `form=="accumulation_warehouse"`) (`6061–6100`); `filter_stock_balance_sales_noise` при триггере остатков убирает `stock_balance_is_sales_noise` (`6139–6158`).
5. **Готовые ответы** — `stock_balance_named_no_data` → `kind=no_data` (`6042–6049`); `balance_bridge_clarify` → `kind=clarify` со списком `capable` (`6103–6136`).

Потребители вне участка (тот же файл): `answer`/`ветка кандидатов` — `11920–11925`, `12156–12181`, `12565–12570`; также `question_asks_stock_balance` в `5247`.

## Выходы

| Функция | Возврат |
|---|---|
| `balance_registers` / `balance_capable_*` / `balance_registers_with_goods` | `frozenset[str]` `src_table` |
| `balance_map_rows` | `list` строк `(src_table, form, has_record_type, has_debit_credit, has_period, has_ext_dimension)` |
| `question_asks_stock_balance`, `stock_asks_named_product`, `stock_balance_is_sales_noise` | `bool` |
| `filter_balance_structural`, `filter_stock_balance_sales_noise` | отфильтрованный список `cands`; в `diag` — `balance_structural_drop` / `stock_sales_noise_drop` |
| `stock_balance_named_no_data` | `{"partial","kind":"no_data","text","sources":[],"diag"}`; `diag.stock_named_absent=True` |
| `balance_bridge_clarify` | `None` если `capable` пуст; иначе `{"kind":"clarify","text","options","sources","diag"}` с `balance_bridge="clarify"`, `balance_capable` |

## Обращения наружу

Все через `psql` (подпроцесс `psql`+DSN, `327–361`). HTTP в участке нет.

| Место | SQL / вызов | Назначение |
|---|---|---|
| `5910` | `SELECT v FROM search_meta WHERE k='balance_registers'` | список регистров остатков |
| `5928–5930` | `SELECT src_table, form, has_record_type, has_debit_credit, has_period, has_ext_dimension FROM search_balance_map` | карта баланс-источников |
| `5973–5976` | `SELECT DISTINCT src_table FROM search_corpus WHERE src_table IN (…) AND map_extract_value(refs_map,'ТМЦ') IS NOT NULL` | регистры с осью ТМЦ |
| `5987` | `SELECT ts_lexize(STEM_DICT, текст)` | стемы для scaffold/именованности |
| `6076–6080` | `SELECT src_table FROM search_corpus WHERE … nums IS NOT NULL AND len(map_keys(nums))>0 GROUP BY 1` | «живые» источники с мерой |
| `6112–6114` | `SELECT src_table, label FROM search_tables WHERE src_table IN (…)` | подписи для clarify |
| `6046` → `refuse_text` (`3482–3504`) | при пустом `NO_DATA_TEXT`: `ds_chat` (языковая модель) | текст отказа |
| `6120` | `disambiguate_labels` (внутри — своя логика/SQL вне участка) | развести одинаковые label |

## Переключатели

| Имя | Где читается | Умолчание | Влияние в участке |
|---|---|---|---|
| `ASK_STEM_DICT` | `903` → `STEM_DICT` | `"search_dict_stem"` | имя словаря в `ts_lexize` (`5987`) |
| `ASK_NO_DATA_TEXT` | `317` → `NO_DATA_TEXT` | `""` | текст `no_data`; пусто → `refuse_text(question)` (`6046`) |
| TTL кэша 300 с | `5908`, `5925` | литерал `300` | повторный SQL meta/map не чаще раза в 300 с |
| `SERENEDB_DSN_RO` | внутри `psql` (`329–330`) | нет (иначе RuntimeError) | все SQL участка |

Флагов `ASK_*` специально для stock/balance в этом участке нет.

## Развилки

- Кэш meta/map свеж (<300 с) → без SQL (`5907–5909`, `5924–5926`).
- `search_balance_map` отсутствует → пустые rows; иной RuntimeError → исключение (`5931–5938`).
- `balance_capable_sources()` непуст → он; иначе `balance_registers()` (`5950–5953`).
- Пустой `question` / нет маркеров → не «остатки» (`5959–5961`).
- Нет `regs` → пустой frozenset goods (`5971–5972`).
- `ts_lexize` падает / стемов нет → одно слово `_intent_word` при длине ≥3 (`5989–5994`).
- Нет триггера остатков → `stock_asks_named_product` = False; `filter_stock_balance_sales_noise` без изменений (`6016–6017`, `6153–6154`).
- Пустая карта → `filter_balance_structural` возвращает `cands` как есть; нет пересечения с картой — тоже (`6071–6075`).
- Кандидат в карте: оставляется только при `c in live` и `struct_ok` (`6093–6098`).
- `capable` пуст → `balance_bridge_clarify` = `None` (`6107–6108`).
- В `question` есть кириллица (U+0400–04FF) → русский текст clarify, иначе английский (`6123–6129`).
- `stock_balance_is_sales_noise`: `книгапродаж` / `актсверки`|`reconciliation` / (`реализац` ∧ префикс `accumulationregister_`) (`6139–6148`).

## Чего здесь нет

- Подсчёта остатка (SUM/агрегат количества или суммы) — нет.
- Разреза по складу/номенклатуре в ответе — нет (только фраза в тексте clarify).
- HTTP-вызовов — нет.
- Прямого вызова модели, кроме косвенного `refuse_text` при пустом `ASK_NO_DATA_TEXT` — нет.
- Записи в БД, инвалидации кэша по событию — нет (только TTL 300 с).
- Ранжирования баланс-источников по релевантности вопросу — нет (только отсев и список для clarify).
- Чтения `has_ext_dimension` из карты для решений фильтра — колонка выбирается (`5930`), в `filter_balance_structural` не используется.
