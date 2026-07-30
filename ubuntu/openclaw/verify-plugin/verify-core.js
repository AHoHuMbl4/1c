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
  noDataMarker: "[НЕТ ДАННЫХ", // префикс маркера «нет данных» из моста
  clarifyMarker: "[НУЖНО УТОЧНЕНИЕ", // префикс маркера уточнения из `mcp_ask.py`
  requireDataTool: true, // ход без обращения к данным прогоняется моделью ещё раз
  // Тексты — для МОДЕЛИ, не для человека, поэтому по-английски и без предметных примеров:
  // продукт коробочный, язык клиента заранее неизвестен.
  reviseReason: "This turn ended without consulting the company data tool.",
  reviseInstruction:
    "If the user's message is about company data, you MUST call the data tool before " +
    "answering or before asking any clarifying question: the options you offer have to come " +
    "from this database, not from general knowledge. If the message is not about company " +
    "data, reply exactly as you did.",
  noDataReply: "К сожалению, по этому вопросу у меня нет данных в системе.",
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
  /^.*\[(?:НЕТ ДАННЫХ|ОТЧЁТ НЕ ВЫПОЛНЕН|ОШИБКА)[^\]]*\].*$/gim, // внутренние маркеры-инструкции
];
const SQL_RE = /\b(?:WITH|SELECT)\b[\s\S]*?\bFROM\b[\s\S]*?(?=\n\s*\n|$)/gi; // SQL-запрос до пустой строки/конца
const PATH_RE = /\/(?:home|var|opt|etc|tmp|usr|root)\/[^\s'")\]]+/gi; // абсолютные серверные пути

export function stripInternal(text) {
  if (!text) return text;
  let t = String(text);
  for (const re of LEAK_LINE_RES) t = t.replace(re, "");
  t = t.replace(SQL_RE, "");
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

export function mergeRef(prev, text, nowMs, noDataMarker, clarifyMarker) {
  const digits = numericTokens(text, 1); // все цифровые токены эталона; порог применяем на исходящем
  const blob = digitBlob(text);
  const isND = String(text).includes(noDataMarker);
  const isCl = isClarify(text, clarifyMarker);
  if (!prev) {
    return { at: nowMs, text: String(text), digits, blob, noData: isND, clarify: isCl };
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

// Главное решение по исходящему тексту. Возвращает одно из:
//   { action: "allow" }                     — отдать «живой» ответ как есть
//   { action: "replace", content: str }     — заменить (обоснованным ответом braine / «нет данных»)
//   { action: "cancel", reason: str }       — не отправлять вовсе
export function evaluate(content, ref, inb, cfg) {
  const c = { ...DEFAULTS, ...(cfg || {}) };
  if (!content) return { action: "allow" };

  // С эталоном сверяем всё, без эталона — только то, что похоже на факт.
  const tokens = [...numericTokens(content, ref ? c.minDigitsWithRef : c.minDigits)];
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
      return { action: "cancel", reason: "числовой факт без обращения к данным (" + risky.join(",") + ")" };
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

  // эталон был. braine нашёл данные -> заменяем на его дословный (обоснованный) ответ.
  if (!ref.noData && ref.text) {
    return { action: "replace", content: ref.text };
  }
  // braine ответил «нет данных», а бот назвал числа -> безопасная строка.
  return { action: "replace", content: c.noDataReply };
}
