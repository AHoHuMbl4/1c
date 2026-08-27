# Д3 — пустой `alias_idx` при живом словаре (27.08.2026)

База замера: **okna** (SereneDB **26.08.1**, `127.0.0.1:7890`).  
Контур кода: `ubuntu/serenedb/` (`wiki_alias.sh`, `corpus_init.sql`,
`corpus_postcheck.sql`). `serene_ask.py` не трогали.

Доки движка (обязательный поход перед выводом):

- [Lifecycle — Inverted Index](https://docs.serenedb.com/sql/indexes/inverted#lifecycle)
- [Refreshing — REFRESH_* (VACUUM)](https://docs.serenedb.com/sql/statements/vacuum#refreshing--refresh_)
- [Visibility and the refresh model](https://docs.serenedb.com/sql/indexes/inverted/maintenance#visibility-and-the-refresh-model)

---

## 1. Причина — фактом

| Шаг | Где | Что делает |
|---|---|---|
| Создание индекса | `corpus_init.sql` | `CREATE INDEX IF NOT EXISTS alias_idx … USING inverted(...)` — обычно на ещё пустой `search_entity_alias` |
| Наполнение | `wiki_alias.sh` | `INSERT` / `UPDATE` / `DELETE` в `$ALIAS_TABLE` (умолч. `search_entity_alias`) пачками из ответа модели |
| Публикация | **не было** | ни `VACUUM (REFRESH_TABLE)`, ни `VACUUM (REFRESH_INDEX)` после записи |

Инвертированный индекс SereneDB **eventually consistent**: строки после
записи не видны поиску, пока их не опубликует refresh (явный `VACUUM
(REFRESH_*)` или фоновый поток с `refresh_interval`, умолч. 1000 мс).
Это прямо в доках (Lifecycle / VACUUM › Refreshing).

Образец правильного контура уже был в проекте:

- `entity_card_build.sql` — после `CREATE INDEX entity_card_idx` сразу
  `VACUUM (REFRESH_TABLE) search_entity_card`;
- `build.sh` / `corpus_merge.sql` — `VACUUM (REFRESH_INDEX) search_idx`
  после корпуса (и отдельно от транзакции записи: REFRESH внутри
  транзакции с INSERT — тихий no-op, CHANGELOG).

У алиасов этого шага не было: словарь рос, `alias_idx` мог оставаться
пустым, ошибок снаружи нет — ранжирование `tfidf` по алиасам просто
молча не участвует. Это ровно п. 13 TARGET.md (молчаливая потеря качества).

### Живой замер поведения движка (okna, 27.08)

Боковая таблица `d3_probe_*` (боевой `alias_idx` не ломали):

| Момент | строк таблицы | записей в индексе |
|---|---:|---:|
| CREATE INDEX на пустой | 0 | 0 |
| сразу после INSERT (без VACUUM) | 1 | **0** |
| через ~3 с (фон) | 1 | 1 |
| bulk INSERT 254 без VACUUM, сразу | 254 | **0** |
| bulk через ~5 с | 254 | 254 |
| сразу после DELETE+INSERT | 100 | 254 (устаревший счёт) |
| через ~5 с | 100 | 100 |
| сразу после INSERT + явный `VACUUM (REFRESH_TABLE)` | 1 | 1 |

Вывод: фон обычно подтягивает за секунды, но **сразу после записи**
индекс пуст/устарел; явный REFRESH — контракт пайплайна (как у карточки
и корпуса). Факт C2: на боевой okna до починки было **254 / 0**, и индекс
наполнился только после ручного `DROP`+`CREATE`+`VACUUM (REFRESH_TABLE)` —
пайплайн явной публикации не делал.

Не верные варианты как «единственная причина»:

- «индекс создан до наполнения» — само по себе нормально; CREATE на уже
  полной таблице сразу даёт count=count (замер);
- «способ записи (INSERT) индекс не обновляет» — обновляет буфер, но
  читателям нужен refresh;
- «нужен только DROP+CREATE» — нет, достаточно `VACUUM (REFRESH_TABLE)`.

---

## 2. Все inverted-индексы okna (после C2)

| индекс | таблица | строк таблицы | записей в индексе | num_docs (sdb_metrics) | пустой при непустой? |
|---|---|---:|---:|---:|---|
| `alias_idx` | `search_entity_alias` | **257** | **257** | 257 | нет (починен в C2 вручную; дальше — пайплайн) |
| `alias_okna_c1_idx` | `alias_okna_c1` | 258 | 258 | 258 | нет |
| `search_idx` | `search_corpus` | 1 230 156 | 1 206 662 | 1 206 662 | нет (не пуст; разница — строки без текстового документа в индексе, не «0 при N») |
| `entity_card_idx` | `search_entity_card` | 254 | 254 | 254 | нет |
| `resolver_ivf_idx` | `resolver_index` | 69 621 | 69 621 | 69 621 | нет |
| `corpus_ivf_idx` | `search_corpus` | 1 230 156 (emb NOT NULL: 1 206 662) | — | 1 230 156 | нет |

**Находок «индекс = 0 при таблице > 0» на текущей okna нет.** Историческая
находка C2 по `alias_idx` (254 / 0) — закрыта пересозданием + этой починкой
пайплайна.

Места создания inverted в репозитории:

| индекс | создание | явный REFRESH после наполнения |
|---|---|---|
| `alias_idx` | `corpus_init.sql` | **было: нет** → теперь `wiki_alias.sh` |
| `search_idx` | `corpus_init.sql` / `serene_search_build.py` | `corpus_merge.sql`, `build.sh` шаг 6 |
| `entity_card_idx` | `entity_card_build.sql` (DROP+CREATE) | там же `VACUUM (REFRESH_TABLE)` |
| IVF | отдельно (выкат/сборка векторов) | свой контур; не тема Д3 |

---

## 3. Что починено

1. **`wiki_alias.sh`** — после итогового SELECT по словарю, отдельным
   вызовом `psql` (не в одной транзакции с INSERT):

   ```bash
   psql "$DSN" -q -c "VACUUM (REFRESH_TABLE) $ALIAS_TABLE;"
   ```

   Работает и для боевой `search_entity_alias`, и для боковой
   `$ALIAS_TABLE` (C1/C2). Soft-echo при сбое — такт не рвём здесь же;
   жёсткий замок — в postcheck.

2. **`corpus_postcheck.sql`** — после такта:

   - нет `alias_idx` при непустом `search_entity_alias` → `error(...)`;
   - `count(alias_idx)=0` при `count(search_entity_alias)>0` → `error(...)`.

   Пустая установка (0 / 0) проходит.

---

## 4. Замок

| слой | файл | что ловит |
|---|---|---|
| чистая функция | `inverted_index_guard.py` → `assert_index_covers_table` | table>0 и index==0 → AssertionError |
| оффлайн-тест | `test_inverted_index_guard.py` | сломанный/целый случай; наличие REFRESH в `wiki_alias.sh`; проверка в `corpus_postcheck.sql` |
| такт сборки | `corpus_postcheck.sql` | живая база: пустой `alias_idx` валит такт |

Демо fail → pass (okna, боковая `d3_guard_probe`):

| phase | table_rows | index_rows |
|---|---:|---:|
| BROKEN (INSERT без VACUUM) | 1 | **0** → замок падает |
| FIXED (`VACUUM (REFRESH_TABLE)`) | 1 | **1** → замок проходит |

Оффлайн: `python3 ubuntu/serenedb/test_inverted_index_guard.py` → **13 ok, 0 fail**
(без DSN; с `SERENEDB_DSN` добавляется live-ветка).

---

## 5. Не делали

- не правили `serene_ask.py` и `deploy-okna-serene-ask.sh` (чужие);
- не звали `VACUUM` из `/health` (уже запрещено контуром freshness);
- не пересоздавали боевой `alias_idx` повторно (после C2 уже 257 / 257).
