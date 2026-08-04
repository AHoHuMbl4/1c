// Оффлайн-тест чистой логики verify-core (node --test не нужен; простые assert).
// Запуск: node test-verify.mjs
import assert from "node:assert";
import { DEFAULTS, boundedGrounded, evaluate, finalizeDecision, isServiceError, mergeRef, numericTokens, selfFetchNeeded, stripInternal, toolMatches, toolMatchesAny } from "./verify-core.js";

const ND = DEFAULTS.noDataMarker;
const ref = (text) => mergeRef(null, text, 1000, ND);
const inbound = (text) => ({ at: 1000, digits: numericTokens(text, 1), blob: String(text).replace(/\D/g, "") });

let pass = 0;
const t = (name, fn) => {
  fn();
  pass++;
  console.log("ok  -", name);
};

// --- toolMatches: MCP проецирует инструмент как <server>__ask_1c ---
t("toolMatches: точное имя", () => assert.ok(toolMatches("ask_1c", "ask_1c")));
t("toolMatches: MCP-неймспейс second-brain__ask_1c", () => assert.ok(toolMatches("second-brain__ask_1c", "ask_1c")));
t("toolMatches: чужой инструмент не матчится", () => assert.ok(!toolMatches("memory_search", "ask_1c")));
t("toolMatches: не ловим ложный суффикс без разделителя", () => assert.ok(!toolMatches("myask_1c", "ask_1c")));
t("toolMatchesAny: report_1c из списка (MCP-неймспейс)", () =>
  assert.ok(toolMatchesAny("second-brain-reports__report_1c", ["ask_1c", "report_1c"])));
t("toolMatchesAny: ask_1c из списка", () => assert.ok(toolMatchesAny("second-brain__ask_1c", ["ask_1c", "report_1c"])));
t("toolMatchesAny: чужой не матчится", () => assert.ok(!toolMatchesAny("memory_search", ["ask_1c", "report_1c"])));

// --- токенайзер ---
t("ИНН одним числом", () => assert.ok(numericTokens("ИНН 7727406020", 4).has("7727406020")));
t("ИНН с пробелами-разделителями склеивается", () =>
  assert.ok(numericTokens("ИНН 7 727 406 020", 4).has("7727406020")));
t("сумма 1 234,56 -> 123456", () => assert.ok(numericTokens("итого 1 234,56", 4).has("123456")));
t("список 5, 10, 15 НЕ слипается", () => {
  const s = numericTokens("числа: 5, 10, 15", 1);
  assert.deepStrictEqual([...s].sort(), ["10", "15", "5"]);
});
t("100% не проходит порог minDigits=4", () => assert.strictEqual(numericTokens("на 100% уверен", 4).size, 0));

// --- evaluate: обоснованные факты пропускаем ---
t("faithful: ИНН из эталона -> allow", () => {
  const d = evaluate("Контрагент с ИНН 7727406020.", ref("МИ ФНС, ИНН 7727406020"), null, {});
  assert.strictEqual(d.action, "allow");
});
t("faithful: другой формат группировки -> allow (blob substring)", () => {
  const d = evaluate("ИНН 7 727 406 020", ref("inn=7727406020"), null, {});
  assert.strictEqual(d.action, "allow");
});

// --- evaluate: выдуманный факт при живом эталоне -> замена на эталон ---
t("hallucinated ИНН при эталоне без него -> replace на текст braine", () => {
  const r = ref("Казначейство России");
  const d = evaluate("Казначейство России, ИНН 1234567890.", r, null, {});
  assert.strictEqual(d.action, "replace");
  assert.strictEqual(d.content, "Казначейство России");
});

// --- evaluate: нет эталона + длинное «фактовое» число -> честная замена (НЕ тишина) ---
t("нет эталона + выдуманный ИНН -> replace на unverifiedReply", () => {
  const d = evaluate("Его ИНН 1234567890, точно.", null, null, {});
  assert.strictEqual(d.action, "replace");
  assert.strictEqual(d.content, DEFAULTS.unverifiedReply);
});
t("нет эталона + короткое число (год) -> allow", () => {
  const d = evaluate("Это было в 2026 году.", null, null, {});
  assert.strictEqual(d.action, "allow"); // 2026 (len4) не high-risk, эталона нет -> не блокируем
});
t("нет эталона + нет чисел -> allow (small talk)", () => {
  assert.strictEqual(evaluate("Здравствуйте! Рад помочь.", null, null, {}).action, "allow");
});

// --- evaluate: эхо числа пользователя не считается галлюцинацией ---
t("эхо номера заказа пользователя -> allow", () => {
  const d = evaluate("Ваш заказ 1234567 принят.", null, inbound("оформи заказ 1234567"), {});
  assert.strictEqual(d.action, "allow");
});

// --- evaluate: braine сказал «нет данных», а бот назвал число -> безопасная строка ---
t("no_data эталон + бот выдал число -> replace на noDataReply", () => {
  const r = ref(ND + " по этому вопросу]");
  const d = evaluate("У вас долг 1500000 рублей.", r, null, {});
  assert.strictEqual(d.action, "replace");
  assert.strictEqual(d.content, DEFAULTS.noDataReply);
});

// --- mergeRef: несколько вызовов ask_1c за ход сливаются ---
t("mergeRef объединяет цифры двух вызовов", () => {
  let r = mergeRef(null, "ИНН 7727406020", 1000, ND);
  r = mergeRef(r, "счёт 40702810000000012345", 1001, ND);
  assert.ok(r.digits.has("7727406020"));
  assert.ok(r.blob.includes("40702810000000012345"));
  assert.strictEqual(r.noData, false);
});

// --- конфиг-нейтральность: minDigits=3 строже ловит 3-значную цену ---
t("minDigits=3 ловит выдуманную 3-значную цену при эталоне", () => {
  const d = evaluate("Цена 450 рублей.", ref("Товар без цены"), null, { minDigits: 3 });
  assert.strictEqual(d.action, "replace");
});

// --- stripInternal: детерминированная зачистка внутреннего (анти-слив кодом) ---
t("strip: убирает «Трактовка (SQL): ...»", () => {
  const out = stripInternal("Топ городов\n| Москва | 630 |\nТрактовка (SQL): SELECT city FROM banks GROUP BY city");
  assert.ok(!/SQL|SELECT|FROM/i.test(out));
  assert.ok(out.includes("Москва"));
});
t("strip: убирает маркер [ГРАФИК-ФАЙЛ: ...]", () => {
  const out = stripInternal("Вот отчёт.\n[ГРАФИК-ФАЙЛ: /home/undebot/.openclaw/workspace/charts/c.png]\nГотово.");
  assert.ok(!out.includes("ГРАФИК-ФАЙЛ"));
  assert.ok(!out.includes("/home/"));
});
t("strip: убирает Attachment и серверный путь", () => {
  const out = stripInternal("Готово.\nAttachment: /home/undebot/.openclaw/workspace/charts/x.png");
  assert.ok(!out.includes("Attachment"));
  assert.ok(!/\/home\//.test(out));
});
t("strip: голый SQL вырезается", () => {
  assert.strictEqual(stripInternal("SELECT count(*) FROM banks").trim(), "");
});
t("strip: внутренний маркер [НЕТ ДАННЫХ ...] убирается", () => {
  const out = stripInternal("[НЕТ ДАННЫХ во втором мозге] — сообщи клиенту");
  assert.strictEqual(out.trim(), "");
});
t("strip: чистый текст не трогается", () => {
  const s = "Здравствуйте! Чем помочь по данным компании?";
  assert.strictEqual(stripInternal(s), s);
});
t("strip: путь /var|/opt тоже режется", () => {
  assert.ok(!/\/(var|opt)\//.test(stripInternal("файл /var/lib/serenedb-charts/a.png и /opt/x")));
});

// === ИЗОЩРЁННЫЕ (adversarial) ===

// substring-заземление: короткое выдуманное число НЕ должно проходить как подстрока длинного обоснованного
t("adv: 2740 ⊂ 7727406020, но выдумано -> replace (не заземлять по подстроке)", () => {
  const d = evaluate("Прибыль 2740 тыс.", ref("ИНН 7727406020"), null, {});
  assert.strictEqual(d.action, "replace");
});
t("adv: cross-number 3456 из '1234'+'5678' -> replace", () => {
  let r = mergeRef(null, "код 1234", 1000, ND);
  r = mergeRef(r, "счёт 5678", 1001, ND);
  assert.strictEqual(evaluate("Значение 3456.", r, null, {}).action, "replace");
});
t("adv: эхо-подстрока номера юзера не спасает выдумку (2740 ⊂ 7727406020) -> replace", () => {
  const d = evaluate("Сумма 2740.", ref("текст без числа"), inbound("проверь 7727406020"), {});
  assert.strictEqual(d.action, "replace");
});
// регресс: разная группировка тысяч ДОЛЖНА заземляться (через точный токен, не подстроку)
t("adv-regress: 7 727 406 020 == 7727406020 -> allow", () => {
  assert.strictEqual(evaluate("ИНН 7 727 406 020", ref("inn=7727406020"), null, {}).action, "allow");
});
// БЫЛО известной дырой: при пороге minDigits=4 короткие числа не сверялись вовсе —
// количества, штуки, проценты и дни уходили клиенту без проверки, хотя эталон был.
// Теперь при наличии эталона сверяются ВСЕ числа.
t("короткое число при эталоне ТОЖЕ сверяется -> replace", () => {
  assert.strictEqual(evaluate("В выборке 5 банков.", ref("таблица без пятёрки"), null, {}).action, "replace");
});
t("короткое число, которое ЕСТЬ в эталоне -> allow", () => {
  assert.strictEqual(evaluate("В выборке 5 банков.", ref("найдено 5 записей"), null, {}).action, "allow");
});
// без эталона порог остаётся: обычная реплика с годом или мелким числом не блокируется,
// но выдуманная сумма от пяти цифр — блокируется (было — только от семи).
t("без эталона: выдуманная сумма 45000 -> replace, а НЕ тишина", () => {
  const d = evaluate("Ваш долг 45 000 руб.", null, null, {});
  assert.strictEqual(d.action, "replace");
  assert.strictEqual(d.content, DEFAULTS.unverifiedReply);
  assert.notStrictEqual(d.action, "cancel"); // F222: отмена доставки = молчание в мессенджере
});
t("без эталона: год 2025 в реплике -> allow", () => {
  assert.strictEqual(evaluate("Отчёт за 2025 год готовлю.", null, null, {}).action, "allow");
});
// БЫЛА дыра «отмывание через вопрос»: достаточно упомянуть число в своём сообщении,
// и бот мог назвать его фактом из 1С. Теперь числа пользователя заземляют ответ только
// когда эталона нет вовсе (обычный разговор), а при наличии эталона — нет.
t("отмывание через вопрос при ЕСТЬ эталон -> replace", () => {
  const inb = { at: Date.now(), digits: new Set(["12500000"]), blob: "12 500 000" };
  assert.strictEqual(
    evaluate("Продажи составили 12 500 000 руб.", ref("итого 3615700"), inb, {}).action,
    "replace");
});
t("эхо числа пользователя БЕЗ эталона -> allow", () => {
  const inb = { at: Date.now(), digits: new Set(["12500000"]), blob: "12 500 000" };
  assert.strictEqual(
    evaluate("Да, 12 500 000 — это ваша цифра.", null, inb, {}).action, "allow");
});

// stripInternal — доп. рёбра
t("adv-strip: несколько серверных путей в одной строке", () => {
  const out = stripInternal("см. /etc/passwd и /root/.ssh/id_rsa и /var/lib/x");
  assert.ok(!/\/(etc|root|var)\//.test(out));
});
t("adv-strip: SQL в нижнем регистре тоже режется", () => {
  assert.strictEqual(stripInternal("select code from banks where city='x'").trim(), "");
});

// === Э4: целость ответа на пути к человеку (02.08) ===

// F217 — анти-слив резал живой текст: «with … from» в любом языке считалось SQL, и всё
// между ними исчезало молча. Ответ на английской базе — норма, а не край.
t("F217: живая английская фраза с with…from НЕ режется", () => {
  const s = "We started with 3 suppliers from the north region. That is all.";
  assert.strictEqual(stripInternal(s), s);
});
t("F217: живая фраза с select…from без формы запроса НЕ режется", () => {
  const s = "Please select an option from the list below.";
  assert.strictEqual(stripInternal(s), s);
});
t("F217: русский текст с латинскими with/from НЕ режется", () => {
  const out = stripInternal("Отбор шёл with учётом from поставщиков.\n\nВторой абзац.");
  assert.ok(out.includes("поставщиков"));
  assert.ok(out.includes("Второй абзац"));
});
t("F217-регресс: настоящий CTE всё ещё режется", () => {
  assert.strictEqual(
    stripInternal("WITH t AS (SELECT id, city FROM banks) SELECT count(*) FROM t").trim(), "");
});
t("F217-регресс: SELECT * FROM режется", () => {
  assert.strictEqual(stripInternal("SELECT * FROM search_corpus").trim(), "");
});

// F218 — блок вариантов уходил клиенту вместе с внутренними именами таблиц.
t("F218: из вариантов уходит метка, а внутреннее имя источника — нет", () => {
  const out = stripInternal(
    "Какой тип записи?\n\nOPTIONS:\n- Реализация товаров | focus=Document_РеализацияТоваровУслуг\n"
    + "- Возврат | measure=СуммаДокумента | focus=Document_ВозвратТоваров");
  assert.ok(!/focus=|measure=|Document_/.test(out), "внутренние имена не должны уходить клиенту");
  assert.ok(out.includes("Реализация товаров") && out.includes("Возврат"), "метки вариантов обязаны остаться");
});

// F220 — сбой сервиса данных превращался в «нет данных»: маркер вырезался, пустой
// остаток подменялся фразой про отсутствие данных.
t("F220: сбой сервиса отличается от «нет данных»", () => {
  const r = mergeRef(null, "[SERVICE ERROR: HTTP 503] Tell the user the data is unavailable.",
                     1000, ND, DEFAULTS.clarifyMarker, DEFAULTS.serviceErrorMarker);
  assert.strictEqual(r.svcError, true);
  assert.strictEqual(r.noData, false);
  const d = evaluate("У вас 12 345 документов.", r, null, {});
  assert.strictEqual(d.action, "replace");
  assert.strictEqual(d.content, DEFAULTS.serviceErrorReply);
  assert.notStrictEqual(d.content, DEFAULTS.noDataReply);
});
t("F220: маркер сбоя опознаётся до зачистки", () => {
  assert.ok(isServiceError("[SERVICE ERROR: HTTP 503] …", DEFAULTS.serviceErrorMarker));
  assert.ok(!isServiceError("[NO DATA] …", DEFAULTS.serviceErrorMarker));
  assert.strictEqual(stripInternal("[SERVICE ERROR: HTTP 503] …").trim(), ""); // сама строка по-прежнему режется
});

// F287 — нумерация списка считалась фактом, и живой ответ подменялся машинным.
t("F287: нумерация списка не считается фактом о данных", () => {
  const r = ref("Продано 850 шт на сумму 1 236 800 руб.");
  const d = evaluate("Итого:\n1. Товар А\n2. Товар Б\nВсего 850 шт на 1 236 800 руб.", r, null, {});
  assert.strictEqual(d.action, "allow");
});
// F248 — перечисление одной строкой: «Итого 850: 1) Товар А, 2) Товар Б». На стороне
// сервиса этот класс замерен (7 верных ответов из 44 вопросов отвергались только за
// нумерацию), здесь та же граница.
t("F248: перечисление внутри строки не считается фактом о данных", () => {
  const r = ref("Продано 850 шт.");
  const d = evaluate("Итого 850 шт: 1) Товар А, 2) Товар Б, 3) Товар В.", r, null, {});
  assert.strictEqual(d.action, "allow");
});
t("F248-регресс: длинный номер в середине строки разметкой НЕ считается", () => {
  const r = ref("Продано 850 шт.");
  const d = evaluate("Итого 850 шт: 103) выдумка.", r, null, {});
  assert.strictEqual(d.action, "replace");
});
t("F248-регресс: число после запятой без скобки сверяется как обычно", () => {
  const r = ref("Продано 850 шт.");
  const d = evaluate("Итого 850 шт, из них 47 просрочены.", r, null, {});
  assert.strictEqual(d.action, "replace");
});
t("F287-регресс: выдуманное число в пункте списка ловится по-прежнему", () => {
  const r = ref("Продано 850 шт.");
  const d = evaluate("1. Товар А — 4321 шт.", r, null, {});
  assert.strictEqual(d.action, "replace");
});
t("F287-регресс: короткое количество при эталоне сверяется (порог не поднят)", () => {
  assert.strictEqual(evaluate("В выборке 5 банков.", ref("таблица без пятёрки"), null, {}).action, "replace");
});

// --- ЗАВЕРШЕНИЕ ХОДА: числовой гейт на пути БЕЗ доставки в канал ---
// [замер 03.08] по журналу шлюза за 23.07-03.08: after_tool_call 239, before_agent_finalize
// 443, а message_sending — 1 и message_received — 1. Числовая половина гейта живёт на
// доставке, которой у `openclaw agent` нет, — значит на пути приёмки её не было вовсе.
// Эти случаи проверяют ровно то, что теперь она есть и на завершении хода.
t("finalize: данных не спрашивали — гоним модель заново (прежнее поведение цело)", () => {
  const d = finalizeDecision("Здравствуйте!", null, null, {}, false);
  assert.strictEqual(d.action, "revise");
  assert.strictEqual(d.why, "no-data-tool");
  assert.strictEqual(d.idempotencyKey, "require-data-tool");
});
t("finalize: обоснованные числа проходят", () => {
  const r = ref("Контрагентов: 155.");
  const d = finalizeDecision("У нас 155 контрагентов.", r, null, {}, true);
  assert.strictEqual(d.action, "pass");
  assert.strictEqual(d.why, "figures-ok");
});
t("🔴 finalize: НЕОБОСНОВАННОЕ число ловится БЕЗ доставки в канал", () => {
  const r = ref("Контрагентов: 155.");
  const d = finalizeDecision("У нас 4 217 контрагентов.", r, null, {}, true);
  assert.strictEqual(d.action, "revise");
  assert.strictEqual(d.why, "figures");
  assert.strictEqual(d.idempotencyKey, "verify-figures");
});
t("finalize: в инструкцию кладётся сам обоснованный ответ, а не «попробуй ещё раз»", () => {
  const r = ref("Контрагентов: 155.");
  const d = finalizeDecision("У нас 4 217 контрагентов.", r, null, {}, true);
  assert.ok(d.instruction.includes("Grounded answer:"), "инструкция обязана нести эталон");
  assert.ok(d.instruction.includes("155"), "в эталоне обязано быть верное число");
});
t("finalize: сервис попросил уточнить — число модели не проходит", () => {
  const r = mergeRef(null, "[CLARIFICATION NEEDED] Какой из складов?", 1000, ND,
                     DEFAULTS.clarifyMarker, DEFAULTS.serviceErrorMarker);
  const d = finalizeDecision("На складе 1 240 позиций.", r, null, {}, true);
  assert.strictEqual(d.action, "revise");
  assert.strictEqual(d.why, "figures");
});
t("finalize: сбой сервиса — тоже не проходит числом", () => {
  const r = mergeRef(null, "[SERVICE ERROR: HTTP 503] …", 1000, ND,
                     DEFAULTS.clarifyMarker, DEFAULTS.serviceErrorMarker);
  const d = finalizeDecision("Всего 12 345 документов.", r, null, {}, true);
  assert.strictEqual(d.action, "revise");
  assert.ok(d.instruction.includes(DEFAULTS.serviceErrorReply), "модели уходит строка про сбой, не про пустую базу");
});
// 🔴 ЧИСЛА ВОПРОСА ПРИ НАЛИЧИИ ЭТАЛОНА В БЕЛЫЙ СПИСОК НЕ ИДУТ — И ЭТО НАМЕРЕННО
// (`isGrounded`: иначе достаточно назвать число в вопросе, чтобы бот выдал его за факт из
// 1С). Здесь это закреплено тестом: на завершении хода решение обязано быть тем же, что и
// на доставке, — иначе прогонщик снова мерил бы не то, что уходит клиенту.
t("finalize: год из вопроса при наличии эталона НЕ заземляет (как и на доставке)", () => {
  const r = ref("Продаж за период: 272 документа.");
  const inb = inbound("Сколько продали в 2018 году?");
  const d = finalizeDecision("В 2018 году продаж 272 документа.", r, inb, {}, true);
  assert.strictEqual(d.action, "revise");
  assert.strictEqual(evaluate("В 2018 году продаж 272 документа.", r, inb, {}).action, "replace",
                     "доставка на том же входе тоже не пропускает — решения обязаны совпадать");
});
t("finalize: без эталона числа вопроса заземляют (и туда мы не доходим — ловит requireDataTool)", () => {
  const inb = inbound("Мой заказ 4517, что с ним?");
  assert.strictEqual(evaluate("Заказ 4517 в работе.", null, inb, {}).action, "allow");
  assert.strictEqual(finalizeDecision("Заказ 4517 в работе.", null, inb, {}, false).why, "no-data-tool");
});
// 🔴 п. 19: то, что уходит В МОДЕЛЬ, ограничено сверху и не растёт с размером базы.
// На доставке обоснованный ответ ставится ЗАМЕНОЙ и в модель не идёт; здесь он идёт
// инструкцией — значит обязан быть ограничен, а обрезка названа вслух (п. 13).
t("🔴 finalize: обоснованный ответ в инструкции ограничен сверху", () => {
  const long = "Позиций: 227. " + "строка выборки; ".repeat(4000);
  const r = ref(long);
  const d = finalizeDecision("У нас 9 999 999 позиций.", r, null, {}, true);
  assert.strictEqual(d.action, "revise");
  assert.ok(d.instruction.length < 3000, "инструкция не должна расти с размером выборки, длина " + d.instruction.length);
  assert.ok(d.instruction.includes("truncated"), "обрезка обязана быть названа");
});
t("finalize: короткий обоснованный ответ не режется и обрезкой не помечается", () => {
  const d = finalizeDecision("У нас 4 217 контрагентов.", ref("Контрагентов: 155."), null, {}, true);
  assert.ok(d.instruction.includes("155"));
  assert.ok(!d.instruction.includes("truncated"));
});
t("finalize: граница настраивается, ноль отключает обрезку", () => {
  const r = ref("Позиций: 227. " + "x".repeat(5000));
  assert.ok(finalizeDecision("9 999 999.", r, null, { groundedMaxChars: 100 }, true).instruction.length < 600);
  assert.ok(finalizeDecision("9 999 999.", r, null, { groundedMaxChars: 0 }, true).instruction.length > 5000);
});
t("finalize: выключатель verifyOnFinalize возвращает прежнее поведение", () => {
  const r = ref("Контрагентов: 155.");
  const d = finalizeDecision("У нас 4 217 контрагентов.", r, null, { verifyOnFinalize: false }, true);
  assert.strictEqual(d.action, "pass");
});
t("finalize: пустой текст ответа не трогаем", () => {
  const d = finalizeDecision("", ref("Контрагентов: 155."), null, {}, true);
  assert.strictEqual(d.action, "pass");
  assert.strictEqual(d.why, "no-answer-text");
});
t("finalize: политика ОДНА — решение совпадает с evaluate на том же входе", () => {
  const r = ref("Контрагентов: 155.");
  for (const text of ["У нас 155 контрагентов.", "У нас 4 217 контрагентов.", "Посмотрю в данных."]) {
    const viaEval = evaluate(text, r, null, {}).action === "allow" ? "pass" : "revise";
    assert.strictEqual(finalizeDecision(text, r, null, {}, true).action, viaEval, text);
  }
});

// --- свой поход за данными, когда модель не позвала инструмент -------------------
// Правило владельца 03.08: «промты не работают, это закон». Заставить модель движок не
// умеет, просить бесполезно ([замер] 5, 5, 4 из 10 после расширения описания инструмента),
// поэтому плагин идёт за данными сам. Здесь проверяется РЕШЕНИЕ идти — без сети.
const ASK = { ...DEFAULTS, askUrl: "http://127.0.0.1:8099/ask" };

t("свой поход: эталона нет, вопрос есть, адрес задан — идём", () => {
  assert.strictEqual(selfFetchNeeded(false, ASK, { text: "сколько продали" }), true);
});
t("свой поход: эталон за ход уже есть — не идём", () => {
  assert.strictEqual(selfFetchNeeded(true, ASK, { text: "сколько продали" }), false);
});
t("свой поход: адрес не задан — механизм выключен, поведение прежнее", () => {
  assert.strictEqual(selfFetchNeeded(false, DEFAULTS, { text: "сколько продали" }), false);
});
t("свой поход: вопроса нет — спрашивать нечего", () => {
  assert.strictEqual(selfFetchNeeded(false, ASK, { text: "   " }), false);
  assert.strictEqual(selfFetchNeeded(false, ASK, null), false);
});
t("свой поход: requireDataTool выключен — не идём", () => {
  assert.strictEqual(selfFetchNeeded(false, { ...ASK, requireDataTool: false }, { text: "x" }), false);
});
t("свой поход НЕ распознаёт «про данные ли вопрос» — это была бы догадка (п. 12)", () => {
  // Приветствие и деловой вопрос неразличимы по построению: цена ошибки — один лишний
  // запрос к своему же сервису, а не неверный ответ.
  assert.strictEqual(selfFetchNeeded(false, ASK, { text: "привет" }),
                     selfFetchNeeded(false, ASK, { text: "сколько у нас контрагентов" }));
});

t("свой поход: служебный прогон нашей же сборки (wiki-alias) пропускается", () => {
  // [замер 03.08] первая проба сработала именно на нём: шаг словаря к данным не обращается
  // по замыслу, и поход за данными жёг бы сервис на каждом таком ходе.
  assert.strictEqual(selfFetchNeeded(false, ASK, { text: "придумай слова" }, "agent:main:wiki-alias"), false);
  assert.strictEqual(selfFetchNeeded(false, ASK, { text: "сколько продали" }, "agent:main:telegram:direct:1"), true);
});

console.log(`\n${pass} tests passed`);
