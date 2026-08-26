# 09. fork-detector

## Зачем участок нужен
Участок `ubuntu/serenedb/serene_ask.py:3935-4760` считает по корпусу полный круг кандидатов (`fork_scan` / `fork_scan_readings`), строит типизированный атом ответа (`_fork_atom_of`) и группирует источники в классы эквивалентности (`fork_classes` / `fork_classes_windowed`). Ключ класса и подписи веток (`fork_key_of`, `fork_labels_*`, `_class_label_lookup`) обслуживают журнал `search_fork_class` и разведение веток. Модель в участке не вызывается.

## Входы
- **`fork_scan(match, preds, rel_by_src)`** — `match` в WHERE не идёт (`:4136`); `preds` — SQL-предикаты; `rel_by_src`: `{src_table: [меры]}` (`:4107-4139`).
- **`fork_scan_readings(match, readings, rel_by_src)`** — `readings`: список dict с `period` / `origin` / `interpretation_id` / `day_basis` / `window_fp` (`:4184-4226`).
- **`fork_detector_scan(match, preds, intent, today, rel_by_src, period_from_prior=False, measure_word="", want=None, day_basis_prefer=None, trusted=None)`** (`:4261-4298`).
- **`fork_classes(rows, measure_word="", want=None, rel_by_src=None, period_meta=None)`** — `rows` из скана (`:4359-4378`).
- **`_fork_atom_of(row, srcs, measure_word="", alias_by=None, want=None, rel_measures=None, period=None)`** — строка `{count, folders, sums}` (`:4651-4710`).
- **`fork_key_of(src_set, measure_ctx, window_fp="")`**, **`fork_labels_of(fork_key, srcs)`**, **`fork_labels_covering(srcs)`** (`:4381-4544`).
- Таблица корпуса: `CORPUS` = `"search_corpus"` (объявлено `:77`, используется `:4142-4170`).
- Env участка: см. «Переключатели». `ASK_ENTITY_FORM` читается здесь, объявлен вне (`:1431`).

## Порядок работы
1. При загрузке: `FORK_DETECT`, `FORK_OUTCOMES`, `ASK_JOURNAL`, `ASK_CHOICE_MEMORY`, `ASK_MEMORY_APPLY`, `_FORK_MEAS_TTL` (`:3948-3970`).
2. `_measures_by_src(cands)`: кэш TTL → иначе `SELECT DISTINCT src_table, map_keys(nums)` → `{src: [k]}` (`:3974-3995`).
3. `_aliases_by_src(cands)`: `SELECT … FROM search_measure_alias` → `{src: {measure: aliases}}` (`:3998-4014`).
4. `_fork_relevant(word, names, alias_by, want)` → список мер атома через `measure_choice` / headline-pool (`:4051-4097`).
5. `fork_detector_scan`: `period_readings` → опц. `expand_readings_calendar_axis`; при `len(readings)<=1` — один `fork_scan` (+ разрез catalog/dated при `ASK_ENTITY_FORM`) → `fork_classes`; иначе `fork_scan_readings` → `fork_classes_windowed` (`:4261-4298`).
6. `fork_scan`: WHERE = `preds` + `src_table IN (…)`; SQL1 count/folders `GROUP BY src_table`; SQL2 `unnest(map_entries(nums))` суммы по мерам; в `out` только `count>0`; нулевые суммы отбрасываются (`:4107-4181`).
7. `fork_scan_readings`: по каждому reading — preds окна; catalog без date-pred при `ASK_ENTITY_FORM`; ячейки `computed` / `no_live_cells` (`:4184-4226`).
8. `_fork_atom_of` → `build_answer_atom`; `_fork_atom_equiv_fp` — отпечаток; `fork_classes*` кладут src в бакеты и `fork_classes._meta_by_fp` (`:4315-4378`, `:4229-4258`, `:4651-4710`).
9. `_fork_log` / `_fork_log_day_basis` при `len(classes)>=2`: UPSERT в `search_fork_class` (`:4433-4490`).
10. `_class_label_lookup`: day-basis → `fork_labels_of` по id ветки; иначе `render_window_label` или `fork_labels_of` / `fork_labels_covering` (`:4722-4752`).

## Выходы
| Функция | Возврат | Потребитель в участке |
|---|---|---|
| `fork_scan` | `{src: {count, folders, sums}}` | `fork_scan_readings`, `fork_detector_scan` |
| `fork_scan_readings` | `(cells, merged_rows, period_by_src)` | `fork_detector_scan` |
| `fork_classes` / `fork_classes_windowed` | `{fp: [src…]}` + side `_meta_by_fp` | `_fork_log*`, `fork_detector_scan` |
| `fork_detector_scan` | `(rows, cls, readings, cells)` | нет внутри участка |
| `_fork_atom_of` | dict атома | `fork_classes*` |
| `fork_key_of` / `_fork_key_for_period` | sha1 hex | `_fork_log*`, `_class_label_lookup` |
| `fork_labels_of` / `fork_labels_covering` | `{src: label}` [, fork_key] | `_class_label_lookup` |
| `fork_label_siblings` | всегда `[]` (`:4547-4554`) | — |
| `_class_label_lookup` | `(label\|None, fork_key\|None)` | нет внутри участка |
| `_fork_pool_excluded` | `[{src, reason: no_live_cells}]` | нет вызова в участке |

## Обращения наружу
HTTP / LLM: нет.
| Место | SQL / вызов | Назначение |
|---|---|---|
| `:3985-3986` | `SELECT DISTINCT src_table, unnest(map_keys(nums)) FROM search_corpus` | карта мер |
| `:4004-4007` | `SELECT … FROM search_measure_alias WHERE src_table IN (…)`` | алиасы мер |
| `:4142-4143` | `SELECT src_table, count(*) FILTER (…) … GROUP BY 1` | счёт/папки |
| `:4165-4170` | `unnest(map_entries(nums))` + `sum(TRY_CAST…)` | суммы мер |
| `:4442-4448`, `:4482-4488` | `INSERT … search_fork_class ON CONFLICT DO UPDATE` | журнал классов |
| `:4502-4505` | `SELECT src, label FROM search_fork_label WHERE fork_key=…` | подписи по ключу |
| `:4527-4530` | `SELECT fork_key, src, label FROM search_fork_label WHERE src IN (…)`` | покрытие подписями |
| `:4668` | `measure_aliases_of(src0)` (вне участка) | алиасы, если не переданы |

При `RuntimeError` у `psql`: пустые карты/скан/метки; суммы — `pass` (`:4180`); лог — `pass` (`:4449-4450`, `:4489-4490`).

## Переключатели
| Имя | Чтение | По умолчанию | Эффект в участке |
|---|---|---|---|
| `ASK_FORK_DETECT` | `:3948` | `"1"` → True | объявлен; использование в участке: нет |
| `ASK_FORK_OUTCOMES` | `:3949` | `"1"` → True | объявлен; использование в участке: нет |
| `ASK_JOURNAL` | `:3952` | `"1"` → True | объявлен; запись журнала исходов здесь: нет |
| `ASK_CHOICE_MEMORY` | `:3957` | `"1"` → True | объявлен; применение здесь: нет |
| `ASK_MEMORY_APPLY` | `:3959` | `"0"` → False | объявлен; применение здесь: нет |
| `ASK_FORK_MEAS_TTL` | `:3970` | `600` | TTL кэша `_measures_by_src` |
| `ASK_ENTITY_FORM` | вне `:1431`, использование `:4204+`, `:4275+`, `:4341` | `"0"` → False | catalog без date-pred; form/axis в fp |

Выкл. строками `"0"`/`"false"`/`"no"` для fork/journal/memory (`:3948-3959`); `ASK_ENTITY_FORM` — только `"1"`.

## Развилки
- Пустой `rel_by_src` / нет строк с `count>0` → `{}` (`:4132-4133`, `:4155-4156`).
- `want=sum` + пустой `rel_measures` или пустые sums после отсева нулей → атом `PROOF_NA` (`:4672-4683`).
- `want=count` → только count; иначе sum-путь / fallback count при пустых sums (`:4684-4704`).
- `exact is not None` → `PROOF_COMPUTED`, иначе `PROOF_UNCOUNTED` (`:4705`).
- Один reading vs несколько → `fork_classes` vs `fork_classes_windowed` (`:4270-4298`).
- `ASK_ENTITY_FORM` + date-preds → catalog сканируется без preds (`:4204-4214`, `:4275-4284`).
- `_fork_atom_equiv_fp`: для `PROOF_NA` — `(op, status, window)`; для sum не включает count/folders; для count — folders; окно `(origin, from, to)` всегда; `day_basis` в fp не входит (`:4315-4344`).
- Day-basis с ≥2 id на одну (src, base_wfp) → отдельная запись лога с `src_set`=id веток; эти fp не дублируются обычным логом (`:4433-4474`).
- `_class_label_lookup`: приоритет day-basis label → `render_window_label` → labels по fork_key → covering (`:4722-4752`).
- `fork_label_siblings` → всегда `[]` (`:4554`).

## Чего здесь нет
- Вызовов LLM / HTTP.
- Разбора вопроса / intent (только потребление готовых `intent`/`preds`/`readings`).
- Исходов A/B/C ответа клиенту (флаги `FORK_*` объявлены, ветвление ответа здесь нет).
- Записи в `search_fork_label` (только чтение).
- Применения `ASK_JOURNAL` / `ASK_CHOICE_MEMORY` / `ASK_MEMORY_APPLY` (только объявления `:3950-3959`).
- Использования `match` в WHERE скана (`:4136`).
- Функция `count_question_skips_axis` начинается на границе (`:4755`); тело за `:4760`.
