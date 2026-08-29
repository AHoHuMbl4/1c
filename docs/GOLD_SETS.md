# Gold-наборы: реестр и разделение «правки / приёмка»

Задача **И4** [`PLAN_TO_TARGET.md`](PLAN_TO_TARGET.md). **Закрыта 28.08.2026** — реестр
сверен с деревом, роли проставлены, замок `test_gold_sets_split.py` зелёный.
Содержимое наборов этим документом **не меняется** — только роли и правило.

Число **21/25** снято на `ab-gold-okna.tsv` — наборе, по которому чинили.
Пока нет прогона на наборе, не участвовавшем в правках, это не оценка продукта
(§0 плана).

---

## 1. Итоговая таблица (канон)

| Файл | Роль | N | Эталоны | Замок |
|---|---|---:|---|---|
| [`ubuntu/serenedb/ab-gold-okna.tsv`](../ubuntu/serenedb/ab-gold-okna.tsv) | **правки** (рабочий okna) | **25** | живой SQL в момент прогона (`ab_scorer.py`) | `test_gold_sets_split` |
| [`ubuntu/serenedb/ab-probe-okna.tsv`](../ubuntu/serenedb/ab-probe-okna.tsv) | **правки** (smoke до коммита) | **8** | из gold-okna; `AB_PROBE=okna` | `test_gold_sets_split` + `check-live-probe` |
| [`ubuntu/serenedb/ab-gold.tsv`](../ubuntu/serenedb/ab-gold.tsv) | **правки** (smoke ut_test) | **8** | живой SQL; `AB_BASE=ut_test` | `test_gold_sets_split` |
| [`ubuntu/serenedb/golden-questions.txt`](../ubuntu/serenedb/golden-questions.txt) | **правки** (smoke база1) | **8** | живой SQL; `golden.sh` | `test_gold_sets_split` |
| [`ubuntu/serenedb/ab-calendar-axis-okna.tsv`](../ubuntu/serenedb/ab-calendar-axis-okna.tsv) | **правки** (ось фичи) | **6** | живой SQL; `AB_CALENDAR_AXIS=okna` | `test_gold_sets_split` |
| `/tmp/f61_boy/ab-gold-24.tsv` (контур-24, **вне git**) | **контроль свежести окна** | **24** | живой SQL v2; пересобирается под «сегодня» | нет (временный) |
| [`docs/ACCEPTANCE_UT.md`](ACCEPTANCE_UT.md) | **приёмка** (ut_test, заморожен; **выведен** из okna-замеров 26.08) | **58** | сверены с SQL ut_test (29.07); с 18.08 не правился | `test_gold_sets_split` |
| [`ubuntu/serenedb/ab-acceptance-ut.tsv`](../ubuntu/serenedb/ab-acceptance-ut.tsv) | **приёмка** (зеркало UT, ut_test) | **58** | дословно из `ACCEPTANCE_UT.md`; не в git на 28.08 | `test_acceptance_ut_tsv` |
| [`ubuntu/serenedb/client-gold-okna.tsv`](../ubuntu/serenedb/client-gold-okna.tsv) | **приёмка** (okna, эталоны 1С) | **67** | И0 `work/gold/client_gold.py` packet↔vitrine; **29.08** live match **22** / needs_read **23** / pending **21** | `test_gold_sets_split` + `test_client_gold` |
| [`ubuntu/serenedb/ab-ambiguous-okna.tsv`](../ubuntu/serenedb/ab-ambiguous-okna.tsv) | **приёмка неоднозначности** (okna) | **18** | контракт clarify/kind; [`I1_AMBIGUOUS_SET.md`](I1_AMBIGUOUS_SET.md) | `test_gold_sets_split` + `test_ab_ambiguous_set` |
| [`docs/ACCEPTANCE_OKNA_LIVE.md`](ACCEPTANCE_OKNA_LIVE.md) | **приёмка** (okna, live-спека) | **~25 правил** | эталон = правила §A/§B при прогоне | оркестратор (не TSV) |
| [`ubuntu/serenedb/ab-acceptance-ambiguous.tsv`](../ubuntu/serenedb/ab-acceptance-ambiguous.tsv) | **черновик Э3** (ut_test) | **18** | копия ambiguous под ut; **не гонять на okna** | нет (не в git) |
| [`docs/ACCEPTANCE_OKNA_2026-08-18.md`](ACCEPTANCE_OKNA_2026-08-18.md) | **архив** | 6 (отчёт) | снимок B7 | — |
| `work/acceptance/intent_cases.tsv` | **не gold** | 59 | — | — |
| `work/acceptance/zero_measure_cases.tsv` | **не gold** | 5 | — | — |
| `work/acceptance/client-gold-okna.tsv` | **артефакт** | — | копия прогона | не канон |
| `work/acceptance/runs/**` | **артефакты** | — | — | — |

**Итого ролей в git (okna-контур):** 5 рабочих TSV/txt + 3 приёмочных полки
(`client-gold`, `ab-ambiguous`, live-спека) + заморозка UT (md + зеркало tsv).

### Контур-24 (today-gold) — вне реестра файлов

Рабочий прогон **24 вопроса** на боевом `:8091` (`user=gold-v2`): набор
`/tmp/f61_boy/ab-gold-24.tsv` — **не в git**, пересобирается под окно «сегодня»
(см. [`SCORER_12_24_RAZBOR.md`](SCORER_12_24_RAZBOR.md)). Это **контроль
свежести окна и регрессии выката**, не набор приёмки: на нём чинили (производен
из v2-спеки gold-okna), пересечение с `client-gold-okna` не проверяется замком
И4. В отчётах называется «контур-24» / «today-gold»; **[замер 28.08]** полный
набор флагов **20/24**, средняя **24,58 с**.

---

## 2. Что изменилось (И4, 28.08)

| Действие | Почему |
|---|---|
| Добавлена итоговая таблица §1 «файл → роль → N → эталоны → замок» | формальное закрытие И4 |
| Внесён `ab-acceptance-ut.tsv` (58) | зеркало `ACCEPTANCE_UT.md` для `load_gold`; файл в дереве, не в git |
| Описан контур-24 `/tmp/f61_boy/ab-gold-24.tsv` | висел неучтённым вне git |
| `ab-acceptance-ambiguous.tsv` помечен «черновик, не в git» | дубль Э3 под ut; не эталон okna |
| `ACCEPTANCE_UT.md` в таблице — «выведен для okna-замеров» | решение владельца 26.08; роль заморозки сохранена для гейта И5 |
| Замок: полка `ab-ambiguous-okna` (18, не в WORKING) | роль «приёмка неоднозначности» не покрывалась |
| Статусы `client-gold-okna` обновлены по TSV 28.08 | pending 36, match 5, … |
| И4 закрыт в `TARGET_STATUS.md` | инфраструктура измерения, не стадия TARGET |

Не менялось: содержимое TSV, `ab_scorer.py`, `serene_ask.py`; пересечение
`client-gold ∩ рабочие = 0` (чистка 27.08, `6709214`).

---

## 3. Разделение ролей (объявление для гейта И5)

| Роль | Набор | Почему |
|---|---|---|
| **Приёмочный (заморожен)** | `docs/ACCEPTANCE_UT.md` (**58**) | не правился с 18.08; И2/И3; гейт И5 |
| **Приёмочный (заморожен, TSV)** | `ubuntu/serenedb/ab-acceptance-ut.tsv` (**58**) | зеркало MD; тот же смысл |
| **Приёмочный (okna, эталоны 1С)** | `ubuntu/serenedb/client-gold-okna.tsv` (**48**) | И0; в правках не участвовал; 6 дублей рабочих исключены (`6709214`); замок ∩ рабочие = 0 |
| **Приёмка неоднозначности (okna)** | `ubuntu/serenedb/ab-ambiguous-okna.tsv` (**18**) | п. 12/18/21; `AB_AMBIGUOUS=okna`; отдельная полка, не WORKING |
| **Рабочий (правки okna)** | `ab-gold-okna.tsv` (**25**) | 21/25, правился с кодом (`993ad81`) |
| **Рабочий (smoke)** | `ab-probe-okna.tsv`, `ab-gold.tsv`, `golden-questions.txt` | короткие пробы |
| **Рабочий (фича)** | `ab-calendar-axis-okna.tsv` | регрессия оси |
| **Контроль окна (не приёмка)** | `/tmp/.../ab-gold-24.tsv` (**24**) | контур-24; вне git |
| **Приёмка live-спека** | `docs/ACCEPTANCE_OKNA_LIVE.md` | правила §A/§B, не TSV |
| **Черновик Э3 (ut)** | `ab-acceptance-ambiguous.tsv` | не эталон okna; пересечения с рабочим — долг |
| **Архив** | `ACCEPTANCE_OKNA_2026-08-18.md` | снимок B7 |

И4 «свести 25 + 58»: **две роли одного измерения**, не один файл. Базы разные
(okna vs ut_test) — смешивать нельзя.

---

## 4. Факты git: участие в отладке

| Набор | В правках с `serene_ask` / скорером |
|---|---|
| `ab-gold-okna.tsv` | **да** — `993ad81`, `b3fb796`, `c0f8e8a`, `3cd727d` (5 коммитов) |
| `ab-probe-okna.tsv` | да — с гейтом пробы (`f4e271a`) |
| `ab-calendar-axis-okna.tsv` | да — с кодом оси (`7c8564c`) |
| `ab-gold.tsv` | старые коммиты ut_test smoke |
| `golden-questions.txt` | `64e5582`, без okna-подгонки |
| `client-gold-okna.tsv` | **нет** — `786aae1`, `6709214` (И0/И4), не с serene_ask |
| `ab-ambiguous-okna.tsv` | **нет** — `fd8bcac` (И1), не в цикле 21/25 |
| `ab-acceptance-ut.tsv` | **нет** — не в git |
| `ab-acceptance-ambiguous.tsv` | **нет** — не в git |
| `ACCEPTANCE_UT.md` | **нет** с 18.08 |

---

## 5. Пересечения (нормализованный текст)

Норма: lower, `ё→е`, обрезка пунктуации, сжатие пробелов.

| Пара | Точных | Почти | Заметки |
|---|---:|---:|---|
| gold-okna ∩ probe-okna | **7** | 0 | probe ⊂ gold (8-й вне gold) |
| gold-okna ∩ ambiguous | **1** | **1** | «как у нас дела?»; склад ≈ склад |
| probe-okna ∩ ambiguous | **1** | **1** | «сколько товара на складе?» |
| ambiguous ∩ ACCEPTANCE_UT | **5** | 0 | намеренно (Э3) |
| ACCEPTANCE_UT ∩ рабочие `ab-*` | **0** | 0 | заморозка чиста |
| client-gold ∩ рабочие | **0** | 0 | после чистки И4 |
| client-gold ∩ ambiguous | **0** | — | отдельные полки |

Пересечение ambiguous ∩ gold-okna **допустимо** — другая роль (не client-gold).

---

## 6. Правило пользования

1. **Приёмочные** (`ACCEPTANCE_UT`, `client-gold`, `ab-ambiguous`) **не открывают
   при отладке** конкретного провала.
2. Прогон приёмки — **целиком** (или фиксированной пачкой прибора).
3. Провал → чинят **код** или заводят в **рабочий** набор; эталон приёмки не
   подгоняют под ответ системы.
4. Перед добавлением в **рабочий** — нет той же формулировки в `client-gold` /
   `ACCEPTANCE_UT`.
5. Контур-24 — только для свежести окна / выката; не объявлять «приёмкой».

### Чем держится механически

Офлайн-замок [`ubuntu/serenedb/test_gold_sets_split.py`](../ubuntu/serenedb/test_gold_sets_split.py):

- `ACCEPTANCE_UT` (58) и `client-gold-okna` (48) не пересекаются с WORKING;
- `ab-ambiguous-okna` (18) объявлен в реестре, не входит в WORKING;
- счётчики и пути совпадают с §1.

Зеркало UT: [`test_acceptance_ut_tsv.py`](../ubuntu/serenedb/test_acceptance_ut_tsv.py).

Гейт И5 [`check-gold-split.sh`](../.claude/hooks/check-gold-split.sh) читает §3;
установка — `install-gates.sh` (владелец).

`ab-acceptance-ambiguous.tsv` в замок И4 **не входит** (черновик ut, не в git).

---

## 7. Как гонять замок

```bash
cd ubuntu/serenedb
python3 test_gold_sets_split.py
# или
python3 -m unittest test_gold_sets_split -q
```

Ожидание: **PASS 30, FAIL 0** (после И4 28.08).

Зеркало UT:

```bash
python3 ubuntu/serenedb/test_acceptance_ut_tsv.py
```

Ожидание: **PASS 15, FAIL 0**.
