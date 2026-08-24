# Разбор okna ab_scorer 12/24 (23.08.2026)

Замер: боевой `:8091`, пользователь `gold-v2`, набор `/tmp/f61_boy/ab-gold-24.tsv` (24 вопроса v2).
Прогоны: `/tmp/f61_ab/scorer_flag0.txt` (без `ASK_SQL_RRF`) и `scorer_flag1.txt` (с `ASK_SQL_RRF`) —
**оба 12/24**, те же 12 провалов; SQL-RRF не причина.

Окно замера в `ask_journal`: **14:00–14:55 UTC** 23.08.2026 (`code_md5` `760c3923…`, два полных
прогона подряд). **journalctl TRACE за это окно пуст** (`-- No entries --`); путь ответа
восстановлен по `ask_journal` (`rid`, `outcome`, `intent_json`, `atoms`, `clarify_options`, `doubt`).

Эталоны SQL на живой базе (SereneDB `7890`, `Europe/Chisinau`, дата замера 23.08.2026) совпадают
с заголовком прогона scorer:

| SQL-эталон | Значение |
|---|---|
| продажи MTD («этот месяц» до сегодня) | **3 346 620,65** |
| продажи полный календарный месяц | **3 817 442,31** |
| diff неделя vs прошлая | **817 289,51** |
| diff месяц vs прошлый (MTD окна) | **579 169,67** |
| позиций без продаж в месяце | **1 891** |
| покупающих клиентов за 12 мес | **141** |
| топ клиент месяца | **DYNAMIC SELLING GROUP SRL / 0000000004 / …** |
| топ-3 прошлая неделя (1-й) | **VEFASISTEM-COMPANIE SRL / 0000000025 / …** |
| топ товар за всё время (qty) | **356715 Piesa inchidere toc HG VEKA… / 00000000242** |
| документов реализации дек 2025 | **307** |

---

## Сводка по кучам

| Куча | Число фейлов | Комментарий |
|---|---:|---|
| **(а) дефект ответа сервиса** | **12** | Все 12 провалов — неверный `kind`, неверное число/агрегат, clarify вместо ответа, rank без имени |
| **(б) дефект набора/эталона** | **0** | SQL v2 на `search_corpus` даёт те же числа, что scorer; MTD vs full month — осознанное правило gold (`doc_date < today+1d`) |
| **(в) дефект сверки ab_scorer** | **0** как первичная причина | `extract_number_digits_candidates` тащит фрагменты дат (`got` «00,01,012026,…»), но в 11/12 случаев верного числа в ответе **нет**; в 1/12 (`декабрь 2025`) число **307** посчитано в `atoms`, но scorer не смотрит журнал |
| **(г) законное расхождение** | **0** | Эталон и сервис считались в один день; расхождение MTD vs full month — ошибка периода в сервисе, не «устаревший» эталон |

Дополнительно (не отдельные фейлы, но ухудшают диагностику):

- Режим `AB_CONTOUR=okna` использует `score_digits`, а не `score_digits_probe` — при kind clarify
  класс «число не сошлось» вместо «kind не тот» (#18, #24).
- `score_name` сверяет **финальный** `outf` после clarify-follow; при чужих вариантах (#10–11)
  follow не срабатывает — это следствие (а), не корневая причина.

---

## Таблица 12 провалов

| # | Вопрос | mode | fact (scorer) | Куча | Причина | rid (flag1) | Журнал / TRACE |
|---:|---|---|---|---|---|---|---|
| 1 | сколько продали в этом месяце? | digits | want 334662065; got …381744231… | **(а)** | Сервис суммирует **полный месяц** 3 817 442,31, эталон MTD 3 346 620,65. `atoms` exact_value 3817442.31; intent продажи/Всего | `8b82c5171700c3e0` | Период: gold `doc_date < today+1d`, сервис — до конца месяца. TRACE нет |
| 2 | какой клиент больше всех купил в этом месяце? | name | missing DYNAMIC SELLING GROUP SRL…; got kind answer | **(а)** | rank/лидер не собран: atoms not_applicable, имя лидера не в text | `709a44d23df02968` | intent клиент/Всего верный, rank-путь не отдал группу. TRACE нет |
| 3 | кто из клиентов молодец… три лучших | name | missing VEFASISTEM…; got kind clarify | **(а)** | Вместо top-3 — axis-clarify по accountingregister (меры Cr/Dr), не accumulationregister + Контрагент | `0ba867cec12c7004` | clarify_options — бухгалтерия, не клиенты. TRACE нет |
| 4 | дай топ-3 клиента по деньгам за этот месяц | name | missing DYNAMIC SELLING GROUP…; got kind clarify | **(а)** | Clarify по мерам document_реализациятмц (итого, курс), не rank top-3 | `61b2cab92ff41802` | intent «клиента» — слабый kind; clarify не про контрагентов. TRACE нет |
| 5 | сколько позиций совсем не продаётся в этом месяце? | digits | want 1891; got 01,04,08,… (flag1 kind figures) | **(а)** | Эталон: каталог минус DISTINCT проданные ТМЦ → **1891**. Сервис: exact_value 5 или 8, другой источник/зерно | `16e691a583dbaba7` | intent «позиций», doubt — не та формула. TRACE нет |
| 6 | эта неделя лучше прошлой или хуже? | digits | want 81728951; got …728…997… | **(а)** | Ожидается compare-diff **817 289,51**. Сервис считает count документов (728 реализаций, 997 план счетов, два десятка курсов) | `979d75aabef6761e` | `sales_sum_intent`/`compare_period` не довели до `form=compare`. TRACE нет |
| 7 | в этом месяце продали больше, чем в прошлом? | digits | want 57916967; got …381744231… | **(а)** | Ожидается diff **579 169,67**. Сервис отдаёт одну сумму 3 817 442,31 (как #1), не сравнение двух MTD окон | `db35cccd80a1e937` | Тот же MTD/full-month дефект + нет compare. TRACE нет |
| 8 | сколько клиентов реально покупают? | digits | want 141; got …353… (flag1 kind clarify) | **(а)** | Эталон **141** DISTINCT контрагент за 12 мес. Сервис — clarify (intent «клиенты»), в тексте **353** (всего клиентов, вопрос №17) | `97c565bb0f5fe852` | Clarify вместо count distinct; scorer: «число не сошлось». TRACE нет |
| 9 | какого товара больше всего продали за всё время? | name | missing 356715 Piesa…; got kind answer | **(а)** | Rank по **Количество** → 356715 Piesa…. Сервис: суммы по посторонним мерам (Сумма 1879.54, КодДляОтчета 528), лидер не в тексте | `cac3a3520397faa3` | intent продажи/Всего — мера/ось не ТМЦ+qty. TRACE нет |
| 10 | кому мы больше всего продали за всё время? | name | missing DYNAMIC SELLING GROUP…; got kind answer | **(а)** | Rank по Контрагент + Всего. Сервис: несколько несвязанных sum по разным сущностям (107M, 80M, …), без имени | `2516f1b7d2d93703` | intent «продажи» без клиента; rank не активирован. TRACE нет |
| 11 | как у нас дела? | clarify | want kind clarify; got kind figures | **(а)** | Широкий вопрос → gold ждёт **clarify**. Сервис — **figures** с count 189043 (План счетов) | `2e76012ff76813d9` | intent пустой; нет ветки «уточни аспект». TRACE нет |
| 12 | сколько документов реализации за декабрь 2025? | digits | want 307; got 1,2,2025 (kind clarify) | **(а)** | **307** посчитано (atoms exact_value 307, doubt unique), но отдан **clarify** по нерелевантным справочникам | `a12092e1f314e94f` | Гейт doubt/unique режет готовый ответ; scorer не читает `atoms`. TRACE нет |

Цитаты fact — из `scorer_flag1.txt` (идентичны flag0 по составу провалов).

---

## Приоритет починок

Оценка «+N» — сколько **дополнительных** OK даст починка при неизменном gold-24 (верхняя граница,
если исправления независимы).

| Приоритет | Что чинить | Где | Ожидаемый эффект |
|---:|---|---|---|
| **1** | **MTD для «этот месяц»**: верхняя граница периода `doc_date < today+1d` (Chisinau), не конец месяца | `serene_ask.py` — построение окна периода / `outside_period` / фильтр `doc_date` в агрегате продаж | **+1** (#1). Разблокирует корректную базу для compare (#7) |
| **2** | **`form` compare** для «лучше/хуже/больше чем» + двух окон (неделя/месяц): diff двух сумм, не count документов | `serene_ask.py`: `sales_sum_intent` → `compare_period`, `grain_dec_from_axis_ticket`, ветка compare (~3438, ~5207, ~7038) | **+2** (#6, #7) → 15 из 24 вместе с #1 |
| **3** | **Rank/leader в тексте** для «больше всего/топ-N/какой клиент/какого товара»: `grain=group`, ось Контрагент/ТМЦ, `rank_leader_answer_text`, подавление axis-clarify при `rank_intent_from` | `serene_ask.py`: `rank_intent_from`, `rank_question_text`, `rank_leader_answer_text`, `total_question_skips_axis`, compose rank-слоты | **+5** (#2–4, #9–10) → до **20 из 24** |
| **4** | **«Не продаётся»** = count(номенклатура) − count(distinct проданные ТМЦ в месяце) | `serene_ask.py` — intent «позиций» + формула на `catalog_номенклатура` / `accumulationregister_реализациятмц` | **+1** (#5) |
| **5** | **Широкие вопросы** («как у нас дела?») → kind clarify, не figures по случайному count | `serene_ask.py` — классификация vague/broad до агрегата | **+1** (#11) |
| **6** | **doubt unique**: если atom computed один и совпадает с intent — ответ, не clarify | `serene_ask.py` — гейт doubt / ticket_variant (~11649+) | **+1** (#12) |
| **7** | **Count distinct покупателей** за окно без clarify; не подменять «всего клиентов» (353) | `serene_ask.py` — distinct grain по Контрагент + `count_question_skips_axis` | **+1** (#8) |
| **8** | (Диагностика, не продукт) **`score_digits_probe` для CONTOUR**, фильтр годов 1900–2099 в `digits()`, опционально сверка по `diag.claims` | `ab_scorer.py`: `score_digits`, `extract_number_digits_candidates`, `main()` ~641 | **0** на score при текущих ответах; чище классы провалов |

**Три первые починки (#1–3)** при полной реализации дают до **+8** OK (с 12 из 24 до 20 из 24),
если остальные семь вопросов чинятся отдельно по #4–7.

---

## Что проверено и чем

| Источник | Что сделано |
|---|---|
| `/tmp/f61_ab/scorer_flag0.txt`, `scorer_flag1.txt` | Построчные verdict/fact, сводка 12/24 |
| `/tmp/f61_boy/ab-gold-24.tsv` | SQL-эталоны и режимы v2 |
| `ubuntu/serenedb/ab_scorer.py` | Логика `score_digits` / `score_name` / `score_clarify`, CONTOUR vs PROBE |
| `psql` okna `:7890` | Пересчёт эталонов; MTD vs full month; top-3/top-1 |
| `ask_journal` + `ask_journal_text` | 46 записей 14:00–14:55 UTC, `rid`, `outcome`, `atoms`, `intent_json`, `clarify_options` |
| `journalctl -u 1c-serene-ask@okna` 14:00–14:55 | **Пусто** — TRACE по rid не восстановлен |

Сервис `/ask`, юниты и повторный прогон `ab_scorer` **не вызывались** (параллельный выкат).
