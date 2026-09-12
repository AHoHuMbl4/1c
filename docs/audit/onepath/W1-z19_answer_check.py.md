# W1 — карта живости `z19_answer_check.py`

Зона: `ubuntu/serenedb/ask/z19_answer_check.py` (файл **368** строк; сумма span определений верхнего уровня **329**).

## Метод

1. Символы — AST top-level (`def` / константа-`Assign`); строки = span определения (`end_lineno − lineno + 1`).
2. Упоминания — AST `Name`/`Attribute` Load + строковые литералы с границей слова: все `ask/z*.py`, `_bootstrap.py`, `_imports.py`, `_wire.py`, `ubuntu/serenedb/test_*.py`.
3. Граф — фактические вызовы по общему namespace (не import-модули). `getattr(..., "лит")` на символы зоны — **нет**.
4. Ловушка: в legacy `answer` имена `_readings` на строках 2405/2954 — **локальные** из `fork_detector_scan`, не `z19._readings`.
5. `_imports.py` / `_wire.py` — символов z19 не упоминают. `_bootstrap.py` только грузит файл (`"z19_answer_check.py"` в списке зон).

## Итог зоны

| Вердикт | Строк | Символов |
|---|---:|---:|
| ЖИВА НОВОМУ | **329** | 14 |
| ЖИВА ТОЛЬКО LEGACY | **0** | 0 |
| МЁРТВА | **0** | 0 |
| Всего | 329 | 14 |

**Зона целиком нужна одному пути.** Гейт ответа, проверка цифр/утечки/свежести и белый список условий отбора перенесены в новый тракт (`gate` / `_onepath_compose_gate` / `_coverage_answer` / `Handler.do_POST`). После flip+сноса legacy зона **остаётся** — она не legacy-only.

## Таблица символов

| Символ | Строки | Span | Кто зовёт (файл:строка) | Вердикт |
|---|---:|---|---|---|
| `_readings` | 41 | 9–49 | internal← `_date2_readings`, `_tokens` | ЖИВА НОВОМУ (internal) |
| `_plausible` | 10 | 52–61 | internal← `_dates`, `_date_spans` | ЖИВА НОВОМУ (internal) |
| `_dates` | 21 | 64–84 | new: `z20_ask_main_http.py` `gate` @187,195,199,202,224<br>legacy: `z20_ask_main_http_legacy.py` `gate` @191,199,203,206,228<br>test: `test_gate.py` @54,428,430<br>internal← (нет внешних кроме gate/тестов) | ЖИВА НОВОМУ (прямо) |
| `_date2_readings` | 12 | 87–98 | new: `gate` @236<br>legacy: `gate` @240 | ЖИВА НОВОМУ (прямо) |
| `_date_spans` | 21 | 101–121 | internal← `_tokens` | ЖИВА НОВОМУ (internal) |
| `_tokens` | 31 | 124–154 | new: `gate` @222<br>legacy: `gate` @226<br>zone: `z18_compose.py` `copied_figures` @594<br>internal← `_norm_numbers` | ЖИВА НОВОМУ (прямо) |
| `_norm_numbers` | 6 | 157–162 | new: `gate` @127,128,159; `_opt_values` @272<br>legacy: `gate` @131,132,163; `_opt_values` @277<br>zone: `z18_compose.py` `ensure_n_groups_named` @289, `ensure_count_named` @313, `copied_figures` @567<br>zone: `z07_rrf_vectors.py` `refuse_text` @326<br>test: `test_gate.py` @45–108,428,430; `test_partial_flag_propagation.py` @62<br>internal← `asked_figure_missing`, `_filter_values` | ЖИВА НОВОМУ (прямо) |
| `ROLE_TOL` | 1 | 165–165 | internal← `check_claims` | ЖИВА НОВОМУ (internal) |
| `check_claims` | 34 | 168–201 | new: `_coverage_answer` @803<br>legacy: `_coverage_answer` @808<br>test: `test_gate.py` @140,142,145 | ЖИВА НОВОМУ (прямо) |
| `prompt_leak` | 20 | 205–224 | new: `gate_out` @257; `_coverage_answer` @822; `_onepath_compose_gate` @1734,1778<br>legacy: `gate_out` @262; `_coverage_answer` @827; `answer` @4164,4224<br>test: `test_gate.py` @186,189,191 | ЖИВА НОВОМУ (прямо) |
| `asked_figure_missing` | 88 | 227–314 | new: `_onepath_compose_gate` @1731,1774<br>legacy: `answer` @4161,4221<br>zone: `z07_rrf_vectors.py` — только комментарий/докстрока @232<br>test: `test_gate.py` @114–135,475–494; `test_compose.py` @448,450,452; `test_partial_flag_propagation.py` @231,371; `test_period_empty.py` @73 | ЖИВА НОВОМУ (прямо) |
| `stale_note` | 16 | 317–332 | new: `Handler.do_POST` @2902<br>legacy: `Handler.do_POST` @5053<br>test: `test_gate.py` @150,153,155,157 | ЖИВА НОВОМУ (прямо) |
| `_threshold_values` | 5 | 335–339 | internal← `_filter_values` | ЖИВА НОВОМУ (internal) |
| `_filter_values` | 23 | 342–364 | new: `_onepath_compose_gate` @1672<br>legacy: `answer` @4054<br>test: `test_gate.py` @319,322,325 | ЖИВА НОВОМУ (прямо) |

## Транзитивные цепочки до z20

### A. Живы новому

```
# HTTP → ответ
Handler.do_POST
  → stale_note                                    # z19 прямо
  → answer_checked → _answer_checked_core → answer
       → _coverage_answer
            → check_claims                        # z19
            → prompt_leak                         # z19
            → gate → _norm_numbers/_dates/_tokens/_date2_readings
            → refuse_text → _norm_numbers         # z07 → z19
       → _onepath_compose_gate
            → _filter_values → _threshold_values → _norm_numbers
            → asked_figure_missing → _norm_numbers
            → prompt_leak
            → gate → … (как выше)
            → ensure_n_groups_named / ensure_count_named / copied_figures  # z18
                 → _norm_numbers / _tokens

# меню прочтений (тоже на новом пути)
readings_menu → clarify_opts_response → clarify_say
  → gate_out → prompt_leak; gate → …
  → _opt_values → _norm_numbers

# internal внутри z19 (нужны гейту/фильтрам выше)
_tokens → _date_spans → _plausible
_tokens / _date2_readings → _readings
_dates → _plausible
check_claims → ROLE_TOL
```

### B. Только legacy

Нет. Все символы зоны достижимы из нового `z20_ask_main_http.py` (прямо или internal к прямо живым).

### C. Мёртвые

Нет.

## Скрытые выбиратели

**В зоне нет.** Символы — разбор чисел/дат, сверка ролей, утечка промта, обязательные цифры в ответе, приписка о старении, белый список порогов/`terms`. Источник / меру / период / ось кодом не выбирают.

Исходящие вызовы из зоны в другие зоны — только `_fmt` (`z01`) и `_group_leader` (`z17`): формат числа и лидер группы, не выбиратели.

Через транзитив «новый тракт зовёт z19 → z19 зовёт выбиратель» — **не тащит**. Обратное (новый тракт зовёт `refuse_text` / compose-ensure, а те зовут `_norm_numbers`) — зона лишь поставщик гейта чисел, не источник выбора.

## Инфра

| Файл | Роль |
|---|---|
| `_bootstrap.py:42` | загрузка зоны в общий namespace |
| `_imports.py` | упоминаний символов z19 нет |
| `_wire.py` | упоминаний символов z19 нет |
| `register_zone('ask.z19_answer_check', …)` | @368 в самой зоне |

## Замки (тесты)

| Файл | Что держит |
|---|---|
| `test_gate.py` | основной замок: `_norm_numbers`/`_dates`/`_filter_values`/`check_claims`/`asked_figure_missing`/`stale_note`/`prompt_leak` |
| `test_compose.py` | `asked_figure_missing` на group-агрегате |
| `test_partial_flag_propagation.py` | folders / undated через `asked_figure_missing`; `_norm_numbers` |
| `test_period_empty.py` | `asked_figure_missing` при нуле |

## Вердикт для одного пути

Зону **оставить и провести** в этап-2 (как в activeContext: «проводка …/z19/…»). Сносить нечего: после удаления legacy весь объём 329 строк остаётся живым для onepath.
