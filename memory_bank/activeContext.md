# Active Context

_Обновлено: **2026-08-27** (Т1: TARGET_STATUS = факты дня). Здесь — только живое.
История по дням — в [`progress.md`](progress.md); стадии по контракту — в
[`docs/TARGET_STATUS.md`](../docs/TARGET_STATUS.md)._

---

# ⏭ С ЧЕГО НАЧАТЬ СЛЕДУЮЩУЮ СЕССИЮ

🔴 **Д5 meta packet `[27.08]`**: inbox **74** delta, `included=false` у всех
(задумано); файла `$metadata` нет. Сигнал `need_metadata=1` / cv **4**
выставлен; замок в `build.sh` с внятным fail. Живой агент **1.0.2** флаг
не читает — **одно действие на Windows:** `packet-agent.exe --smoke`
(или upgrade до **1.1.3**). Таймер пайплайна **остановлен**. Отчёт
[`D5_META_PACKET.md`](../docs/D5_META_PACKET.md).


🔴 **Т1 статус синхронизирован `[27.08]`**: `docs/TARGET_STATUS.md` приведён к
замерам/коммитам дня. Стадии **не** повышали (итог 🟢2 · 🟡15 · 🔴4).
Полный scorer **23/25** (`c706625`) после словаря **не** переснимался.

## Что мешает приёмке (житьё, числа)

1. **Свежесть / Д5** — нет `$metadata`; такт fail до корпуса с
   `need_metadata`. Init OK. Ждёт `--smoke` / агент ≥1.1.3. Отчёт
   `docs/D5_META_PACKET.md` (Д4 — init/выкат SQL).
2. **K6** — live **0/2** (эталоны **141**/**1891**); обрыв на сущности.
   Мера `answer_fit` есть (`bb6779f`, place **5→1**), в ask **не** вшита.
   `ASK_ENTITY_FORM=1` **не** подтверждена (Q2 → догадка).
3. **К2 compare** — бой `:8091` **0/8**; золото SQL **1 049 991,33** живо
   (`4ac3c38`).
4. **Ambiguous** — **5/18** (`96b51ab`); после К5 (AB_PROBE **8/8**) **не**
   перемерено.

## Следующий шаг (порядок)

1. **Windows `--smoke` (или upgrade агента)** → файл `$metadata` →
   `systemctl start 1c-serene-pipeline@postgres.timer`.
2. **K6** — вшить `answer_fit` / clarify двух атомов по проекту
   `docs/K6_ENTITY_RANK.md` §5 (**не** слепой `ASK_ENTITY_FORM`).
3. **К2** — терминальный compare без гейта `ASK_ENTITY_FORM` (`docs/K2_COMPARE_TAIL.md`).
4. **Перемер** ambiguous после коммита/выката К5; затем полный scorer-25.

🔴 **Чужие файлы:** `serene_ask.py` / `ab_scorer.py` / эталоны — другие сессии.
К5 ask в дереве (md5 `4ec52861…`), коммит ask — оркестратор после probe
(отметка `okna probe live 0err/8` уже есть).

## Сделано 27.08 (доказано числом; не закрытие пунктов контракта)

| Коммит / факт | Числа |
|---|---|
| Э4 `bf8ac41` partial в ответе | замок **13/5→20/0**; AB_PROBE **8/8** |
| С2 `3350b12` словарь | **254→257**, avg **55→84**; K6 live **0/2** |
| С3 `343d856` морфология | alias_rank лидер **0→3** |
| С5 `fbbc84c` stem в пайплайне | alias_idx **257**; **3/0/20**; замок **19/0** |
| Д3 `5fb8bf3` пустой alias_idx | **257/257**; замок **13/0** |
| С4 `b80d935` обрыв K6 | эталоны **141**/**1891**; clarify не на предикате |
| К2 `4ac3c38` compare | **0/8**; золото **1049991.33** |
| Д4 `247c2f3`/`0e050b3` такт | **3083×** fail → init OK → metadata **0** |
| K5 в дереве | замки 13/12/11/11/51; стейджинг **8/8** |
| K6 `bb6779f` answer_fit | gold-23 **2→1**; «покупают» **5→1** |

Отчёты: `docs/C2_ALIAS_SWAP.md`, `C3_MORPHOLOGY.md`, `C4_K6_BREAKDOWN.md`,
`C5_MORPH_IN_PIPELINE.md`, `D3_EMPTY_INDEX.md`, `D4_PIPELINE_BROKEN.md`,
`K2_COMPARE_TAIL.md`, `K5_APPLIED.md`, `K6_ENTITY_RANK.md`.

🔴 **GPU в норме `[26.08, слово владельца]`**: embed + 27B + reranker живы.

🔴 **приёмка — только okna** (ut_test выведен, 26.08).

🔴 **И0 / И5**: etalon_1c в дереве; гейт gold-split **7/7** в git — установка
`install-gates.sh` за владельцем.

🔴 **Ф6**: бой `:8091` — `ASK_SQL_RRF`; IVF/freshness/solr/calendar **выкл.**
Чеклист `docs/F6_ROLLOUT_CHECKLIST.md`. Словарь С1–С5 на okna уже живой;
K6 словарём **не** закрыт.

🔴 **режим оркестрации**: `docs/ORCHESTRATION_CURSOR.md` — свежий
`cursor-agent -p --force --model auto`, без резюме сессий.

🔴 **канон GPU vSwitch `[23.08]`**: `10.3.1.11` / `10.3.1.12`
([`docs/NETWORK.md`](../docs/NETWORK.md) §2.1).

🔴 **Полноту данных ведёт оркестратор** —
[`docs/PLAN_ORCHESTRATOR.md`](../docs/PLAN_ORCHESTRATOR.md).

История 25–26.08 и развёрнутые буллеты дня — в `progress.md` (перенос Т1).
