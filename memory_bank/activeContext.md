# Активный контекст

## С ЧЕГО НАЧАТЬ (срез вечер 29.08)

1. **Нативный цикл векторов идёт на окне** (nohup bash /tmp/run_native.sh, лог /tmp/native_run.log):
   массовый ai_embed одним оператором на раунд (решение владельца: ТОЛЬКО нативный),
   ~32 строк/с без пауз, очередь 1.6M → утро. Контроль: tail лога + два среза
   count(emb). Упало — перезапустить тем же nohup.
2. **После очереди**: systemctl start 1c-serene-pipeline@postgres → ЗЕЛЁНЫЙ ТАКТ
   (все ступени починены: checkpoint/coverage/merge/solr-RE2/resolver-монстры/\if/секреты) →
   лаг свежести живым числом (п. 17) → пересъём эталонов → контрольный набор (6 вопросов).
3. **ЧП1 закрыт**: client-gold 67/67 (match 65 / mismatch 2 — полнота), 52b47f8. Вход в И2 открыт.
4. **И2** (главный замер): раннер готов (`work/gold/i2_runner.py`, замок **29/0**);
   живой прогон 67×2 (:8091 движок, :18801 веб) — после векторов и пересъёма эталонов.
5. **z21-первичность** — ветка wip/z21-primary (живой прогон дал 6/6 красных при зелёных замках);
   доработка до 6/6 живьём, merge только после.
6. **О5-спека** (PLAN_WIKI_CHOICE §7): вся ручная работа 29.08 → механизмы; первый шаг —
   Restart=on-failure на юните такта (сейчас no: упавший такт лежит молча) и wal_autocheckpoint
   в конфиг движка (SET GLOBAL слетает при рестарте — проверено).
7. Секреты эмбедера: механизм `1c-serene-embed-secrets.service` (О5 ✅); drop-in
   serenedb → авто-пуск после рестарта движка. TEMPORARY в такте — как было.

## Состояние (29.08 вечер, транспорт f7f10236)

- **Дефект транспорта f7f10236 — разобран, сервер закрыт:**
  - Потеря на **seq195** (`000195-dc66c520`): partial apply — `full_entity` регистров
    без Recorder=f7 перезаписал витрину; document delta → `delta_without_key`
    (Ref_Key/ref_key); карантин не откатывает DROP/CREATE.
  - seq154–176 applied — движения **в чанках**; винда выгружала.
  - **Починка:** `_ci_col` (git 30cf7d7), выкат okna; re-apply **000171-9ca09876** →
    витрина f7 **19/19/19/21**. **000195** в карантине — не apply (f7=0 в регистрах).
- **okna такт:** merge f7 без STOP; **красный** solr_synonyms_compile + embed
  (1 642 476 corpus, emb NULL 1 584 759) — отдельно от транспорта.
- **coverage_build**: `_ci_col`/duckdb_columns — в коде (30cf7d7).

## Следующий шаг (по приоритету)

1. **Зелёный такт okna:** solr + embed; карантин 195 — ждать seq196+ с движениями f7.
2. **K8**: скилл `ubuntu/openclaw/skills/ask-decomposer/` → контур бота
   (/home/undebot/.openclaw, правит root на окне) → приёмка compare 8/8.
   Compare = AB_CALENDAR_AXIS: помни, рабочие-дни-строки corpus-блокированы
   (search_meta пуст, такт мёртв) — приёмка честно частичная.
2. **К2-остаток**: мера-развилка при недосчитываемой ветке → исход B с лидером
   (сейчас clarify вместо цифр на «календарная неделя»/«с 1 по 15»; эталоны
   47 082 166 / 208 367 025 живым SQL). Агентом, не руками.
3. **Скорость С4-вопроса**: «позиций не продаётся» >120 с — таймауты curl;
   посмотреть латентность (В1-класс).
4. Спорные эталоны ambiguous (№5/№8/№12/№11/№4-игла-руб-при-лее) — вопрос
   владельцу набора, не подгонка.
5. c5-перенос остальных слов — ТОЛЬКО механизмом с диффом живых слов (§3.99).

## Механика дня (проверено живьём)

- **Контур бота 29.08 (всё проверено живьём, разбор — INSTALL_LOG §29.08)**:
  рабочий фронт — **веб** baulogistic → `http://10.3.1.11:18801/v1` (LXD proxy
  на хосте → web-шлюз okna). **Телеграм :18800 остановлен+disable (решение
  владельца)**, возврат `systemctl --user enable --now openclaw-gateway`.
  Web-шлюз: `--bind lan` + `gateway.http.endpoints.chatCompletions.enabled=true`
  (❗ НЕ `gateway.http.enabled` — 78/CONFIG); дефолтный агент — явный
  `{"id":"main","default":true}` в `agents.list`; auth main — per-agent sqlite
  (копируется из основного профиля); токен = ключ морды. Память OpenClaw —
  наш эмбеддер по домену `http://gpu-erw.timpul.pro:8000/v1`
  (Qwen3-Embedding-**4B**, ключ `/etc/1c-embed.env`). verify-плагин ставится
  `npm pack` → `openclaw plugins install npm-pack:<tgz> --force` в каждый
  профиль (29.08 отсутствовал у обоих с 23.08 — переустановлен).
  Тяжёлые вопросы веб-чата — до ~3 мин (С4-класс, отчёт
  `docs/drafts/s4-latency-2026-08-29.md`).
- **Сеть окно/фронт (зафиксировано 29.08, полная схема —
  `ubuntu/open-webui/README.md` §«Сеть»)**: прод = контейнер **okna 10.10.10.12**
  на хосте gpu-1c (`gpu-erw.timpul.pro`, vSwitch-нога **10.3.1.11**, ssh снаружи
  `178.63.211.188:2202`); фронт baulogistic = 2.28.49.158 / 10.3.0.2. 🔴 10.3.0.4
  и 167.233.249.110 — мёртвые адреса старого бэкенда. Внутри okna: ask :8091
  loopback, не трогать.
- Стейджинг: systemd-run + EnvironmentFile-цепочка, ПОРТ — отдельным
  оверрайд-файлом ПОСЛЕДНИМ (EnvironmentFile перекрывает Environment=).
- Гейты коммита: add и commit РАЗНЫЕ вызовы Bash; граф — observation → sleep 3
  → add → commit. Замки: `python3 test_*.py` (pytest нет);
  test_fork_atom_aggregate живой-БД — на деве виснет.
- pkill -f по строке из своей ssh-команды убивает свою сессию — kill по pid из ss.
- Выкат ask: `bash /tmp/deploy-ask.sh` (восстановить по описанию в RUNBOOK,
  если исчез: md5-дифф → scp → atomic mv; сверка md5 z-файлов после).
- НЕ рестартовать :8091 во время скореров (дважды смешивал состояния прогонов).
- `search_meta` окна = только balance_registers + period_relative_forms:
  календарные/валютные фразы и карты отсутствуют — всё, что их читает,
  на этой базе no-op'ает (calendar_axis_unavailable_block и значения оси места).

## Что мешает

1. Такт/$metadata (агент 1.0.2) — держит К3, свежесть, corpus-половину К2,
   контур-24, живое действие календарного словаря. Отложено владельцем.
2. Скорость тяжёлых вопросов (С4 >120 с) на 27B.

## Рецептура К3 (когда агент Windows станет 1.1.3)

Собрать exe `windows/packet-agent/build.cmd` → залить в S3 (сейчас там 1.1.2 от
13.08!) → `upgrade-agent.cmd` на машине okna → агент увидит need_metadata=1 (уже
стоит) → kind=meta → apply напишет `/var/lib/serenedb/packet-meta/okna-1/$metadata`
→ такт `1c-serene-pipeline@postgres` оживёт → corpus_build §1-quint/§1-кватер
наполнят карты валют/календаря → проверка: accounting_currency_constant непуст,
amount_map≥1, calendar_day_basis_phrases непуст → перемерить ВСЁ (corpus сменится).

История дней — `progress.md`.
