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
import { DEFAULTS, buildClarifyPresentation, channelUserOf, digitBlob, evaluate, extractText, finalizeDecision, injectAskUser, isClarify, isServiceError, mergeRef, newRid, numericTokens, parseAtomJson, parseClarifyOptions, parsePresentationJson, rewriteAsk1cParams, selfFetchNeeded, stripInternal, toolMatchesAny, traceEnabled, traceLine } from "./verify-core.js";

let PLUGIN_API = null; // штатный api движка; выставляется в register()

function traceLog(cfg, rid, layer, step, ms, status) {
  if (!traceEnabled(cfg)) return;
  const line = traceLine(rid, layer, step, ms, status);
  const api = PLUGIN_API;
  try {
    if (api && api.logger && typeof api.logger.info === "function") api.logger.info(line);
    else console.error(line);
  } catch {}
}

function ridFor(sessKey, cfg, create) {
  if (!sessKey) return create ? newRid() : "";
  const now = Date.now();
  const ttl = (cfg && cfg.refTtlMs) || 10 * 60 * 1000;
  let rec = turnRid.get(sessKey);
  if (!rec || now - rec.at > ttl) {
    if (!create) return "";
    rec = { at: now, rid: newRid() };
    turnRid.set(sessKey, rec);
  }
  rec.at = now;
  prune(turnRid, ttl);
  return rec.rid;
}

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
// 🔴 ВОПРОС ХОДА ОТДЕЛЬНО ОТ `inbound`. `message_received` живёт ТОЛЬКО на доставке в
// канал ([замер 03.08] 1 срабатывание за одиннадцать дней), а свой поход за данными нужен
// на любом пути — иначе он не работает ни в приёмке, ни при вызове агента напрямую.
// Проверено пробой: на прогоне без доставки `self_fetch` не сработал ни разу именно из-за
// пустого `inbound`. Текст берётся из `before_agent_run`, который даёт текущий ввод
// пользователя и срабатывает всегда (доки `plugins/hooks.md`).
const prompts = new Map(); // sessKey -> { at, text } (вопрос текущего хода)
const clarifyLocks = new Map(); // sessKey -> { at, question, options[] }
const identities = new Map(); // run:<id>|sess:<key> -> { user, kind, channel, at }
const turnRid = new Map(); // sessKey -> { at, rid }

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

function runIdOf(ctx, event) {
  return (ctx && ctx.runId) || (event && event.runId) || null;
}

function storeIdentity(ctx, event) {
  const rec = { ...channelUserOf(ctx, event), at: Date.now() };
  if (!rec.user) return rec;
  const runId = runIdOf(ctx, event);
  const sess = sessKeyOf(ctx, event);
  if (runId) identities.set("run:" + runId, rec);
  if (sess) identities.set("sess:" + sess, rec);
  prune(identities, 30 * 60 * 1000);
  try {
    const api = PLUGIN_API;
    if (api && api.runContext && runId && typeof api.runContext.setRunContext === "function")
      api.runContext.setRunContext({ runId, namespace: "ask1c.identity", value: rec });
  } catch (_) { /* runContext — штатный scratch; нет API — Map */ }
  return rec;
}

function loadIdentity(ctx, event) {
  const runId = runIdOf(ctx, event);
  const sess = sessKeyOf(ctx, event);
  try {
    const api = PLUGIN_API;
    if (api && api.runContext && runId && typeof api.runContext.getRunContext === "function") {
      const v = api.runContext.getRunContext({ runId, namespace: "ask1c.identity" });
      if (v && v.user) return v;
    }
  } catch (_) { /* нет API — Map */ }
  if (runId && identities.has("run:" + runId)) return identities.get("run:" + runId);
  if (sess && identities.has("sess:" + sess)) return identities.get("sess:" + sess);
  return channelUserOf(ctx, event);
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

    // Telegram: callback=decision_id → снять кнопки и отдать id как текст хода
    // (clarify_lock / rewriteAsk1cParams кладут decision_id в ask_1c). Доки:
    // plugins/message-presentation.md, registerInteractiveHandler + clearButtons.
    if (typeof api.registerInteractiveHandler === "function") {
      try {
        api.registerInteractiveHandler({
          channel: "telegram",
          namespace: "ask1c",
          handler: async (ctx) => {
            const payload = (ctx && ctx.callback && (ctx.callback.payload || ctx.callback.data)) || "";
            try {
              if (ctx && ctx.respond && typeof ctx.respond.clearButtons === "function")
                await ctx.respond.clearButtons();
            } catch (_) { /* снятие кнопок best-effort */ }
            const text = String(payload || "").trim();
            if (!text) return { handled: true };
            return { handled: true, submitText: text };
          },
        });
      } catch (e) {
        // Старые сборки без интерактива — текстовый OPTIONS остаётся.
      }
    }

    // 🔴 СВОЙ ПОХОД ЗА ДАННЫМИ. Тот же сервис и тот же контракт, что у моста `ask_1c`:
    // второго места правды не заводим. Возвращаем ТЕКСТ в том же виде, в каком его отдал бы
    // инструмент, — дальше он идёт через `mergeRef`, как обычный эталон хода.
    //
    // Ошибка любого рода — это `null`, а не выдуманный ответ: молча подставить пустоту
    // значило бы выдать «данных нет» там, где сервис просто не ответил (п. 18).
    const askService = async (cfg, question, identity, sessKey) => {
      const url = String(cfg.askUrl || "").trim();
      if (!url || !question) return null;
      const ctl = new AbortController();
      const t = setTimeout(() => ctl.abort(), Math.max(1000, cfg.askTimeoutMs || 120000));
      try {
        // 🔴 ТОКЕН — ИЗ ОКРУЖЕНИЯ СЛУЖБЫ, А НЕ ИЗ ФАЙЛА НАСТРОЕК. Штатный `SecretRef`
        // покрывает только перечисленные встроенные плагины (доки,
        // `reference/secretref-credential-surface`), нашего в реестре нет — значит значение
        // легло бы в `openclaw.json` открытым текстом, а правило проекта держит секреты в
        // `/etc/*.env` с правами 600. Настройкой можно задать лишь ИМЯ переменной.
        const token = String(process.env[cfg.askTokenEnv || "ASK_TOKEN"] || cfg.askToken || "");
        const headers = { "Content-Type": "application/json" };
        if (token) headers.Authorization = "Bearer " + token;
        const body = { question };
        if (identity && identity.user) body.user = identity.user;
        if (identity && identity.channel) body.channel = identity.channel;
        const rid = ridFor(sessKey, cfg, false) || ridFor(sessKey, cfg, true);
        if (rid) body.rid = rid;
        const r = await fetch(url, {
          method: "POST", headers, signal: ctl.signal,
          body: JSON.stringify(body),
        });
        if (!r.ok) return null;
        const d = await r.json();
        // Маркеры кладёт мост, а не сервис: здесь ветки те же, что в `mcp_ask.py`, иначе
        // числовая сверка не узнает «нет данных» и «уточнение».
        const kind = (d && d.kind) || "";
        const text = (d && (d.text || "")) || "";
        if (kind === "unavailable") return cfg.serviceErrorMarker + "] " + text;
        if (kind === "no_data") return cfg.noDataMarker + "] " + text;
        if (kind === "clarify") return cfg.clarifyMarker + "] " + text;
        // Числа, посчитанные базой, обязаны попасть в эталон: по ним и идёт сверка.
        const figs = d && d.figures && typeof d.figures === "object"
          ? Object.entries(d.figures).map(([k, v]) => `${k}=${v}`).join(" ") : "";
        return figs ? text + "\n" + figs : text;
      } catch {
        return null;
      } finally {
        clearTimeout(t);
      }
    };

    // 0) вопрос хода — для своего похода за данными. Только текст и только в память на
    // время хода; лишней привилегии это не берёт: `allowConversationAccess` плагину и так
    // нужен для `before_agent_finalize`, где живёт числовая сверка.
    api.on("before_agent_run", async (event, ctx) => {
      const cfg = getCfg();
      storeIdentity(ctx, event);
      const sessKey = sessKeyOf(ctx, event) || (event && event.runId ? "run:" + event.runId : null);
      const rid = ridFor(sessKey, cfg, true);
      traceLog(cfg, rid, "gateway", "agent_start", 0, "ok");
      if (sessKey) {
        const q = (event && (event.prompt || event.input || "")) || "";
        if (q && typeof q === "string") {
          prompts.set(sessKey, { at: Date.now(), text: q.slice(0, 2000) });
          prune(prompts, cfg.refTtlMs);
        }
      }
      if (!cfg.askUrl) return;
    });

    api.on("before_tool_call", async (event, ctx) => {
      const cfg = getCfg();
      const wants = cfg.toolNames && cfg.toolNames.length ? cfg.toolNames : [cfg.toolName];
      if (!event || !toolMatchesAny(event.toolName, wants)) return;
      const sessKey = sessKeyOf(ctx, event) || null;
      const identity = loadIdentity(ctx, event);
      const lock = sessKey ? clarifyLocks.get(sessKey) : null;
      let params = { ...(event.params || {}) };
      let changed = false;
      if (!lock) {
        if (params.prior) {
          params.prior = "";
          changed = true;
          dbg(cfg, `before_tool_call strip prior sess=${sessKey}`);
        }
      } else {
        const promptRec = prompts.get(sessKey);
        const prompt = (promptRec && promptRec.text) || "";
        const rewritten = rewriteAsk1cParams(params, prompt, lock);
        params = rewritten.params;
        if (rewritten.action === "release") clarifyLocks.delete(sessKey);
        changed = true;
        dbg(cfg, `before_tool_call rewrite sess=${sessKey} action=${rewritten.action} q=${String(params.question || "").slice(0, 80)} focus=${params.focus || ""} decision_id=${params.decision_id || ""} prior=${String(params.prior || "").slice(0, 80)}`);
      }
      const rid = ridFor(sessKey, cfg, true);
      let injected = injectAskUser(params, identity);
      injected = injectAskRid(injected, rid);
      if (injected.user !== params.user || injected.channel !== params.channel || injected.rid !== params.rid) {
        changed = true;
        dbg(cfg, `before_tool_call user=${injected.user || ""} kind=${(identity && identity.kind) || "none"} ch=${injected.channel || ""}`);
      }
      if (changed) return { params: injected };
      return;
    });

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
      if (isClarify(text, cfg.clarifyMarker)) {
        const pr = event.params && typeof event.params === "object" ? event.params : {};
        const q = String(pr.question || pr.q || "")
          || ((prompts.get(sessKey) && prompts.get(sessKey).text) || "");
        const options = parseClarifyOptions(text);
        if (q && options.length) {
          clarifyLocks.set(sessKey, { at: Date.now(), question: q, options });
          prune(clarifyLocks, cfg.refTtlMs);
          dbg(cfg, `clarify_lock set sess=${sessKey} opts=${options.length} q=${q.slice(0, 80)}`);
        }
      } else if (clarifyLocks.has(sessKey)) {
        clarifyLocks.delete(sessKey);
        dbg(cfg, `clarify_lock clear sess=${sessKey}`);
      }
      const rid = ridFor(sessKey, cfg, false) || ridFor(sessKey, cfg, true);
      traceLog(cfg, rid, "gateway", "tool_call", 0, event.error ? "error" : "ok");
      dbg(cfg, `after_tool_call tool=${event.toolName} sess=${sessKey} runId=${runId} refDigits=${merged.digits.size} noData=${merged.noData}`);
    });

    api.on("session_end", async (event, ctx) => {
      const cfg = getCfg();
      const sessKey = sessKeyOf(ctx, event);
      if (sessKey && clarifyLocks.delete(sessKey)) {
        dbg(cfg, `clarify_lock clear sess=${sessKey} reason=session_end`);
      }
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
      let haveRef = !!(ref && (!runId || ref.runId === runId));
      const inb = sessKey ? inbound.get(sessKey) || null : null;
      // 🔴 МОДЕЛЬ НЕ ПОЗВАЛА ИНСТРУМЕНТ — ЗОВЁМ САМИ. Разбор, почему именно так, а не
      // просьбой к модели, — в `selfFetchNeeded` (verify-core). Коротко: заставить её
      // движок не умеет, а просить бесполезно и это замерено.
      let ref2 = ref;
      // Вопрос берём из `before_agent_run` (есть всегда), а `inbound` — запасной путь:
      // он наполняется только на доставке в канал.
      const qrec = (sessKey && prompts.get(sessKey)) || inb || null;
      if (selfFetchNeeded(haveRef, cfg, qrec, sessKey)) {
        const own = await askService(cfg, qrec.text, loadIdentity(ctx, event), sessKey);
        if (own) {
          ref2 = mergeRef(null, own, Date.now(), cfg.noDataMarker, cfg.clarifyMarker,
                          cfg.serviceErrorMarker);
          ref2.runId = runId;
          if (sessKey) refs.set(sessKey, ref2);
          haveRef = true;
          dbg(cfg, `self_fetch sess=${sessKey} runId=${runId} refDigits=${ref2.digits.size} noData=${ref2.noData}`);
        } else {
          // Сервис не ответил — это НЕ повод выдать ответ модели за обоснованный.
          // Оставляем прежний путь: движок прогонит модель ещё раз.
          dbg(cfg, `self_fetch sess=${sessKey} runId=${runId} FAILED`);
        }
      }
      const d = finalizeDecision((event && event.lastAssistantMessage) || "", ref2, inb, cfg, haveRef);
      // 🔴 УСПЕХ ГЕЙТА ПИШЕТСЯ В ЖУРНАЛ НАРАВНЕ С ОТКАЗОМ. Пока молчал только успех,
      // «проверил и пропустил» было неотличимо от «не звался вовсе» — ровно так дыра с
      // доставкой и прожила одиннадцать дней незамеченной.
      const rid = ridFor(sessKey, cfg, false) || ridFor(sessKey, cfg, true);
      traceLog(cfg, rid, "plugin", d.action === "revise" ? "revise" : "pass", 0, d.why || "ok");
      dbg(cfg, `before_agent_finalize sess=${sessKey} runId=${runId} action=${d.action} why=${d.why}`);
      if (d.action !== "revise") return;
      return {
        action: "revise",
        reason: d.reason,
        retry: { instruction: d.instruction, maxAttempts: 1, idempotencyKey: d.idempotencyKey },
      };
    // 🔴 БЮДЖЕТ ХУКА ПОДНЯТ ПОД СВОЙ ПОХОД ЗА ДАННЫМИ. Умолчание движка — 15 с, а сервис
    // ответов отвечает 30-70 с ([замер 03.08] приёмка: 16-175 с на вопрос). При таймауте
    // движок пишет отказ в журнал и продолжает с прежним ответом — то есть механизм молча
    // не работал бы. Ручка штатная: `api.on(..., { timeoutMs })`, доки `plugins/hooks.md`.
    }, { timeoutMs: DEFAULTS.askTimeoutMs + 10000 });

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
      storeIdentity(ctx, event);
      const sessKey = sessKeyOf(ctx, event);
      if (!sessKey) return;
      const now = Date.now();
      lastInbound.set(sessKey, now);
      const rid = ridFor(sessKey, cfg, true);
      traceLog(cfg, rid, "gateway", "received", 0, "ok");
      const text = (event && event.content) || "";
      // Текст вопроса хранится, чтобы плагин мог САМ сходить за данными, когда модель
      // инструмент не позвала (см. `before_agent_finalize`). Ограничен сверху: в памяти
      // плагина не должно копиться переписки больше, чем нужно для одного хода.
      inbound.set(sessKey, { at: now, digits: numericTokens(text, 1), blob: digitBlob(text),
                             text: text.slice(0, 2000) });
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

      const lock = sessKey ? clarifyLocks.get(sessKey) : null;
      let presentation = parsePresentationJson(content)
        || (lock && lock.options ? buildClarifyPresentation(lock.options) : null)
        || null;
      // Из ATOM_JSON options с decision_id — если текстовый OPTIONS без id.
      if (!presentation) {
        const atom = parseAtomJson(content);
        if (atom && Array.isArray(atom.options))
          presentation = buildClarifyPresentation(atom.options);
      }

      const rid = ridFor(sessKey, cfg, false) || ridFor(sessKey, cfg, true);
      const decision = evaluate(content, ref, inb, cfg, presentation);
      const gate = decision.action === "cancel" ? "block" : (decision.action === "replace" ? "revise" : "pass");
      traceLog(cfg, rid, "plugin", gate, 0, decision.reason || "ok");
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
        `message_sending sess=${sessKey} action=${decision.action} hasRef=${!!ref} refNoData=${ref ? ref.noData : "-"} stripped=${leaked} hasPres=${!!presentation}`,
      );
      const outContent = (decision.action === "replace" || clean !== content)
        ? (clean.trim() ? clean : emptyReply(base, ref, cfg))
        : content;
      traceLog(cfg, rid, "gateway", "reply_sent", 0, gate);
      if (presentation || decision.action === "replace" || clean !== content) {
        const ret = { content: outContent };
        if (presentation) ret.presentation = presentation;
        return ret;
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

      const lock = sessKey ? clarifyLocks.get(sessKey) : null;
      let presentation = p.presentation
        || parsePresentationJson(p.text)
        || (lock && lock.options ? buildClarifyPresentation(lock.options) : null)
        || null;
      if (!presentation) {
        const atom = parseAtomJson(p.text);
        if (atom && Array.isArray(atom.options))
          presentation = buildClarifyPresentation(atom.options);
      }

      const decision = evaluate(p.text, ref, inb, cfg, presentation);
      // `cancel` на этом пути отменить нечего (картинка уже уходит), поэтому подпись
      // заменяется честной строкой — это и есть поведение п. 21 «ответ обязан дойти».
      const base = decision.action === "replace" ? decision.content
                 : decision.action === "cancel" ? cfg.unverifiedReply
                 : p.text;
      const clean = cfg.stripInternal === false ? base : stripInternal(base);
      const out = clean.trim() ? clean : emptyReply(base, ref, cfg);
      if (out === p.text && !presentation) return undefined;
      dbg(cfg, `reply_payload_sending action=${decision.action} hasRef=${!!ref} hasPres=${!!presentation} (was ${p.text.length} -> ${out.length})`);
      const payload = { ...p, text: out };
      if (presentation) payload.presentation = presentation;
      return { payload };
    });

    // Эталон НЕ удаляем на agent_end (доставка идёт после него) — чистка по TTL в prune().
  },
});
