# ПАМЯТКА ПРОДОЛЖЕНИЯ после компакта (записана 13.09 глубокая ночь, эпизод «очередь J», regen J-3 на 27B)

Прочитать ПЕРВЫМ вместе с memory_bank/activeContext.md (шапка «С ЧЕГО НАЧАТЬ»).

## 1. Законы (не нарушать никогда)

- **Один путь бота** (приказ владельца 12.09, действует всегда):
  вопрос → интерпретация из вики (z21) → запрос в базу → варианты с человеческими
  подписями из вики (если прочтений >1) → выбор человека → ответ.
  Одно прочтение → сразу ответ. Переспрос ≠ ошибка. Никаких люков/гейтов-веток/
  «подготовок семейств»/молчаливых выборов. Правки под конкретные вопросы ЗАПРЕЩЕНЫ.
- **TARGET.md п.0 (железно):** универсальность. Репо работает на незнакомой базе БЕЗ
  рук. Окна-специфика — только /etc env на сервере. Никаких списков слов, имён
  сущностей, языковых перечней, правок «под этот вопрос/эту базу». Проверка:
  «сработает ли на базе, которую я никогда не видел?»
- **TARGET п.12/13/19/21:** догадка = ошибка; молчаливая потеря данных = дефект;
  модель не считает и не ищет (считает база); отказ при наличии данных = дефект
  (порядок: ответ → уточняющий вопрос → отказ).
- **Запрет своих скриптов для данных (п.20):** данные — внутри SereneDB (MERGE,
  представления, индексы). Своё — только то, чего у движка нет (OData, вызов LLM,
  отрисовка, проверка ответа модели). Сначала MCP serenedb-docs, потом агент
  serenedb-native, и только потом свой код. Снайпер это останавливает (живой
  пример 13.09: самописный стеммер в J-2 отклонён → ts_lexize).
- **Никаких правил в промтах** (запрет владельца): поведение держится кодом/
  механизмом, не текстом для модели. Хук check-prompt-rules бьёт по императивам
  (never/must/always/должен) в литералах питона и модельных полях.

## 2. Режим работы: Кimi = оркестратор, руки = cursor-agent

- **Регламент: docs/ORCHESTRATION_CURSOR.md** (читать §9 «ловушки режима» целиком
  перед каждой пачкой) + режим описан в AGENTS.md шапке и activeContext раздел
  «РЕЖИМ — АРМИЯМИ».
- **ВСЕ агенты — только cursor-agent** (субагенты Kimi = 402, баланс пуст).
  1 задача = 1 свежий процесс, промт ТОЛЬКО файлом:
  `cd /srv/1c && nohup timeout 1800 cursor-agent -p "$(cat .claude/state/prompt-<id>.md)" \
    --force --model auto --output-format stream-json > .claude/state/cursor-run-<id>.log 2>&1 &`
- **Волны: планировщики ×3-4 на тему → сводка оркестратором → проверяющие ×3-4
  на план → исполнители → красная ×3-4 на каждый дифф → круги до схождения
  (REJECT → правка → новый круг).** Одно и то же задание — нескольким агентам
  (приказ владельца 13.09: «красная не ×2, а 3-4»; «на каждый вопрос по 2-3 агента»).
- **Исполнители не коммитят.** Приёмка — ТОЛЬКО замеры оркестратора (замки,
  SELECT, журналы), не слова агентов. Итог агента = последний `"type":"result"`
  в логе; уведомления о completion приходят ПРЕЖДЕВРЕМЕННО — проверять лог.
- Осторожно с параллельными исполнителями на ОДНОМ файле: 13.09 exec-j2 при
  ревизии откатил правку exec-j1 в test_one_path.py (покрытие уцелело в другом
  замке). Общий файл — разводить по волнам или одному исполнителю.

## 3. Ритуалы git и гейты

- `git add` ОТДЕЛЬНЫМ вызовом от commit (иначе снайпер: «ДИФФ НЕ СНЯТ»).
- Коммит пат-спеком перечислением файлов (не каталогами, не `git add .`).
- В сообщении: «Числа:» (замеры) и/или «Доки:» (разделы serenedb-docs) — гейты
  check-diff/check-sql-docs. CHANGELOG в каждом коммите (метки [замер]/[код]/[решение]).
- Граф MCP тем же коммитом: add_observations/create_relations → sleep 3 → grep по
  memory_bank/mcp-memory.json → git add его же. Новый компонент без графа и правка
  компонента без наблюдения — стоп (check-graph-fresh).
- activeContext.md ≤ 300 строк (ровно 300 проходит; check-active-size). История —
  в progress.md, не сюда. Коммит+push после КАЖДОГО законченного шага.
- Документы не отстают от кода (главное правило AGENTS.md); ошибся — запись в
  docs/HOW_NOT_TO.md по свежему.
- Люк гейтов — ТОЛЬКО владелец (строка в .claude/hooks/override.txt → коммит →
  обнулить файл; при ложном git-gate — --no-verify с причиной в сообщении).
- Выкат на OKNA (scp в /opt) — только из закоммиченного дерева (check-golden).

## 4. Ловушки (выученные, сегодня тоже)

- python через ssh — ТОЛЬКО файлом (scp) или heredoc `python3 - <<'PYEOF'`;
  `python3 -c` через ssh съедает кавычки. Длинный SQL — файлом по scp + psql -f.
- `pkill/pgrep -f <подстрока из команды>` = самоубийство (маска в argv). Только по
  PID; pgrep с маской «[c]ursor-agent» (скобки).
- ssh-обёртки умирают по 600 с — длинные прогоны на окне через nohup + наблюдатель
  фоном; systemctl start --no-block; состояние oneshot — `systemctl show -p
  ActiveState --value` ∈ (active, activating), НЕ is-active.
- 🔴 regexp в SQL: литералы движка стандарт-конформны, `'\\|'` доходит как
  «буквальный backslash ИЛИ пробел» (сплит по пробелу!). Спецсимволы — классами
  `[|]`. Любой regexp с backslash проверять ЖИВЫМ SELECT через psql -f файлом,
  не inline -c (HOW_NOT_TO §3.119, techContext ловушка 61).
- Ручная проба генератора словаря — только с `env OPENCLAW_HOME=/home/undebot/
  .openclaw-sandbox` (иначе уходит в дом бота, «model does not support tools» —
  §3.120). Юнит получает env из /etc, ручная команда — нет.
- `/etc/1c-mcp-reports.env`: SERENEDB_DSN с пробелами без кавычек — source ломает;
  брать `grep '^SERENEDB_DSN=' | cut -d= -f2-`; для reshoot L67 — DSN
  user=postgres + PGPASSWORD из того же файла (serene_ro без пароля).
- tail -n 30 (не tail -30); EnvironmentFile сильнее Environment=.
- /tmp на OKNA периодически чистится — входные файлы прогонов (tsv, env) там не живут.

## 5. GPU и переключения — зачем и как

- Карта одна (49 ГБ): **27B (~42 ГБ) и embedder+reranker (~8+16 ГБ) вместе НЕ
  влезают**. Поэтому эпохи: словари делаем на 27B → снимаем 27B → возвращаем
  embedder+reranker.
- **Приказ владельца (13.09 поздно): словари НЕ делать на OpenRouter — денег не
  хватит.** Regen/доборы — только на локальной 27B, которую владелец поднимает
  по запросу временно (вместо эмбеддера). Пока 27B снята, генератор в ПАУЗЕ
  (мелкие штатные доборы ждут; юнит не трогать).
- Побочка: без эмбеддера такт pipeline падает на embed_check (build.sh:211) —
  штатно для окна, догонит после возврата. С эмбеддером такт идёт 234 с (замер).
- Механика переключения (делает оркестратор, железо — владелец):
  /etc/1c-wiki-alias-postgres.env и /etc/1c-serene-pipeline-postgres.env:
  WIKI_ALIAS_MODEL / BRANCH_ALIAS_MODEL = vllm/Qwen3.8-27B (локальная) ↔
  vllm/qwen/qwen3.8-27b (OpenRouter); песочница /home/undebot/.openclaw-sandbox/
  .openclaw/openclaw.json — бэкапы: .bak-local27b-20260913 (27B+json_object,
  РАБОЧИЙ), .bak-switch-20260913 (OpenRouter), канон-рендер
  ubuntu/openclaw/wiki_alias_setup_home.sh.

## 6. Что сделано 13.09 (всё закоммичено и запушено; коммиты по 1c854da включительно)

- Словари эпоха + P4 + пустышки развилок 698→0: 3152/3152 классов (582bf77).
- R4 (rc0+0 разобранных = попытка, mark_skip MERGE) + dual-Solr + scs-фикс
  (fedd606, 3c36b7b).
- COV: FORCE-regen + collision → A3 c5 43/13/62→43/19/56; promote union-MERGE
  в бой (гейты a-d, list_has_all) + residual sep: бой 259/774, comma 0, Solr
  16→70, A3 боя 56/12/50→57/18/43 (0b54062). Снапшоты: *_pre_promote_20260913.
- Генератор на OpenRouter (9e889e9) → потом ПРИКАЗ: не тратить OpenRouter — пауза.
- Очередь J РАЗОБРАНА (b0b3524): 36 honest_no = 18 складских корректных (остатков
  нет, эталон no_stock) + 6 clarify-меню (не ошибка; корзина clarify_menu в
  i2_runner) + 12 дефектов в 3 классах. Починки:
  J-1 (z21): wiki_pick=clarify ⇒ не no_data (keep_empty → mk_opts(preds=None);
  <2 опций → demote none, НЕ лидер из sole-unsure).
  J-2 (z21): want=count → fit по тождеству сущности через ts_lexize(STEM_DICT)
  (снайпер снял самописный стеммер; оффлайн-фолбэк строгий _homonym_norm).
  J-3: event-формы в промты v2 генератора (общее правило, без wordlist).
  J-4: скорер clarify_menu (переспрос ≠ ошибка).
  Замки: 103/0, 117/0, 19/0 и регресс зелёный. Красные волны ACCEPT везде.
- L67 перезамер j3 (полигон :8092 с новым кодом): match 30→32, honest_no
  36→26 (18 склад корректных), clarify_menu 8, wrong 1, unresolved 0.
  J-2 закрыл 7 кейсов («движений в книгапокупок/книгапродаж/номерабсо/
  реализациятмц» + «Сколько валют?»).

## 7. ГДЕ ОСТАНОВИЛИСЬ (прямо сейчас, на момент записи)

- **Идёт regen J-3 на 27B** (владелец поднял 27B, «готово»): FORCE=1,
  COLLISIONS=0 в /etc/1c-wiki-alias-postgres.env; юнит 1c-wiki-alias@postgres
  запущен (systemctl show -p ActiveState --value). Снапшот alias_okna_c5_pre_j3
  (+measure) снят ДО. Цель: event-формы в aliases (5-7 кейсов: «наторговали»,
  «вышло», «сделали», «реально покупают», «покупателей за месяц», «позавчера»).
  Проверка хода: journalctl -u 1c-wiki-alias@postgres.service | tail.
- **J-fallback ЗАКРЫТ РЕШЕНИЕМ ВЛАДЕЛЬЦА (13.09, CHANGELOG (33)) — БЕЗ ПРАВОК.**
  Разобран полностью: красная ×4 на вердикт аналитика (j-fallback.md), затем
  живая проба B (work/jfb-probe.py → .claude/state/jfb-probe.md): action_axis=""
  у обеих формулировок; ось «ТМЦ» — из resolved_unaccounted_slice_axis_word
  (токен вопроса, эхо имени); efc(«ТМЦ») → чужие каталоги, refcol лидера
  «ТМЦ → catalog_номенклатура» в проверку не попадает → axis_not_carried →
  честный no_data. Владелец: «усложнение понесёт проблемы как снежный ком.
  Четко один путь. Ничего больше. Ничего блокирующего нигде.» Волна
  проектировщиков остановлена, z21/z12 не тронуты. 🔴 УРОК-СТРАЖ: post-verify
  НЕ расширять и НЕ ослаблять новыми механизмами (ни эхо-именем, ни
  refcol-совпадением, ни срезом резолвера) — даже под общим правилом и с
  замками; это решение владельца, не переоткрывать.
- Ожидание regen ~45 мин + collision ~1 ч (ROUNDS пока 40 в env; при доборе
  collision вернуть COLLISIONS=1, можно ROUNDS=120 временно).

## 8. ДАЛЬШЕ ПО ПОРЯДКУ (после компакта продолжить отсюда)

1. Дождаться regen (юнит inactive). Проверить журнал (пустышки/пропуски) и
  diff alias_okna_c5 vs alias_okna_c5_pre_j3 (сколько строк переписано).
2. COLLISIONS=1 (FORCE=0) → collision-добор до «осталось 0» (можно ROUNDS=120).
3. Promote: psql -f wiki_alias_promote.sql (snap_suffix=20260914) → residual
  wiki_alias_migrate_sep.sql → Solr из боя (ожидание ~70+ правил) → A3 на бое
  (/tmp/metric_a3.sql, dict_table=search_entity_alias) → финальный L67 на
  полигоне :8092 (команда ниже) — ожидание: event-кейсы → match, match 32→37+.
4. Сказать владельцу: можно возвращать эмбеддер+реранкер (27B снимется).
  Генератор — в паузу (модель в env оставить vllm/Qwen3.8-27B? НЕТ: вернуть
  vllm/qwen/qwen3.8-27b? НЕТ — приказ «на OpenRouter не запускай»: env вернуть
  к OpenRouter-id, но генерация не пойдёт, пока пул пуст; либо просто оставить
  как есть — РЕШИТЬ с владельцем, записать).
5. Итоговый коммит эпизода J (CHANGELOG (33)+, activeContext, граф).
6. ~~Fallback-фикс~~ — ОТМЕНЁН решением владельца 13.09 (см. §7: один путь,
   ничего блокирующего). Кейс остаётся честным no_data.
7. Стоп-точка выката I0 на прод (L67 30/36/1 → теперь лучше) — ТОЛЬКО владелец.
8. Скобочные 13/27 (best/nef с запятой в скобках) — force-regen отдельным эпизодом.

Команда L67 (рабочая, проверена 13.09 j3): ssh окно →
  cd /opt/1c-mcp-reports/work/gold && PW=$(grep '^PGPASSWORD=' /etc/1c-mcp-reports.env | cut -d= -f2-) && DSN="host=127.0.0.1 port=7890 user=postgres dbname=postgres" && T=$(grep -h '^ASK_TOKEN' /etc/1c-serene-ask*.env /etc/1c-mcp-reports.env | head -1 | cut -d= -f2 | tr -d '"') && PGPASSWORD="$PW" ASK_TOKEN="$T" I2_TAG=<tag> I2_ASK_URL=http://127.0.0.1:8092 I2_RESHOOT_DSN="$DSN" ETALON_DSN="$DSN" SERENEDB_DSN="$DSN" nohup python3 -u i2_runner.py run --tsv /tmp/v2-full.tsv --path engine --out /tmp/i2-<tag> --reshoot-rules reshoot-rules-okna.json --workers 4 > /tmp/i2-<tag>.log 2>&1 &
  (tsv = ubuntu/serenedb/client-gold-okna.tsv из репо → scp в /tmp/v2-full.tsv;
  полигон обновлять: scp ubuntu/serenedb/ask/*.py → /tmp/probe_root/ask/ +
  serene_ask.py → /tmp/probe_root/ + rm -rf __pycache__ + systemctl restart
  probe8092.service + curl :8092/health)

## 9. Механика OKNA (шпаргалка)

- Окно: ssh -i ~/.ssh/id_ed25519_deploy -p 2202 root@gpu-erw.timpul.pro
- Движок: psql "host=127.0.0.1 port=7890 user=postgres dbname=postgres"
- Юниты: 1c-wiki-alias@postgres (генератор), 1c-serene-pipeline@postgres (такт;
  timer active), probe8092 (полигон L67), 1c-serene-ask@postgres (прод, НЕ
  НАШ КОНТУР — не трогать), 1c-mcp-ask@postgres.
- A3: psql -v dict_table=<таблица> -f /tmp/metric_a3.sql (на окне).
- Токен бота: grep -h '^ASK_TOKEN' /etc/1c-serene-ask*.env /etc/1c-mcp-reports.env.
- Прод-бот отвечает через :8091 (не трогаем); полигон :8092 — наш стенд.
