# Active Context

_Обновлено: **2026-08-25** (словарь синонимов — обиход). Здесь — только живое.
История по дням — в [`progress.md`](progress.md); стадии по контракту — в
[`docs/TARGET_STATUS.md`](../docs/TARGET_STATUS.md)._

---

# ⏭ С ЧЕГО НАЧАТЬ СЛЕДУЮЩУЮ СЕССИЮ

🔴 **словарь синонимов `[25.08 вечер]`**: дефект генератора — prompt
просил SHORT NAMES+title → морфология метаданных; collision дропал общие
обиходные слова. Починка: everyday words + title; filter_entity_aliases;
bridge = слот без писателя. Замок `test_wiki_alias_parse.py` **17/0**.
Живой пересбор aliases — оркестратор (идемпотентность!).

🔴 **rank×sales qty на товарной оси `[25.08 вечер]`**: класс «топ-N товара»
без названной меры → Количество (`sales_rank_product_axis` + qty источника);
money только если названа/нет qty. Срыв был money-fallback при «топ»≠«top».
Замок `test_sales_rank_canon.py` **43/0**.

🔴 **карта serene_ask `[25.08 вечер]`**: зоны в `docs/audit/zones.json` —
якоря `start`[/`end`] (не абсолютные строки); `code_map.py` считает
границы из AST. Выходы `code-map.json` + `CODE_MAP_ASK.md`. Замок
`test_code_map.py` **28/0** (рост файла без правки зон + пропавший якорь).
Строк **15851**, функций **461**, сквозных **29**, внутренних зон **0**.
`serene_ask.py` не резать — только карта.

🔴 **сводка ночи 25.08** (коммиты `a67eec7`…`588d080`; живые `/ask` не
снимали — Qwen3.8-27B выключен владельцем):

| Тема | Факт | Числа |
|---|---|---|
| Ф6.3 хвост | `solr_synonyms` в такте `build.sh` шаг **7-solr**, fail-closed | замки **26/0** + **28/0** |
| Ф6.6 аудит | `docs/F6_HARDCODE_AUDIT.md` | **12** находок: **1** argv (города), **9** законны, **2** оставлены |
| Ф6.6 #11 | warehouse в `corpus_build` — отбор по Edm, не `IN quantity/количество` | сверка okna **3 ⊂ 13** |
| Ф6.5 | `docs/F6_ROLLOUT_CHECKLIST.md` + `f6_rollout_measure.sh` | замок **15/0** |
| §7bis шаг 3 | `ab-calendar-axis-okna.tsv` в AB/scorer | **6** вопросов; замки **22/0** + **19/0** |
| §7bis след. | проект валютной оси `work/currency-axis-design.md` | валют **6**, курсов **3824**, FX-шапок **40**/8240; Σ **78 789 043** vs **79 164 480** |
| память | `ask_choice_memory` на okna | **0** строк при журнале **1445**, fork B+C **142**, ticket_used **104** → в бой нельзя |
| замки | `docs/LOCKS_SWEEP_2026-08-25.md` | **79** файлов, **2150** оффлайн **0** падений; **9** live не зачтены |
| dev :7890 | `docs/DEV_ENGINE_HANG_2026-08-25.md` | ESTAB **337**, ask@ut_test **232** psql, CPU **0 %**, WAL застыл с **24.08** |


🔴 **закрыт дефект period_relative_forms (25.08 вечер)**: шаг такта **1-period**
кладёт JSON в `search_meta`; пустой словарь виден в `/health`
(`period_relative_forms.loaded=false` → 503). Замок
`test_period_relative_forms_ready.py` **24/0**. Выкат такта на контуры —
после слова владельца.

🔴 **где мы по планам**

- [`PLAN_UPGRADE_NATIVE.md`](../docs/PLAN_UPGRADE_NATIVE.md) **Ф6**: код Ф6.1–6.4
  + хвост Ф6.3 (такт) + аудит Ф6.6 + чеклист Ф6.5 в дереве. Бой `:8091` —
  `ASK_SQL_RRF` без IVF/freshness/solr. Стейджинг `:8092` — Ф6.1/6.2/6.4
  (и словарь/solr после выката 24.08). Порядок боя — чеклист Ф6.5 (сначала
  freshness → IVF → solr; calendar на okna пока no-op).
- [`PLAN_ANSWER_CONTRACT.md`](../docs/PLAN_ANSWER_CONTRACT.md) **§7bis**: шаги
  1–3 календаря в дереве (`corpus` карта + `ASK_CALENDAR_AXIS` + AB-набор).
  На okna `search_meta.calendar_*` **пусты** — пакетный контур не отдаёт
  `$metadata`; `calendar_axis_open()` = false. Следующая ось — **валютная**
  (только проект, кода нет).

🔴 **ждёт включения 27B** (без модели живые пробы/выкат не гонять):

1. выкат такта с 7-solr / словарь на контурах + `ASK_SOLR_SYNONYMS=1` где надо;
2. проба `:8092` с календарной осью после появления карты `calendar_*`;
3. прибор Ф6.5 ДО/ПОСЛЕ на бое по чеклисту;
4. перемер латентности Ф6.1 на свободном GPU.

🔴 **заблокировано (не код этой ночи)**

1. **dev SereneDB `:7890` залип** — рестарт за владельцем (WAL ненулевой, риск
   OOM-петли; см. `DEV_ENGINE_HANG_2026-08-25.md`).
2. **такт / карта календаря на okna** — пакетный контур не отдаёт `$metadata`
   → `calendar_*` пусты; включение `ASK_CALENDAR_AXIS` на okna бессмысленно
   до починки контура / выката карты.
3. **память выбора в бой** — замер коллизий непоказателен (`memory_total=0`).

🔴 **бой okna `:8091` `[24.08]`**: md5 **11d8f158**; `/health` ~**0,05 с**;
AB_PROBE **8/8** ~**55,98 с**; маркер `okna probe live 0err/8`. Флаги
IVF/freshness/solr/calendar на бое **выкл.**

🔴 **стейджинг `:8092` `[24.08]`**: кандидат с Ф6.2+Ф6.4; AB **8/8**;
`/health` native freshness **0,13 с**. Календарная карта в meta ещё пуста.

🔴 **режим оркестрации (владелец, 22.08)**: исполнители — свежие
`cursor-agent -p --force --model auto`; регламент
[`docs/ORCHESTRATION_CURSOR.md`](../docs/ORCHESTRATION_CURSOR.md).

🔴 **Ф5 IVF okna `[23.08]`**: `resolver_ivf_idx` 69 621 + `corpus_ivf_idx`
1,23M; recall@10≈**1.0**; дальше — Ф6 в бой по чеклисту + слово владельца.

🔴 **канон GPU vSwitch `[23.08]`**: `10.3.1.11` / `10.3.1.12`
([`docs/NETWORK.md`](../docs/NETWORK.md) §2.1). 27B сейчас выключен владельцем.

🔴 **кнопка «в дашборд» `[19.08]`**: фронт готов; ждёт `ask_scope` в метаданных
OWUI + админ-функцию. Подробности — `progress.md` / `DASHBOARD_GRAFANA`.

🔴 **Полноту данных ведёт оркестратор** —
[`docs/PLAN_ORCHESTRATOR.md`](../docs/PLAN_ORCHESTRATOR.md).
