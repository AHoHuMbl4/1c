# С5-пайплайн: словарь обиходных слов на любой базе

Дата: 28.08.2026. Поток С, задача С5 в `docs/PLAN_TO_TARGET.md`.

## Cold start (новая база)

Первый проход `wiki_alias.sh` идемпотентен: в пачку попадают только сущности
без непустого алиаса (пустышки старше `WIKI_ALIAS_RETRY_H` переспрашиваются).

Отбор пачки — `ubuntu/serenedb/wiki_alias_select_entity_batch.sql`:

```sql
WHERE f.cls <> 'service'
  AND NOT EXISTS (SELECT 1 FROM :alias_table a WHERE a.src_table = f.src_table
                  AND (coalesce(a.aliases,'') <> ''
                       OR a.seen_at > now() - INTERVAL :retry_h HOUR))
ORDER BY d, f.src_table LIMIT :batch
```

Сначала seed — первая непокрытая сущность; остальные — по векторной близости
к ней. Покрытые с непустым `aliases` в пачку не попадают.

### Тактов до полного покрытия сущностей

| Параметр | Умолчание | Где |
|---|---|---|
| `WIKI_ALIAS_PER_TACT` | 100 | `build.sh` → аргумент CAP `wiki_alias.sh` |
| `WIKI_ALIAS_BATCH` | 20 | `wiki_alias.sh` |

Формула (только сущности, `cls <> 'service'`):

```
ticks_entity = ceil(E / WIKI_ALIAS_PER_TACT)
```

`E` — число сущностей из `wiki_entity_facts` (или `search_quality.k='meta_entities'`
после такта). Не слова, не эталоны — только метаданные.

| База | E (замер) | CAP=100 | ticks |
|---|---:|---:|---:|
| okna | 351 | 100 | **4** |
| ut_test | 1502 | 100 | **16** |

Добор величин (`wiki_alias_select_measure_batch.sql`) и разведение столкновений
идут отдельно и могут добавить такты; бюджет `WIKI_ALIAS_MAX_SEC` (120 с)
ограничивает работу за один такт, но не блокирует завершение — остаток берёт
следующий такт.

## Периодическое доучивание (существующая база)

**По умолчанию выключено:** `WIKI_ALIAS_REASK_EVERY=0` — боевые базы не меняются
молча.

| Env | Умолчание | Смысл |
|---|---|---|
| `WIKI_ALIAS_REASK_EVERY` | 0 | раз в N тактов (`wiki_alias_tick` в `search_quality`) |
| `WIKI_ALIAS_REASK_STALE_DAYS` | 30 | записи основного словаря старше — кандидаты reask |
| `WIKI_ALIAS_REASK_CAP` | =BATCH | лимит сущностей за один reask-прогон |

Счётчик такта: `build.sh` инкрементирует `search_quality.k='wiki_alias_tick'`,
передаёт в `wiki_alias.sh` как `WIKI_ALIAS_TICK`.

Поток reask (только при `REASK_EVERY > 0` и `tick % EVERY == 0`):

1. `alias_reask_pool.py` — журнал (`alias_candidates`) + stale из основного словаря.
2. Модель → боковая таблица `alias_<db>_reask` (не `search_entity_alias`).
3. `alias_reask_confirm.py` — сверка: `confirm_count >= 2` **или** gold `pass`.
4. Подтверждённые → `wiki_alias_reask_merge_confirmed.sql` в основной словарь.
5. Остальное → `alias_<db>_reask_journal` (прецедент `ask_choice_memory`).

Файлы: `wiki_alias_reask_*.sql`, `work/pipeline/alias_reask_{pool,confirm}.py`.

Замки: `work/pipeline/test_wiki_alias_psql.py`, `test_alias_candidates.py` 22/0.
