# N2

Линза на MOL_PLAN §2–3 (E8 + K6-индекс). Только чтение. Дата: 11.09.2026.
Объект: `docs/audit/MOL_PLAN_2026-09-11.md` §2–3.
Фундамент: `docs/audit/mol-k6-m1.md` (карта SQL + EXPLAIN-лист E1–E8).
Код: `corpus_init.sql:420–422`, `entity_rank_v2.py:133–136,370–378,745–755`,
`coverage_build.sql:96`, стиль зон `z07_rrf_vectors.py:262` (`src_table @@`).
Доки: Sql › Indexes › Inverted (query / INCLUDE); `ts_starts_with` / `ts_like`.

**Вердикт одной строкой:** §2–3 **не готовы** — лист E1–E8 не закрывает три
молекулы K6 индексными формами и FILTER-семантику; п.3 обещает «через search_idx»
без ответа, чем считать `n_cards`/`n_with_nums` (их нет в INCLUDE). Нужны дословные
правки ниже.

---

## Сверка

### Что требует план

| Пункт | Текст | Нужно доказать |
|---|---|---|
| §2 | «Снять по списку mol-k6-m1 E1–E8… индекс vs таблица» | Живые планы/стоимость до правки SQL |
| §3 | «corp / live / unnest → search_idx **или** materialized по src_table» | Три молекулы K6 + решение по E8 |
| профиль #1 | corp + live + unnest | Все три с своим доказательством |
| §4c (вне §2–3, но завязан) | post-K6 stock «через тот же индекс/агрегат п.3» | E6 уже в m1; в §2–3 не назван |

### Лист m1 vs три молекулы K6 + stock

| Молекула / зонд | Есть table-EXPLAIN? | Есть index-EXPLAIN? | В §2–3 учтён? |
|---|---|---|---|
| **L1 live** `LIKE accum%` + date/nums/EXISTS | **E1** ✓ | **нет** | назван в профиле/§3, зонда индекса нет |
| **F1 corp** `count`+3×FILTER IN(77) | **E2** ✓ (полный FILTER) | **E3** частичный: только `count(*)`, **без** FILTER | «переписать corp» — E3 не доказывает фикс F1 |
| **M1 unnest** `map_keys(nums)` | **E4** ✓ | **нет** (`nums` ∉ INCLUDE) | назван в §3 без зонда |
| **F5 axis** (не в профиле плана) | **E5** ✓ опц. | нет | вне §2–3 — ок |
| **post-K6 stock EXISTS** | **E6** ✓ | нет | §4c, не §2–3 |
| транспорт | **E7** ✓ | н/п | калибровка |
| субмаркеры TRACE | **E8** (не SQL!) | н/п | §2 назван «E8-EXPLAIN» — **ловушка имени** |

### Пробелы листа (дополнить именами)

1. **E1i — live через индекс (префикс):**  
   `FROM search_idx WHERE src_table @@ ts_starts_with('accumulationregister_')`  
   (или `@@ ts_like('accumulationregister_%')`) + `doc_date IS NOT NULL` из INCLUDE;  
   отдельно — как закрыть `nums`/`EXISTS search_refcols` без TABLE_SCAN корпуса.
2. **E3b — corp index + n_dated:**  
   `count(*)` и `count(*) FILTER (WHERE doc_date IS NOT NULL)` **только** из INCLUDE  
   (`doc_date` уже в `INCLUDE (src_table, row_key, doc_date)` — `corpus_init.sql:422`).
3. **E3c — corp полный FILTER:**  
   index→строка: `FROM search_idx i JOIN search_corpus c ON c.src_table=i.src_table AND c.row_key=i.row_key`  
   (или расширенный INCLUDE с `flags`/`nums`) — доказать, что wall ≤ table E2, а не хуже.
4. **E3d — масштаб OR:**  
   `src_table @@ 't1' OR … OR 't77'` vs `FROM search_corpus WHERE IN(77)` на **малой** базе  
   (десятки/тысячи строк) и на okna — п.0 / универсальность.
5. **E4i — unnest / меры:**  
   отрицательный зонд «nums из индекса» (ожидание: колонки нет) **или**  
   `DISTINCT` ключей из `search_measure_alias` / один проход F1∪M1 без второго скана.
6. **E6i (для §4c, зафиксировать в §2 как вход):**  
   EXISTS/`n_with_nums` из того же источника, что выберет п.3 (индекс+JOIN / витрина).

**Итог сверки:** table-зонды трёх молекул **есть** (E1/E2/E4). Индексный зонд **один и
урезанный** (E3 без FILTER). Post-K6 stock в листе есть (E6), в §2–3 не обязан сниматься
как вход п.3 — но план не говорит, что E6 достаточно для §4c. E8 — TRACE, не EXPLAIN:
формулировка §2 «E8-EXPLAIN» смешивает весь лист с одним пунктом.

---

## Варианты SQL

Источник индекса `[код] corpus_init.sql:420–422`:

```sql
CREATE INDEX IF NOT EXISTS search_idx ON search_corpus
  USING inverted(doc search_dict, refs search_dict, src_table)
  INCLUDE (src_table, row_key, doc_date);
```

`src_table` — verbatim (без словаря) → точный `@@ 'имя'`. INCLUDE отдаёт
`src_table`/`row_key`/`doc_date` без TABLE_SCAN базы (`[доки]` Indexed vs INCLUDEd).
`flags`, `nums` **в индексе нет**.

### Формы, реально возможные в стиле зон

| # | Форма | Где уже так | Что закрывает из F1/L1/M1 |
|---|---|---|---|
| A | `FROM search_idx WHERE src_table @@ 'exact'` | `z07:262` | точечный lookup; не IN-пул |
| B | `… @@ 'a' OR @@ 'b' …` (дизъюнкция) | CHECK1_REVIEW_3: 169 мс vs table IN 253 мс на **2** таблицах | кандидат на F1 **n_rows**; на 77 — **не замерено** |
| C | `@@ ts_starts_with('accumulationregister_')` / `ts_like` | доки FTS; в ask-коде для `src_table` не видно | кандидат на L1 вместо `LIKE` по таблице |
| D | `FROM search_idx` + FILTER по `doc_date` INCLUDE | блог INCLUDE + analytics | **n_rows, n_dated** без корпуса |
| E | `search_idx` ⋈ `search_corpus` по `(src_table,row_key)` | штатный fallback, если INCLUDE узок | полный F1 (flags/nums) / unnest — ценой join |
| F | `FROM search_corpus WHERE IN (…) GROUP BY` | **текущий** F1/M1 | baseline; индекс не подхватывается (m1 P5) |
| G | materialized `src_table → (n_rows,n_dated,n_cards,n_with_nums[, meas_keys])` | аналог идеи m1; `search_coverage` даёт только `в_корпусе`, не FILTER-фичи | все счётчики F1 без скана; M1 — отдельная колонка/таблица ключей |

**Невозможно «просто FROM search_idx» для текущего F1 целиком:**  
`n_cards` = FILTER по `flags.IsFolder`, `n_with_nums` = FILTER по `nums` — колонок нет в
INCLUDE. E3 как гипотеза фикса **не эквивалентен** E2.

### Семантика `count(*)` / FILTER с индексного источника

- Индекс отдаёт **документы (строки корпуса)**, совпавшие по терму, не «сырые постинги
  всех полей» как единицу счёта в обычном `SELECT … FROM idx WHERE @@` (`[доки]` querying;
  проект уже сверяет `count(*) FROM search_idx GROUP BY src_table` с корпусом —
  `coverage_build.sql:93–96,140–141`: `в_индексе < в_корпусе` → «не опубликовано»).
- Для **одного** verbatim-предиката `src_table @@ 'T'` → `count(*)` ≈ число строк
  этой таблицы в индексе ≈ `n_rows` (после refresh; дрейф индекса — отдельный риск).
- **Риск дедупа:** широкая дизъюнкция / OR с пересечением предикатов → строки могут
  всплыть дважды, если план не дедупит по row id; для одного поля `src_table` и
  взаимоисключающих имён таблиц пересечения нет. Неверная форма (OR по `doc`∪`src_table`)
  ломает равенство.
- **FILTER:**  
  - `n_dated` — да, из INCLUDE `doc_date`;  
  - `n_cards` / `n_with_nums` — **нет** без JOIN/расширения INCLUDE/витрины;  
  - unnest(`nums`) — **нет** из индекса.

### Materialized-агрегат (ветка «если индекс не покрывает»)

| Вопрос | Ответ для плана |
|---|---|
| Универсальность (п.0) | Да, если DDL+SQL только `GROUP BY src_table` из `search_corpus` — без имён okna |
| Кто создаёт | `corpus_init` — `CREATE TABLE`; наполнение — **такт** (`corpus_build` / merge после DML корпуса), не руками |
| Кто обновляет | Тот же такт (и ideally path delta/packet, если пишут корпус между тактами) |
| Дрейф между тактами | K6 ранжирует по **устаревшим** счётчикам до следующего refresh |
| Приемлемо? | Для reorder пула — часто да (порядок грубый); для stock-cut по `n_with_nums=0` — **нет**, если дельта добавила nums: молчаливый отсев (п.13) |
| След в diag | Обязателен: `src_stats_ts` / `src_stats_lag_sec` + `src_stats_source=takt|live`; без следа приёмка «≤10с» скрывает регресс качества |
| Альтернатива M1 | Не unnest корпуса, а `search_measure_alias` (+ кэш в запросе) — m1 уже пишет; план §3 обязан выбрать: слить F1+M1 / alias / витрина ключей |

---

## Приёмка «K6 52с → ≤10с»

**Что есть в плане:** «шаг K6 на тяжёлом вопросе 52с → ≤10с; L67; замки» + общая
«тайминги 3 классов на полигоне».

**Чего не хватает (дословно нужно):**

1. Замер = wall маркера `шаг("K6 v2")` в журнале полигона (`z20:2269`) на **тех же**
   3 классах, что в общей приёмке; baseline 52449 мс — rid/`mol-k6-m1`, не новый.
2. Класс, где сработал A2 (§1), **исключить** из приёмки п.3 (K6 не бежит) — иначе
   «≤10с» пустой; см. N4 Ат2.
3. До правки SQL — **E8 TRACE** (субмаркеры expand / features / stock#1): иначе
   «K6≤10» может быть срезом stock#1, попавшим в накопленный маркер, или наоборот
   не доказать P1/P2/P3.
4. L67 **после** п.3 на полном пути (не-A2), не только wall.

**Риск малых баз (п.0):** план OR×77 / index-first, выигравший на okna (1.67M), на
базе с малым корпусом может **проиграть** table `IN` (накладная OR-дерева /
IRESEARCH_SCAN). CHECK1_REVIEW_3 мерил только 2 имени. Без E3d «везде» = только okna.

---

## Атаки

### Ат1 — E8/лист недоснят → фикс не туда

§2 зовёт «E1–E8», но индексная гипотеза для live и unnest **отсутствует**, E3 не
равен F1. Внедрение «всё на `@@`» по одному E3 → правят corp `count(*)`, оставляют
LIKE-скан L1 и второй проход M1 → цель ≤10с не бьётся; или наоборот пилят stock,
пока P1 жив. **E8-TRACE** отдельно: без разреза 52с фикс по «главной» молекуле —
угадайка.

### Ат2 — индекс-план ломает count-семантику

(а) Считают постинги/дубли OR как строки → `n_rows`≠корпус → сдвиг ранга.  
(б) Берут E3 (`count(*)` only) и подставляют в `n_dated`/`n_cards`/`n_with_nums`
нули или тот же count → логика `features_table` врёт.  
(в) JOIN idx→corpus «для FILTER» на больших posting lists = почти тот же table-scan
+ хуже план. Без E3b/E3c это не видно до L67.

### Ат3 — агрегат-кэш скрывает свежесть дельты

Витрина с такта → после packet/HTTP delta корпус новее счётчиков → K6/stock режут
по старью. На okna packet-контур живой (activeContext). Без `*_ts` в diag и без
правила «кто refresh при delta» — ускорение ценой п.13/п.21.

### Ат4 (доп.) — «search_idx покрывает» при INCLUDE-дыры

План §3 одной фразой уравнивает corp/live/unnest. Live нужен префикс+nums+refcols;
unnest нужен `nums`. Индекс **как есть** закрывает максимум n_rows±n_dated. Без
явной ветки «расширить INCLUDE / витрина / слить SQL» исполнитель выкатит неполный фикс.

---

## Вердикт

**§2–3: доработка** (к стоп-точке по этим пунктам — нет).

### Правки дословно в `MOL_PLAN_2026-09-11.md`

**§2 заменить на:**

```
### 2. EXPLAIN+TRACE вход для п.3 (оркестратор; до любой правки SQL)
Снять на живой базе (полигон) лист mol-k6-m1 E1–E7 плюс дополнения:
E1i (live: src_table @@ ts_starts_with/ts_like на search_idx),
E3b (corp index: count + FILTER doc_date из INCLUDE),
E3c (corp полный FILTER через JOIN idx→corpus ИЛИ расширенный INCLUDE),
E3d (OR×N vs table IN на малой базе и на okna),
E4i (unnest: доказать отсутствие nums в индексе; зонд search_measure_alias /
     один SQL F1∪M1),
E6 как вход §4c (stock EXISTS vs n_with_nums из выбранного источника п.3).
Отдельно E8-TRACE (субмаркеры: stock#1, expand_holders, expand_stem_and_live,
features_table, stock#2 pred/body) — разрезать 52с и 21.5с. Имя «E8» ≠ весь лист.
Стоп п.3, пока нет wall E1/E2/E4 и хотя бы одного рабочего index/mat пути с
эквивалентом FILTER F1.
```

**§3 заменить на:**

```
### 3. K6: индекс и/или витрина (после §2; с L67)
Три молекулы — три решения по факту §2 (не одной фразой):
(1) corp F1: search_idx для n_rows±n_dated, если E3b выигрывает; n_cards/n_with_nums —
    JOIN E3c, либо расширение INCLUDE (flags/nums), либо materialized
    search_src_stats(src_table, n_rows, n_dated, n_cards, n_with_nums) —
    DDL в corpus_init, refresh на такте (merge/build), без ручной набивки под базу;
(2) live L1: префикс через индекс (E1i) + условие nums/refcols без полного скана
    корпуса, либо предвычисленный пул live-accum на такте;
(3) unnest M1: слить с F1 в один SQL, либо ключи из search_measure_alias / колонка
    витрины — не второй table-scan IN(77).
Запрет: питон-пулы поверх базы (п.20). Универсальность (п.0): формы только по
src_table/структуре корпуса; запрет калибровать OR×77 только под кардинальность okna
без E3d. Дрейф витрины: в diag src_stats_ts (+lag); решение «приемлемо до такта»
— явное, со стоп-точкой владельца.
Приёмка: на 3 классах полигона, где A2 НЕ перехватил путь — wall шага «K6 v2»
(z20:2269) baseline≈52с → ≤10с; L67-ранг; замки. Малая база: E3d не регресс
>baseline table IN (или явный fallback на table scan при малом |corpus|).
```

**В профиль / приёмку общую одной строкой:**  
«п.3 не суммировать с выигрышем A2 на одном Q; post-K6 stock — §4c после выбора
источника счётчиков в п.3».

---

## Источники

- `docs/audit/MOL_PLAN_2026-09-11.md` §2–3, профиль #1
- `docs/audit/mol-k6-m1.md` E1–E8, P1–P5, вердикт-таблица
- `ubuntu/serenedb/corpus_init.sql:420–422`
- `ubuntu/serenedb/entity_rank_v2.py:133–136,370–378,745–755`
- `ubuntu/serenedb/coverage_build.sql:93–96`
- `ubuntu/serenedb/ask/z07_rrf_vectors.py:262`
- `ubuntu/serenedb/ask/z20_ask_main_http.py:2254–2287`
- `docs/CHECK1_REVIEW_3.md` §7 (idx OR vs table IN)
- SereneDB docs: inverted querying / INCLUDE; `ts_starts_with` / `ts_like`
