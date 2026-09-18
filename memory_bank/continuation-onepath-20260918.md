# ПАМЯТКА линии «ОДИН ПУТЬ — БЕЗ ЛОВУШЕК» (активная; старт владельца «поехали» 18.09)

HEAD на срезе: 657f019. 🔴 РЕШЕНИЕ ВЛАДЕЛЬЦА (18.09, вечер): «простое задание — один
путь, вызов LLM везде, лишнее убрать, обходы вычистить» — канон ЗАМОРОЖЕН
(.claude/state/design-c.md, тело = канон; 23 круга красной по документу прекращены:
последние ловили дрейф сводок, не идею). Красная ×3 теперь ТОЛЬКО на диффы кода.

## ЧТО ДЕЛАТЬ ПОСЛЕ КОМПАКТА (по порядку)

1. Прочитать канон: `.claude/state/design-c.md` (тело; шапка — только сводка).
   Реестры фактов: `.claude/state/c-lens{1..4}-*.md`.
2. Волна C1+C2 (ОДИН исполнитель cursor-agent, промт-файл по образцу
   .claude/state/prompt-redc.md): проход полного пула. Файлы: z21_wiki_choice.py,
   wiki_card_hybrid.sql, z20_ask_main_http.py (хвосты: terms_for_probe перед
   z20:3921, ТОЧКА 2, src_layer, билеты rescue_concepts в z14 whitelist/accumulate).
   Готовый дифф → красная ×3 НА ДИФФ (промт: показать `git diff`, сверить с каноном,
   вердикт ACCEPT/REJECT с file:line) → круги до ACCEPT ×3 → коммит (пат-спек,
   «Числа:/Доки:») → следующая волна.
3. C4 (z06 probe: spans/supersede/exclude-only-гард) → красная ×3 на дифф.
4. C3 (z20: _journal_intent ключи unknown_words/unknown_terms_unmatched на любом
   завершении прохода) → красная ×3.
5. C5: замок test_onepath_rescue (R-A..R-K, моки psql --csv 't'/'f'!), краснеет на
   HEAD; ПРЕДШАГ: сверка эталона Q5 (80 173 владельца vs client-gold tsv 78 176 —
   разбор, эталон не менять молча) → красная ×3.
6. Перепрогон ВСЕХ замков (one_path 77, degenerate 97, digest 52, homonym 42,
   card_hybrid 79, ask_journal, step2, verify 144, mcp_ask 39+25+16) + осознанный
   список смены ожиданий no_data→меню.
7. Выкат на окно (scp z21/z06/z20 + wiki SQL; systemctl restart 1c-serene-ask@postgres)
   → GO/NO-GO → живые пробы → L67 (:8092) → доки (HOW_IT_WORKS, CHANGELOG, HOW_NOT_TO
   при граблях, памятка) + граф mcp-memory тем же коммитом.

## КЛЮЧЕВЫЕ ФОРМУЛЫ КАНОНА (выжимка для промтов исполнителям)

- ТОЧКА 1 = wiki_primary_entity_cascade ПЕРЕД no_data (вход: любой отказ каскада,
  КРОМЕ off-topic/wiki_none_empty; один раз, diag wiki_full_pool).
- ТОЧКА 2 = перед no_data «значения не найдены» (z20:3927): concepts-вызов;
  после exclude: (1) непонятийный unmatched→no_data; (2) continue при
  (wiki_full_pool ∨ rescue ∨ settled ∨ (детерминированное покрытие ∧ LLM дважды
  недоступна)) ∧ ¬(ii)-only; (3) cascade_truncated (¬wiki_full_pool ∧ ¬rescue_origin)
  ∧ ¬settled ∧ ¬escalated ИЛИ (ii)-only → ОДНОРАЗОВЫЙ escalate в rescue ТОЧКИ 1;
  (4) иначе явный R-D. Без fall-through.
- Понятийность: (i) слоты measure/kind ∪ (ii) LLM-concepts ∪ (iii) span-DL к
  хвосту/label выбранного src (≥2 токенов, через границы групп; ВСЕГДА до probe при
  известном src; span≡имени src = exclude-only, НЕ матч — иначе сужение строк) ∪
  (iv) платформенные слова всей группой с границами (класс _NAMED_TYPE_WORD_RE,
  «регистр*»/«движен*» — производные платформенного механизма, без нового списка).
- rescue_pool = hybrid-SQL с параметрами rescue_alias_n=96 / WIKI_RESCUE_TOP=24,
  rescue-режим БЕЗ axis_ok/filtered; состав слоёв ≡ hybrid; норм-слагаемое — скалярный
  damerau_levenshtein на lower-склейке против хвоста src_table (после первого «_»).
  🔴 ЖИВОЙ ЗАМЕР 18.09 (окно): damerau_levenshtein(«реализациитмц»,«реализациятмц»)=2
  (levenshtein тоже 2; БЕЗ lower=7) → допуск = 2, lower обязателен, негатив-фикстуры
  обязательны. Формула функции жива на сборке — предпосылка закрыта.
- Батч-verify: enrich полным body на КАЖДЫЙ слайс; merge ВСЕХ батчей; НОВАЯ
  outcome-функция (копипаста z21:1110 с срезом запрещена); sole = ровно 1 yes ∧ все
  прочие no ∧ |verdicts|==|pool| ∧ ¬ceiling_hit (pre>24); ceiling_hit → sole запрещён
  (меню+клик); verify-clarify ≥2 → (b2) tie-меню (skip: wiki_rescue ∨
  (wiki_separability ∧ wiki_full_pool)); kind-гомоним после sole — D2 db-гейт.
- Резолвер «где что»: ОДИН вызов на проход (даже при sole — ради concepts);
  трихотомия только до sole; ★ только llm_option_highlight; сужений НЕТ; «ровно
  один» при полном вердикте → меню; |pool|==1 не-sole → R-D; fail-soft/truncated →
  меню; «никакие» при полном покрытии → честный no_data (ПОЛИТИКА владельца).
- rescue_concepts(+pending): в option → whitelist z14:324–328 → accumulate_resolution
  z14:262–281 (переживают цепочку кликов); consume-повтор 1 раз (call-site: z20 сразу
  после 4620–4621); повтор-fail при детерминированном покрытии → continue.
- r[9]=src_layer (r[8]=platform_prefix уже есть, не трогать; 1=kNN, 2=struct).
- ПОЛИТИКА (владелец; красная не блокирует): честный отказ = «данных нет И резолвер
  подтвердил пустоту». «Резолвер отверг живой пул» — в журнал/приёмку.

## ПРИЁМКА (6/67 → 0)

«наторговали»×2=357393,03/0,00(честный ноль!); «наотгружали»=661458,38; «вышло»=
2083550,46; «движений в регистре реализации ТМЦ»=80173 (сверка с tsv — предшаг C5);
«клиентов сейчас»=361. Каждый — ДО ЧИСЛА всей цепочкой кликов. wrong 0; L67 (I0=30/
36/1): match≥30, wrong≤1, «6 не honest_no», −6 ровно (сдвиг соседних → стоп).
GO/NO-GO: ранг «клиентов» в финальном пуле ≤24; p95 спасённого ≤60 с; 0 AskDeadline.
Пробы: мост :6016, свои MCP-сессии, разбавитель «сколько всего валют», выбор только
ask_1c(question=исходный, decision_id=…); веб :18801 (кредиты владельца — 402).

## ПРАВИЛА (действуют полностью)

Только сервер окно: `ssh -i ~/.ssh/id_ed25519_deploy -p 2202 root@gpu-erw.timpul.pro`.
psql 7890; ask :8091 (юнит 1c-serene-ask@postgres, /opt/1c-mcp-reports/ask/);
мост :6016 (Bearer: grep -E "^[A-Z_]+=" /etc/1c-mcp-ask-postgres.env). Исполнители
ТОЛЬКО cursor-agent (`timeout 2400 cursor-agent -p "$(cat .claude/state/prompt-X.md)"
--force --model auto --output-format stream-json | tee .claude/state/cursor-run-X.log`,
фоном); 1 задача = 1 процесс; красная ×3 на каждый дифф до ACCEPT ×3; приёмка —
замеры оркестратора + живые пробы; п.0 TARGET (имена базы только в фикстурах,
словарь руками не правится, работает на незнакомой базе); git: add и commit РАЗНЫМИ
вызовами, пат-спек, «Числа:/Доки:», граф тем же коммитом; ложный блок
check-prompt-rules на .md — править файл через heredoc/python (правило 7, отметить в
коммите); красной запрещён stash; моки формата транспорта ('t'/'f').

## ИСТОРИЯ СЕССИИ (кратко)

4 линзы (c-lens1..4, коммит 4c96d06) → дизайн v19 → 23 круга красной ×3 по документу
(69 вердиктов; польза кругов 1–10: меню-из-одного, срезы судьбы [:8], concepts
переживают клик, Q5 exclude-first; круги 11+ — дрейф сводок) → заморозка 59fa267,
шлифовка 657f019 → живой замер damerau (допуск 2). Коммиты: 4c96d06, e75c747,
75b6818, 59fa267, 657f019.

## ДОЛГИ ВЛАДЕЛЬЦУ (не блокируют)

Кредиты 402 (веб-профиль; субагенты Kimi); ремонт check-prompt-rules; search_dict_syn;
эталон Q5 80173 vs 78176.
