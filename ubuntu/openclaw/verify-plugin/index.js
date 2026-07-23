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
//     plugins.entries.braine-verify.hooks.allowConversationAccess=true.
//   • MCP-инструмент проецируется боту под ИМЕНЕМ СЕРВЕРА: `<server>__ask_1c`
//     (напр. `second-brain__ask_1c`) — поэтому имя матчим по суффиксу.
//   • Конфиг плагина приходит через `api.pluginConfig` (в ctx хука его НЕТ).
//   • message_sending срабатывает только на РЕАЛЬНОЙ доставке в канал (deliver.ts),
//     не на `openclaw agent` без --deliver.
//
// Чистая политика и функции — в verify-core.js (оффлайн-тесты test-verify.mjs).

import { appendFileSync } from "node:fs";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { DEFAULTS, digitBlob, evaluate, extractText, mergeRef, numericTokens, stripInternal, toolMatchesAny } from "./verify-core.js";

const DEBUG_FILE = (process.env.HOME || "/tmp") + "/.openclaw/braine-verify-debug.log";
function dbg(cfg, line) {
  if (!cfg || !cfg.debug) return;
  try {
    appendFileSync(DEBUG_FILE, new Date().toISOString() + " " + line + "\n");
  } catch {
    /* диагностика не должна ломать доставку */
  }
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

export default definePluginEntry({
  id: "braine-verify",
  name: "Braine Verify",
  description: "Code-level anti-hallucination gate over braine ask_1c (verifies hard numeric facts in outbound messages).",
  register(api) {
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
      const merged = mergeRef(sameTurn ? prev : null, text, Date.now(), cfg.noDataMarker);
      merged.runId = runId;
      refs.set(sessKey, merged);
      prune(refs, cfg.refTtlMs);
      dbg(cfg, `after_tool_call tool=${event.toolName} sess=${sessKey} runId=${runId} refDigits=${merged.digits.size} noData=${merged.noData}`);
    });

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
      let ref = sessKey ? refs.get(sessKey) || null : null;
      // отсечь ЧУЖОЙ ход: если эталон старше последнего входящего этой сессии — это прошлый ход
      if (ref && sessKey) {
        const li = lastInbound.get(sessKey);
        if (li && ref.at < li) ref = null;
      }
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
        return { content: clean.trim() ? clean : cfg.noDataReply };
      }
      return undefined; // allow без изменений
    });

    // 3b) анти-слив на payload-пути: подпись к МЕДИА (фото) идёт через payload.text,
    // а НЕ через message_sending.content. Режем внутреннее и здесь — полное кодовое покрытие.
    api.on("reply_payload_sending", async (event, ctx) => {
      const cfg = getCfg();
      if (cfg.stripInternal === false) return undefined;
      const p = event && event.payload;
      if (!p || typeof p.text !== "string" || !p.text) return undefined;
      const clean = stripInternal(p.text);
      if (clean === p.text) return undefined; // нечего резать
      dbg(cfg, `reply_payload_sending stripped caption/text (was ${p.text.length} -> ${clean.length})`);
      return { payload: { ...p, text: clean.trim() ? clean : cfg.noDataReply } };
    });

    // Эталон НЕ удаляем на agent_end (доставка идёт после него) — чистка по TTL в prune().
  },
});
