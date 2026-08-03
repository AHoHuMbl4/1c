// braine-verify — anti-hallucination gate for the OpenClaw bot layer.
//
// ПРИНЦИП (требование владельца): галлюцинации на слое OpenClaw режем КОДОМ, не промтом.
// braine (наш «второй мозг») уже гарантирует, что его ответ обоснован (гейты + цитаты).
// Риск — LLM бота (DeepSeek), «оживляя тон», может добавить/исказить факт.
//
// Механизм (детерминированный, как verify.py в braine, но на исходящем сообщении):
//   after_tool_call(ask_1c) -> захватываем эталонный ответ braine за ход (ключ = runId)
//   message_received        -> запоминаем числа из ввода пользователя (эхо его номера ≠ выдумка)
//   message_sending         -> каждый «жёсткий» числовой токен (ИНН/суммы/даты/цены/коды)
//                              обязан быть обоснован эталоном braine или вводом пользователя;
//                              необоснованное -> замена на дословный ответ braine /
//                              безопасную строку, в крайнем случае cancel.
//
// Требования движка (проверено на 2026.7.1, НЕ угадано):
//   • Хуки с доступом к переписке у НЕ-bundled плагина включаются только флагом
//     ВАЖНО: этот флаг нам НЕ нужен. Он гейтит только хуки диалога (llm_input,
//     llm_output, before_agent_run, agent_end и т.п.); наши четыре — after_tool_call,
//     message_received, message_sending, reply_payload_sending — в тот список не входят.
//     Раньше мы его выставляли, выдавая плагину лишнюю привилегию читать переписку.
//   • MCP-инструмент проецируется боту под ИМЕНЕМ СЕРВЕРА: `<server>__ask_1c`
//     (напр. `second-brain__ask_1c`) — поэтому имя матчим по суффиксу.
//   • Конфиг плагина приходит через `api.pluginConfig` (в ctx хука его НЕТ).
//   • message_sending срабатывает только на РЕАЛЬНОЙ доставке в канал (deliver.ts),
//     не на `openclaw agent` без --deliver.
//
// Чистая политика и функции — в verify-core.js (оффлайн-тесты test-verify.mjs).

import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { DEFAULTS, digitBlob, evaluate, extractText, finalizeDecision, isServiceError, mergeRef, numericTokens, stripInternal, toolMatchesAny } from "./verify-core.js";

let PLUGIN_API = null; // штатный api движка; выставляется в register()

function dbg(cfg, line) {
  if (!cfg || !cfg.debug) return;
  const api = PLUGIN_API;
  // Штатный логгер движка: общий gateway.log, ротация, уровни, скрабинг секретов,
  // видно через `openclaw logs`. Свой файл рос без ограничения и не был виден
  // никакими штатными средствами диагностики.
  try {
    // Уровень info, а не debug: отладка включается явным флагом конфига, а при
    // logging.level=info записи уровня debug движок отбрасывает — диагностика была бы
    // невидима, то есть замена самописного файла ничего бы не дала.
    if (api && api.logger && typeof api.logger.info === "function") api.logger.info("[braine-verify] " + line);
    else console.error("[braine-verify] " + line);
  } catch {}
}

// КОРРЕЛЯЦИЯ (проверено в рантайме): у `message_sending` в ctx НЕТ runId — есть только
// `sessionKey`. Доставка идёт ПОСЛЕ `agent_end`. Поэтому эталон храним по sessionKey, а не
// по runId, и НЕ удаляем на agent_end (иначе к доставке эталона уже нет). Внутри хода
// (тот же runId) вызовы ask_1c сливаем; новый runId в сессии → эталон СБРАСЫВАЕМ (это новый ход).
const refs = new Map(); // sessKey -> { at, runId, text, digits:Set<string>, blob:string, noData:boolean }
const lastInbound = new Map(); // sessKey -> ts (граница хода: входящее сообщение)
const inbound = new Map(); // sessKey -> { at, digits:Set<string>, blob:string } (числа пользователя)

function prune(map, ttl) {
  const cut = Date.now() - ttl;
  for (const [k, v] of map) if ((typeof v === "number" ? v : v.at) < cut) map.delete(k);
  if (map.size > 2000) {
    const excess = [...map.keys()].slice(0, map.size - 2000);
    for (const k of excess) map.delete(k);
  }
}

// ключ сессии для корреляции (в обоих хуках это ctx.sessionKey)
function sessKeyOf(ctx, event) {
  return (ctx && ctx.sessionKey) || (event && event.sessionKey) || null;
}

// 🔴 ОТ ЗАЧИСТКИ НИЧЕГО НЕ ОСТАЛОСЬ — ЧТО СКАЗАТЬ ЧЕЛОВЕКУ. Раньше здесь стояла одна
// строка «данных нет», и сбой сервиса приходил к клиенту как уверенное «таких данных у
// нас нет» — самый вредный ответ из возможных (п. 18: при отказах — честный отказ, а не
// ответ на неполных данных). Различаем по маркеру моста, который был в тексте ДО зачистки,
// и по эталону хода: сбой мог прийти и первым вызовом инструмента, а не только в тексте.
function emptyReply(base, ref, cfg) {
  if (isServiceError(base, cfg.serviceErrorMarker) || (ref && ref.svcError)) return cfg.serviceErrorReply;
  return cfg.noDataReply;
}

// эталон хода для этой сессии, с отсечкой чужого хода (эталон старше последнего входящего)
function refFor(sessKey) {
  let ref = sessKey ? refs.get(sessKey) || null : null;
  if (ref && sessKey) {
    const li = lastInbound.get(sessKey);
    if (li && ref.at < li) ref = null;
  }
  return ref;
}

export default definePluginEntry({
  id: "braine-verify",
  name: "Braine Verify",
  // 🔴 Это описание показывает `openclaw plugins inspect` — оно, а НЕ текст из
  // `openclaw.plugin.json`. Держать их согласованными: расходятся молча, и проверка
  // «обновился ли плагин на стенде» по описанию из манифеста даёт ложный ответ.
  description: "Code-level anti-hallucination gate over ask_1c: verifies hard numeric facts in outbound messages AND media captions; delivery is never silently dropped.",
  register(api) {
    PLUGIN_API = api;
    // конфиг плагина берём из api.pluginConfig (не из ctx хука — там его нет)
    const getCfg = () => {
      const pc = api && api.pluginConfig && typeof api.pluginConfig === "object" ? api.pluginConfig : {};
      return { ...DEFAULTS, ...pc };
    };

    // 1) захват эталона braine за ход (ключ = sessionKey; сброс при новом runId)
    api.on("after_tool_call", async (event, ctx) => {
      const cfg = getCfg();
      const wants = cfg.toolNames && cfg.toolNames.length ? cfg.toolNames : [cfg.toolName];
      if (!event || !toolMatchesAny(event.toolName, wants)) return;
      const runId = event.runId || (ctx && ctx.runId) || null;
      const sessKey = sessKeyOf(ctx, event) || (runId ? "run:" + runId : null);
      if (!sessKey) return;
      const text = event.error ? cfg.noDataMarker + " tool_error]" : extractText(event.result);
      const prev = refs.get(sessKey);
      const sameTurn = prev && prev.runId === runId; // тот же ход → сливаем; иначе новый ход → сброс
      const merged = mergeRef(sameTurn ? prev : null, text, Date.now(), cfg.noDataMarker,
                              cfg.clarifyMarker, cfg.serviceErrorMarker);
      merged.runId = runId;
      refs.set(sessKey, merged);
      prune(refs, cfg.refTtlMs);
      dbg(cfg, `after_tool_call tool=${event.toolName} sess=${sessKey} runId=${runId} refDigits=${merged.digits.size} noData=${merged.noData}`);
    });

    // 1b) 🔴 ХОД ЗАВЕРШАЕТСЯ ОТВЕТОМ, А К ДАННЫМ НЕ ОБРАЩАЛИСЬ — ГОНИМ МОДЕЛЬ ЗАНОВО.
    //
    // Указание владельца 30.07: «правила ставятся штатными механизмами openclaw, промт не
    // работает; запрещено свой код делать». Это тот самый механизм: движок сам прогоняет
    // модель ещё раз, а мы лишь говорим, почему.
    //
    // [замер 30.07] на вопрос «Сколько НДС в наших продажах?» бот ответил уточнением при
    // `toolSummary: None` — то есть придумал варианты из общих знаний о предметной области,
    // а не из ЭТОЙ базы. На другой базе тот же вопрос был бы бессмыслицей.
    //
    // Движок вызывает этот хук ТОЛЬКО когда ход завершается естественным видимым ответом и
    // инструментов в нём не было, — то есть условие «к данным не обращались» проверять не
    // нужно, оно уже в самом факте вызова. Мы добавляем лишь одно: был ли эталон за этот ход.
    //
    // Один дополнительный проход, не больше: `maxAttempts: 1`. Если вопрос не про данные
    // (приветствие, «работаю с текстом»), модель на втором проходе ответит так же — цена
    // одного прохода. Городить распознавание «про данные или нет» нельзя: это была бы
    // догадка, а догадка запрещена (п. 12).
    //
    // Требует `plugins.entries.braine-verify.hooks.allowConversationAccess: true` — без него
    // движок МОЛЧА не зарегистрирует хук у неbundled-плагина.
    api.on("before_agent_finalize", async (event, ctx) => {
      const cfg = getCfg();
      if (cfg.requireDataTool === false) return;
      const sessKey = sessKeyOf(ctx, event) || (event && event.runId ? "run:" + event.runId : null);
      const ref = sessKey ? refs.get(sessKey) : null;
      const runId = (event && event.runId) || (ctx && ctx.runId) || null;
      // 🔴 ДАННЫЕ СПРАШИВАЛИ — ЭТОГО МАЛО, СВЕРЯЕМ ЕЩЁ И ЧИСЛА, ИМЕННО ЗДЕСЬ.
      // Прежде на этом месте стоял `return`: ход с обращением к данным считался проверенным,
      // а числа в нём сверялись только хуком доставки. [замер 03.08] хук доставки за весь
      // журнал шлюза сработал ОДИН раз на 239 захваченных вызовов инструмента — то есть на
      // пути, которым снимается приёмка (`openclaw agent` без `--deliver`), числовой
      // проверки не было ни одной.
      //
      // Политика — та же (`finalizeDecision` поверх того же `evaluate`): двух копий правила
      // быть не должно, на разошедшихся копиях проект уже обжигался. Отличается только ФОРМА
      // принуждения: заменить текст движок здесь не даёт
      // (`PluginHookBeforeAgentFinalizeResult` умеет `revise`/`finalize`, но не `content`),
      // поэтому вместо замены требуем ещё один проход и кладём в инструкцию сам обоснованный
      // ответ — модели есть что написать, и это не «попробуй ещё раз» вслепую.
      //
      // Один проход, не больше (`maxAttempts: 1`): бесконечное «перепиши» превращает верный
      // ответ в молчание, а п. 21 называет проверку, отвергнувшую верный ответ, дефектом
      // проверки.
      const haveRef = !!(ref && (!runId || ref.runId === runId));
      const inb = sessKey ? inbound.get(sessKey) || null : null;
      const d = finalizeDecision((event && event.lastAssistantMessage) || "", ref, inb, cfg, haveRef);
      // 🔴 УСПЕХ ГЕЙТА ПИШЕТСЯ В ЖУРНАЛ НАРАВНЕ С ОТКАЗОМ. Пока молчал только успех,
      // «проверил и пропустил» было неотличимо от «не звался вовсе» — ровно так дыра с
      // доставкой и прожила одиннадцать дней незамеченной.
      dbg(cfg, `before_agent_finalize sess=${sessKey} runId=${runId} action=${d.action} why=${d.why}`);
      if (d.action !== "revise") return;
      return {
        action: "revise",
        reason: d.reason,
        retry: { instruction: d.instruction, maxAttempts: 1, idempotencyKey: d.idempotencyKey },
      };
    });

    // ⚠ ЗДЕСЬ БЫЛ ЗАВЕДЁН `before_agent_run` — ЧТОБЫ ЗАПОМИНАТЬ ЧИСЛА ВОПРОСА И НА
    // БЕЗКАНАЛЬНОМ ПУТИ (`message_received` [замер 03.08] сработал 1 раз за весь журнал).
    // Снят в том же заходе: премиса была неверной. `isGrounded` намеренно НЕ пускает числа
    // пользователя в белый список, когда эталон за ход есть, — иначе достаточно назвать
    // число в вопросе, чтобы бот выдал его за факт из 1С. А когда эталона нет, до числовой
    // сверки на завершении хода дело не доходит вовсе: там срабатывает `requireDataTool`.
    // То есть хук не давал ничего и при этом брал плагину лишнюю привилегию читать
    // переписку — ровно ту, от которой здесь уже отказывались однажды.

    // 2) числа из ввода пользователя + граница хода (эхо его номера — не галлюцинация)
    api.on("message_received", async (event, ctx) => {
      const cfg = getCfg();
      const sessKey = sessKeyOf(ctx, event);
      if (!sessKey) return;
      const now = Date.now();
      lastInbound.set(sessKey, now);
      const text = (event && event.content) || "";
      inbound.set(sessKey, { at: now, digits: numericTokens(text, 1), blob: digitBlob(text) });
      prune(inbound, cfg.refTtlMs);
      prune(lastInbound, cfg.refTtlMs);
      dbg(cfg, `message_received sess=${sessKey} len=${text.length}`);
    });

    // 3) проверка исходящего (срабатывает на доставке в канал)
    api.on("message_sending", async (event, ctx) => {
      const cfg = getCfg();
      const content = (event && event.content) || "";
      const sessKey = sessKeyOf(ctx, event);
      // отсечь ЧУЖОЙ ход: если эталон старше последнего входящего этой сессии — это прошлый ход
      const ref = refFor(sessKey);
      const inb = sessKey ? inbound.get(sessKey) || null : null;

      const decision = evaluate(content, ref, inb, cfg);
      if (decision.action === "cancel") {
        dbg(cfg, `message_sending sess=${sessKey} action=cancel`);
        return { cancel: true, cancelReason: "braine-verify: " + decision.reason };
      }
      // база: обоснованный текст (или дословная замена braine) → детерминированная зачистка ВНУТРЕННЕГО (кодом)
      const base = decision.action === "replace" ? decision.content : content;
      const clean = cfg.stripInternal === false ? base : stripInternal(base);
      const leaked = clean !== base;
      dbg(
        cfg,
        `message_sending sess=${sessKey} action=${decision.action} hasRef=${!!ref} refNoData=${ref ? ref.noData : "-"} stripped=${leaked}`,
      );
      if (decision.action === "replace" || clean !== content) {
        return { content: clean.trim() ? clean : emptyReply(base, ref, cfg) };
      }
      return undefined; // allow без изменений
    });

    // 3b) подпись к МЕДИА (фото) идёт через payload.text, а НЕ через message_sending.content.
    //
    // 🔴 ЗДЕСЬ ТОТ ЖЕ ЧИСЛОВОЙ ГЕЙТ, ЧТО И НА ТЕКСТЕ. Раньше этот путь звал только
    // `stripInternal`, то есть подпись к графику — ровно то место, где числа и живут, —
    // не сверялась с эталоном вообще. Дыра против пп. 3 и 10: подпись такая же часть
    // ответа, как и текст, и человек читает её точно так же. Эталон берём тот же, что и
    // на текстовом пути (тот же ход, тот же sessionKey) — иначе гейт мерил бы разное на
    // двух половинах одного ответа.
    api.on("reply_payload_sending", async (event, ctx) => {
      const cfg = getCfg();
      const p = event && event.payload;
      if (!p || typeof p.text !== "string" || !p.text) return undefined;
      const sessKey = sessKeyOf(ctx, event);
      const ref = refFor(sessKey);
      const inb = sessKey ? inbound.get(sessKey) || null : null;

      const decision = evaluate(p.text, ref, inb, cfg);
      // `cancel` на этом пути отменить нечего (картинка уже уходит), поэтому подпись
      // заменяется честной строкой — это и есть поведение п. 21 «ответ обязан дойти».
      const base = decision.action === "replace" ? decision.content
                 : decision.action === "cancel" ? cfg.unverifiedReply
                 : p.text;
      const clean = cfg.stripInternal === false ? base : stripInternal(base);
      const out = clean.trim() ? clean : emptyReply(base, ref, cfg);
      if (out === p.text) return undefined; // нечего менять
      dbg(cfg, `reply_payload_sending action=${decision.action} hasRef=${!!ref} (was ${p.text.length} -> ${out.length})`);
      return { payload: { ...p, text: out } };
    });

    // Эталон НЕ удаляем на agent_end (доставка идёт после него) — чистка по TTL в prune().
  },
});
