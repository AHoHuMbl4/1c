# S2-d: финальный `test_one_path.py` (проект расширения)

Срез: 12.09.2026. Read-only по коду HEAD; код не менялся.
Объект: `ubuntu/serenedb/test_one_path.py` ← разбор `ask/z20_ask_main_http.py` +
`ask/z21_wiki_choice.py` (+ точечно z05/z12/z14 для (г)/(д)).
Стиль: как текущий замок (Path → `ast.parse` → `t(name, cond)` → `N/0` / exit 1);
не pytest; не живой SQL; не вопросы конкретной базы.

Канон контракта: O5-locks §2 + решение владельца «одноимённые → МЕНЮ» +
три silent-выбирателя W2 (мера / ось count / пара регистров).

---

## 0. Что уже есть и чего не хватает

Текущий `test_one_path.py` (41/0 на HEAD):

| Проверка | Сейчас | Финал |
|---|---|---|
| (г) старый FORBIDDEN + hatch + B4 grep | да | оставить + расширить |
| (а) bare `Dict{kind:clarify}` в `answer` | частично (ломается на builder-only; журнал не отделён явно) | полная AST + исключения журнала + z21 |
| (в) SQL_CALLS до `wiki_primary` по lineno | да (грубо) | да + ticket-исключение + расширенный список |
| (б) вторые числа | **нет** (только hatch-имена) | полная по O5 §2.3 |
| (д) одноимённые label → не silent leader | **нет** | NEW, z21 AST/текст |
| silent-тройка → меню при >1 | **нет** (символы живы и silent) | NEW контракт AST |

На текущем HEAD финальный замок будет **красным** ровно в местах S2-чистки /
меню-починок — это ожидаемо. Зелёный = долгов не осталось.

---

## 1. Объект разбора и примитивы

```python
ROOT = Path(__file__).resolve().parent
ASK = ROOT / "ask"
Z20_PATH = ASK / "z20_ask_main_http.py"
Z21_PATH = ASK / "z21_wiki_choice.py"
Z05_PATH = ASK / "z05_entity_form.py"
Z12_PATH = ASK / "z12_stock_balance.py"
Z14_PATH = ASK / "z14_clarify_memory.py"

ALLOWED_CLARIFY_BUILDERS = {
    "clarify_opts_response",
    "readings_menu",
}
# captions / mk_opts / wiki_menu_captions — только аргументы builder, не return clarify

FORBIDDEN_SELECTORS = {
    # наследие pre-wiki / fork / arb (как сейчас)
    "try_entity_form_answer",
    "try_event_count_period_clarify",
    "period_assumed_needs_clarify",
    "axis_focus_plan",
    "warehouse_clarify",
    "arbitrate",
    "_fork_early",
    "fork_outcome_b",
    "fork_outcome_a",
    # B4 терминалы / silent-имена (раньше отдельным B4_FORBIDDEN)
    "pick_measure",
    "kind_axis_rerank",
    "_fork_atom",
    "arb_pool",
    "entity_form_gate_open",
    "measure_in_kin",
    "apply_period_leader",
    "prefer_window_leader",
    "_ec_atom_fps",
    "try_entity_form",
}

HATCH_NAMES = (
    "measure_hatch", "measure_hatch_B", "measure_hatch_C",
    "_fork_headline", "_fork_headline_measure", "FORK_OTHER_READING",
)

# Имена SQL-ступеней, запрещённые в answer() до wiki (по Call.attr/id).
SQL_CALLS = {
    "aggregate",
    "aggregate_groups",
    "rows_of",
    "totals_of",
    "aggregate_stock_net_distinct",
    "aggregate_compare_sales",
    "aggregate_distinct_axis",
    "live_src_counts",
    "tables_of",          # живой счёт по match до src — тоже SQL-ступень
}

# Ticket: wiki можно пропустить ТОЛЬКО при явной проверке билета.
TICKET_GUARDS = {
    "entity_choice_locked",
    "hold_settled_entity",
}

# Silent-тройка: символы живут, но контракт «>1 → меню / None», не winner.
SILENT_SELECTORS = (
    "measure_choice",
    "_pick_kind_axis_col",
    "stock_net_register_pair",
)
```

Вспомогательные (как в текущем замке + O5):

- `_func_node(tree, name)` — top-level `FunctionDef`
- `_call_name(Call)` — `Name.id` / `Attribute.attr`
- `_dict_kind(node) → str|None` — значение `"kind"` если `Constant`
- `_real_calls(src, sym)` — вхождения вне `#`-хвоста строки
- `_line_of(node)` — `lineno`

---

## 2. Проверка (а) — clarify только через построитель

### 2.1. Call-вершины, которые считаются легитимным clarify

Только:

1. `return readings_menu(...)`
2. `return clarify_opts_response(...)`
3. `return <Name>`, если `Name` присвоен **только** из Call (1) или (2)
   в той же функции (простое dataflow: `Assign` targets → value Call builder).

Captions (`wiki_menu_captions`, `measure_captions`, `axis_clarify_options`,
`_readings_to_opts`, `mk_opts`) — **не** builders: их результат без обёртки
в `readings_menu`/`clarify_opts_response` = fail.

### 2.2. Где искать Dict `{kind: "clarify"}`

| Место | Правило |
|---|---|
| Тело `clarify_opts_response` | **OK** (единственный канонический Dict) |
| Тело `readings_menu` | OK только как `return clarify_opts_response(...)` (Dict внутри builder не дублировать) |
| Тело `answer` | **запрещён** любой `ast.Dict` с `kind=="clarify"`; Return-Call только из ALLOWED |
| `try_wiki_hybrid_entity_pick` / `wiki_primary_entity_cascade` (z21) | clarify-исход **обязан** звать `readings_menu` или `clarify_opts_response` (не bare Dict, как сейчас :1111–1116) |
| Журнал (`_journal_*`, `_ask_journal_*`, Handler) | см. §2.3 — **не** считать созданием clarify |

### 2.3. Как исключить журнальные словари

Журнал **читает** `out["kind"]`, не конструирует clarify:

- `_journal_clarify_options` сравнивает `kind not in ("clarify", "figures")` —
  это `Compare`/`Constant`, не `Dict` с ключом kind→clarify.
- Копирующие dict-comprehension вида
  `{k: d.get(k) for k in ("kind", ...)}` — ключи без литерала `"clarify"`
  как **значения** kind → не матч `_dict_kind`.

Правило замка (жёсткое, без «угадывания»):

```python
JOURNAL_FUNCS = {
    "_journal_clarify_options", "_journal_doubt", "_journal_ticket_variant",
    "_journal_atoms", "_ask_journal_write", "_ask_journal_row",
    # при появлении новых _journal_* — расширять явно
}

def _enclosing_func(tree, node):
    """Ближайший FunctionDef-предок (через parent map)."""
    ...

def _is_clarify_dict(node):
    return isinstance(node, ast.Dict) and _dict_kind(node) == "clarify"

def _clarify_dict_ok(tree, node):
    fn = _enclosing_func(tree, node)
    if fn is None:
        return False
    if fn.name in ALLOWED_CLARIFY_BUILDERS:
        return True
    if fn.name in JOURNAL_FUNCS:
        return True   # журнал не создаёт clarify-ответ
    return False
```

Fail: любой `_is_clarify_dict` с `not _clarify_dict_ok`, плюс в `answer` —
любой Return, чей value не builder-Call/builder-Name, но «проносит» clarify
(в т.ч. `return _ep` без гарантии, что `_ep` из builder — поэтому z21 чинят
на builder, а замок на z21 смотрит отдельно, см. ниже).

### 2.4. Эскиз проверок (а)

```python
# --- z20: answer ---
answer = _func_node(z20_tree, "answer")
bare_ret = []
for n in ast.walk(answer):
    if isinstance(n, ast.Return) and n.value is not None:
        if _is_clarify_dict(n.value):
            bare_ret.append(n.lineno)
        # return readings_menu(...) / clarify_opts_response(...) — OK
t("answer: 0 bare return Dict kind=clarify", not bare_ret, bare_ret)

bad_dicts = [
    n.lineno for n in ast.walk(answer)
    if _is_clarify_dict(n)
]
t("answer: 0 Dict kind=clarify (только builder снаружи)", not bad_dicts)

used = {
    _call_name(n) for n in ast.walk(answer)
    if isinstance(n, ast.Call) and _call_name(n) in ALLOWED_CLARIFY_BUILDERS
}
t("answer: readings_menu зовётся", "readings_menu" in used)
t("readings_menu / clarify_opts_response определены",
  _func_node(z20_tree, "readings_menu")
  and _func_node(z20_tree, "clarify_opts_response"))

# --- z20 целиком: clarify-Dict только в builder/journal ---
bad_mod = [
    getattr(n, "lineno", "?")
    for n in ast.walk(z20_tree)
    if _is_clarify_dict(n) and not _clarify_dict_ok(z20_tree, n)
]
t("z20: clarify-Dict только builder|journal", not bad_mod, bad_mod)

# --- z21: clarify-исход через builder (финал S2) ---
hybrid = _func_node(z21_tree, "try_wiki_hybrid_entity_pick")
z21_bare = [
    n.lineno for n in ast.walk(hybrid)
    if _is_clarify_dict(n)
]
t("z21 hybrid: 0 bare Dict kind=clarify", not z21_bare, z21_bare)
z21_builder = any(
    isinstance(n, ast.Call) and _call_name(n) in ALLOWED_CLARIFY_BUILDERS
    for n in ast.walk(hybrid)
)
t("z21 hybrid: зовёт readings_menu|clarify_opts_response", z21_builder)
```

**Щель сейчас:** z21 :1111 строит bare Dict — финальный (а) красный, пока clarify
wiki не переведён на `readings_menu`/`clarify_opts_response` (подписи уже через
`mk_opts` + `wiki_menu_captions`).

---

## 3. Проверка (б) — ни одного ответа со «вторыми числами»

Смысл O5 §2.3: при >1 прочтении — **clarify**, не `figures`/`answer` с вторым
числом / unsigned fork / hatch.

### 3.1. Паттерны в return-ветках `kind in {answer, figures}`

Сканировать `answer`, `_finalize_answer` / compose-хвост (в текущем z20 —
финальный блок ~1806–1840 и `build_period_empty_answer`), а также любые
`Return`/`Assign`, где payload-Dict имеет `_dict_kind ∈ {"answer","figures"}`.

| Паттерн | Как ловить | Почему |
|---|---|---|
| Имена люка | `HATCH_NAMES` / `FORK_OTHER_READING` в исходнике z20 (вне комментария) | fork-C unsigned |
| Второй atom-список рядом с ответом | в том же Dict/Assign: ключи `"atoms"` с `List` длины >1 **и** нет ухода в clarify; или Call `render_atom_pair` в `answer` | пара чисел без меню |
| Вторичные поля | в payload `answer`/`figures` ключи-константы из `SECOND_KEYS` при наличии `atom`/`agg`/`figures` | «другое прочтение» |
| Меню, замаскированное figures | `kind=="figures"` **и** ключ `"options"` с len≥2 в том же Dict | B-люк; допустим только журнал-чтение, не создание в answer |

```python
SECOND_KEYS = frozenset({
    "other_reading", "secondary", "alts", "alt_figures",
    "fork_other", "unsigned", "FORK_OTHER_READING",
})

def _payload_kind(dict_node):
    return _dict_kind(dict_node)  # answer|figures|clarify|...

def _second_number_hits(fn_node):
    bad = []
    for n in ast.walk(fn_node):
        if not isinstance(n, ast.Dict):
            continue
        k = _payload_kind(n)
        if k not in ("answer", "figures"):
            continue
        keys = []
        for key in n.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                keys.append(key.value)
        if any(x in SECOND_KEYS for x in keys):
            bad.append((n.lineno, "second_key"))
        if k == "figures" and "options" in keys:
            bad.append((n.lineno, "figures+options"))
        # atoms: List с >1 elt в литерале
        for key, val in zip(n.keys, n.values):
            if (isinstance(key, ast.Constant) and key.value == "atoms"
                    and isinstance(val, ast.List) and len(val.elts) > 1):
                bad.append((n.lineno, "atoms>1"))
    return bad
```

Дополнительно (как сейчас + O5):

```python
for name in HATCH_NAMES:
    t("0 имя %s в z20" % name, name not in z20_src or not _real_calls(z20_src, name))
t("answer: 0 render_atom_pair",
  not any(isinstance(n, ast.Call) and _call_name(n) == "render_atom_pair"
          for n in ast.walk(answer)))
t("answer/finalize: 0 second-number payload",
  not _second_number_hits(answer), _second_number_hits(answer))
```

**Легитимное не путать с нарушением:**

- `figures` coverage (`rows_in_1c` / `rows_in_search`) — это **одно** состояние
  полноты, не два прочтения; ключей из `SECOND_KEYS` нет → OK.
- `atoms: [_atom]` (литерал длины 1) — OK.
- `measure_alts` / `axis_alts` **до** SQL, уходящие в `readings_menu` — не
  return answer/figures → OK.

---

## 4. Проверка (в) — SQL только после wiki

### 4.1. Список SQL-имён по текущему z20

В `answer` после wiki реально зовутся (lineno ориентиры HEAD):

| Имя | Роль |
|---|---|
| `rows_of` | probe пустого окна; TOPK |
| `totals_of` | totals меры |
| `aggregate_groups` | GROUP BY |
| `aggregate` | обычный agg |
| `aggregate_stock_net_distinct` | net-distinct |
| `aggregate_compare_sales` | compare-окна |
| `aggregate_distinct_axis` | COUNT DISTINCT оси |
| `tables_of` | found по match |
| `live_src_counts` | **не** в `answer` напрямую; в `mk_opts` (z20) — OK вне answer |

В `SQL_CALLS` замка держать все из таблицы + `live_src_counts` (защита от
возврата pre-wiki live-count в `answer`).

Не считать SQL-ступенью one-path: `psql` внутри `ambiguous_labels` /
`opts_hints` / journal / health — они **вне** `answer` или после решения;
замок смотрит Call-имена из `SQL_CALLS` **только в `def answer`**.

### 4.2. Ticket-исключение

Допустимо отсутствие Call `wiki_primary_entity_cascade` в части веток, если
в `answer` есть **оба**:

1. Call/использование `entity_choice_locked` (или присвоение `_ticket_locked`),
2. Call `hold_settled_entity`,

и wiki зовётся в ветке `if not _ticket_locked`.

Замок:

```python
def _sql_before_wiki(answer_node):
    wiki_line = None
    for n in ast.walk(answer_node):
        if isinstance(n, ast.Call) and _call_name(n) == "wiki_primary_entity_cascade":
            wiki_line = n.lineno
            break
    ticket_ok = all(
        any(isinstance(n, ast.Call) and _call_name(n) == g
            for n in ast.walk(answer_node))
        for g in ("entity_choice_locked", "hold_settled_entity")
    )
    if wiki_line is None:
        return [] if ticket_ok else ["no wiki_primary_entity_cascade"]
    bad = []
    for n in ast.walk(answer_node):
        if isinstance(n, ast.Call) and _call_name(n) in SQL_CALLS:
            if (n.lineno or 0) < wiki_line:
                bad.append("%s@%s" % (_call_name(n), n.lineno))
    return bad

t("answer: wiki_primary зовётся", wiki_line is not None)
t("answer: ticket-guards на месте", ticket_ok)
t("answer: 0 SQL_CALLS до wiki_primary", not _sql_before_wiki(answer))
```

Дополнительно (O5): до `wiki_line` нет Return с `_dict_kind in {answer, figures}`
(кроме явного infra — в финале **не** разрешаем; `calendar_axis_unavailable_block`
до wiki допустим только если kind ∉ {answer, figures} **или** это честный
unavailable без чисел прочтения — проверить kind константой в возвращаемом
хелпере отдельно простым grep: хелпер не в SQL_CALLS).

Coverage: `_coverage_answer` **после** wiki (сейчас :1972) — OK; Call до wiki → fail.

---

## 5. Проверка (г) — чёрный список выбирателей

### 5.1. Старые FORBIDDEN — ноль call-site в z20

Как сейчас: `_real_calls` + `sym(`; для `_fork_early` ещё `=`.
HATCH_NAMES — отсутствие имени. B4-имена влиты в `FORBIDDEN_SELECTORS`.

```python
for sym in sorted(FORBIDDEN_SELECTORS):
    t("0 call-site %s" % sym, not _call_sites(z20_src, sym))
for name in HATCH_NAMES:
    t("0 имя %s" % name, name not in z20_src)
t("B4: 0 max(by в z20", "max(by" not in z20_src)
t("B4: 0 sales_compare-терминал",
  "форма compare" not in z20_src or "compose+gate" in z20_src)
```

### 5.2. Silent-тройка — не «запрет символа», а контракт >1 → меню

После S2 символы **остаются**, но:

| Символ | Файл | Контракт |
|---|---|---|
| `measure_choice` | z14 | `len(names)==1` → взять; `>1` и нет **точного** единственного покрытия слова → `(None, alts, 'ask')`; запрещены silent `return (names[0], …)` / `exact[0]` при нескольких равных по смыслу без ask. Практический AST-минимум ниже. |
| `_pick_kind_axis_col` | z05 | при `len(matched)>1` / `len(hits)>1` — **не** `return matched[0]` / `reranked[0]` / `hits[0]`; либо `return None` (меню выше), либо явный clarify-путь |
| `stock_net_register_pair` | z12 | при нескольких равноправных парах/siblings — не выбирать `sorted_s[0]` / `max(...)` молча; `return None` → меню выше по тракту |

Эскиз статических маркеров (после правки кода — зелёные; на HEAD — красные):

```python
z05 = Z05_PATH.read_text(encoding="utf-8")
z12 = Z12_PATH.read_text(encoding="utf-8")
z14 = Z14_PATH.read_text(encoding="utf-8")

# (г-silent) _pick_kind_axis_col: нет winner при >1
pick_fn = _func_node(z05_tree, "_pick_kind_axis_col")
src_pick = ast.get_source_segment(z05, pick_fn) or ""
t("z05: _pick_kind_axis_col без matched[0]/hits[0] winner",
  "matched[0]" not in src_pick and "hits[0]" not in src_pick
  and "reranked[0]" not in src_pick)
# вместо winner — явный None / ask-маркер
t("z05: _pick_kind_axis_col при >1 → None|ask",
  "len(matched) > 1" in src_pick or "len(hits) > 1" in src_pick)

# (г-silent) stock_net_register_pair: нет max(others)/sorted_s[0] как единственный выбор при >1
pair_fn = _func_node(z12_tree, "stock_net_register_pair")
src_pair = ast.get_source_segment(z12, pair_fn) or ""
t("z12: stock_net_register_pair без silent sorted_s[0]/max(others)",
  "sorted_s[0]" not in src_pair and "max(others" not in src_pair)

# (г-silent) measure_choice: how=='ask' ветка жива; запрет «всегда names[0]»
mc = _func_node(z14_tree, "measure_choice")
src_mc = ast.get_source_segment(z14, mc) or ""
t("z14: measure_choice отдаёт ask при >1", "'ask'" in src_mc or '"ask"' in src_mc)
t("z14: measure_choice single только при len==1",
  "len(names) == 1" in src_mc)
# запрет вызова kind_axis_rerank из z05 (уже в FORBIDDEN глобально)
t("z05: 0 kind_axis_rerank call",
  not _call_sites(z05, "kind_axis_rerank"))
```

В `answer` / `_settle_measure`: при `_how == "ask"` обязателен путь в
`readings_menu` (уже есть :2028–2035) — замок:

```python
t("answer: _settle_measure + readings_menu(measure)",
  "_settle_measure" in z20_src and 'readings_menu(\n            question, "measure"' in z20_src
  or ('"measure"' in z20_src and "readings_menu" in z20_src))
```

---

## 6. Проверка (д) NEW — одноимённые прочтения не утверждаются молча

### 6.1. Дефект

`search_tables.label` срезает тип → документ и регистр «реализациятмц» делят
одну человеческую метку. Verify/pick может отдать **одного** yes-лидера
(лотерея), хотя второе прочтение живо и неразличимо по label. Контракт
владельца: ≥2 живых одноимённых → clarify-меню с различителем
«документ / регистр накопления» (`label_with_kind` / `disambiguate_labels`).

### 6.2. Что проверить статически в z21

Положительные маркеры (после починки кода обязаны появиться):

1. Перед `outcome: "leader"` при пуле ≥2 — вызов проверки одноимённости
   (имя-кандидат: `same_label_tie`, `homonym_labels`, `ambiguous_captions`,
   или явный Call `disambiguate_labels` / чтение нормализованного label и
   `len(set(labels)) < len(candidates)` → clarify).
2. Ветка clarify для tie по label (не только по verify yes/unsure).
3. Меню строится через builder (см. (а)) + подписи с kind-различителем
   (`label_with_kind` / `wiki_human_menu_caption` / `mk_opts`).

Негативы (запрещённые формы «лидер при равных label»):

```python
# В wiki_outcome_from_verify / try_wiki_hybrid:
# запрещено: return leader без проверки label-коллизии, когда
# candidates/passports могли быть >1 с одним human label.
```

Эскиз:

```python
outcome_fn = _func_node(z21_tree, "wiki_outcome_from_verify")
hybrid_fn = _func_node(z21_tree, "try_wiki_hybrid_entity_pick")

def _returns_leader(fn):
    """Есть Return/Dict с outcome==leader."""
    hits = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Dict):
            # ключ "outcome" → "leader"
            pairs = {}
            for k, v in zip(n.keys, n.values):
                if isinstance(k, ast.Constant):
                    pairs[k.value] = v
            o = pairs.get("outcome")
            if isinstance(o, ast.Constant) and o.value == "leader":
                hits.append(n.lineno)
    return hits

# Текст/AST: рядом с leader-путём при n>1 должен быть guard одноимённости.
HOMO_GUARD_MARKERS = (
    "same_label", "homonym", "ambiguous_label", "label_tie",
    "disambiguate_labels", "norm_label", "equal_label",
)
z21_src = Z21_PATH.read_text(encoding="utf-8")
t("z21: есть guard одноимённых label",
  any(m in z21_src for m in HOMO_GUARD_MARKERS))

# Негатив: leader при единственном yes без label-check на пуле ≥2 —
# проверяем, что функция-исход verify зовёт guard ДО return leader,
# либо leader допускается только при len(passports)==1.
src_out = ast.get_source_segment(z21_src, outcome_fn) or ""
t("z21: wiki_outcome_from_verify не лидер при label-tie",
  # после починки: либо явный clarify при same label,
  # либо leader только когда labels уникальны
  any(m in src_out for m in HOMO_GUARD_MARKERS)
  or "len(passports) == 1" in src_out)

# В hybrid: clarify-меню для tied использует mk_opts (kind-различитель)
t("z21: mk_opts на clarify-tie (различитель вида)",
  "mk_opts" in (ast.get_source_segment(z21_src, hybrid_fn) or ""))
t("z20: label_with_kind / disambiguate_labels живы",
  "def label_with_kind" in z20_src and "def disambiguate_labels" in z20_src)
```

**Минимальный поведенческий якорь (оффлайн, без базы)** — опциональный
хвост замка, в духе `test_verify_threshold_menu` / `test_focus_loop`:

```python
# Если в z21 появится чистая функция, например:
#   wiki_label_tie(passports) -> bool
# то:
# t("два src с одним label → tie", wiki_label_tie([
#     {"src_table": "document_x", "label": "Реализация ТМЦ"},
#     {"src_table": "accumulationregister_x", "label": "Реализация ТМЦ"},
# ]))
# t("разные label → не tie", not wiki_label_tie([...]))
```

Пока чистой функции нет — достаточно AST/текстовых маркеров; runtime-якорь
добавить **тем же** коммитом, что и guard.

---

## 7. Готовый каркас файла (сводка порядка проверок)

```python
#!/usr/bin/env python3
"""Замок «один путь» — полный (а)(б)(в)(г)(д). S2-d.

Читает диск: z20/z21 (+ z05/z12/z14 для silent-контракта).
Не load_all / не pytest / не SQL.
"""
from __future__ import annotations
import ast, re, sys
from pathlib import Path

# ... константы §1 ...

PASS, FAIL = 0, []

def t(name, cond, detail=None):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail if detail is not None else "")

# загрузка деревьев z20/z21/z05/z12/z14
# (г) FORBIDDEN + HATCH + B4
# (г-silent) тройка measure_choice / _pick_kind_axis_col / stock_net_register_pair
# (а) clarify builders + journal exclude + z21 builder
# (б) second-number payloads + render_atom_pair + hatch
# (в) SQL_CALLS после wiki + ticket guards
# (д) homonym label guard в z21 + mk_opts/disambiguate в меню
# sanity: compose / count_defer / WIKI_PICK_SYS / без CLARIFY_SYS в OUR_PROMPTS

print()
total = PASS + len(FAIL)
if FAIL:
    print("ПРОВАЛЕНО: %s/%s" % (len(FAIL), total), FAIL)
    sys.exit(1)
print("%s/0 зелёные" % PASS)
sys.exit(0)
```

Ожидаемый порядок зеленения относительно S2:

1. Снос мёртвых символов → (г) старый список стабилен.  
2. Починка silent-тройки → (г-silent).  
3. z21 clarify → builder + (д) label-tie → (а)+(д).  
4. (б) уже почти зелёный на HEAD; добить, если всплывут `figures+options`.  
5. Полный прогон замка → L67 → выкат.

---

## 8. Состояние HEAD vs финал (шпаргалка)

| Пункт | HEAD сейчас | Финальный замок |
|---|---|---|
| (а) answer bare clarify | 0 Dict в answer (clarify только в builder) | OK; **добавить** z21→builder |
| (а) z21 clarify | bare Dict :1111 | **красный**, пока не readings_menu |
| (б) hatch / render_atom_pair | уже 0 | включить SECOND_KEYS / figures+options |
| (в) SQL до wiki | 0 | расширить SQL_CALLS; ticket явный |
| (г) FORBIDDEN | 41/0 | + silent-тройка контракт |
| (д) одноимённые | нет guard | **красный**, пока нет label-tie → clarify |

Итог проекта: один файл-замок, ~120–180 проверок `t(...)`, тот же UX
`N/0 зелёные`. Внедрять **после** (или вместе с) правками S2-а/б/в по коду;
сам этот отчёт код не меняет.
