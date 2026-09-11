# СНОС-15 Z3: патч → тело (долг V4c)

Линза Z3 «патч → тело», срез 11.09. Код только читался.
Источники: `ubuntu/serenedb/ask/_bootstrap.py` целиком;
`z20_ask_main_http.py` на диске; живой `load_all`; `snos15-PLAN` волны В6/В7.

**Вердикт.** Единственный `_patch_*` — `_patch_z20_wiki_primary`
(`_bootstrap.py:48–286`, зов `_exec_zone:327–328`). V4c-гейты wiki-лидера
живут **только в рантайме через патч** (`fork_deferred_to_wiki` на диске —
нет; после `_patch_z20_wiki_primary` — да). Перенос в тело z20 + урезка
четырёх V4c-веток патча закрывает долг владельца «Никаких долгов». Net/ef
оставить до В7/В6.

---

## 0. Состав `_bootstrap.py` (не патч)

| элемент | строки | роль |
|---|---|---|
| `_ZONE_FILES` | 16–40 | порядок зон; z20 последний |
| комментарий «файл блокируется check-prompt-rules» | 44–45 | причина долга V4c |
| **`_patch_z20_wiki_primary`** | 48–286 | **единственный** `_patch_*` |
| `_body_start_line` / `_body_end_line` | 289–322 | вырез тела зоны |
| `_exec_zone` | 325–339 | для z20: `text = _patch_z20_wiki_primary(text)` |
| `load_all` / `zone_paths` / `combined_source` | 351–378 | склейка |

Других `_patch_z20_*` / `_patch_*` в файле **нет** (подтверждено `ast`: одна
функция с префиксом `_patch`).

---

## 1. Таблица якорей / вставок `_patch_z20_wiki_primary`

Статус «жив» = точная строка-якорь есть на диске z20 **сейчас**.
«Срабатывает» = при `load_all` ветка реально меняет текст (проверено
симуляцией патча: disk 262921 → patched 265025, Δ+2104).

| # | якорь (переменная / строки bootstrap) | условие срабатывания | что вставляется / меняется | символы рантайма | якорь на диске z20 | срабатывает сейчас | волна / долг |
|---|---|---|---|---|---|---|---|
| A | stock `wiki_hybrid_pick` `:57–67` | `"and not diag.get(\"wiki_hybrid_pick\")\n            and stock_question_engaged(...)):" in text` | OR: `wiki_pick==stock_override` \|\| `stock_canon_locked` | diag-ключи | **мёртв** (такого фрагмента нет) | no-op | можно урезать сейчас (мусор) |
| B | catalog comment `:68` | — | нет кода; «снесён в В2» | — | n/a | no-op | уже урезан |
| C | `_net_anchor` `:74–100` | якорь ровно перед `_dac = live_axis_col…` в ветке `no_axis_member` | блок `aggregate_stock_net_distinct` при `stock_canon_locked` \|\| `stock_count_aggregate_without_subject` + `not stock_asks_named_product` | `aggregate_stock_net_distinct`, `stock_count_aggregate_without_subject`, `stock_asks_named_product` (z12) | **жив** (`z20:3758–3761`) | **да** | **В7** — не трогать в переносе V4c |
| C′ | fallback `:97–100` | якорь пропал, но `no_axis_member` есть и рядом нет `stock_net_distinct` | `RuntimeError("…net-distinct anchor not found")` | — | — | не активен (якорь жив) | ловушка: правка `no_axis_member` без синхрона патча → падение `load_all` |
| D | `_net2_old` `:102–116` | узкий гейт без `stock_canon_locked` | расширить OR + `not stock_asks_named_product` | те же z12 | **жив** (`z20:3789–3792`) | **да** | **В7** |
| E | `_fork_old` `:120–138` | якорь есть **и** `fork_deferred_to_wiki` ещё нет в тексте | defer A/B/C → `deferred_wiki` при `wiki_leader_alive` | `wiki_leader_alive` (z21:1079) | **жив** (`z20:2963–2966`) | **да (V4c)** | **перенести сейчас** |
| F | `_c_old` `:140–191` | якорь есть **и** `fork_clarify_from_wiki_pool` нет | C → меню из `wiki_pool`; иначе `fork_outcome_c` + `fork_c_options_without_left_srcs`; пусто → `no_data` | `fork_clarify_from_wiki_pool`, `fork_c_options_without_left_srcs` (z13:820, :870); `NO_DATA_TEXT`, `_diag_pack` | **жив** (`z20:2986–3000`) | **да (V4c)** | **перенести сейчас** |
| G | `_live_old` `:193–207` | якорь есть **и** в окне 400 символов от `unique / empty / A` нет `deferred_wiki` | live_srcs в `arb_pool` только если **нет** wiki-лидера | `wiki_leader_alive` | **жив** (`z20:3008–3012`) | **да (V4c)** | **перенести сейчас** |
| H | `_ec_ban_old` `:210–224` | якорь есть **и** `wiki_leader_alive(diag, picked))` нет | `or wiki_leader_alive(diag, picked)` в `_ec_ban` | `wiki_leader_alive` | **жив** (`z20:3046–3050`) | **да (V4c)** | **перенести сейчас** |
| I | `_ef_gate_old` `:227–232` | `"if ASK_ENTITY_FORM and not no_arbiter"` есть **и** `entity_form_gate_open` ещё нет | `(ASK_ENTITY_FORM or entity_form_gate_open(intent, diag))` | `entity_form_gate_open` (z05:534) | **жив** 1× (`z20:2845`) | **да** | **В6** — не трогать в переносе V4c |
| J | ecp reorder `:236–285` | марка `# z21-boot: entity_form before event_count_period_clarify` | swap F↔ecp0 | текст блоков F/ecp0 | **марка мертва** | no-op | **В6** (станет no-op при сносе F; можно вычистить вместе с I) |

### Символы — где определены (все на месте)

| символ | файл |
|---|---|
| `wiki_leader_alive` | `z21_wiki_choice.py:1079` |
| `fork_clarify_from_wiki_pool` | `z13_fork_outcomes.py:820` |
| `fork_c_options_without_left_srcs` | `z13_fork_outcomes.py:870` |
| `resolve_fork_wiki_gate` | `z13_fork_outcomes.py:890` (зеркало логики; замок `test_wiki_leader_not_overridden.py`) |
| `entity_form_gate_open` | `z05_entity_form.py:534` |
| `aggregate_stock_net_distinct` / `stock_count_aggregate_without_subject` / `stock_asks_named_product` | `z12_stock_balance.py` |

### Идемпотентность

Ветки E–H и I уже с маркерами «уже вставлено → skip». После переноса
текста на диск патч по ним становится no-op **сам**, даже до удаления
веток из `_bootstrap.py`. Это спасает промежуточный момент «тело уже
новое, патч ещё старый». Обратный порядок («патч урезан, тело ещё
старое») **теряет** V4c-поведение на `load_all` без `RuntimeError`.

Ветка C при сломанном якоре — жёсткий `RuntimeError` (не тихий no-op).

---

## 2. План переноса V4c → тело z20 (один коммит)

Цель: диск z20 содержит E–H дословно как сейчас даёт патч; патч эти
четыре ветки теряет (удалить или оставить пустой комментарий «на диске»).
Net (C/D) и ef (I/J) **не** трогать.

### 2.1 Куда в теле (маркеры диска, не номера строк)

| вставка | место в `z20_ask_main_http.py` | действие |
|---|---|---|
| **E** defer A/B/C | сразу после `_picked0 = picked[0] if picked else None` и двух комментариев «В4: fork-авто…»; **вместо** голого `if _outc == "A":` | вставить `_wiki_lead = wiki_leader_alive…` / `fork_deferred_to_wiki` / `_outc = "deferred_wiki"`; затем `elif _outc == "A":` (как `_fork_new`) |
| **F** C → wiki_pool | блок `if _outc == "C":` с комментарием `z09 live rivals → arb_pool` и `return fork_outcome_c(...)` | заменить целиком на `_c_new`: сначала `fork_clarify_from_wiki_pool`; иначе live_srcs + `fork_outcome_c` → `fork_c_options_without_left_srcs` → возм. `no_data` |
| **G** live_srcs | комментарий `unique / empty / A — ниже early clarify…` + цикл `live_srcs` → `arb_pool` | заменить на `_live_new`: комментарий с `deferred_wiki`; цикл под `if not wiki_leader_alive(diag, picked):` |
| **H** early-clarify ban | `_ec_ban = ( bool(trusted) or bool(_ec_locks) or _ec_one_src or _ec_same_fam_no_atoms)` | добавить `or wiki_leader_alive(diag, picked)` последним членом |

Текст вставок — **копировать из `_fork_new` / `_c_new` / `_live_new` / `_ec_ban_new`**
в `_bootstrap.py:126–136, 156–189, 199–204, 216–222` (не сочинять заново).

### 2.2 Как менять патч (тем же коммитом)

После того как E–H на диске:

1. Удалить блоки `_fork_old/_fork_new`, `_c_old/_c_new`, `_live_old/_live_new`,
   `_ec_ban_old/_ec_ban_new` (строки ~118–224) **или** заменить одним
   комментарием: «V4c wiki-лидер — на диске z20; патч no-op».
2. **Оставить** ветки A (можно вычистить как мёртвую), C/D (net), I/J (ef).
3. Обновить шапочный комментарий `:44–45` / docstring функции `:49–52`:
   убрать формулировку «здесь wiki-лидер», указать «на диске: wiki-лидер;
   патч: net + ef_gate».
4. Замок `test_wiki_leader_not_overridden.py`: проверки
   `"fork_deferred_to_wiki" in patched` останутся зелёными (текст уже
   на диске → проходит через патч без изменений). Лучше добавить явный
   assert **на диск** (`"fork_deferred_to_wiki" in z20`), чтобы долг
   не вернулся.

### 2.3 Порядок правок, чтобы `load_all` не упал ни на шаге

Атомарный коммит git скрывает промежутки; при правке в редакторе /
двух `Write` важен порядок **сохранений**:

| шаг | файл | состояние `load_all` |
|---|---|---|
| 0 (сейчас) | патч вставляет E–H | OK, V4c в рантайме |
| 1 | **сначала** z20: записать E–H в тело (якоря E–H исчезают, маркеры появляются) | OK: патч no-op по E–H (условия `and "marker" not in text`), C/D/I ещё работают |
| 2 | **затем** `_bootstrap.py`: удалить ветки E–H | OK: поведение уже на диске |
| 3 | (опц.) docstring `gate()` — нейтральная формулировка §3 | OK; разблокирует будущие правки z20 |
| 4 | (опц.) вычистить мёртвую ветку A (stock) | OK |
| 5 | офлайн: `PYTHONPATH=ubuntu/serenedb python3 -c 'import serene_ask'` + `test_wiki_leader_not_overridden.py` | без NameError; defer/меню замки зелёные |

**Запрещённый порядок:** урезать патч E–H **до** записи тела → на
`load_all` wiki-лидер снова перебивается fork B/C / early-clarify
(тихая регрессия, не `RuntimeError`).

**Запрещено в этом коммите:** любой рефактор вокруг
`no_axis_member(grain_dec)` / `_dac = live_axis_col…` и
`stock_count_aggregate_without_subject` без синхронной правки C/D
(ловушка C′ → `RuntimeError`).

Пат-спек коммита (когда оркестратор попросит):  
`z20_ask_main_http.py` + `_bootstrap.py` + (замок) + docs/CHANGELOG/граф —
одним коммитом; **без** правок net/ef «заодно».

---

## 3. Docstring `gate()` — нейтральная переформулировка

Сейчас (`z20:75`):

```text
"""Каждое число ответа обязано встречаться в данных, в итоге или в наших условиях.
```

Слово **«обязано»** попадает под `MARK` хука `check-prompt-rules`
(`обязан\w*`). Docstring = строковый литерал → PreToolUse / commit-гейт
ловят правку z20, если строка оказывается в «добавленных» (типично
Write целого файла или крупный `new_string`, куда попал старый docstring).
Это и есть ложное срабатывание на HEAD-строке, из‑за которого V4c ушёл в
патч.

**Предлагаемая замена первой строки (смысл тот же, без долженствований):**

```text
"""Числа ответа сверяются кодом с данными, итогом и нашими условиями.
```

Остальной docstring `:77–88` слов `обязан*/должен*/запрещ*/нельзя/никогда/всегда`
не содержит — менять не требуется для гейта. (Комментарии ниже по файлу с
«обязано»/`нельзя` хук на Write не режет: они вне строковых литералов.)

Правку docstring делает оркестратор (желательно тем же коммитом, что
перенос V4c, либо отдельным крошечным до него — чтобы следующие правки
z20 не упирались в гейт).

---

## 4. Риски: что живо и что урезать сейчас

### Не переносить / не урезать в коммите V4c

| ветка | почему |
|---|---|
| **C/D net-distinct** | PLAN В7 (`_net_anchor/_net2`); живые якоря; C′ роняет `load_all` при рассинхроне |
| **I ef_gate** | PLAN В6 (снос `ASK_ENTITY_FORM` + boot ef); сейчас реально расширяет гейт формы |
| **J ecp reorder** | уже no-op (марки нет); чистить вместе с В6, не отдельно «для красоты» в V4c |

### Можно урезать уже сейчас (вместе с переносом V4c или сразу после)

| ветка | почему безопасно |
|---|---|
| **E–H (V4c)** | цель долга; после тела — патч-ветки только шум |
| **A stock wiki_hybrid** | якорь мёртв с В2-эпохи; no-op |
| **B catalog** | уже комментарий |

### Ловушки

1. Правка якоря на диске без синхронной правки патча → для net = падение
   сервиса; для V4c после переноса = риск только если вернуть старый
   текст якоря и одновременно вычистить маркеры.
2. `test_wiki_leader_not_overridden.py` сейчас проверяет **патч**, не диск —
   без assert на диск долг может вернуться незаметно.
3. `resolve_fork_wiki_gate` (z13) — зеркало для замков; тракт ask идёт через
   вставки в z20, не через этот helper. После переноса helper остаётся
   валидным зеркалом; docstring «зеркало патча» стоит поправить на
   «зеркало тракта z20».
4. K2-отчёт (`snos15-K2-core.md`) описывает **старую** карту якорей
   (meas/rank_fold/sales_force) — на срезе 11.09 их в `_bootstrap.py` уже
   нет. Ориентир по якорям — **эта** таблица Z3, не K2 §1.

---

## 5. Краткий чеклист исполнителю (не Z3)

- [ ] z20: E, F, G, H дословно из патча  
- [ ] `_bootstrap.py`: удалить E–H; net/ef оставить  
- [ ] (рекоменд.) docstring `gate()` §3  
- [ ] (рекоменд.) вычистить мёртвую A  
- [ ] замок: assert маркеров на **диске** z20  
- [ ] `import serene_ask` + `test_wiki_leader_not_overridden.py`  
- [ ] документы/граф тем же коммитом (когда оркестратор коммитит)

Код этой линзой не менялся; коммитов нет; серверы/база не трогались.
