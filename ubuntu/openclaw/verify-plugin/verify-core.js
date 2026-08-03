// verify-core — чистая (без зависимостей от OpenClaw SDK) логика анти-галлюцинационного
// гейта. Вынесена отдельно, чтобы гонять юнит-тестами оффлайн. index.js только подключает
// это к хукам движка. Принцип и политика описаны в index.js / OPENCLAW_BOT.md.

export const DEFAULTS = {
  toolName: "ask_1c", // (устар.) одиночное имя; ниже toolNames — список заземляемых инструментов
  toolNames: ["ask_1c", "report_1c"], // и факты braine, и числа отчётов SereneDB — эталон для сверки
  minDigits: 4, // без эталона: с какой длины токен считаем «фактом», а не болтовнёй
  minDigitsWithRef: 1, // ЕСТЬ эталон -> сверяем ВСЕ числа. Раньше порог 4 пропускал
  //   количества, штуки, проценты и дни: «продано 850 шт» не проверялось никогда,
  //   хотя эталон под рукой и сверить было чем.
  highRiskDigits: 5, // без эталона: с какой длины выдумка блокируется. Было 7 —
  //   пятизначные и шестизначные суммы («долг 45 000», «выручка 950 000») уходили
  //   клиенту из воздуха, без единого обращения к данным.
  // 🔴 МАРКЕРЫ — ПРОТОКОЛ МЕЖДУ КОДОМ И КОДОМ, и менять их можно ТОЛЬКО с обеими
  // сторонами разом. [замер 31.07] мост перевели на английские маркеры ради коробочности,
  // а здесь остались русские: `noData` и `clarify` не взвелись бы никогда, то есть правило
  // «сервис попросил уточнить — числом отвечать нельзя» молча отключилось бы, а сами
  // служебные пометки поехали бы клиенту. Ниже — те же строки, что шлёт `mcp_ask.py`.
  noDataMarker: "[NO DATA", // префикс маркера «нет данных» из моста
  clarifyMarker: "[CLARIFICATION NEEDED", // префикс маркера уточнения из `mcp_ask.py`
  // 🔴 СБОЙ СЕРВИСА ≠ ОТСУТСТВИЕ ДАННЫХ (п. 18). Мост шлёт его отдельным маркером
  // (`mcp_ask.py`, ERROR_REPLY), и до 02.08 гейт этого различия не знал: строка маркера
  // вырезалась как внутреннее, пустой остаток подменялся `noDataReply`, и человек слышал
  // «данных нет» там, где сервис просто не ответил. Хуже отказа: он уходит с пустой базой.
  serviceErrorMarker: "[SERVICE ERROR", // префикс маркера сбоя сервиса данных из моста
  requireDataTool: true, // ход без обращения к данным прогоняется моделью ещё раз
  // 🔴 ЧИСЛОВОЙ ГЕЙТ НА ПУТИ ЗАВЕРШЕНИЯ ХОДА, А НЕ ТОЛЬКО НА ДОСТАВКЕ.
  // [замер 03.08] по всему журналу шлюза (23.07 → 03.08): `after_tool_call` 239 вызовов,
  // `before_agent_finalize` 443, а `message_sending` — 1 и `message_received` — 1. То есть
  // три из пяти хуков гейта живут ТОЛЬКО на доставке в канал, и всё, что меряется
  // прогонщиком (`openclaw agent` без `--deliver`), идёт с выключенной числовой половиной
  // защиты. Один раз за одиннадцать дней — это не защита, а её видимость.
  // Здесь та же политика (`evaluate`, один источник правды) применяется на завершении хода:
  // заменить текст движок на этом хуке не даёт, но даёт потребовать ещё один проход модели
  // с точной инструкцией и обоснованным ответом в ней.
  verifyOnFinalize: true,
  // 🔴 ГРАНИЦА ТОГО, ЧТО УХОДИТ В МОДЕЛЬ. Обоснованный ответ кладётся в инструкцию
  // повторного прохода — значит он становится КОНТЕКСТОМ, а не заменой текста, как на
  // доставке. Без границы его размер растёт с числом строк и колонок выборки, а п. 19
  // контракта требует обратного: «то, что уходит, ограничено сверху и не растёт с размером
  // базы». Обрезка называется в самом тексте: молчаливая потеря запрещена (п. 13).
  groundedMaxChars: 2000,
  figureReviseReason: "A numeric fact in the answer is not grounded in the data tool result.",
  figureReviseInstruction:
    "Every figure you state MUST come from the data tool result for this turn. Rewrite the "
    + "answer using only the grounded answer below; do not add, round, recompute or invent "
    + "any number. If the grounded answer says there is no data, say exactly that and give "
    + "no figures.",
  // Тексты — для МОДЕЛИ, не для человека, поэтому по-английски и без предметных примеров:
  // продукт коробочный, язык клиента заранее неизвестен.
  reviseReason: "This turn ended without consulting the company data tool.",
  reviseInstruction:
    "If the user's message is about company data, you MUST call the data tool before " +
    "answering or before asking any clarifying question: the options you offer have to come " +
    "from this database, not from general knowledge. If the message is not about company " +
    "data, reply exactly as you did.",
  // ⚠ ЭТИ ТРИ СТРОКИ ВИДИТ ЧЕЛОВЕК, и они заданы по-русски — известный остаток
  // неуниверсальности (продукт коробочный, язык клиента заранее неизвестен). Держатся
  // настройкой плагина, а не константой в коде, чтобы их можно было задать под язык
  // установки; вынести их в данные — отдельная работа, записана в `BOXED_BLOCKERS.md`.
  noDataReply: "К сожалению, по этому вопросу у меня нет данных в системе.",
  serviceErrorReply: "Сейчас не могу получить данные из системы: сервис данных не отвечает. "
    + "Повторите вопрос, пожалуйста, чуть позже.",
  // 🔴 ЗАМЕНА ВМЕСТО ТИШИНЫ. Раньше здесь был отказ от доставки (`cancel`), и человек
  // видел, что бот просто промолчал: ни ответа, ни причины. Контракт (п. 21) требует
  // обратного — ответ обязан дойти; выдуманное число при этом уйти не должно (п. 12).
  // Поэтому сообщение не отменяется, а заменяется честной строкой.
  unverifiedReply: "Не могу подтвердить это число по данным системы, поэтому не называю его. "
    + "Спросите ещё раз — я посмотрю в данных.",
  refTtlMs: 10 * 60 * 1000, // сколько держать эталон хода в памяти
  debug: false, // console.log решения гейта (для диагностики)
  stripInternal: true, // детерминированно резать внутреннее (SQL/пути/маркеры) из исходящего — КОДОМ
};

// числовой токен = группы цифр, соединённые ОДИНОЧНЫМ разделителем тысяч/десятых
// (7 727 406 020, 1 234,56, 1.000.000). Разделитель засчитывается только если сразу за
// ним снова идут цифры, поэтому список «5, 10, 15» не слипается в один токен.
// Класс разделителей: обычный пробел, NBSP ( ), узкие пробелы ( ,  ), точка, запятая.
// Разделителем внутри числа бывает и ДЕФИС: «8-999-123-45-67», «40702-81090-00000».
// Без него выдуманные счета и телефоны распадались на короткие токены и проходили
// порог highRiskDigits — проверено прогоном.
const NUM_TOKEN_RE = new RegExp("\\d+(?:[ \\u00a0\\u202f\\u2009.,-]\\d+)*", "g");

export function numericTokens(text, minDigits) {
  const out = new Set();
  const found = String(text).match(NUM_TOKEN_RE);
  if (!found) return out;
  for (const raw of found) {
    const d = raw.replace(/\D/g, "");
    if (d.length >= minDigits) out.add(d);
  }
  return out;
}

export function digitBlob(text) {
  return String(text).replace(/\D/g, "");
}

// MCP-инструмент проецируется боту как "<server>__ask_1c" (напр. second-brain__ask_1c).
// Матчим по суффиксу — конфиг-нейтрально, имя MCP-сервера может быть любым.
export function toolMatches(name, want) {
  if (!name || !want) return false;
  return name === want || name.endsWith("__" + want) || name.endsWith(":" + want) || name.endsWith("." + want);
}

// матч против списка (ask_1c + report_1c и т.п.) — оба инструмента дают эталонные числа
export function toolMatchesAny(name, wants) {
  return (wants || []).some((w) => toolMatches(name, w));
}

// Детерминированная зачистка ВНУТРЕННЕГО из исходящего сообщения — КОДОМ, не промтом.
// Режем НАШИ известные форматы (это не открытая классификация, а точная замена):
// SQL-запросы, серверные пути, наши служебные маркеры/инструкции.
const LEAK_LINE_RES = [
  /^.*\[ГРАФИК-ФАЙЛ:[^\]]*\].*$/gim, // маркер файла-графика
  /^\s*\(\s*Отправь этот файл[\s\S]*?\)\s*$/gim, // инструкция про отправку файла
  /^.*Attachment:\s*\/\S+.*$/gim, // CLI-строка вложения с путём
  /^.*Трактовк[аи]\s*\(SQL\):.*$/gim, // «Трактовка (SQL): ...»
  // Русские варианты оставлены: их всё ещё шлёт отчётный слой. Английские — новые, из моста.
  // 🔴 СПИСОК — ВТОРАЯ ПОЛОВИНА ПРОТОКОЛА С МОСТОМ. `FIGURES` и `PARTIAL` заведены 02.08
  // вместе с ними в `mcp_ask.py`: это служебные заголовки блоков для МОДЕЛИ, и если бот
  // перескажет их дословно, они уйдут человеку. Добавлять сюда обязательно тем же заходом,
  // что и в мост, — иначе новый маркер утекает клиенту молча.
  /^.*\[(?:НЕТ ДАННЫХ|ОТЧЁТ НЕ ВЫПОЛНЕН|ОШИБКА|NO DATA|CLARIFICATION NEEDED|SERVICE ERROR|FIGURES|PARTIAL)[^\]]*\].*$/gim,
];
// 🔴 ВНУТРЕННИЕ ИМЕНА ИСТОЧНИКОВ ИЗ БЛОКА ВАРИАНТОВ. Мост собирает уточнение машинным
// форматом `- <метка> | measure=<величина> | focus=<src_table>` (`mcp_ask.py`), где
// `focus` — имя таблицы витрины (`Document_РеализацияТоваровУслуг`). Модели оно нужно
// дословно, чтобы позвать инструмент повторно, а человеку — нет: до 02.08 весь блок
// уходил клиенту как есть. Правило стоит ОТДЕЛЬНО от списка выше не для красоты: там
// замена пустая, а здесь строка не удаляется, а укорачивается — метку варианта человек
// обязан видеть, иначе выбирать ему будет не из чего.
//   «- Реализация товаров | measure=Сумма | focus=Document_…» → «- Реализация товаров»
const OPTION_TAIL_RE = /^([ \t]*[-*][ \t]+.*?)[ \t]*\|[ \t]*(?:measure|focus)=.*$/gim;
// 🔴 SQL РЕЖЕТСЯ ПО ФОРМЕ ЗАПРОСА, А НЕ ПО ДВУМ СЛОВАМ. Прежнее правило
// (`WITH|SELECT … FROM …` до пустой строки) срабатывало на живой речи: [замер 02.08]
// «We started with 3 suppliers from the north region. That is all.» → «We started» —
// остаток абзаца исчезал молча. Английский текст ответа на чужой базе — это норма, а не
// край: `stripInternal` обязан резать НАШИ форматы, а не всё, что похоже на них словами.
const SQL_CAND_RE = /\b(?:WITH|SELECT)\b[\s\S]*?\bFROM\b[\s\S]*?(?=\n\s*\n|$)/gi;
// Второй признак — то, чего в обычной фразе не бывает: служебное слово запроса,
// звёздочка отбора, перечисление колонок через запятую или точка с запятой в конце.
const SQL_KEYWORD_RE = /\b(?:WHERE|GROUP\s+BY|ORDER\s+BY|LEFT\s+JOIN|INNER\s+JOIN|JOIN|HAVING|LIMIT|OFFSET|UNION|DISTINCT|COUNT\s*\(|SUM\s*\(|AVG\s*\(|MIN\s*\(|MAX\s*\()/i;
function looksLikeSql(span) {
  const s = String(span);
  // Одного `WITH … FROM` мало: у настоящего запроса всегда есть связка SELECT … FROM
  // (в том числе внутри CTE). Именно её отсутствие и отличает живую речь.
  if (!/\bSELECT\b[\s\S]*?\bFROM\b/i.test(s)) return false;
  return SQL_KEYWORD_RE.test(s)
    || /\bSELECT\s+\*/i.test(s)                       // SELECT * FROM …
    || /\bSELECT\b[^\n]*,[^\n]*\bFROM\b/i.test(s)     // перечисление колонок через запятую
    || /;\s*$/.test(s.trim());                        // запрос закрыт точкой с запятой
}
const PATH_RE = /\/(?:home|var|opt|etc|tmp|usr|root)\/[^\s'")\]]+/gi; // абсолютные серверные пути

export function stripInternal(text) {
  if (!text) return text;
  let t = String(text);
  for (const re of LEAK_LINE_RES) t = t.replace(re, "");
  t = t.replace(OPTION_TAIL_RE, "$1"); // не удаление строки, а обрезка машинного хвоста
  t = t.replace(SQL_CAND_RE, (m) => (looksLikeSql(m) ? "" : m));
  t = t.replace(PATH_RE, "");
  return t
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

// достаём читаемый текст из результата MCP-инструмента произвольной формы
export function extractText(result) {
  if (result == null) return "";
  if (typeof result === "string") return result;
  if (typeof result === "number" || typeof result === "boolean") return String(result);
  if (Array.isArray(result)) return result.map(extractText).filter(Boolean).join("\n");
  if (typeof result === "object") {
    const o = result;
    if (typeof o.text === "string") return o.text;
    if (Array.isArray(o.content)) return o.content.map(extractText).filter(Boolean).join("\n");
    for (const k of ["result", "value", "data", "output", "message"]) {
      if (o[k] != null) {
        const t = extractText(o[k]);
        if (t) return t;
      }
    }
    try {
      return JSON.stringify(o);
    } catch {
      return "";
    }
  }
  return "";
}

// объединить эталон хода (несколько вызовов ask_1c за ход)
// 🔴 УТОЧНЕНИЕ ОТ СЕРВИСА ДАННЫХ — ЭТО ЗАПРЕТ ОТВЕЧАТЬ ЧИСЛОМ.
// Когда `serene_ask` не уверен, какая запись имеется в виду, он возвращает НЕ ответ, а
// уточняющий вопрос с вариантами. Бот обязан задать этот вопрос человеку, а не отвечать
// самому. Признак — маркер, который ставит мост `mcp_ask.py`; текст его настраивается,
// поэтому сверяем по префиксу из конфигурации, а не по словам.
export function isClarify(text, marker) {
  return String(text || "").includes(marker || "[НУЖНО УТОЧНЕНИЕ");
}

// 🔴 СБОЙ СЕРВИСА ДАННЫХ — ЭТО НЕ «ДАННЫХ НЕТ» (п. 18 контракта). Признак нужен ДО
// зачистки: после неё строка маркера уже вырезана, остаток пуст, и отличить сбой от
// пустого ответа нечем — ровно так сбой и превращался в «нет данных».
export function isServiceError(text, marker) {
  return String(text || "").includes(marker || DEFAULTS.serviceErrorMarker);
}

// Разметка списка — не факт о данных. «1.», «2.» в начале строки нумеруют пункты, и при
// наличии эталона они попадали в сверку наравне с суммами: любой перечисленный ответ
// («1. Товар А») объявлялся необоснованным и живой текст бота подменялся машинным.
// Убираем ТОЛЬКО ведущий маркер строки — само содержимое пункта проверяется как обычно.
const LIST_MARKER_RE = /^[ \t]*\d+[.)][ \t]+/gm;
export function withoutListMarkers(text) {
  return String(text == null ? "" : text).replace(LIST_MARKER_RE, "");
}

export function mergeRef(prev, text, nowMs, noDataMarker, clarifyMarker, serviceErrorMarker) {
  const digits = numericTokens(text, 1); // все цифровые токены эталона; порог применяем на исходящем
  const blob = digitBlob(text);
  const isND = String(text).includes(noDataMarker);
  const isCl = isClarify(text, clarifyMarker);
  const isSE = isServiceError(text, serviceErrorMarker);
  if (!prev) {
    return { at: nowMs, text: String(text), digits, blob, noData: isND, clarify: isCl, svcError: isSE };
  }
  for (const d of digits) prev.digits.add(d);
  return {
    at: nowMs,
    text: prev.text ? prev.text + "\n" + String(text) : String(text),
    digits: prev.digits,
    blob: prev.blob + blob,
    noData: prev.noData && isND,
    // хоть один инструмент попросил уточнить — ход считается уточняющим
    clarify: Boolean(prev.clarify || isCl),
    // хоть один вызов упал — про сбой надо сказать честно, а не выдать за пустоту (п. 18)
    svcError: Boolean(prev.svcError || isSE),
  };
}

// токен обоснован, если он ТОЧНО присутствует среди числовых токенов эталона braine ИЛИ ввода
// пользователя. НЕ по подстроке blob: короткое выдуманное число (2740) может оказаться подстрокой
// длинного обоснованного (7727406020) или склейки нескольких — это ложное заземление (галлюцинация
// проходит). Разную группировку тысяч (7 727 406 020 == 7727406020) покрывает сам токенайзер: обе
// стороны нормализуются в один и тот же токен, поэтому точного сравнения по digits достаточно.
export function isGrounded(token, ref, inb, cfg) {
  if (ref && ref.digits.has(token)) return true;
  // Числа из сообщения пользователя заземляют ответ ТОЛЬКО когда эталона нет вовсе
  // (обычный разговор, эхо номера заказа). Если эталон есть, они белым списком не
  // работают: иначе достаточно упомянуть число в вопросе, чтобы бот мог назвать его
  // фактом из 1С. То же отмывание закрыто на стороне serene_ask.
  if (!ref && inb && inb.digits.has(token)) return true;
  return false;
}

// Обоснованный ответ, ограниченный сверху, — он уходит В МОДЕЛЬ (инструкцией повторного
// прохода), а не человеку. На доставке тот же текст ставится ЗАМЕНОЙ и в модель не идёт,
// поэтому границы там не нужно, а здесь нужна: п. 19 требует, чтобы уходящее в модель не
// росло с размером базы. Обрезка ГОВОРИТСЯ вслух (п. 13: молчаливая потеря — дефект), и
// сказана она по-английски, потому что читает её модель, а не человек.
export function boundedGrounded(text, cfg) {
  const c = { ...DEFAULTS, ...(cfg || {}) };
  const s = typeof text === "string" ? text : "";
  if (!s) return "";
  const lim = c.groundedMaxChars;
  if (!(lim > 0) || s.length <= lim) return s;
  return s.slice(0, lim) + "\n[truncated: the grounded answer is longer than "
       + lim + " characters; state only the figures shown above]";
}

// РЕШЕНИЕ НА ЗАВЕРШЕНИИ ХОДА — чистой функцией, чтобы проверялось оффлайн.
// В index.js остаётся только перевод этого решения в форму движка (`revise`/`finalize`):
// правило и его проверка не должны жить в разных местах — на двух разошедшихся копиях
// одного правила проект уже обжигался (`HOW_NOT_TO`, разбор про две копии проверки).
//
// `haveRef` — спрашивали ли данные за ЭТОТ ход (сверка runId делается вызывающим).
// Возвращает: {action:"pass"|"revise", why, reason, instruction}.
export function finalizeDecision(answer, ref, inb, cfg, haveRef) {
  const c = { ...DEFAULTS, ...(cfg || {}) };
  if (!haveRef) {
    if (c.requireDataTool === false) return { action: "pass", why: "require-data-tool-off" };
    return { action: "revise", why: "no-data-tool", reason: c.reviseReason,
             instruction: c.reviseInstruction, idempotencyKey: "require-data-tool" };
  }
  if (c.verifyOnFinalize === false) return { action: "pass", why: "verify-on-finalize-off" };
  if (!answer) return { action: "pass", why: "no-answer-text" };
  const d = evaluate(answer, ref, inb, c);
  if (d.action === "allow") return { action: "pass", why: "figures-ok" };
  const grounded = boundedGrounded(d.action === "replace" ? d.content : "", c);
  return {
    action: "revise", why: "figures", reason: c.figureReviseReason,
    instruction: grounded ? c.figureReviseInstruction + "\n\nGrounded answer:\n" + grounded
                          : c.figureReviseInstruction,
    idempotencyKey: "verify-figures",
  };
}

// Главное решение по исходящему тексту. Возвращает одно из:
//   { action: "allow" }                     — отдать «живой» ответ как есть
//   { action: "replace", content: str }     — заменить (обоснованным ответом braine / «нет данных»)
//   { action: "cancel", reason: str }       — не отправлять вовсе
export function evaluate(content, ref, inb, cfg) {
  const c = { ...DEFAULTS, ...(cfg || {}) };
  if (!content) return { action: "allow" };

  // С эталоном сверяем всё, без эталона — только то, что похоже на факт. Нумерация
  // пунктов снимается до токенизации: она разметка, а не число из данных (F287).
  const tokens = [...numericTokens(withoutListMarkers(content), ref ? c.minDigitsWithRef : c.minDigits)];
  if (tokens.length === 0) return { action: "allow" }; // нет жёстких фактов — не трогаем

  const ungrounded = tokens.filter((t) => !isGrounded(t, ref, inb, c));
  if (ungrounded.length === 0) return { action: "allow" }; // все факты обоснованы

  if (!ref) {
    // 🔴 ЗА ЭТОТ ХОД К ДАННЫМ НЕ ОБРАЩАЛИСЬ ВОВСЕ. [замер 30.07] бот отвечал и переспрашивал
    // при `инструменты: None` — то есть из общих знаний о предметной области, а не из ЭТОЙ
    // базы. На другой базе тот же ответ был бы выдумкой. Указание владельца: правила держатся
    // инструментами, а не промтом, — поэтому запрет стоит здесь, а не в инструкции боту.
    //
    // Порог `minDigits` отделяет факт от речи: «около 23 часов», «1.», «2.» — не факты о
    // данных. Всё, что длиннее и не названо человеком, без обращения к данным не проходит.
    const risky = ungrounded.filter((t) => t.length >= c.highRiskDigits);
    if (risky.length) {
      // 🔴 НЕ `cancel`: отмена доставки = тишина в мессенджере, взамен не уходит ничего.
      // [замер 02.08] «Долг составляет 45 000 рублей.» без обращения к данным → человек
      // видел, что бот промолчал, и не мог отличить это от поломки. Контракт (п. 21)
      // требует, чтобы ответ дошёл; выдуманное число при этом остаётся запрещённым
      // (п. 12), поэтому уходит не оно, а честная строка о том, что число не подтверждено.
      return { action: "replace", content: c.unverifiedReply,
               reason: "числовой факт без обращения к данным (" + risky.join(",") + ")" };
    }
    // 🔴 Я ПОПРОБОВАЛ БЛОКИРОВАТЬ ЛЮБОЕ ЧИСЛО БЕЗ ОБРАЩЕНИЯ К ДАННЫМ — И ТЕСТ ЭТО ОТВЁРГ,
    // справедливо: «в 2026 году» — год в речи, а не факт о данных. Отличить их по длине
    // нельзя, поэтому правило осталось прежним: блокируется только заведомо фактовое
    // (`highRiskDigits`). Случай «бот переспросил, не обратившись к данным» этим гейтом НЕ
    // ловится — там чисел нет вовсе; для него нужен признак надёжнее текста.
    return { action: "allow" };
  }

  // 🔴 СЕРВИС ПОПРОСИЛ УТОЧНИТЬ — ЧИСЛО В ОТВЕТЕ ЗАПРЕЩЕНО. Иначе бот, получив вопрос
  // «какая из записей имеется в виду», отвечает своим числом и обходит уточнение. Отдаём
  // человеку сам вопрос сервиса — он уже содержит варианты, собранные из данных.
  if (ref.clarify) {
    return { action: "replace", content: ref.text, reason: "сервис данных запросил уточнение" };
  }

  // 🔴 СЕРВИС ДАННЫХ УПАЛ — ГОВОРИМ ПРО СБОЙ, А НЕ ПРО ПУСТУЮ БАЗУ (п. 18). Проверяется
  // ДО ветки «нет данных»: у сбоя `noData` не взведён, поэтому его дословный текст уходил
  // в замену, зачистка вырезала строку маркера целиком, а пустой остаток подменялся
  // фразой «данных нет». Клиент получал самый вредный из возможных ответов: уверенное
  // «таких данных у нас нет» в момент, когда мы попросту не смогли посмотреть.
  if (ref.svcError) {
    return { action: "replace", content: c.serviceErrorReply, reason: "сбой сервиса данных" };
  }
  // эталон был. braine нашёл данные -> заменяем на его дословный (обоснованный) ответ.
  if (!ref.noData && ref.text) {
    return { action: "replace", content: ref.text };
  }
  // braine ответил «нет данных», а бот назвал числа -> безопасная строка.
  return { action: "replace", content: c.noDataReply };
}
