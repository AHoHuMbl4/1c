# ПАМЯТКА ПРОДОЛЖЕНИЯ после компакта (записана 14.09 ~10:00, эпизод «починка словаря: 1 задача = 1 вызов», regen ожидает «да» владельца; ДОП 10:50: «да» ПОЛУЧЕНО, regen ЗАПУЩЕН — §3а)

Прочитать ПЕРВЫМ вместе с memory_bank/activeContext.md (шапка «С ЧЕГО НАЧАТЬ»).
Это продолжение continuation-j3-20260913.md (законы/механика там не устарели).

## 1. Законы (действуют, кратко — полные в j3-памятке и AGENTS.md)

- **Один путь бота** (код бота сейчас ЧИСТЫЙ = 62b2ba2, не трогать без слова
  владельца): вопрос → вики (z21) → запрос → меню при >1 прочтении → выбор →
  ответ. Переспрос ≠ ошибка. Никаких люков/гейтов/подготовок под вопросы.
- **TARGET п.0:** универсальность; списки слов/имён базы/языковые перечни —
  только в приёмке-замере, никогда в коде и промтах.
- **ВСЕ агенты — только cursor-agent**, свежие процессы, промт файлом:
  `cd /srv/1c && nohup bash -c "timeout 2400 cursor-agent -p \"\$(cat
  .claude/state/prompt-<id>.md)\" --force --model auto --output-format
  stream-json > .claude/state/cursor-run-<id>.log 2>&1; echo EXIT=\$? >>
  .claude/state/cursor-run-<id>.log" > /dev/null 2>&1 &`
- **Волны:** планы/исполнение → красная ×3 на каждый план и каждый дифф,
  круги до ACCEPT; исполнители НЕ коммитят; приёмка — ТОЛЬКО замеры
  оркестратора (замки, SQL, журналы), не слова агентов.
- **Git:** git add ОТДЕЛЬНЫМ вызовом перед commit; пат-спек файлами;
  «Числа:»/«Доки:» в сообщении; CHANGELOG в каждом коммите; граф MCP тем же
  коммитом (add_observations → sleep 3 → grep mcp-memory.json → add);
  activeContext ≤300 строк; push после шага.
- 🔴 **Ловушки дня (оплачены сегодня повторно):**
  - `pkill/pgrep -f '<подстрока из своей команды>'` = самоубийство (дважды
    за день!). Только по PID из pgrep -af с маской '[c]ursor-agent', или
    pgrep -f 'подстро[к]а'.
  - Снайпер коммита парсит сообщение: строка `git checkout 62b2ba2 -- файлы`
    В ТЕКСТЕ сообщения = ложный pathspec → «ДИФФ НЕ СНЯТ». Не писать
    `git … -- …` в сообщениях коммитов.
  - ssh + JSON: только файлами (scp /tmp/q.json), не inline -d.
  - Промежуток: cursor-agent ×6 может упасть разом транзитно (~6 мин) —
    просто перезапустить залпом с захватом EXIT= кода (работает).
- **GPU:** карта одна. СЕЙЧАС поднята 27B (владелец, «запускай»), эмбеддер+
  реранкер СНЯТЫ → полигон/такт без kNN; после regen+promote понадобится
  возврат эмбеддера (владелец) для карточек/embed и L67. Переключение
  генератора: /etc/1c-wiki-alias-postgres.env и
  /etc/1c-serene-pipeline-postgres.env: WIKI/BRANCH_ALIAS_MODEL=
  vllm/Qwen3.8-27B (локальная) ↔ vllm/qwen/qwen3.8-27b (OpenRouter);
  песочница /home/undebot/.openclaw-sandbox/.openclaw/openclaw.json:
  бэкапы .bak-local27b-final-20260913 (27B+json_object, ТЕКУЩИЙ) и
  .bak-switch-20260913 (OpenRouter). Словари НЕ генерить на OpenRouter
  (деньги). Параметры песочницы: temp 0 / seed 42 / maxTokens 12288 /
  enable_thinking false — ОСОЗНАННО (детерминизм; два regen без битых).

## 2. Состояние (что сделано 13-14.09, всё в git)

- **(33)** J-fallback закрыт решением владельца без правок (2031613).
- **(34)** Словарный цикл: regen 260/260 (0 пустых) → collision 85 кругов
  (0 осталось) → promote 259/775 → Solr 70→89 → A3 58/18/41.
- **(35)** ВОЗВРАТ кода бота к чистому одному пути 62b2ba2 (2b2a746):
  −1239 строк I0/J; замки 10/10; полигон режим B (md5=git show 62b2ba2);
  L67 return62c = 34 match / 25 honest_no / 6 clarify / 2 wrong
  (прайс — снятие П4; «прошлый месяц» — снятие П2b/П5; оба предсказаны).
  25 honest_no = 14 складских ПРАВИЛЬНЫХ + 7 разговорных форм (дыра
  словаря) + 3-4 регистра словами. Вывод владельца: чинить СЛОВАРЁМ.
- **(36)** Генератор «1 задача = 1 вызов» (4c61521, явное решение владельца
  «точно 100% много точечных вызовов»): монолит упразднён; три сайта
  wiki_alias.sh (entity-init ~198, reask ~454, collision ~372/373) — по
  три вызова шлюза A/B/C (aliases/bestUsedFor/notEnoughFor раздельно);
  сборка однопольных JSON в полный item → ОДИН MERGE сайта (merge_entity/
  collision_merge/reask_merge_confirmed — SQL не менялись); ретрай по полю
  (пустой NEF ≠ падение); сторож целостности entity («причёсанная» entity
  → пропуск+stderr, n_unknown>0 → ретрай поля); collision_round.sql +flows
  в struct_pack (зеркало entity-select); MAX_SEC=0; measure ~280 и
  dayfork ~556 НЕ тронуты. Выкат на окно: deploy_wiki_alias.sh — 26 файлов
  md5 ok (бэкап /opt/1c-mcp-reports/.bak-deploy-20260914-090617).
- **Промт-канон:** .claude/state/dictfix-final-prompt.md — ШЕСТЬ промтов
  (init-A/B/C, collision-A/B/C) дословно в wiki_alias.sh (проверено 6/6
  посимвольно). Правила: event-квота (Input lists flows ИЛИ movement/
  money-total/event quantities, не голый Count → ≥1 разговорный глагол в
  aliases; BAN «подходит соседу» — только для существительных; различие
  в NEF); лимит 3-10; «unsure omit» не для events; hard format best =
  без «скобка+запятая» (запятая без скобок ЛЕГАЛЬНА — P4, замок sep);
  hard format NEF без запятых/скобок (в collision — впервые);
  «Every Input entity appears once; entity values copy Input exactly»
  во всех шести (ревью владельца).
- **Принятые решения дня:** «вики в контекст» ОТВЕРГНУТА (не влезает в 65k,
  дорого, против п.19/«схема в модель не уходит»); A/B проба отменена
  владельцем; вариант (г) лечения замороженных best/nef выбран владельцем
  («г, если так считаешь»); параметры генерации НЕ менять под рекомендацию
  Qwen (temp 0/seed 42 — детерминизм, два regen без битых).

## 3. ПРЯМО СЕЙЧАС (в полёте при записи памятки)

- **Исполнитель-5** (лог .claude/state/cursor-run-exec5-promote.log):
  правки по красной promote REJECT ×3 — (1) переписать лгущие комментарии
  wiki_alias_promote.sql ~120/~138 под матрицу (г) + ~317 счётчики snap×draft;
  (2) test_wiki_alias_sep.py ~185-211: порядок веток (find(THEN s.draft_best)
  < find(THEN t.best_used_for), для nef тоже) + count("regexp_matches(
  coalesce(s.draft_best") >= 2 и draft_nef >= 2 (NOT в heal + положительный
  в keep-dirty-draft); мутационная проба на копии. После него: мой прогон
  sep → красная-подтверждение ×3 → КОММИТ promote (wiki_alias_promote.sql +
  test_wiki_alias_sep.py + CHANGELOG (37) + activeContext + граф) → scp
  promote.sql на окно в /opt/1c-mcp-reports (deploy скрипт его тоже носит —
  но promote НЕ в списке FILES deploy_wiki_alias.sh? ПРОВЕРИТЬ; при
  необходимости scp вручную).
- **Матрица (г) в promote уже в дереве** (исполнитель-4, живая фикстура на
  *_test таблицах все ветки зелёные, бой не тронут): heal=replace чистым
  непустым draft; keep при битом/пустом draft; бой-чист+draft-грязный → бой
  (НЕ union); оба чисты → union; счётчики after: best/nef healed/dirty/
  empty + insert_with_pattern; btrim НЕТ в SereneDB 26.07.3 — trim.

## 4. ДАЛЬШЕ ПО ПОРЯДКУ (regen — ТОЛЬКО после «да» владельца)

1. Показать владельцу канон промтов (dictfix-final-prompt.md, шесть текстов)
   и получить «да». Владелец хочет сам читать финальные промты.
2. Снапшоты на окне: CREATE TABLE alias_okna_c5_pre_split AS SELECT * FROM
   alias_okna_c5; (+ _measure; + контрольные SELECT count).
3. env на окне (/etc/1c-wiki-alias-postgres.env): WIKI_ALIAS_FORCE=1,
   WIKI_ALIAS_COLLISIONS=0, WIKI_ALIAS_MAX_SEC=0 (без потолка; 3× вызовов).
4. systemctl start --no-block 1c-wiki-alias@postgres.service; ход:
   journalctl -u 1c-wiki-alias@postgres.service -f (пачки «алиасов разобрано»;
   теперь ×3 вызова на пачку; ретраи полей видны в stderr). Ожидание ~2 ч.
   Наблюдатель фоном с disable_timeout (ssh-обёртки умирают по 600 с).
5. По финишу: FORCE=0, COLLISIONS=1 (ROUNDS 40; при доборе можно 120
   временно, вернуть 40) → collision до «осталось 0».
6. Promote (новая матрица г): scp ubuntu/serenedb/wiki_alias_promote.sql +
   wiki_alias_migrate_sep.sql в /tmp на окне → psql -v draft_table=alias_okna_c5
   -v battle_table=search_entity_alias -v draft_measure=alias_okna_c5_measure
   -v battle_measure=search_measure_alias -v snap_suffix=<дата> -f
   /tmp/wiki_alias_promote.sql → -f /tmp/wiki_alias_migrate_sep.sql →
   Solr: cd /opt/1c-mcp-reports && psql … -v dict_locale='ru_RU.utf8' -v
   solr_syn_dict='search_dict_syn' -v alias_table='search_entity_alias' -f
   /tmp/solr_synonyms_compile.sql → A3: psql -v dict_table=search_entity_alias
   -f /tmp/metric_a3.sql -At.
7. Слово владельцу: вернуть эмбеддер+реранкер (снять 27B), затем такт
   pipeline (entity_card_build+embed; wiki_pages — VIEW, пересборки не
   требует; passport nef живой) → контрольный L67 на полигоне :8092
   (команда в continuation-j3 §8; если /tmp/v2-full.tsv стёрт — scp
   ubuntu/serenedb/client-gold-okna.tsv).
8. Приёмка (замеры из dictfix-plan.md §5): event-токены в aliases
   реализациятмц и по корпусу (пробный список ТОЛЬКО в замере:
   наторговали/наотгружали/отгрузили/продали/сделали/вышло);
   aliases @@ 'наторговали' ненулевой; яд «установка цен» ушёл из best
   номенклатуры (замороженное лечится); NEF начислениезп с темой оборота;
   L67 до/после; REGRESSION_BASE1 запись; коммит с «Числа:».
9. Стоп-точка выката I0 на прод :8091 — ТОЛЬКО владелец. Скобочные
   остатки (не вылеченные) — видны в счётчиках промота.

## 5. Механика (шпаргалка, детали в j3-памятке §9)

- Окно: ssh -i ~/.ssh/id_ed25519_deploy -p 2202 root@gpu-erw.timpul.pro;
  движок: psql "host=127.0.0.1 port=7890 user=postgres dbname=postgres".
- Полигон :8092 = transient probe8092 (systemd-run рецепт в j3 §8 и в
  return-onepath-plan.md §3.5); прод :8091 НЕ НАШ КОНТУР.
- Замки локально: cd /srv/1c/ubuntu/serenedb && python3 test_<имя>.py.
  Текущие зелёные: parse 34/0, prompts_v2 113/0, sep 110/0, deploy 46/0,
  branch 27/0, one_path 77/0, zone_names 96/0, homonym 10/0,
  measure_menu 12/0, no_pre_wiki 41/0, candidate_verify@62 64/0,
  card_hybrid@62 67/0, trace_rid 10, fork_atom 27/0.
- Юниты: 1c-wiki-alias@postgres (генератор), 1c-serene-pipeline@postgres
  (такт, timer), probe8092 (полигон).
- Ключевые файлы эпизода: .claude/state/dictfix-plan.md (план, 7 кругов
  ACCEPT), dictfix-final-prompt.md (канон промтов), red-*.md (вердикты),
  exec*-*.md (отчёты исполнителей), return-onepath-plan.md (план возврата).

## 6. Чего не знаю / открытые вопросы

- Итог исполнителя-5 и финальной красной promote (в полёте при записи).
- Ляжет ли event-квота на «серую зону» (величины типа «количество заказов»)
  — покажет regen (приёмка §5).
- Время regen на 3× вызовов (оценка ~2 ч, MAX_SEC=0).
- Судьба 27B после regen: снять и вернуть эмбеддер — слово владельца.

## TODO List
  [in_progress] исполнитель-5 → красная ×3 → коммит promote → выкат
  [pending] «да» владельца на промты → regen на 27B (FORCE) → collision
  [pending] promote (г) → Solr → A3 → возврат эмбеддера (владелец) → L67
  [pending] приёмка §5 + коммит эпизода + REGRESSION_BASE1
  [pending] стоп-точка I0 на прод — владелец

## 3а. REGEN ЗАПУЩЕН 14.09 10:44 («да» владельца: «фиксируем и внедряем»)

- Коммиты до запуска: d91b6c9 (37, promote г) и 0599241 (38, entity-строка
  COLL-B/C + замок 6/6) — оба запушены; выкат deploy 26 файлов md5 ok
  (бэкап .bak-deploy-20260914-104344); promote+migrate_sep в /opt/1c-mcp-reports.
- Снапшоты: alias_okna_c5_pre_split_20260914 (260) +
  _measure_pre_split_20260914 (795).
- env /etc/1c-wiki-alias-postgres.env: FORCE=1, COLLISIONS=0, MAX_SEC=0;
  модель vllm/Qwen3.8-27B ЛОКАЛЬНАЯ (песочница baseUrl 178.63.211.188:8000,
  шлюз жив — Unauthorized без ключа, ключ в auth-store песочницы).
- Старт: systemctl start --no-block 1c-wiki-alias@postgres.service (10:44).
  Живой ход: ретраи полей работают («поле aliases попытка 0 не прошло
  валидацию» → переспрос), сторожа живые (duplicate entity skipped,
  meta token stripped).
- Наблюдатель ФОНОМ у меня: bash-t2a3xttd, лог
  .claude/state/regen-watch.log (каждые 2 мин: is-active + count/max-seen_at
  alias_okna_c5 + 2 строки журнала). Финиш = is-active inactive/failed.
- ДАЛЬШЕ по финишу: env FORCE=0 COLLISIONS=1 → collision до «осталось 0»
  (ROUNDS=40 уже в env) → promote (г) из /opt/1c-mcp-reports с
  snap_suffix=20260914b → migrate_sep → Solr → A3 → слово владельцу на
  возврат эмбеддера → L67 → приёмка §5 (п.8 ниже) → REGRESSION_BASE1.

## 3б. СОСТОЯНИЕ НА ВЕЧЕР 14.09 (~17:40)

- Коммиты дня: d91b6c9 (37 promote-г), 0599241 (38 entity-строка COLL-B/C),
  2e625b7 (39 BATCH=1+WORKERS), 40d70e5 (40 COLL_BATCH), 5c8da0e (41
  collision-параллель), 66d0203 (42 план автоматизации), (43) сироты-promote.
- Реген-2: 256/260, 0 пустых, 3 брошено (NEF hard-format у выдачибланков;
  below-min плательщикиндс) — видно в журнале, не молчаливо.
- Collision параллельный (COLL_WORKERS=3) идёт с 16:56; хвост 230→~185,
  наблюдатель bash-l1n3bvgj (coll5-watch.log). По финишу: ROUNDS вернуть 40!
- Promote теперь с фильтром сирот (wiki_entity_facts) + orphan_skipped;
  живая проба на *_t — фантом отсеян.
- После collision: promote snap_suffix=20260914c → migrate_sep → solr → A3
  → СЛОВО ВЛАДЕЛЬЦА на возврат эмбеддера → такт → L67 + REGRESSION_BASE1.
- Памятка о том, как НЕ делать: юнит, стартовавший ДО деплоя, работает
  старым кодом (coll-3); pkill/pgrep -f по своей подстроке; ssh-кавычки —
  файлами; python3 -c многострочник — heredoc-файлом; git add отдельным
  вызовом (снайпер).

## 3в. ФИНАЛ ЭПИЗОДА (ночь 14→15.09, коммиты до (44))

- Collision до нуля: окно-1 300 кругов (172) + добор 123 = 0 (00:44).
- Promote 20260914c: гейты t; 259 (фантом отсеян, orphan_skipped=1);
  (г) healed 10+22; токены 1789→2679; comma 0. migrate 0 остатков.
- Solr 84→161. A3: КАША 68 / ОК 16 / ПРОБЕЛ 36 (было 58/18/41).
- ROUNDS=40 возвращён. Откат: search_entity_alias_pre_promote_20260914c.
- ОСТАЛОСЬ: слово владельца (возврат эмбеддера) → такт → L67 →
  REGRESSION_BASE1 → стоп-точка I0 (прод) — тоже владелец.
