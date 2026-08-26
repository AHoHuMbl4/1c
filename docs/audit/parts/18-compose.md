# 18. compose

## Зачем участок нужен
Собрать для LLM текст задания с примерами строк и **именами** слотов (без значений итогов), получить сырой ответ, разобрать его, подставить числа из `agg`/`totals`/`extra`, дописать служебные хвосты (`n_groups`, паспорт, `count`), отбраковать формулировку с пустыми/нераспознанными слотами и рукописными цифрами. Единица валюты через `_unit_for_measure`; `postprocess_money_answer_text` текст не меняет.

## Входы
| Функция | Аргументы |
|---|---|
| `compose` | `question`, `rows`, `agg`, `corrections`, `totals`, `coverage`, `measure_used`, `folders`, `money=True`, `src`, `slot_mode`, `atom_pairs` (`:9448-9450`) |
| `_fill_figures` | `text`, `agg`, `totals`, `has_measure=True`, `extra`, `slot_mode` (`:8994`) |
| `ensure_*` / паспорт | текст + `agg` / фрагмент / поля периода-источника-меры (`:9118-9257`, `:9185-9245`) |
| `_split_answer` / `_ask_back` | сырая строка модели (`:8925`, `:9431`) |
| `formulation_flaws` | `text`, `slots_bad` (`:9310`) |
| `copied_figures` | `text`, `agg`, `rows` (`:9340`) |
| `_filled_ask` | `ask`, `agg`, `totals`, `money`, `diag`, `extra`, `slot_mode` (`:9410`) |
| `measure_label_of` / `_table_label` | `src_table`, `measure` (`:9260`, `:9272`) |
Env в этом диапазоне не читаются; используются модульные `MONEY_UNIT`, `ROWS_TO_MODEL`, `ROWS_BUDGET`, `TABLES` (`:75`, `:99`, `:118`, `:77`).

## Порядок работы
1. **`compose`** (`:9448-9670`): `shown = rows[:ROWS_TO_MODEL]`; при `slot_mode=="rank"` и `grain=="group"` — `shown=[]` (`:9452-9454`). `slot_mode` по умолчанию: `rank` если `grain=="group"`, иначе `list` (`:9458-9459`). `pairs_only = pair_slots_only(len(atom_pairs))` (`:9461`).
2. Строки: обрезка `doc` бюджетом `per_row`; хвост `amount=` только при `slot_mode=="list"` и `money`; `date=` при наличии (`:9462-9481`).
3. Заголовок `GROUPS`/`ROWS` / `ROWS FOUND` — ветки по `grain`, `slot_mode`, `pairs_only`, наличию `agg` (`:9491-9511`). Тело `QUESTION` + payload (`:9512-9513`).
4. При `grain=="group"` и `slot_mode in ("rank","list")` и не `pairs_only` — строки `name: total -> {total:gN}` (`:9516-9523`).
5. Блок `COMPUTED…`: либо только `{pair:pN}` (`:9546-9553`); либо без денег — `{count_kind}`/`{count}`/`даты`/`undated`/`outside_period` (`:9554-9574`); либо с мерой — роли `count`/`sum`/`max`/`min`/`avg`/`n_groups`/`даты` по `slot_mode` и `grain` (`:9575-9615`).
6. Именованные `totals` → `{total|max|min:имя}` (`:9616-9626`); `coverage` → слоты `{in_1c}`/`{in_search}`/`{missing}` (`:9627-9638`); `measure_used`, `folders`, `corrections` — текстовые указания (`:9645-9668`).
7. Возврат: `ds_chat([ANSWER_SYS, body], max_tokens=800)` (`:9669-9670`).
8. У вызывающего (вне участка, потребители): `_split_answer` → `copied_figures` → `_fill_figures` → `ensure_n_groups_named` → `build_answer_passport` + `ensure_answer_passport` → `_filled_ask` → `formulation_flaws`; после успешного гейта — `ensure_count_named`; при fail — повторный `compose` с `corrections`.
9. **`_fill_figures`**: набор `known` из скаляров `agg`; фильтр ролей по `slot_mode` / `has_measure` / `grain` (`:9014-9054`); `extra` в `known` (`:9058-9060`); `by_name` из `totals` и `gN` (`:9061-9069`); `SLOT.sub` → `_fmt_human` или дата как str; пустое → в `bad`, слот оставляется (`:9072-9115`).
10. **`ensure_n_groups_named`**: если `n_groups > shown` и числа ещё нет в тексте — хвост ` · всего позиций: …` (`:9118-9136`). **`ensure_count_named`**: только `slot_mode in ("sum","rank")`, хвост ` · всего записей: …` (`:9139-9157`).
11. **Паспорт**: `build_answer_passport` склеивает `from..to [origin]`, `label (kind)`, `measure`, `axis`, `form` через ` · `, без дублей с `text` (`:9185-9245`); `ensure_answer_passport` дописывает фрагмент (`:9248-9257`). `_passport_origin` / `_passport_axis_label` — маркеры (`:9286-9307`).
12. С `9690` начинаются `NUMTOK`/`DATE*`/`_readings` — уже блок гейта, не compose.

## Выходы
| Что | Куда |
|---|---|
| `compose` → str ответа LLM | `_split_answer` / `_ask_back` |
| `_fill_figures` → `(text, bad)` | ответ и `_filled_ask` |
| `ensure_*` / паспорт → str | текст до/после гейта |
| `formulation_flaws` / `copied_figures` → list[str] | причины отказа формулировки |
| `_filled_ask` → str или `""` | уточнение; при изъяне `diag["ask_dropped"]` |
| `measure_label_of` → str/None | метка меры в ответе/атомах (снаружи) |
| `postprocess_money_answer_text` → тот же `text` | no-op (`:9175-9183`) |

## Обращения наружу
| Место | Что | Назначение |
|---|---|---|
| `compose` → `ds_chat` `:9669-9670` | HTTP chat completions (через `ds_chat_post`) | формулировка ответа |
| `_table_label` `:9277-9278` | SQL `SELECT label FROM search_tables WHERE src_table=… LIMIT 1` | метка источника для паспорта |
| `measure_label_of` → `measure_aliases_of` (вне участка) | SQL к `search_measure_alias` | подписи мер |
Других SQL/HTTP/LLM в диапазоне `8925-9670` нет.

## Переключатели
В диапазоне env не читаются. Косвенно:
- `ASK_MONEY_UNIT` → `MONEY_UNIT` (модуль `:75`) → `_unit_for_measure` при `money` (`:9162-9172`); иначе `""`.
- `ASK_ROWS_TO_MODEL` (default `25`), `ASK_ROWS_BUDGET_CHARS` (default `24000`) — лимит строк и бюджет символов в `compose` (`:9452-9457`).
Флаг `money` / `has_measure` / `slot_mode` / `pairs_only` / `period_dropped` — аргументы, не env.

## Развилки
- `_split_answer`: JSON с `text` → текст+claims; битый `"text"` → вырезание/пусто; сырой `{` → `""`; иначе весь raw (`:8935-8955`).
- `slot_mode`: `count`/`compare`/`sum`/`rank`/`list` — разные наборы ролей в `_fill_figures` и слотов в `compose` (`:9018-9038`, `:9546-9615`).
- `grain=="group"`: без `max`/`min` в known; слоты `gN`; заголовок GROUPS (`:9052-9054`, `:9065-9069`, `:9491-9503`).
- `pairs_only`: только `{pair:pN}`, без одиночных числовых слотов (`:9546-9553`).
- `has_measure`/`money` ложны: убрать `sum/max/min/avg` из подстановки; ветка «без денежной колонки» в теле (`:9046-9048`, `:9554-9574`).
- `ensure_n_groups_named` / `ensure_count_named`: дописывают хвост только если числа ещё нет в тексте.
- `build_answer_passport`: при `period_dropped` окно не добавляется (`:9208`); `form in ("rank","compare")` добавляет маркер формы (`:9242-9243`).
- `_filled_ask`: изъян → `""` и `diag["ask_dropped"]` (`:9421-9427`).

## Чего здесь нет
Гейта чисел (`gate` — после `:9673`); подстановки `{pair:pN}` (`fill_atom_pairs` снаружи); записи в БД; разбора intent; реальной постобработки валюты в тексте (`postprocess_money_answer_text` возвращает вход как есть); чтения env внутри функций участка.
