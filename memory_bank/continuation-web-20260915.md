# ПАМЯТКА ПРОДОЛЖЕНИЯ: веб-контур (вопросы-ответы), эпизод 15.09 — web1+web4 закрыты

Читать ПЕРВЫМ при продолжении этой линии. Сестринская линия (параллельная
сессия): continuation-pipeline-20260915.md (пайплайн словаря, шаги 1-3+).
Шапка activeContext — общая.

## ОТКУДА ЭТО ВЗЯЛОСЬ

Владелец принёс живой веб-диалог (Open WebUI → OpenClaw web-профиль → ask_1c)
«сколько выручки за вчера» — я разобрал его по журналам/эталонам SQL, вышло
4 слоя дефектов:

1. **слой 1 — транспорт**: webchat кладёт вопрос в конверт
   `[Chat messages since your last reply - for context] … [Current message -
   respond to this] User: …` (532–1225 симв) → pending-сведение к decision_id
   мертво, locked_q грязный, опции из мусора, «вчера» тонет. **ЗАКРЫТО (web1)**.
2. **слой 2/3 — источник и мера**: гомоним «Реализация ТМЦ» (документ ↔ регистр
   накопления); у регистра мера «Сумма»='0' во ВСЕХ 79 762 строках (деньги в
   «Всего»: август 4 218 825,39 при ответе бота «0,00, продаж нет»). Словарь мер
   повесил слова «выручка|сумма продаж» на мёртвое поле. **ОТКРЫТО** — решение
   владельца: механизм живости мер (шаг 7 PLAN_DICT_AUTOMATION) или отдельная
   волна. Подгонка («повесить слова на Всего у этого регистра») запрещена (п.0).
3. **слой 4 — финальная миля**: персона (DeepSeek) теряла меню, добавляла
   «продаж не было» и «единственные данные — 73 222,39» (число из старой реплики).
   **ЗАКРЫТО (web4)** — нативными хуками, промты не трогали (указание владельца:
   «промты не работают тут, есть средства openclaw нативные»).

## ЧТО СДЕЛАНО (коммиты; всё запушено)

- **web1** `b21b07c` + выкат `6bc7e64`: `mcp_ask.py` —
  `strip_webchat_question_envelope` (два маркера, substring не конверт,
  `(?i)^User:\s*`, пустой хвост → исходник, no-op → тот же объект), вызов ДО
  `apply_pending_before_ask`; focus/measure при маркере; TRACE
  `envelope_stripped было/стало`. Замок test_mcp_ask_envelope.py **25/0**
  (без чистки 11/25 красных). Выкат: /opt/openclaw-mcp/mcp_ask.py md5=репо,
  рестарт 1c-mcp-ask@postgres. Живая проба: конверт 200→19, answer «7 валют»
  (=контроль (47)); цепочка меню→выбор конвертом → decision_id доезжает
  (ticket_variant «Оптовая Торговля», q_len 30).
- **web4** `a9d7249` + выкат `e864010`: verify-plugin 1.1.8 — WHY_MAX_ATTEMPTS
  {figures:2, no-figures-in-answer:2, clarify-lock:2, no-data-tool:1}
  (worst-латентность 50–75 с); mergeRef clarify-only (цифры опций заземлены,
  цифры данных не наследуются; figures-после-clarify = полная замена); замок
  уточнения на finalize по runId (fail-closed на пустом) → why=clarify-lock;
  no-figures-in-answer (числа в эталоне есть, ответ их не называет) ДО раннего
  allow. Инструкции — в DEFAULTS, ПОЗИТИВНЫЕ («Rewrite using only… Its figures
  are the numbers to state») — гейт check-prompt-rules ловит императивы в
  добавленных строках, в т.ч. do not/must. Замки node test-verify.mjs **138**
  (на HEAD краснеют P0-1/2/3+P1/P1b). Выкат: npm pack → openclaw plugins
  install npm-pack:<tgz> --force в ОБА профиля (web + дефолт) → рестарт
  user-юнита openclaw-gateway-web (undebot, XDG_RUNTIME_DIR=/run/user/1001,
  systemctl --user -M undebot@). Живая проба через chatCompletions
  (:18801, токен в openclaw-web.json gateway.auth.token): «сколько выручки за
  вчера» → меню доехало (ранее давало «нельзя получить данные»); 4× revise
  why=clarify-lock в журнале.
- CHANGELOG (52)(54)(57)(58) — мои; (50)(51)(53)(55)(56) — соседняя линия.

## 🔴 ПРАВИЛА РАБОТЫ (кратко; полные — AGENTS.md + ORCHESTRATION_CURSOR §9)

- **Язык с владельцем — русский. Работаем ТОЛЬКО на окне** gpu-erw.timpul.pro:2202
  (клиент/сервисы в контейнере okna). Другие хосты не трогать.
- **Все агенты — ТОЛЬКО cursor-agent** `-p "$(cat .claude/state/prompt-<id>.md)"
  --force --model auto --output-format stream-json | tee .claude/state/cursor-run-<id>.log`,
  таймаут 1500-1800, запуск ФОНОВЫМ Bash (run_in_background, disable_timeout).
  1 задача = 1 процесс. Субагенты Kimi запрещены. Промты ТОЛЬКО файлами
  (Write; слова git add/commit в тексте промта → снайпер ловит команду).
- **Волны**: анализ ×3 независимых линзы (каждая строит реестр сама) → план →
  красная ×3 (круги до ACCEPT ×3; у web4 ушло 4 круга — это нормально) →
  исполнение (1 процесс; НЕ коммитит) → красная ×3 на РЕАЛЬНЫЙ дифф → мои
  замеры → коммит → push → выкат → живая проба. Приёмка — ТОЛЬКО замеры
  оркестратора (md5, тесты, журнал), веры сводкам нет.
- **git-ритуалы**: add и commit РАЗНЫМИ вызовами; commit ПАТ-СПЕКОМ
  (`-- файл1 файл2`, не каталог); «Числа:» и «Доки:» в сообщении; mcp-memory.json
  тем же коммитом (add_observations → sleep 3 → git add). 🔴 CHANGELOG: вставка
  новой записи — якорем ЗАГОЛОВКА, заголовок якоря ОБЯЗАН вернуться в
  new_string (HOW_NOT_TO §1.71 — я съедал его дважды 15.09). Номер проверять:
  параллельная сессия занимает номера (было две (54), моя (53)→(54)).
- **Гейты живые**: check-prompt-rules — императивы в строках для модели
  (инструкции revise писать позитивно, в DEFAULTS); check-golden — держит
  ЛЮБОЙ выкат пока в ubuntu/ есть py-файлы ≠ HEAD (лечится ожиданием коммита
  соседа; дозор: фоновый цикл `git status --porcelain ubuntu/ | grep '\.py'`);
  граф — наблюдение на правимый компонент.
- Python-диагностика — heredoc-файлами, НЕ -c. pkill -f по подстрокам промта
  запрещён. /tmp на окне чистится.

## МЕХАНИКА ВЕБ-КОНТУРА (выучено)

| Что | Где/как |
|---|---|
| фронт | Open WebUI на openclaw-okna (2.28.49.158), ходит в `10.3.1.11:18801/v1` |
| шлюз | OpenClaw `--profile web`, user-юнит undebot `openclaw-gateway-web`, каталог `/home/undebot/.openclaw-web/` |
| сессии диалогов | `.openclaw-web/agents/main/sessions/*.jsonl` (type:message, message.role=user/assistant/toolResult; выбор пользователя виден как `[Chat messages since your last reply - for context]…[Current message…] User: <текст>`) |
| журнал плагина | `.openclaw-web/logs/gateway.log`, grep `braine-verify` → clarify_lock set / rewrite slot|release / before_agent_finalize action=… why=… |
| мост | MCP :6016 (streamable-http, Bearer MCP_TOKEN из /etc/1c-mcp-ask-postgres.env), код /opt/openclaw-mcp/mcp_ask.py; выкат scp+рестарт юнита |
| сервис ответов | :8091 (прод, юнит 1c-serene-ask@postgres); журнал ask_journal в базе postgres |
| выкат плагина | npm pack в ubuntu/openclaw/verify-plugin/ → scp → `su - undebot -c "openclaw plugins install npm-pack:<tgz> --force --profile web"` и без --profile → рестарт gateway-web |
| живой вызов моста | /opt/openclaw-mcp/venv/bin/python + mcp.client.streamable_http на :6016/mcp, tool ask_1c (env из /etc/1c-mcp-ask-postgres.env) |
| живой вызов шлюза | POST :18801/v1/chat/completions, Bearer gateway.auth.token из openclaw-web.json |

## ОСТАТОК / ОЧЕРЕДЬ (ждут слова владельца)

1. **Слои 2/3** (плавающий документ↔регистр; «выручка» на мёртвой мере) —
   решение владельца: вплести в шаг 7 PLAN_DICT_AUTOMATION (мерный сайт) или
   отдельная волна. Ключ: механизм живости меры из данных при генерации словаря,
   никогда не правка конкретных строк.
2. **Долги web1/web4** (записаны в HOW_IT_WORKS §8a / README плагина):
   `clarifyLocks.question` в плагине хранит конверт (замок ставит грязный
   вопрос); симметрия чистки `context`. Узкие заходы по мере надобности.
3. Живой контроль владельцем: повторить диалог «сколько выручки за вчера» в
   вебе UI — меню должно доходить, «единственных данных» быть не должно.
4. Соседняя линия (пайплайн) идёт своей чередой — её файлы/выкаты не трогать.

## КООРДИНАЦИЯ С СОСЕДОМ

Параллельная сессия ведёт PLAN_DICT_AUTOMATION (wiki_alias.sh cycle и др.).
Её незакоммиченные файлы держат гейт check-golden → мои выкаты ждут дозором
(см. правило выше). Её записи CHANGELOG нумеруются вперегонки — номер брать
head -1 + 1 и переспроверить grep перед вставкой.
