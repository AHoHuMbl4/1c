// Оффлайн-тест чистой логики verify-core (node --test не нужен; простые assert).
// Запуск: node test-verify.mjs
import assert from "node:assert";
import { DEFAULTS, evaluate, mergeRef, numericTokens, stripInternal, toolMatches, toolMatchesAny } from "./verify-core.js";

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

// --- evaluate: нет эталона + длинное «фактовое» число -> cancel ---
t("нет эталона + выдуманный ИНН -> cancel", () => {
  const d = evaluate("Его ИНН 1234567890, точно.", null, null, {});
  assert.strictEqual(d.action, "cancel");
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

console.log(`\n${pass} tests passed`);
