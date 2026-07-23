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
import { DEFAULTS, digitBlob, evaluate, extractText, mergeRef, numericTokens, toolMatches } from "./verify-core.js";

const DEBUG_FILE = (process.env.HOME || "/tmp") + "/.openclaw/braine-verify-debug.log";
function dbg(cfg, line) {
  if (!cfg || !cfg.debug) return;
  try {
    appendFileSync(DEBUG_FILE, new Date().toISOString() + " " + line + "\n");
  } catch {
    /* диагностика не должна ломать доставку */
  }
}

// эталон braine за ход, ключ = "run:<runId>"; несколько вызовов ask_1c в ходе — сливаем
const refs = new Map(); // key -> { at, text, digits:Set<string>, blob:string, noData:boolean }
// последний ввод пользователя, ключ = "sess:<sessionKey>"
const inbound = new Map(); // key -> { at, digits:Set<string>, blob:string }

function prune(map, ttl) {
  const cut = Date.now() - ttl;
  for (const [k, v] of map) if (v.at < cut) map.delete(k);
  if (map.size > 2000) {
    const excess = [...map.keys()].slice(0, map.size - 2000);
    for (const k of excess) map.delete(k);
  }
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

    // 1) захват эталона braine за ход
    api.on("after_tool_call", async (event, ctx) => {
      const cfg = getCfg();
      if (!event || !toolMatches(event.toolName, cfg.toolName)) return;
      const runId = event.runId || (ctx && ctx.runId);
      if (!runId) return; // без runId корреляция ненадёжна — пропускаем (деградация безопасна)
      const text = event.error ? cfg.noDataMarker + " tool_error]" : extractText(event.result);
      const key = "run:" + runId;
      const merged = mergeRef(refs.get(key), text, Date.now(), cfg.noDataMarker);
      refs.set(key, merged);
      prune(refs, cfg.refTtlMs);
      dbg(cfg, `after_tool_call tool=${event.toolName} runId=${runId} textLen=${text.length} refDigits=${merged.digits.size} noData=${merged.noData}`);
    });

    // 2) числа из ввода пользователя (эхо его же номера — не галлюцинация)
    api.on("message_received", async (event, ctx) => {
      const cfg = getCfg();
      const sessKey = ctx && ctx.sessionKey;
      if (!sessKey) return;
      const text = (event && event.content) || "";
      inbound.set("sess:" + sessKey, { at: Date.now(), digits: numericTokens(text, 1), blob: digitBlob(text) });
      prune(inbound, cfg.refTtlMs);
      dbg(cfg, `message_received sess=${sessKey} len=${text.length}`);
    });

    // 3) проверка исходящего (срабатывает на доставке в канал)
    api.on("message_sending", async (event, ctx) => {
      const cfg = getCfg();
      const content = (event && event.content) || "";
      const runId = (ctx && ctx.runId) || (event && event.runId);
      const sessKey = ctx && ctx.sessionKey;
      const ref = runId ? refs.get("run:" + runId) || null : null;
      const inb = sessKey ? inbound.get("sess:" + sessKey) || null : null;

      const decision = evaluate(content, ref, inb, cfg);
      dbg(
        cfg,
        `message_sending action=${decision.action} tokens=${[...numericTokens(content, cfg.minDigits)].length} hasRef=${!!ref} refNoData=${ref ? ref.noData : "-"} runId=${runId || "-"}`,
      );
      if (decision.action === "cancel") return { cancel: true, cancelReason: "braine-verify: " + decision.reason };
      if (decision.action === "replace") return { content: decision.content };
      return undefined; // allow
    });

    // 4) уборка эталона хода
    api.on("agent_end", async (event, ctx) => {
      const cfg = getCfg();
      const runId = (event && event.runId) || (ctx && ctx.runId);
      dbg(cfg, `agent_end runId=${runId || "-"}`);
      if (runId) refs.delete("run:" + runId);
    });
  },
});
