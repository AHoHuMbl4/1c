# 13. fork-outcomes

Источник: `ubuntu/serenedb/serene_ask.py:6162–6620` (и константы, которые участок читает).

## Зачем участок нужен

Участок классифицирует набор живых классов развилки в исход `A` / `B` / `C` / `unique` / `empty` / `unavailable` (`resolve_fork_outcome`, :6285–6334) и собирает ответный словарь для каждого исхода (`fork_outcome_a/unique/b/c`, :6354–6614). Выбор лидера среди классов с одним `src` делает `fork_leader_class` (:6209–6255). `atom_terminal_gate_text` (:6458–6468) и `prefer_mute_computed_over_clarify` (:6427–6455) отдают текст/ответ из computed-атома при включённом флаге.

## Входы

| Функция | Аргументы |
|---|---|
| `resolve_fork_outcome` | `classes` (dict fp→set src), `rows`, `measure_ctx`, `scan_error`, `want`, `rel_by_src`, `today` (:6285–6286) |
| `fork_outcome_a` / `unique` | `question`, `class_item` (`atom`/`srcs`), `diag`, `cut`, `t0` (:6354, :6378) |
| `fork_outcome_b` | `question`, `payload` (`classes`, `fork_key`), `diag`, `cut`, `t0`, `picked_src`, `day_basis_prefer` (:6472–6473) |
| `fork_outcome_c` | `question`, `payload`, `classes`, `rows`, `diag`, `cut`, `t0`, `lab_by`, `marks`, `by`, `match`, `preds`, `picked_src`, `day_basis_prefer` (:6524–6526) |
| `atom_terminal_gate_text` | `atom`, `question`, `agg` (:6458) |
| `prefer_mute_computed_over_clarify` | `mute`, `picked_src`, `figures_list`, `question`, `cut`, `diag`, `t0` (:6427–6428) |
| `fork_leader_class` | `picked_src`, `classes` (list items), `day_basis_prefer` (:6209) |
| `ordered_fork_classes` | `classes`, `rows`, `measure_word`, `want`, `rel_by_src`; meta из `fork_classes._meta_by_fp` (:6258–6261) |

Окружение: `ASK_ATOM_TERMINAL` (:1428, чтение :6433, :6460), `ASK_TOTAL_TEXT` → `TOTAL_TEXT` (:318, чтение :6466). Константа участка: `FORK_OTHER_READING = "есть другое прочтение"` (:6187).

## Порядок работы

1. `_dedupe_fork_classes` — ключ `(label, fingerprint, operation, round(exact_value,2))`; дубли сливают `srcs` (:6162–6183).
2. `ordered_fork_classes` — по каждому fp строит item через `_fork_atom_of`, сортирует по `(fingerprint, srcs)` (:6258–6276).
3. `_fork_applicable_classes` — отбрасывает `proof_status == PROOF_NA` (`"not_applicable"`, :7491) (:6279–6282).
4. `resolve_fork_outcome` (:6294–6334):
   - `scan_error` → `("unavailable", {reason: scan_error})`;
   - пустые `classes` → `("empty", no_live_cells)`;
   - `applicable` пуст → `("empty", no_applicable_cells)`;
   - есть uncounted (`proof_status != PROOF_COMPUTED` или `exact_value is None`) → `("C", uncounted_cell)`;
   - один applicable, один src → `("unique", {class})`; один applicable, много src → `("A", …)`;
   - иначе `_class_label_lookup` на каждый класс; нет label → `("C", unsigned_class)`; иначе dedupe → `("B", {classes})`.
5. `fork_outcome_a` — копия атома без `src`, `render_atom_pair` → `kind=answer`, `source_fixed=False`, `memory_eligible=False`, `sources=[]` (:6354–6374).
6. `fork_outcome_unique` — как A, но `fork_outcome=unique`, `sources=[tag]` из первого src; пустой text → `None` (:6378–6403).
7. `fork_outcome_b` — `fork_leader_class`; fail → `None`; иначе текст лидера + `options` по rest, `kind=figures` (:6472–6521).
8. `fork_outcome_c` (:6524–6614):
   - `reason==unsigned_class` и есть `picked_src`: лидер + `"%s · %s" % (pair, FORK_OTHER_READING)`, `kind=figures`, `options=[]`; нет лидера/рендера → `kind=unavailable`, `retry=True`;
   - иначе: опциональный SQL подписей, `mk_opts` + `clarify_say`, `kind=clarify`; к text дописывается note для `uncounted_cell` / `unsigned_class`.
9. `atom_terminal_gate_text`: при `ASK_ATOM_TERMINAL` и computed atom → `render_atom_pair`; иначе `TOTAL_TEXT.format(...)` если задан; иначе `refuse_text(question)` (:6458–6468).
10. `prefer_mute_computed_over_clarify`: только при `ASK_ATOM_TERMINAL`, пустых соперниках (`_rivals_figures_empty`) и computed mute-атоме → `kind=figures` (:6427–6455).

Выбор лидера (`fork_leader_class`, :6209–6255): классы, чьи `srcs` содержат `picked_src`; при нескольких — предпочитает `_class_window_form ∈ ("mtd","wtd")` (:1705); затем `day_basis == prefer` (умолч. `calendar_days`, :1433–1436); иначе `None`.

## Выходы

Возврат — кортеж `(код, payload)` из `resolve_fork_outcome` или dict ответа (`kind`, `text`, `atom`/`atoms`, `figures`/`options`, `diag`, флаги).

Потребители в том же файле (вне участка):
- `resolve_fork_outcome` → :13418; ветвление A/B/C/unique/unavailable :13436–13473;
- `fork_outcome_a/unique/b/c` → return оттуда же;
- `prefer_mute_computed_over_clarify` → :13623–13628;
- `atom_terminal_gate_text` → поле `text` при `gate_rejected` :14810;
- `_fork_figures_of` также :2563, :14343.

## Обращения наружу

| Место | Что | Назначение |
|---|---|---|
| :6580–6582 | `psql("SELECT src_table, label FROM search_tables WHERE src_table IN (…)")` (`TABLES`=:77) | подписи таблиц для clarify-ветки C, если `lab_by` пуст |
| — | HTTP | нет |
| — | вызов языковой модели | нет (в участке; `clarify_say` зовётся как функция :6603) |

Остальное — локальные вызовы: `_fork_atom_of`, `_class_label_lookup`, `render_atom_pair`, `fork_labels_of`, `fork_key_of`, `mk_opts`, `_diag_pack`, `split_ident`, `_fmt`, `refuse_text`.

## Переключатели

| Имя | Где читается в участке | Определение / умолчание |
|---|---|---|
| `ASK_ATOM_TERMINAL` | :6433, :6460 | `os.environ.get("ASK_ATOM_TERMINAL","0")=="1"` (:1428) → False |
| `TOTAL_TEXT` (`ASK_TOTAL_TEXT`) | :6466–6467 | `os.environ.get("ASK_TOTAL_TEXT","")` (:318) → `""` |
| `FORK_OTHER_READING` | :6557 | литерал `"есть другое прочтение"` (:6187) |
| `day_basis_prefer` | :6236–6237, :6478, :6536 | аргумент; иначе `_DAY_BASIS_LEADER_DEFAULT` = `"calendar_days"` |

Иных env в :6162–6620 нет.

## Развилки

- `resolve`: unavailable / empty / C(uncounted) / unique / A / C(unsigned) / B — условия :6294–6334.
- `fork_outcome_unique`: `None` при пустом text (:6389–6390).
- `fork_outcome_b`: `None` если лидер не найден или `render_atom_pair` вернул `None` (:6479–6480, :6493–6494).
- `fork_outcome_c` unsigned+picked: figures с фразой «другое прочтение» vs unavailable (:6532–6571); иначе clarify (:6572–6614).
- `atom_terminal_gate_text`: pair / TOTAL_TEXT / refuse (:6460–6468).
- `prefer_mute…`: `None` при выкл. флаге, непустых соперниках, не-computed (:6433–6446).
- `fork_leader_class`: `None` при отсутствии src/classes/matching или неснятой неоднозначности (:6221–6222, :6229–6230, :6255).

## Чего здесь нет

- Нет HTTP и прямого вызова LLM.
- Нет записи в БД; один SELECT только в clarify-ветке C.
- Нет обработки исходов `empty`/`unavailable` внутри builders A/B/C/unique (их собирает вызывающий :13467–13473).
- `question` в `fork_outcome_a`/`b` в теле не используется.
- `_alias_parts` (:6617–6621) — разбор алиасов; к fork-исходам не подключён.
- Нет IVF/поиска/скана корпуса — только классификация уже посчитанных классов и сборка ответа.
