# СНОС-15 · линза Z1: кто перебивает вики-каскад

Срез: 11.09.2026. Код только читался. Рантайм ≠ диск: `ask/_bootstrap.py._patch_z20_wiki_primary`
при `load_all` дописывает в текст `z20` гейты V4c (см. §0). Утверждения — `файл:строки`.

Формула №15 (владелец): вопрос → интерпретация из вики → запрос в базу → варианты с
описаниями из вики (если прочтений >1) → выбор человека → ответ. Ничего больше.
Указание: «Ничего не должно перебивать вики-каскад».

Вики-каскад (`z21.wiki_primary_entity_cascade`, зов `z20:2504`) отдаёт:
**лидер** (ровно один неотвергнутый verify), **tie-меню** (`kind=clarify`, ≥2 yes/unsure),
или **no_data**. Tie/no_data/`answer` из каскада z20 **сразу возвращает** (`z20:2507-2508`) —
нижележащий тракт их не видит. Z1 смотрит на путь **после живого лидера** и на точки,
которые при лидере всё равно строят своё меню / меняют src / kind.

---

## 0. Диск vs рантайм (обязательно)

| Слой | Что реально исполняется |
|---|---|
| **Диск** `z20_ask_main_http.py` | Каскад на диске с 01.09. Fork A/B/C, early-clarify A, live_srcs→arb_pool — **без** `wiki_leader_alive`. |
| **Патч** `_bootstrap.py:48-286` → `_exec_zone` `:327-328` | При load: (1) fork A/B/C при лидере → `deferred_wiki` (`:119-138`); (2) исход C сначала `fork_clarify_from_wiki_pool` (`:140-191`); (3) live_srcs в arb_pool только если **нет** лидера (`:193-207`); (4) early-clarify ban += `wiki_leader_alive` (`:209-224`); (5) F-гейт `entity_form_gate_open` (`:226-232`); (6) ecp0↔F swap — **якорь на диске отсутствует** (`ecp_swapped_mark` False), no-op; (7) net-distinct stock (`:70-117`). |
| **z21** | `wiki_leader_alive` `:1079-1099` — на диске; патч z20 её **зовёт**, но сама функция в патче не создаётся. |

Проверка якорей патча на текущем диске (11.09): `fork_old`/`c_old`/`live_old`/`ec_ban_old`/`ef_gate_old`/`net_anchor` = True; `wiki_leader_alive` / `fork_deferred_to_wiki` **на диске ещё нет** (появятся только после load).

Дальше в таблице: **Д** = поведение диска; **R** = после `_patch_z20_wiki_primary`.

---

## 1. Исходы самого каскада (не «перебив», а каскад)

| Исход | Где | Что уходит |
|---|---|---|
| tie-меню | `z21:949-968` → `z20:2507-2508` | `kind=clarify`, options из verify-кандидатов + `wiki_menu_captions` |
| no_data (пустой пул / none / fallback) | `z21:874-883`, `907-917`, `944-948`; post_verify fail → None → `874+` | `kind=no_data` |
| лидер | `z21:969-973` → dict `picked=[leader]` | z20 продолжает тракт с `picked` |

Внутри каскада **до** возврата лидера: `wiki_leader_post_verify` (`z21:1046-1076`) может отвергнуть лидера (мера/ось не на носителе) → `None` → no_data. Это судья каскада, не пост-каскадный перебив.

---

## 2. Таблица точек ПОСЛЕ решения каскада

Легенда класса: **а** заменить/перебить результат (меню entity / no_data / другой src / другой kind); **б** свой вопрос человеку при уже выбранном лидере; **в** проигнорировать tie-меню каскада и построить своё (при лидере — «второе entity-меню»; при гипотетическом проходе без раннего return — своё меню вместо wiki-tie).

| # | Точка | Файл:строки | Условие | Что перебивает | При живом лидере | Класс | Д / R |
|---|---|---|---|---|---|---|---|
| 1 | **code_ambiguous** расширяет `picked` | `z20:2519-2535` | есть code-термы, `not focus`, holders `ts_starts_with` вне `by`/`picked`/`not_for` | добавляет чужие src в `picked` → дальше меню entity | **Да**: лидер остаётся, но `len(picked)>1` → clarify #9/#10 | а→б | Д=R |
| 2 | **signals_disagree** + append `top_by_question` | `z20:2661-2682` | `SIGNAL_DISAGREE`, top∉picked, **не** `(wiki_hybrid_pick ∧ wiki_verify==picked[0])`, не service | расширяет `picked` | **Нет** при нормальном лидере (`wiki_verify==picked[0]`) | а | Д=R (гейт вики уже на диске) |
| 3 | **writer_pair → arb_pool** | `z20:2730-2734`, `2767-2771` | `written_by` у лидера, нет catalog/stock lock | документ-регистратор в круг | **Да**: `arb_pool=[leader, writer]` → fork/early при Д | а | Д: да; R: fork/early глушатся (#6/#8), но пул всё равно раздут до их гейта |
| 4 | **_locked_src singleton** | `z20:2773-2777`, `2836-2840` | `catalog_count_locked` / `stock_canon_locked` / `register_count_locked` | подмена `picked`/`arb_pool` | Сеттеров в тракте **нет** (после В2) — мёртвый читатель | а† | Д=R †dead |
| 5 | **event_filter_pool** | `z20:2755-2759` | `event_path_active` | сужает `arb_pool`, может сбросить doubt | При одном лидере обычно no-op | а (редко) | Д=R |
| 6 | **детектор исходов + fork A/B/C** | `z20:2883-3012`; resolve `z13:286-344`; C `z13:641-817` | `FORK_OUTCOMES∧FORK_DETECT`, `len(arb_pool)>1` ∨ `_window_fork` ∨ `_ef_early` | **C** → `kind=clarify` (entity/axis/period chips) или no_data/unavailable; **B→C**; **A** раздувает picked | **Д: Да** при #3/#1; **R: откладывается** если `wiki_leader_alive` (`_bootstrap:129-136`) → `_outc=deferred_wiki` | а/б/в | **Д≠R** |
| 6a | fork C → `fork_clarify_from_wiki_pool` | патч `_bootstrap:156-166`; реализация `z13:820+` | только R, при `_outc==C` | меню из **всего** `wiki_pool`, не из verify-tie каскада | При лидере R обычно не доходит (defer #6); если defer снят — **своё** entity-меню | в | только R |
| 6b | fork C → `fork_outcome_c` (диск / fallback R) | `z20:2986-3000` (Д); R после wiki_pool None | live_srcs, классы детектора | меню src-веток / place / unsigned; `uncounted_cell`→no_data (`z13:775-779`) | Д: да при раздутом пуле | а/б/в | Д; R fallback |
| 6c | live_srcs → arb_pool | `z20:3009-3012` (Д); R: только если `not wiki_leader_alive` (`_bootstrap:199-204`) | после A/unique/empty | готовит early-clarify | Д: да; R: нет при лидере | а | **Д≠R** |
| 7 | **ecp1 period-clarify** | `z20:2853-2858` → `z05:866-922` | `ASK_ENTITY_FORM`, `event_count_period_clarify_applies` | `kind=clarify` по окнам периода | **Да**, если event+count без периода (коммент `z05:913-919`: после вики) | б | Д=R (патч F-gate расширяет вход в блок, ecp0 pre-cascade на диске нет) |
| 8 | **try_entity_form_answer** | `z20:2859-2864` → `z05:1177+` | тот же блок F | `kind=answer` (форма), не меню entity | Может **ответить** в обход «запрос→…» формулы, не меню | а (kind) | Д=R |
| 9 | **ранний entity-clarify A** | `z20:3030-3078` | `len(picked)>1 ∨ len(arb_pool)>1`, не `_ec_ban` | `kind=clarify` entity options + wiki captions | **Д: Да** (#1/#3); **R: бан** `or wiki_leader_alive` (`_bootstrap:216-222`) — **но** если #1 уже сделал `len(picked)>1`, `wiki_leader_alive` False (`z21:1086-1087`) → бан **не держит** | а/б/в | **Д≠R** (частично) |
| 10 | **mk_opts при len(picked)>1** | `z20:3083-3103` | после early; `len(picked)>1` | второе entity-меню | **Да** после #1 даже при R (лидер «убит» расширением) | а/б/в | Д=R |
| 11 | **подмена src: probe empty → max(by)** | `z20:3169-3185` | `src∉by`, пустой probe, **не** `_wiki_named_entity` | другой src | При `wiki_verify==src` — **защищено** (`:3179-3181`, `_wiki_named_entity` `:1339-1348`) | а | Д=R |
| 12 | **measure_in_kin** смена src | `z20:3241-3257` | want-мера есть у ровно одного kin ≠ src | **другой src** вместо вики-лидера | **Да** | а | Д=R |
| 13 | **measure_choice / pick_measure → measure_alts** | `z20:3259-3308`; `z14:30+`; `z16:586+` | how=`ask` + `measure_ambiguous`; rerank/guess refused; rank_no_quantity | готовит меню мер | Да при >1 мере у лидера | б | Д=R |
| 14 | **unresolved_quantity** (В3) | `z20:3310-3323`; `z16:413-432` | want/compute sum|max|…, >1 имён | `measure_alts=все имена` | Да («итого / без НДС»-класс) | б | Д=R |
| 15 | **measure_class_alts** (sales rank) | `z20:3335-3344`, `3446-3454`; `z16:398+` | rank-sales без меры → money\|qty | меню двух классов | Да на sales-rank | б | Д=R |
| 16 | **мертвая мера → alts живых** | `z20:3391-3407` | выбранная мера all-zero / no values | меню живых мер | Да | б | Д=R |
| 17 | **SLOT_COVER → alts** | `z20:3408-3416` | слово меры не покрыто выбранным полем | меню покрывающих | Да | б | Д=R |
| 18 | **measure_alts → clarify (терминал)** | `z20:3431-3492`, страховка `3506-3528` | alts непусты, не proven; не count_defer | **меню мер** человеку | **Да** — живой замер владельца «итого?/без НДС?» | б | Д=R |
| 18a | subject_unsupported → no_data | `z20:3438-3445`; `z16:246+` | перед measure-clarify | `kind=no_data` вместо ответа/меню мер | Да | а | Д=R |
| 18b | count_defer_measure_clarify | `z20:3433-3435`; `z05:740-756` | want=count\|"" | **глушит** measure-меню | При простом счёте меню мер не строится | (защита) | Д=R |
| 19 | **ecp2 period-clarify** | `z20:3425-3429` | после выбора src/мер-кандидатов | меню периода | Да (event-count) | б | Д=R |
| 20 | **decide_grain → clarify=axis** | `z20:3535-3602`; `serene_axis.py:85-144`; opts `z18:27-51` | `len(kind_hits)>1` или rank multi-col; не skip count/total | **меню осей** («группа ТМЦ?»-класс) | **Да**, если kind/action_axis бьёт в ≥2 refcol | б | Д=R |
| 20a | count_question_skips_axis | `z20:3576-3579`; `z10:9-26` | want count\|list без measure | снимает axis-clarify | При простом счёте ось часто глушится | (защита) | Д=R |
| 20b | total_question_skips_axis | `z20:3589-3593`; `z10:44+` | sum/«итого» без breakdown | снимает axis-clarify | Не глушит rank/list | (защита) | Д=R |
| 20c | rank_axis_hatch → _kh=[] | `z20:3548-3556`, `3569-3570` | rank, `_rank_hatch` ≥2 | форсирует путь clarify через decide_grain | Да на multi-axis rank | б | Д=R |
| 21 | **rank_fold / form rank\|compare без measure** | `z20:3604-3662` | grain form rank/compare, >1 мер | ещё одно measure-меню | Да | б | Д=R |
| 22 | **rank_axis_missing** (после agg) | `z20:4014-4033` | rank_intent, нет group name | axis-clarify поздно | Да | б | Д=R |
| 23 | **compose ask_back** | `z20:4053-4054`, `4254-4278`; промт `z18:55-69` | модель вернула `ask` | *был бы* bare clarify; **сейчас всегда сбрасывается** (`ask_back_dropped=bare_clarify_forbidden` `:4266-4268`) | Мёртвый путь (запрет на диске) | б† | †dead |
| 24 | **no_data после пустого agg/rows** | `z20:3732-3788` и др. | пустой счёт без `_zero_period_not_missing` | kind=no_data при «нет строк» | Не меню; может отказать при живых данных вне окна | а | Д=R |
| 25 | **ранний fork_detect (до каскада)** | `z20:2351-2415` | `FORK_DETECT`, `len(cands)>1` | только `diag.fork` / `_fork_early`; **не return** | Не перебивает сам; кормит #6/#8 позже | (подготовка) | Д=R |

†dead — сеттер/путь снят, читатель остался.

### До каскада (не «после лидера», но рвут формулу №15)

| Точка | Строки | Эффект |
|---|---|---|
| assumed-period clarify | `z20:1861-1888` | `kind=clarify` **до** вики — каскад не зовётся |
| unmatched terms → no_data | `z20:1917-1927` | отказ до вики |
| focus + axis_focus_plan clarify | `z20:2444-2463` | при `focus` каскад в `else` **не зовётся** (`2503`); меню держателей оси |

---

## 3. Хронология пути вопроса с живым лидером

Условия старта: каскад вернул `picked=[L]`, `diag.wiki_hybrid_pick`, `wiki_verify==L`, `wiki_verify_yes==1` → `wiki_leader_alive` True (пока `picked` не раздут).

```
[каскад z21] leader L
    │
    ▼
① code_ambiguous?  (z20:2519)
    │  да → picked=[L, …holders]  ⇒ wiki_leader_alive СЛОМАН
    ▼
② signals_disagree?  — при лидере обычно НЕТ (гейт wiki_verify)
    ▼
③ doubt / arb_pool=[L]
    writer_pair? → arb_pool=[L, doc]     (z20:2767)
    locks? → dead
    doubt+rivals из cands → ещё src     (z20:2778+)  ※ при len(arb_pool)==1 и doubt
      из writer_pair doubt может стать True (z20:2739-2744)
    ▼
④ блок F (ASK_ENTITY_FORM): ecp1 period-меню? → STOP clarify период
    entity_form answer? → STOP answer
    ▼
⑤ детектор исходов (если arb_pool>1 | window_fork | ef_early)
    Д: A→раздуть picked; B→C; C→fork_outcome_c STOP clarify/no_data
    R: wiki_leader_alive → deferred_wiki, C не return
    ▼
⑥ early entity-clarify A (picked|arb_pool >1)
    Д: меню entity STOP
    R: бан wiki_leader_alive — НО если ① раздул picked, бан не работает → STOP
    ▼
⑦ len(picked)>1 → mk_opts entity STOP
    ▼
⑧ src=L; probe/kin:
    empty→max(by) защищён wiki_verify
    measure_in_kin? → src:=kin  (ДРУГОЙ ИСТОЧНИК)
    ▼
⑨ выбор меры:
    pick/unresolved/class/dead/slot → measure_alts?
    count_defer? (want=count) → alts очищены
    иначе → STOP clarify МЕРЫ   ⟵ «итого? / без НДС?»
    ecp2 period? → STOP
    ▼
⑩ decide_grain / axis:
    skip count/total?
    иначе clarify=axis → STOP меню ОСЕЙ  ⟵ «группа ТМЦ?»
    rank_fold measure-меню?
    ▼
⑪ aggregate / compose → answer|figures|no_data
    ask_back запрещён (bare_clarify_forbidden)
```

Типичные живые меню при «честном» лидере (без code_ambiguous):
1. **Меры** (#18) — сущность уже L, вопрос про поле.
2. **Оси** (#20/#22) — сущность L, kind бьёт в несколько refcol / rank без оси.
3. **Период** (#7/#19) — event+count без окна.
4. На **диске** ещё **entity fork/early** (#6/#9), если writer_pair или doubt раздули пул.
5. На **рантайме** entity fork/early глушатся `wiki_leader_alive`, пока `picked`==`[L]`.

---

## 4. Вердикт: что нарушает «ничего не перебивает вики»

Интерпретация формулы №15 для лидера: после одного verify-yes дальше только
**запрос в базу → ответ** (или отказ с данными). Любое **новое меню** (мера / ось /
период / сущность) или **смена src** — перебив каскада. Tie-меню каскада — единственное
разрешённое меню сущностей; строить другое entity-меню при уже выбранном лидере — тоже
нарушение (и класс **в**).

### Нарушают (при живом лидере)

| Приоритет | Точки | Почему |
|---|---|---|
| **P0 — живой замер владельца** | **#18 measure_alts-clarify** (+ #13–17 генераторы alts) | Меню мер после лидера («итого?/без НДС?»). Формула не предусматривает второй вопрос о поле. |
| **P0** | **#20/#20c/#22 axis-clarify** | Меню осей после лидера («группа ТМЦ?» при простом счёте, если skip-гейты не сработали / rank). |
| **P1** | **#12 measure_in_kin** | Тихая **замена src** вики-лидера на kin. |
| **P1** | **#1 code_ambiguous** | Ломает singleton-лидера → открывает entity-меню #9/#10 даже под R-баном. |
| **P1 (диск)** | **#6/#6b/#9 fork C / early A** | Entity-меню поверх verify-лидера. На R частично закрыто `wiki_leader_alive`. |
| **P2** | **#7/#19 ecp1/ecp2** | Period-меню после выбора сущности (осознанно после вики, `z05:913-919`) — всё равно второй вопрос человеку. |
| **P2** | **#3 writer_pair** | Готовит раздутие пула → P1 на диске; на R обезврежен гейтом fork/early, пока picked==[L]. |
| **P2** | **#8 entity_form answer** | Ответ формой в обход «запрос→ответ по лидеру» (не меню, но другой kind-путь). |
| **P3** | **#18a / #24 no_data** | Смена kind на отказ после лидера (дефект п.21, если данные есть). |
| **P3 (только R, если defer снят)** | **#6a fork_clarify_from_wiki_pool** | Entity-меню из **всего** wiki_pool, не из tie каскада — класс **в**. |

### Не нарушают / защищают

| Точка | Почему |
|---|---|
| Tie/no_data return каскада `z20:2507-2508` | Это сам каскад. |
| #2 signals_disagree | Глушится при `wiki_verify==picked[0]`. |
| #11 max(by) | Глушится `_wiki_named_entity`. |
| #18b / #20a / #20b | Глушат лишние measure/axis меню на count/total. |
| #23 ask_back | Запрещён кодом. |
| #4 locks | Сеттеров нет. |
| R-патч `wiki_leader_alive` на fork/early | Закрывает P1 entity-перебивы **пока** picked остаётся `[L]`. |

### Итог одной фразой

**Даже после V4c-патча рантайма вики-лидер не «финальный»:** тракт законно (по коду)
строит **мерные** и **осевые** (и часто **периодные**) меню на том же src; на диске ещё и
**entity**-меню через fork/early. Патч чинит только развилку сущностей (fork/early) и то
ломается от `code_ambiguous` / раздутия `picked`. Это прямое противоречие указанию
«ничего не должно перебивать вики-каскад» и формуле №15 для пути лидера.

---

## 5. Карта файлов (для следующей волны)

| Зона | Роль в перебиве |
|---|---|
| `z21_wiki_choice.py` | Каскад; `wiki_leader_alive`; post_verify |
| `z20_ask_main_http.py` | Все терминалы после `:2504`; диск |
| `ask/_bootstrap.py` | R-гейты V4c `:118-224` |
| `z13_fork_outcomes.py` | resolve A/B/C; `fork_outcome_c`; `fork_clarify_from_wiki_pool` |
| `z16_veto_pick_entity.py` | `unresolved_quantity`, `measure_class_alts`, `pick_measure`, `src_supports_question` |
| `z14_clarify_memory.py` | `measure_choice`, captions |
| `z18_compose.py` | `axis_clarify_options`; ask_back в промте (глушится в z20) |
| `z05_entity_form.py` | ecp period-clarify; entity_form; count_defer_measure |
| `z10_rank.py` | skip axis на count/total; rank helpers |
| `serene_axis.py` | `decide_grain` → `clarify=axis` |

Коммитов нет. Серверы/база не трогались.
