// verify-core — чистая (без зависимостей от OpenClaw SDK) логика анти-галлюцинационного
// гейта. Вынесена отдельно, чтобы гонять юнит-тестами оффлайн. index.js только подключает
// это к хукам движка. Принцип и политика описаны в index.js / OPENCLAW_BOT.md.

export const DEFAULTS = {
  toolName: "ask_1c", // (устар.) одиночное имя; ниже toolNames — список заземляемых инструментов
  toolNames: ["ask_1c", "report_1c"], // и факты braine, и числа отчётов SereneDB — эталон для сверки
  minDigits: 4, // проверяем числовые токены длиной >= столько цифр (год/сумма/ИНН/код)
  highRiskDigits: 7, // токен такой длины (ИНН/счёт/телефон) без эталона -> жёсткий блок
  noDataMarker: "[НЕТ ДАННЫХ", // префикс маркера «нет данных» из mcp_braine
  noDataReply: "К сожалению, по этому вопросу у меня нет данных в системе.",
  refTtlMs: 10 * 60 * 1000, // сколько держать эталон хода в памяти
  debug: false, // console.log решения гейта (для диагностики)
  stripInternal: true, // детерминированно резать внутреннее (SQL/пути/маркеры) из исходящего — КОДОМ
};

// числовой токен = группы цифр, соединённые ОДИНОЧНЫМ разделителем тысяч/десятых
// (7 727 406 020, 1 234,56, 1.000.000). Разделитель засчитывается только если сразу за
// ним снова идут цифры, поэтому список «5, 10, 15» не слипается в один токен.
// Класс разделителей: обычный пробел, NBSP ( ), узкие пробелы ( ,  ), точка, запятая.
const NUM_TOKEN_RE = new RegExp("\\d+(?:[ \\u00a0\\u202f\\u2009.,]\\d+)*", "g");

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
export function mergeRef(prev, text, nowMs, noDataMarker) {
  const digits = numericTokens(text, 1); // все цифровые токены эталона; порог применяем на исходящем
  const blob = digitBlob(text);
  const isND = String(text).includes(noDataMarker);
  if (!prev) {
    return { at: nowMs, text: String(text), digits, blob, noData: isND };
  }
  for (const d of digits) prev.digits.add(d);
  return {
    at: nowMs,
    text: prev.text ? prev.text + "\n" + String(text) : String(text),
    digits: prev.digits,
    blob: prev.blob + blob,
    noData: prev.noData && isND,
  };
}

// токен обоснован, если он есть среди чисел эталона braine ИЛИ его дал сам пользователь
export function isGrounded(token, ref, inb) {
  if (ref && (ref.digits.has(token) || ref.blob.includes(token))) return true;
  if (inb && (inb.digits.has(token) || inb.blob.includes(token))) return true;
  return false;
}

// Главное решение по исходящему тексту. Возвращает одно из:
//   { action: "allow" }                     — отдать «живой» ответ как есть
//   { action: "replace", content: str }     — заменить (обоснованным ответом braine / «нет данных»)
//   { action: "cancel", reason: str }       — не отправлять вовсе
export function evaluate(content, ref, inb, cfg) {
  const c = { ...DEFAULTS, ...(cfg || {}) };
  if (!content) return { action: "allow" };

  const tokens = [...numericTokens(content, c.minDigits)];
  if (tokens.length === 0) return { action: "allow" }; // нет жёстких фактов — не трогаем

  const ungrounded = tokens.filter((t) => !isGrounded(t, ref, inb));
  if (ungrounded.length === 0) return { action: "allow" }; // все факты обоснованы

  if (!ref) {
    // за этот ход braine не спрашивали. Блокируем только явно «фактовые» длинные числа
    // (ИНН/счёт/телефон), которых пользователь не называл, — это почти наверняка выдумка.
    const risky = ungrounded.filter((t) => t.length >= c.highRiskDigits);
    if (risky.length) {
      return { action: "cancel", reason: "числовой факт без обращения к braine (" + risky.join(",") + ")" };
    }
    return { action: "allow" };
  }

  // эталон был. braine нашёл данные -> заменяем на его дословный (обоснованный) ответ.
  if (!ref.noData && ref.text) {
    return { action: "replace", content: ref.text };
  }
  // braine ответил «нет данных», а бот назвал числа -> безопасная строка.
  return { action: "replace", content: c.noDataReply };
}
