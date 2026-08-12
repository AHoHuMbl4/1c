// PacketAgent.cs — агент пакетного транспорта Windows -> Ubuntu.
// Контракт: docs/PACKET_CONTRACT.md (manifest_version=1), CLI: work/installer-exe/AGENT_TZ.md §7.
// Семантика выгрузки — байт-в-байт порт ubuntu/serenedb/poc_load_entity.py (К5),
// проверяется golden-пробой work/packet/golden (probe.cmd, fc /b против reference).
// Транспорт: mTLS на релее (HAProxy проверяет клиентский сертификат по CA
// 1c-packet-ca — без него запрос не проходит вовсе) + Bearer-токен вторым фактором.
// Упаковка: recipient_pubkey задан → zstd+age (контракт §3-4); пуст/отсутствует →
// plain-режим пилота (решение 06.08, AGENT_TZ §2): zstd остаётся, age снимается,
// файлы без суффикса .age; приёмник различает режимы по магии файла.
// C# 5 (csc.exe из .NET Framework 4), только стандартные сборки.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Net;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;

namespace PacketAgent
{
    // ============================ настройки (именованные константы) =============
    // Каждое число можно переопределить ключом в agent.ini — имя ключа в скобках.
    internal static class C
    {
        internal const string Version = "1.1.0";   // отчёт хода такта на приёмник (12.08);
                                                   // 1.0.3 — тупик пустого контура + код смоука;
                                                   // 1.0.2 — outbox логов + skipped-only
        internal const int ManifestVersion = 1;

        internal const int PageSizeDefault = 10000;   // (page_size) размер страницы OData
        internal const int PageMinDefault = 250;      // (page_min) нижний предел уменьшения страницы
        internal const int TactSecondsDefault = 1200; // (tact_seconds) пауза между тактами без конфига сервера
        internal const int ChunkMbDefault = 32;       // (chunk_mb) цель размера чанка до распаковки
        internal const int ChunkMbMin = 4;            // нижний зажим chunk_mb
        internal const int ChunkMbMax = 48;           // верхний зажим: лимит приёмника 64 МБ на чанк (К8)
        internal const int HttpTimeoutSeconds = 600;  // (http_timeout) бюджет времени одного запроса к 1С
        internal const int ReceiverTimeoutSeconds = 300; // (receiver_timeout) запрос к приёмнику
        internal const int StatusPollSeconds = 5;     // (status_poll_seconds) пауза опроса status
        internal const int StatusWaitSeconds = 900;   // (status_wait_seconds) предел ожидания verified/applied
        internal const int ReceiverRetryMax = 5;      // повторы запроса к приёмнику при 5xx/таймауте
        internal const int BackoffBaseSeconds = 2;    // экспоненциальная пауза: base*2^n
        internal const int LogMaxBytes = 10 * 1024 * 1024; // ротация файла журнала по размеру
        internal const int StaleSeqJump = 1000000;    // скачок seq при stale_seq (см. Tact)
        internal const int ProgressSecondsDefault = 60; // (progress_seconds) отчёт хода такта; 0 — выключен
        internal const int ProgressTimeoutSeconds = 10; // бюджет одной попытки отчёта (повторов нет)
    }

    // ============================ конфиг agent.ini ==============================
    internal sealed class Cfg
    {
        internal string BaseId, ReceiverUrl, Token, RecipientPubkey;
        internal string OdataUrl, OdataUser, OdataPassword, DataDir;
        // metadata_file — манифестный режим: синтетический $metadata файлом
        // (его кладёт установщик), агент читает его вместо HTTP (Tact.LoadMetaBytes).
        internal string MetadataFile;
        internal string ClientCertThumbprint;   // client_cert_thumbprint — mTLS на релее
        internal int PageSize = C.PageSizeDefault;
        internal int PageMin = C.PageMinDefault;
        internal int TactSeconds = C.TactSecondsDefault;
        internal int ChunkMb = C.ChunkMbDefault;
        internal int ProgressSeconds = C.ProgressSecondsDefault;
        internal string LogDir = @"C:\1c\logs";

        // Режим упаковки по конфигу: pubkey не задан → plain (пилот).
        internal bool Plain { get { return string.IsNullOrEmpty(RecipientPubkey); } }

        internal static Cfg Load(string path)
        {
            if (!File.Exists(path))
                throw new InvalidDataException("нет конфига " + path + " (его пишет установщик)");
            Dictionary<string, string> kv = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (string raw in File.ReadAllLines(path, Encoding.UTF8))
            {
                string line = raw.Trim();
                if (line.Length == 0 || line.StartsWith("#") || line.StartsWith(";")) continue;
                int eq = line.IndexOf('=');
                if (eq <= 0) continue;
                kv[line.Substring(0, eq).Trim()] = line.Substring(eq + 1).Trim();
            }
            Cfg c = new Cfg();
            c.BaseId = Get(kv, "base_id", true);
            c.ReceiverUrl = Get(kv, "receiver_url", true).TrimEnd('/');
            c.Token = Get(kv, "token", true);
            // recipient_pubkey пуст/отсутствует → plain-режим (пилот 06.08, AGENT_TZ §2):
            // zstd остаётся, снимается только age. Задан — упаковка zstd+age, как прежде.
            // Pubkey может прийти и с сервера (/agent/config) — тогда режим сам станет age.
            c.RecipientPubkey = Get(kv, "recipient_pubkey", false) ?? "";
            c.OdataUrl = Get(kv, "odata_url", true).TrimEnd('/');
            c.OdataUser = Get(kv, "odata_user", true);
            // Пароль 1С бывает легально ПУСТЫМ (учётка без пароля — на стенде УТ
            // именно так): Get(required) на пустом значении бросал «нет ключа».
            // Отсутствие ключа и пустое значение равнозначны — анонимный Basic.
            c.OdataPassword = Get(kv, "odata_password", false) ?? "";
            c.DataDir = Get(kv, "data_dir", true);
            // Манифестный режим (решение 11.08): у клиента на проде $metadata и
            // корень OData отвечают HTTP 500 (баг платформы 8.3.27 при большом
            // составе публикации), а запросы к сущностям работают — установщик
            // генерирует синтетический $metadata из COM-метаданных и кладёт файлом.
            c.MetadataFile = Get(kv, "metadata_file", false);
            c.ClientCertThumbprint = Get(kv, "client_cert_thumbprint", false);
            c.PageSize = GetInt(kv, "page_size", c.PageSize);            c.PageMin = GetInt(kv, "page_min", c.PageMin);
            c.TactSeconds = GetInt(kv, "tact_seconds", c.TactSeconds);
            c.ChunkMb = Math.Max(C.ChunkMbMin, Math.Min(C.ChunkMbMax, GetInt(kv, "chunk_mb", c.ChunkMb)));
            // progress_seconds: 0 — законное значение «отчёты выключены», поэтому не
            // через GetInt (он отбрасывает всё, что не больше нуля).
            string psRaw;
            int psVal;
            if (kv.TryGetValue("progress_seconds", out psRaw)
                && int.TryParse(psRaw, NumberStyles.Integer, CultureInfo.InvariantCulture, out psVal)
                && psVal >= 0)
                c.ProgressSeconds = psVal;
            c.LogDir = Get(kv, "log_dir", false) ?? c.LogDir;
            Log.AddSecret(c.Token);
            Log.AddSecret(c.OdataPassword);
            return c;
        }

        static string Get(Dictionary<string, string> kv, string key, bool required)
        {
            string v;
            if (kv.TryGetValue(key, out v) && v.Length > 0) return v;
            if (required) throw new InvalidDataException("в agent.ini нет ключа " + key);
            return null;
        }

        static int GetInt(Dictionary<string, string> kv, string key, int dflt)
        {
            string v;
            int n;
            if (kv.TryGetValue(key, out v) && int.TryParse(v, NumberStyles.Integer,
                    CultureInfo.InvariantCulture, out n) && n > 0) return n;
            return dflt;
        }
    }

    // ============================ mTLS: клиентский сертификат ===================
    // Решение владельца 06.08: релей (HAProxy) проверяет клиентский сертификат
    // агента по нашему CA 1c-packet-ca; без сертификата запрос не проходит вовсе.
    // Bearer-токен остаётся вторым фактором. Сертификат импортирует установщик
    // (client.pfx из комплекта -> LocalMachine\My), в agent.ini пишет отпечаток —
    // certutil печатает его с пробелами и в верхнем регистре, при сравнении
    // нормализуем (пробелы долой, регистр вверх).
    internal static class Mtls
    {
        internal static X509Certificate2 Current;   // null — сетевые режимы не стартовали

        // Поиск по отпечатку: LocalMachine\My, затем CurrentUser\My. null — не нашёл.
        internal static X509Certificate2 Find(string thumbprint)
        {
            string norm = (thumbprint ?? "").Replace(" ", "").ToUpperInvariant();
            if (norm.Length == 0) return null;
            foreach (StoreLocation loc in new[] { StoreLocation.LocalMachine, StoreLocation.CurrentUser })
            {
                X509Store store = null;
                try
                {
                    store = new X509Store(StoreName.My, loc);
                    store.Open(OpenFlags.ReadOnly | OpenFlags.OpenExistingOnly);
                    X509Certificate2Collection found = store.Certificates.Find(
                        X509FindType.FindByThumbprint, norm, false);
                    if (found.Count > 0) return found[0];
                }
                catch (Exception e)
                {
                    Log.Line("хранилище My (" + loc + ") недоступно: " + e.Message);
                }
                finally
                {
                    if (store != null) store.Close();
                }
            }
            return null;
        }

        // Проверка при старте сетевых режимов. null и сообщение — конфиг/хранилище
        // не готовы; диагностика называет причину ДО похода в сеть.
        internal static string LoadFor(string thumbprint)
        {
            if (string.IsNullOrEmpty((thumbprint ?? "").Replace(" ", "")))
                return "в agent.ini нет client_cert_thumbprint — mTLS на релее обязателен "
                       + "(сертификат импортирует установщик из client.pfx комплекта)";
            X509Certificate2 cert = Find(thumbprint);
            if (cert == null)
                return "сертификат с отпечатком " + thumbprint + " не найден ни в "
                       + "LocalMachine\\My, ни в CurrentUser\\My — переустановите комплект";
            if (!cert.HasPrivateKey)
                return "сертификат " + cert.Thumbprint + " импортирован БЕЗ закрытого ключа "
                       + "(субъект: " + cert.Subject + ") — mTLS-рукопожатие невозможно, "
                       + "импортируйте client.pfx заново";
            Current = cert;
            return null;
        }
    }

    // ============================ журнал ========================================
    internal static class Log
    {
        static readonly List<string> Secrets = new List<string>();
        static string _file;

        internal static void AddSecret(string s)
        {
            if (!string.IsNullOrEmpty(s) && !Secrets.Contains(s)) Secrets.Add(s);
        }

        internal static void Init(string dir)
        {
            try
            {
                if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);
                _file = Path.Combine(dir, "packet-agent.log");
            }
            catch { _file = null; }
        }

        // internal: текст, уходящий с машины (отчёт хода такта), маскируется тем же
        // списком секретов, что и локальный журнал.
        internal static string Mask(string msg)
        {
            foreach (string s in Secrets) msg = msg.Replace(s, "***");
            return msg;
        }

        internal static void Line(string msg)
        {
            string s = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture)
                       + " " + Mask(msg);
            try { Console.WriteLine(s); } catch { }
            if (_file == null) return;
            try
            {
                lock (Secrets)
                {
                    if (File.Exists(_file) && new FileInfo(_file).Length > C.LogMaxBytes)
                    {
                        string old = _file + ".1";
                        if (File.Exists(old)) File.Delete(old);
                        File.Move(_file, old);
                    }
                    File.AppendAllText(_file, s + "\r\n", Encoding.UTF8);
                }
            }
            catch { }
        }
    }

    // ============================ отчёт хода такта ==============================
    // Слепое окно живого прогона (12.08, okna-1 и klient-1): после GET /agent/config
    // агент к приёмнику не обращается, пока не соберёт весь пакет, — а первый полный
    // проход по тысячам сущностей идёт часами. Со стороны сервера «агент работает»
    // было неотличимо от «агент умер»: стадию восстанавливали по косвенным признакам
    // (занятый mutex, ритм тактов сторожа). Отчёт: POST /v1/agent/progress не чаще
    // progress_seconds (60 с; 0 в agent.ini — выключен) + та же строка в журнал.
    //
    // 🔴 Доставка пакетов от отчёта НЕ зависит и зависеть не может: одна попытка с
    // коротким таймаутом, без повторов, любой сбой глотается. Отказ приёмника (404 —
    // старая версия без ручки, 401 и прочие 4xx) выключает отчёты до конца такта;
    // сетевой сбой прореживает попытки экспоненциально, чтобы недоступный приёмник
    // не тормозил чтение 1С паузами таймаута.
    // До Begin() (режимы --smoke, --send-log, --flatten) класс — no-op.
    internal static class Progress
    {
        static Receiver _rx;
        static int _interval;          // секунды; задаётся Begin()
        static bool _off = true;       // до Begin() — всегда no-op
        static bool _sentAny;          // такт уже «звучал» на приёмнике
        static int _netFailures;       // подряд сетевых сбоев — для прореживания
        static int _startTick, _lastTick;
        static string _phase = "", _entity = "", _kind = "";
        static long _i, _n, _rowsEntity, _rowsTotal, _seq;

        internal static void Begin(Receiver rx, int intervalSeconds)
        {
            _rx = rx;
            _interval = intervalSeconds;
            _off = rx == null || intervalSeconds <= 0;
            _sentAny = false;
            _netFailures = 0;
            _startTick = Environment.TickCount;
            _lastTick = _startTick;
            _phase = "config"; _entity = ""; _kind = "";
            _i = 0; _n = 0; _rowsEntity = 0; _rowsTotal = 0; _seq = 0;
        }

        internal static void Kind(string kind, long seq) { _kind = kind; _seq = seq; }

        internal static void Entity(string entity, long i, long n)
        {
            _rowsTotal += _rowsEntity;
            _rowsEntity = 0;
            _phase = "read"; _entity = entity; _i = i; _n = n;
            TrySend(false);
        }

        // Строк прочитано в ТЕКУЩЕЙ сущности (абсолютное значение, не приращение).
        internal static void Rows(long rowsInEntity)
        {
            _rowsEntity = rowsInEntity;
            TrySend(false);
        }

        internal static void Chunks(long total)
        {
            _rowsTotal += _rowsEntity;
            _rowsEntity = 0;
            _phase = "send"; _entity = ""; _i = 0; _n = total;
            TrySend(false);
        }

        // Отправлено чанков (фаза выставляется здесь же — довозка пакета прошлого
        // такта начинается сразу с отправки, минуя чтение 1С).
        internal static void ChunkSent(long sent)
        {
            _phase = "send"; _i = sent;
            TrySend(false);
        }

        // Финал такта — форсированный отчёт, но только если такт уже «звучал»:
        // короткие такты (изменений нет) не добавляют каналу ни одного запроса.
        internal static void Done(bool ok)
        {
            if (_off || !_sentAny) return;
            _phase = ok ? "done" : "not_confirmed";
            _entity = "";
            TrySend(true);
        }

        internal static void Fail(string message)
        {
            if (_off || !_sentAny) return;
            _phase = "error";
            _entity = Log.Mask(message ?? "");
            TrySend(true);
        }

        static void TrySend(bool force)
        {
            if (_off) return;
            int now = Environment.TickCount;
            if (!force)
            {
                // Прореживание: базовый интервал, при сетевых сбоях реже (2^n).
                long need = (long)_interval * 1000 << Math.Min(_netFailures, 5);
                if (now - _lastTick < need) return;
            }
            _lastTick = now;
            long elapsed = (now - _startTick) / 1000;
            Log.Line("ход такта: " + _phase
                     + (_entity.Length > 0 ? " " + _entity : "")
                     + (_n > 0 ? " " + _i + "/" + _n : "")
                     + (_rowsEntity > 0 ? ", строк " + _rowsEntity : "")
                     + (_rowsTotal > 0 ? " (всего строк " + _rowsTotal + ")" : "")
                     + ", " + elapsed + " с от начала такта");
            Dictionary<string, object> d = new Dictionary<string, object>();
            d["phase"] = _phase;
            d["entity"] = _entity;
            d["i"] = _i;
            d["n"] = _n;
            d["rows_entity"] = _rowsEntity;
            d["rows_total"] = _rowsTotal;
            d["elapsed_sec"] = elapsed;
            d["kind"] = _kind;
            d["seq"] = _seq;
            d["agent_version"] = C.Version;
            string verdict = _rx.PostProgress(Encoding.UTF8.GetBytes(Json.Ser(d)));
            if (verdict == null) { _sentAny = true; _netFailures = 0; }
            else if (verdict == "reject")
            {
                Log.Line("отчёт хода: приёмник отказал (нет ручки или права) — "
                         + "отчёты выключены до конца такта");
                _off = true;
            }
            else _netFailures++;   // сеть: попробуем позже и реже
        }
    }

    // ============================ Python-совместимое представление чисел ========
    // _cell в poc возвращает значение как есть, а csv.writer применяет str(): для
    // float это repr() CPython (shortest round-trip, порог научной записи 1e16,
    // "5.0" у целых). Воспроизводим посимвольно, иначе row_key витрины поедет.
    internal static class Py
    {
        internal static string PyFloat(double d)
        {
            if (double.IsNaN(d) || double.IsInfinity(d))
                throw new InvalidDataException("нечисловое значение double — такого в JSON быть не может");
            bool neg = BitConverter.DoubleToInt64Bits(d) < 0;
            double a = neg ? -d : d;
            if (a == 0.0) return neg ? "-0.0" : "0.0";
            // Кратчайшая строка, читающаяся обратно в то же double (G1..G17).
            string s = null;
            for (int p = 1; p <= 17; p++)
            {
                s = a.ToString("G" + p.ToString(CultureInfo.InvariantCulture), CultureInfo.InvariantCulture);
                double back;
                if (double.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out back) && back == a)
                    break;
            }
            int exp = 0;
            int ei = s.IndexOf('E');
            if (ei >= 0)
            {
                exp = int.Parse(s.Substring(ei + 1), CultureInfo.InvariantCulture);
                s = s.Substring(0, ei);
            }
            int dot = s.IndexOf('.');
            int ip = dot < 0 ? s.Length : dot;
            string digits = s.Replace(".", "");
            int z = 0;
            while (z < digits.Length && digits[z] == '0') z++;
            digits = digits.Substring(z).TrimEnd('0');
            int decpt = ip - z + exp;      // положение точки: value = 0.digits * 10^decpt
            if (digits.Length == 0) { digits = "0"; decpt = 1; }
            string res;
            if (decpt > -4 && decpt <= 16) // правило repr() CPython
            {
                if (decpt <= 0) res = "0." + new string('0', -decpt) + digits;
                else if (decpt >= digits.Length)
                    res = digits + new string('0', decpt - digits.Length) + ".0";
                else res = digits.Substring(0, decpt) + "." + digits.Substring(decpt);
            }
            else
            {
                int e2 = decpt - 1;
                string mant = digits.Length == 1 ? digits
                              : digits.Substring(0, 1) + "." + digits.Substring(1);
                res = mant + "e" + (e2 < 0 ? "-" : "+")
                      + Math.Abs(e2).ToString("00", CultureInfo.InvariantCulture);
            }
            return neg ? "-" + res : res;
        }

        // str() контейнера Python — редкий случай: у записи 2+ табличные части,
        // flatten не срабатывает, и в ячейку уходит repr списка/словаря (как в poc).
        internal static string PyContainerStr(object v)
        {
            StringBuilder sb = new StringBuilder();
            ReprInto(v, sb);
            return sb.ToString();
        }

        static void ReprInto(object v, StringBuilder sb)
        {
            if (v == null) { sb.Append("None"); return; }
            if (v is bool) { sb.Append((bool)v ? "True" : "False"); return; }
            string s = v as string;
            if (s != null) { StrReprInto(s, sb); return; }
            if (v is double) { sb.Append(PyFloat((double)v)); return; }
            if (v is int || v is long || v is decimal)
            {
                sb.Append(Convert.ToString(v, CultureInfo.InvariantCulture));
                return;
            }
            IDictionary<string, object> d = v as IDictionary<string, object>;
            if (d != null)
            {
                sb.Append('{');
                bool first = true;
                foreach (KeyValuePair<string, object> kv in d)
                {
                    if (!first) sb.Append(", ");
                    StrReprInto(kv.Key, sb);
                    sb.Append(": ");
                    ReprInto(kv.Value, sb);
                    first = false;
                }
                sb.Append('}');
                return;
            }
            IList l = v as IList;
            if (l != null)
            {
                sb.Append('[');
                for (int i = 0; i < l.Count; i++)
                {
                    if (i > 0) sb.Append(", ");
                    ReprInto(l[i], sb);
                }
                sb.Append(']');
                return;
            }
            throw new InvalidDataException("неподдерживаемый тип JSON-значения: " + v.GetType().Name);
        }

        // repr() строки Python: одинарные кавычки, если нет апострофа без кавычек —
        // двойные; escapes \n \r \t \\ и \xXX для управляющих.
        static void StrReprInto(string s, StringBuilder sb)
        {
            bool sq = s.IndexOf('\'') >= 0, dq = s.IndexOf('"') >= 0;
            char q = (sq && !dq) ? '"' : '\'';
            sb.Append(q);
            foreach (char ch in s)
            {
                if (ch == q || ch == '\\') { sb.Append('\\'); sb.Append(ch); }
                else if (ch == '\n') sb.Append("\\n");
                else if (ch == '\r') sb.Append("\\r");
                else if (ch == '\t') sb.Append("\\t");
                else if (ch < 0x20 || ch == 0x7f)
                    sb.Append("\\x" + ((int)ch).ToString("x2", CultureInfo.InvariantCulture));
                else sb.Append(ch);
                // NB: непечатные юникодные категории сверх \x7f Python экранирует
                // как \xXX/\uXXXX по unicodedata; в данных 1С не встречается (golden).
            }
            sb.Append(q);
        }
    }

    // ============================ safe_col / _cell / CSV (порт poc) =============
    internal static class Fmt
    {
        // Все файлы, которые пишет агент (CSV, манифест, план, индекс) — UTF-8 БЕЗ
        // BOM: манифест разбирает Python json на приёмнике, BOM его ломает.
        internal static readonly Encoding NoBom = new UTF8Encoding(false);

        // poc_load_entity.safe_col: str.isalnum() — категории L* и N* (Unicode),
        // иначе '_'; strip('_') с краёв; пустое/с цифры — приставка "c_".
        // Идём по КОДПОИНТАМ (суррогатные пары = один символ, как в Python).
        internal static string SafeCol(string name)
        {
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < name.Length; i++)
            {
                int cp;
                if (char.IsHighSurrogate(name[i]) && i + 1 < name.Length
                    && char.IsLowSurrogate(name[i + 1]))
                {
                    cp = char.ConvertToUtf32(name[i], name[i + 1]);
                    i++;
                }
                else cp = name[i];
                sb.Append(IsAlnum(cp) || cp == '_' ? char.ConvertFromUtf32(cp) : "_");
            }
            string s = sb.ToString().Trim('_');
            if (s.Length == 0 || IsDigit(char.ConvertToUtf32(s, 0)))
                s = "c_" + s;
            return s;
        }

        static bool IsAlnum(int cp)
        {
            UnicodeCategory uc = CharUnicodeInfo.GetUnicodeCategory(char.ConvertFromUtf32(cp), 0);
            switch (uc)
            {
                case UnicodeCategory.UppercaseLetter:
                case UnicodeCategory.LowercaseLetter:
                case UnicodeCategory.TitlecaseLetter:
                case UnicodeCategory.ModifierLetter:
                case UnicodeCategory.OtherLetter:
                case UnicodeCategory.DecimalDigitNumber:
                case UnicodeCategory.LetterNumber:
                case UnicodeCategory.OtherNumber:
                    return true;
                default:
                    return false;
            }
        }

        static bool IsDigit(int cp)
        {
            UnicodeCategory uc = CharUnicodeInfo.GetUnicodeCategory(char.ConvertFromUtf32(cp), 0);
            return uc == UnicodeCategory.DecimalDigitNumber || uc == UnicodeCategory.OtherNumber;
        }

        static readonly Regex DatetimeRe =
            new Regex(@"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})$", RegexOptions.Compiled);

        // poc_load_entity._cell + str() csv.writer'а.
        // NB: целые за пределами Int64 JavaScriptSerializer читает как double, и
        // Python-точность теряется — у 1С таких значений в текстовых выгрузках нет
        // (проверяется golden-пробой при появлении).
        internal static string Cell(object v)
        {
            if (v == null) return "";
            if (v is bool) return ((bool)v) ? "true" : "false";
            string s = v as string;
            if (s != null)
            {
                Match m = DatetimeRe.Match(s);
                return m.Success ? m.Groups[1].Value + " " + m.Groups[2].Value : s;
            }
            if (v is int || v is long) return Convert.ToString(v, CultureInfo.InvariantCulture);
            if (v is decimal) return ((decimal)v).ToString(CultureInfo.InvariantCulture);
            if (v is double) return Py.PyFloat((double)v);
            if (v is IDictionary<string, object> || v is IList) return Py.PyContainerStr(v);
            throw new InvalidDataException("неподдерживаемый тип значения ячейки: " + v.GetType().Name);
        }

        // Диалект Python csv по умолчанию: quote '"', удвоение, разделитель ',',
        // конец строки CRLF. Файл — UTF-8 БЕЗ BOM.
        internal static void CsvRow(Stream outStream, byte[] buf, IList<string> cells)
        {
            for (int i = 0; i < cells.Count; i++)
            {
                if (i > 0) WriteRaw(outStream, buf, ",");
                WriteField(outStream, buf, cells[i] ?? "");
            }
            WriteRaw(outStream, buf, "\r\n");
        }

        static void WriteField(Stream outStream, byte[] buf, string cell)
        {
            bool quote = cell.IndexOfAny(new char[] { '"', ',', '\r', '\n' }) >= 0;
            if (!quote) { WriteRaw(outStream, buf, cell); return; }
            WriteRaw(outStream, buf, "\"");
            WriteRaw(outStream, buf, cell.Replace("\"", "\"\""));
            WriteRaw(outStream, buf, "\"");
        }

        // Запись строки в UTF-8 кусками под размер буфера: ячейка может быть
        // мегабайтами (у 1С бывают строки по 19 МБ), а GetBytes требует, чтобы
        // влезал весь кусок. Разрез не должен попадать внутрь суррогатной пары.
        internal static void WriteRaw(Stream outStream, byte[] buf, string s)
        {
            int pos = 0;
            while (pos < s.Length)
            {
                int chars = Math.Min(buf.Length / 4, s.Length - pos);
                if (pos + chars < s.Length && char.IsHighSurrogate(s[pos + chars - 1]))
                    chars--;
                if (chars <= 0) chars = 1;
                int n = Encoding.UTF8.GetBytes(s, pos, chars, buf, 0);
                outStream.Write(buf, 0, n);
                pos += chars;
            }
        }
    }

    // ============================ JSON ==========================================
    internal static class Json
    {
        internal static JavaScriptSerializer Make()
        {
            JavaScriptSerializer js = new JavaScriptSerializer();
            js.MaxJsonLength = int.MaxValue;   // страницы OData крупные
            js.RecursionLimit = 1000;
            return js;
        }

        // NB: Dictionary<string,object> в .NET Framework 4 сохраняет порядок вставки
        // (без удалений) — на этом держится union колонок в порядке первого появления,
        // как у dict в poc. JavaScriptSerializer даёт вложенные Dictionary и ArrayList.
        internal static Dictionary<string, object> Obj(string json)
        {
            return Make().Deserialize<Dictionary<string, object>>(json);
        }

        internal static string Ser(object o)
        {
            return Make().Serialize(o);
        }
    }
}

namespace PacketAgent
{
    // ============================ $metadata (разбор как в poc) ==================
    // Те же regex, что poc_load_entity._load_metadata: ключи и типы полей из XML.
    internal sealed class Meta
    {
        readonly Dictionary<string, List<string>> _keys = new Dictionary<string, List<string>>();
        readonly Dictionary<string, List<KeyValuePair<string, string>>> _props =
            new Dictionary<string, List<KeyValuePair<string, string>>>();
        readonly Dictionary<string, string> _ownerCache = new Dictionary<string, string>();
        internal string Fingerprint;   // sha256:<hex> байт metadata.xml

        internal static Meta Parse(byte[] xmlBytes)
        {
            Meta m = new Meta();
            using (SHA256 sha = SHA256.Create())
                m.Fingerprint = "sha256:" + BitConverter.ToString(
                    sha.ComputeHash(xmlBytes)).Replace("-", "").ToLowerInvariant();
            string xml = Encoding.UTF8.GetString(xmlBytes);
            foreach (Match em in Regex.Matches(xml,
                         @"<EntityType\s+Name=""([^""]+)""(.*?)</EntityType>",
                         RegexOptions.Singleline))
            {
                string body = em.Groups[2].Value;
                List<string> key = new List<string>();
                Match km = Regex.Match(body, @"<Key>(.*?)</Key>", RegexOptions.Singleline);
                if (km.Success)
                    foreach (Match pm in Regex.Matches(km.Groups[1].Value,
                                 @"<PropertyRef\s+Name=""([^""]+)"""))
                        key.Add(pm.Groups[1].Value);
                m._keys[em.Groups[1].Value] = key;
                List<KeyValuePair<string, string>> props = new List<KeyValuePair<string, string>>();
                foreach (Match pm in Regex.Matches(body,
                             @"<Property\s+Name=""([^""]+)""\s+Type=""([^""]+)"""))
                    props.Add(new KeyValuePair<string, string>(pm.Groups[1].Value, pm.Groups[2].Value));
                m._props[em.Groups[1].Value] = props;
            }
            return m;
        }

        internal bool HasEntity(string entity)
        {
            return _props.ContainsKey(entity);
        }

        // declared_key из $metadata — источник правды, в т.ч. составной.
        internal List<string> DeclaredKey(string entity)
        {
            List<string> k;
            return _keys.TryGetValue(entity, out k) ? k : new List<string>();
        }

        // Свойства, объявленные самой сущностью (не вложенным типом) — защита
        // реквизитов шапки при развороте (poc.own_props).
        internal HashSet<string> OwnProps(string entity)
        {
            List<KeyValuePair<string, string>> p;
            HashSet<string> s = new HashSet<string>();
            if (_props.TryGetValue(entity, out p))
                foreach (KeyValuePair<string, string> kv in p) s.Add(kv.Key);
            return s;
        }

        // Порядок страниц — по объявленному ключу, без служебных *_Type (poc._order_by).
        // Ключа нет — null (тогда одна страница либо честная ошибка полноты).
        internal string OrderBy(string entity)
        {
            List<string> key = DeclaredKey(entity);
            if (key.Count == 0) return null;
            List<string> cols = new List<string>();
            foreach (string k in key) if (!k.EndsWith("_Type", StringComparison.Ordinal)) cols.Add(k);
            if (cols.Count == 0) cols = key;
            return string.Join(",", cols.ToArray());
        }

        // Есть ли у сущности версионирование платформы (Ref_Key + DataVersion).
        internal bool HasVersions(string entity)
        {
            HashSet<string> own = OwnProps(entity);
            return own.Contains("Ref_Key") && own.Contains("DataVersion");
        }

        // Владелец табличной части (poc.owner_of): у части есть Ref_Key, нет своей
        // DataVersion; кандидат — префикс имени от длинного к короткому, у которого
        // и Ref_Key, и DataVersion есть. null — владельца нет (грузим полностью).
        internal string OwnerOf(string entity)
        {
            string cached;
            if (_ownerCache.TryGetValue(entity, out cached)) return cached;
            string res = null;
            HashSet<string> own = OwnProps(entity);
            if (own.Contains("Ref_Key") && !own.Contains("DataVersion"))
            {
                string[] parts = entity.Split('_');
                for (int cut = parts.Length - 1; cut > 0 && res == null; cut--)
                {
                    string cand = string.Join("_", parts, 0, cut);
                    HashSet<string> cp = OwnProps(cand);
                    if (cp.Contains("Ref_Key") && cp.Contains("DataVersion")) res = cand;
                }
            }
            _ownerCache[entity] = res;
            return res;
        }

        // $select без полей, которые OData 1С физически не отдаёт (poc._select_of):
        // Edm.Stream / Edm.Binary. Запасной вариант, только после двух отказов.
        internal string SelectOf(string entity)
        {
            List<KeyValuePair<string, string>> p;
            if (!_props.TryGetValue(entity, out p)) return "";
            List<string> keep = new List<string>();
            List<string> bad = new List<string>();
            foreach (KeyValuePair<string, string> kv in p)
            {
                if (kv.Value == "Edm.Stream" || kv.Value == "Edm.Binary") bad.Add(kv.Key);
                else keep.Add(kv.Key);
            }
            if (bad.Count == 0 || keep.Count == 0) return "";
            Log.Line("    " + entity + ": пропущены поля, которые OData 1С не отдаёт "
                     + "(Edm.Stream/Edm.Binary): " + string.Join(", ", bad.ToArray()));
            return string.Join(",", keep.ToArray());
        }
    }

    // ============================ разворот вложенных наборов (poc._flatten_nested)
    // Правило структурное: у записи ровно одно поле — непустой список объектов —
    // настоящие строки лежат в нём, внешние скалярные поля общие. У ссылочного
    // объекта (declared_key == [Ref_Key]) реквизиты шапки значениями строк не
    // затираются; у обёртки набора строка и есть данные.
    internal static class Flatten
    {
        internal static List<Dictionary<string, object>> Rows(
            IList rows, string entity, Meta meta)
        {
            bool known = entity != null && meta != null && meta.HasEntity(entity);
            // Синтетические фикстуры golden-пробы (entity не из $metadata) — режим
            // entity_set=None у poc: без разворота. Боевая сущность без свойств в
            // $metadata — fail-closed, как в poc.
            if (entity != null && meta != null && !known && !entity.StartsWith("_", StringComparison.Ordinal))
                throw new InvalidDataException("нет свойств " + entity + " в $metadata — "
                    + "загрузка отменена, иначе реквизиты шапки будут затёрты значениями строк");
            HashSet<string> own = known ? meta.OwnProps(entity) : new HashSet<string>();
            List<string> dk = known ? meta.DeclaredKey(entity) : new List<string>();
            bool isObject = known && dk.Count == 1 && dk[0] == "Ref_Key";

            List<Dictionary<string, object>> outRows = new List<Dictionary<string, object>>();
            foreach (object ro in rows)
            {
                IDictionary<string, object> r = ro as IDictionary<string, object>;
                if (r == null) continue;
                List<string> nested = new List<string>();
                foreach (KeyValuePair<string, object> kv in r)
                {
                    IList l = kv.Value as IList;
                    if (l != null && l.Count > 0 && l[0] is IDictionary<string, object>)
                        nested.Add(kv.Key);
                }
                if (nested.Count != 1)
                {
                    outRows.Add(new Dictionary<string, object>(r));
                    continue;
                }
                string k = nested[0];
                Dictionary<string, object> outer = new Dictionary<string, object>();
                foreach (KeyValuePair<string, object> kv in r)
                    if (kv.Key != k) outer[kv.Key] = kv.Value;
                foreach (object io in (IList)r[k])
                {
                    IDictionary<string, object> inner = io as IDictionary<string, object>;
                    if (inner == null) continue;
                    Dictionary<string, object> merged = new Dictionary<string, object>(outer);
                    foreach (KeyValuePair<string, object> kv in inner)
                    {
                        if (isObject && own.Contains(kv.Key)) continue; // реквизит шапки не затирается
                        merged[kv.Key] = kv.Value;
                    }
                    outRows.Add(merged);
                }
            }
            return outRows;
        }

        // Union полей в порядке первого появления (poc: dict.fromkeys по строкам).
        internal static List<string> UnionCols(List<Dictionary<string, object>> rows)
        {
            List<string> cols = new List<string>();
            HashSet<string> seen = new HashSet<string>();
            foreach (Dictionary<string, object> r in rows)
                foreach (string k in r.Keys)
                    if (seen.Add(k)) cols.Add(k);
            return cols;
        }

        // Заголовок + строки в CSV-байты (UTF-8 без BOM, CRLF) — контракт К5.
        internal static byte[] CsvBytes(List<string> cols, List<Dictionary<string, object>> rows,
                                        int rowFrom, int rowTo)
        {
            MemoryStream ms = new MemoryStream();
            byte[] buf = new byte[65536];
            string[] header = new string[cols.Count];
            for (int i = 0; i < cols.Count; i++) header[i] = Fmt.SafeCol(cols[i]);
            Fmt.CsvRow(ms, buf, header);
            for (int ri = rowFrom; ri < rowTo; ri++)
            {
                Dictionary<string, object> r = rows[ri];
                string[] cells = new string[cols.Count];
                for (int i = 0; i < cols.Count; i++)
                {
                    object v;
                    cells[i] = Fmt.Cell(r.TryGetValue(cols[i], out v) ? v : null);
                }
                Fmt.CsvRow(ms, buf, cells);
            }
            return ms.ToArray();
        }
    }
}

namespace PacketAgent
{
    // 404 при дотяжке — записи уже нет в 1С (gone), отдельный тип, чтобы отличить
    // от сбоев сети.
    internal sealed class OdataNotFoundException : Exception
    {
        internal OdataNotFoundException(string msg) : base(msg) { }
    }

    // Отказ в доступе (401/403, RLS 500 «ограничение доступа»): уменьшение страницы
    // и повторы бессмысленны — прав от них не прибудет, а каждая попытка на
    // RLS-сущности стоит десятки секунд (замер 09.08: регистры УТ по ~4 мин на
    // пропуск → вся полная выгрузка растягивалась на сутки).
    // Reason — машиночитаемая причина (ресерч 4.1/4.4, docs/research/): rls_or_no_right
    // (401 + код 20; развилку решает allowedOnly-проба), auth_failed (401 без
    // OData-тела — отказ веб-сервера), infra_blocked (403), rls_error (500 от RLS-шаблона).
    internal sealed class OdataDeniedException : Exception
    {
        internal readonly string Reason;
        internal OdataDeniedException(string msg, string reason) : base(msg) { Reason = reason; }
    }

    // ============================ клиент OData 1С ===============================
    // Порт poc_load_entity: fetch_all / проба версий / прямой доступ по ключу.
    // Авторизация — HTTP Basic (ai_reader на IIS-публикации).
    internal sealed class OData
    {
        readonly Cfg _cfg;
        readonly string _auth;
        Meta _meta;

        internal OData(Cfg cfg, Meta meta)
        {
            _cfg = cfg;
            _meta = meta;
            _auth = "Basic " + Convert.ToBase64String(
                Encoding.UTF8.GetBytes(cfg.OdataUser + ":" + cfg.OdataPassword));
        }

        internal Meta Meta { set { _meta = value; } }

        // Фолбэк allowedOnly=true (ресерч 4.4): читать только разрешённые записи —
        // применяется наверху как ПОСЛЕДНЯЯ ступень после отказа RLS, чтобы отдать
        // легально читаемое подмножество вместо полного пропуска сущности.
        internal bool AllowedOnly;

        HttpWebRequest NewRequest(string url)
        {
            HttpWebRequest req = (HttpWebRequest)WebRequest.Create(url);
            req.Headers["Authorization"] = _auth;
            req.Timeout = C.HttpTimeoutSeconds * 1000;
            req.ReadWriteTimeout = C.HttpTimeoutSeconds * 1000;
            return req;
        }

        internal static string Q(string s) { return Uri.EscapeDataString(s); }

        static string ReadAll(HttpWebResponse resp)
        {
            using (Stream s = resp.GetResponseStream())
            using (StreamReader r = new StreamReader(s, Encoding.UTF8))
                return r.ReadToEnd();
        }

        // Сырые байты ответа (для $metadata — отпечаток считается по байтам).
        internal byte[] GetBytes(string url)
        {
            HttpWebRequest req = NewRequest(url);
            using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
            using (Stream s = resp.GetResponseStream())
            using (MemoryStream ms = new MemoryStream())
            {
                s.CopyTo(ms);
                return ms.ToArray();
            }
        }

        internal byte[] GetMetadata()
        {
            return GetBytes(_cfg.OdataUrl + "/$metadata");
        }

        // _get_json: обычный запрос -> повтор -> $select без неотдаваемых полей.
        // 404 — отдельное исключение (дотяжка удалённой записи). Таймауты и обрывы
        // не повторяются здесь — их решает уменьшение страницы наверху (К6).
        internal Dictionary<string, object> GetJson(string entity, Dictionary<string, string> prm,
                                                    string key)
        {
            if (AllowedOnly && prm != null && !prm.ContainsKey("allowedOnly"))
            {
                Dictionary<string, string> p3 = new Dictionary<string, string>(prm);
                p3["allowedOnly"] = "true";
                prm = p3;
            }
            string seg = Q(entity) + (key != null ? "(guid'" + key + "')" : "");
            string url = _cfg.OdataUrl + "/" + seg + "?" + BuildQuery(prm);
            try
            {
                return Json.Obj(ReadAll((HttpWebResponse)NewRequest(url).GetResponse()));
            }
            catch (WebException we)
            {
                RethrowMapped(entity, key, we);
                CloseResp(we);
            }
            try {   // 2. просто ещё раз — часть отказов 1С разовые
                return Json.Obj(ReadAll((HttpWebResponse)NewRequest(url).GetResponse()));
            }
            catch (WebException we) { RethrowMapped(entity, key, we); CloseResp(we); }
            string sel = _meta.SelectOf(entity);   // 3. по-другому
            if (sel.Length == 0) throw new InvalidDataException(entity + ": 1С не отвечает");
            Dictionary<string, string> p2 = new Dictionary<string, string>(prm);
            p2["$select"] = sel;
            string url2 = _cfg.OdataUrl + "/" + seg + "?" + BuildQuery(p2);
            return Json.Obj(ReadAll((HttpWebResponse)NewRequest(url2).GetResponse()));
        }

        // Единый разбор HTTP-ошибок OData: 404 → OdataNotFoundException (gone),
        // 401/403 и 500-RLS → OdataDeniedException (страница/повторы бессмысленны).
        // Не замаплено — возврат, решает вызывающий.
        static void RethrowMapped(string entity, string key, WebException we)
        {
            HttpWebResponse resp = we.Response as HttpWebResponse;
            if (resp == null) return;
            if (resp.StatusCode == HttpStatusCode.NotFound)
            {
                resp.Close();
                throw new OdataNotFoundException(entity + " " + (key ?? "") + ": HTTP 404");
            }
            if (resp.StatusCode == HttpStatusCode.Unauthorized
                || resp.StatusCode == HttpStatusCode.Forbidden)
            {
                HttpStatusCode sc = resp.StatusCode;
                // Классификация (ресерч 4.1): 403 платформенный OData для прав не
                // использует — это инфраструктура (IIS ACL/прокси). 401 с кодом 20 —
                // «нет роли» или «RLS без allowedOnly» (развилка — allowedOnly-пробой
                // наверху); 401 без OData-тела — отказ аутентификации веб-сервера.
                if (sc == HttpStatusCode.Forbidden)
                {
                    resp.Close();
                    throw new OdataDeniedException(entity + ": HTTP 403 — инфраструктурный отказ (IIS/прокси)", "infra_blocked");
                }
                string eb = ReadErrorBody(resp);
                bool code20 = eb.IndexOf(">20<", StringComparison.Ordinal) >= 0
                              || eb.IndexOf("\"code\":\"20\"", StringComparison.Ordinal) >= 0
                              || eb.IndexOf("\"code\": \"20\"", StringComparison.Ordinal) >= 0
                              || eb.IndexOf("\"code\":20", StringComparison.Ordinal) >= 0;
                if (code20)
                    throw new OdataDeniedException(entity + ": HTTP 401 (код 20 — права/RLS)", "rls_or_no_right");
                throw new OdataDeniedException(entity + ": HTTP 401 без OData-тела — аутентификация (веб-сервер)", "auth_failed");
            }
            // 500: RLS-шаблон 1С падает с «ограничение доступа» в теле — это отказ,
            // а не «крупная страница»; сужать её бесполезно (замер 09.08).
            if (resp.StatusCode == HttpStatusCode.InternalServerError)
            {
                string eb = ReadErrorBody(resp);
                if (eb.IndexOf("ограничен", StringComparison.OrdinalIgnoreCase) >= 0
                    || eb.IndexOf("оступ запрещен", StringComparison.OrdinalIgnoreCase) >= 0)
                    throw new OdataDeniedException(entity + ": HTTP 500 (ограничение доступа RLS)", "rls_error");
            }
        }

        internal static void CloseResp(WebException we)
        {
            if (we.Response != null) we.Response.Close();
        }

        static string ReadErrorBody(HttpWebResponse resp)
        {
            try
            {
                using (Stream s = resp.GetResponseStream())
                using (StreamReader r = new StreamReader(s, Encoding.UTF8))
                    return r.ReadToEnd();
            }
            catch { return ""; }
            finally { try { resp.Close(); } catch { } }
        }

        static string BuildQuery(Dictionary<string, string> prm)
        {
            List<string> parts = new List<string>();
            foreach (KeyValuePair<string, string> kv in prm)
                parts.Add(kv.Key + "=" + Q(kv.Value));
            return string.Join("&", parts.ToArray());
        }

        // Проба версий БЕЗ перебора вариантов (poc._fetch_page_doc): подменённый
        // $select сделал бы пробу дорогой.
        internal Dictionary<string, object> FetchPageDoc(string entity, Dictionary<string, string> prm)
        {
            if (AllowedOnly && prm != null && !prm.ContainsKey("allowedOnly"))
            {
                Dictionary<string, string> p3 = new Dictionary<string, string>(prm);
                p3["allowedOnly"] = "true";
                prm = p3;
            }
            string url = _cfg.OdataUrl + "/" + Q(entity) + "?" + BuildQuery(prm);
            try
            {
                return Json.Obj(ReadAll((HttpWebResponse)NewRequest(url).GetResponse()));
            }
            catch (WebException we)
            {
                RethrowMapped(entity, null, we);
                CloseResp(we);
                throw;
            }
        }

        internal int CountOf(string entity)
        {
            try
            {
                HttpWebRequest req = NewRequest(_cfg.OdataUrl + "/" + Q(entity) + "/$count");
                using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                using (StreamReader r = new StreamReader(resp.GetResponseStream()))
                    return int.Parse(r.ReadToEnd().Trim(), CultureInfo.InvariantCulture);
            }
            catch { return -1; }
        }

        static IList ValueOf(Dictionary<string, object> doc)
        {
            object v;
            return doc.TryGetValue("value", out v) ? (v as IList ?? new ArrayList()) : new ArrayList();
        }

        static int ExpectedOf(Dictionary<string, object> doc)
        {
            object c;
            if (!doc.TryGetValue("odata.count", out c) && !doc.TryGetValue("__count", out c))
                return -1;
            try { return Convert.ToInt32(c, CultureInfo.InvariantCulture); }
            catch { return -1; }
        }

        // fetch_all: первая страница БЕЗ $orderby и с $inlinecount; данных больше
        // страницы — заново с $orderby по объявленному ключу; HTTP-ошибка — страница
        // вчетверо до page_min и сущность читается СНАЧАЛА; сверка с odata.count.
        internal List<Dictionary<string, object>> FetchAll(string entity)
        {
            int expected = -1, page = _cfg.PageSize, skip = 0, shortPages = 0;
            string order = "";
            bool first = true;
            List<Dictionary<string, object>> rows = new List<Dictionary<string, object>>();
            while (true)
            {
                Dictionary<string, string> prm = new Dictionary<string, string>();
                prm["$format"] = "json";
                prm["$top"] = page.ToString(CultureInfo.InvariantCulture);
                prm["$skip"] = skip.ToString(CultureInfo.InvariantCulture);
                if (first) prm["$inlinecount"] = "allpages";
                if (order.Length > 0) prm["$orderby"] = order;
                IList v;
                try
                {
                    Dictionary<string, object> doc = GetJson(entity, prm, null);
                    v = ValueOf(doc);
                    if (first)
                    {
                        first = false;
                        expected = ExpectedOf(doc);
                        if (v.Count >= page && (expected < 0 || expected > page))
                        {
                            order = _meta.OrderBy(entity) ?? "";
                            if (order.Length > 0)
                            {
                                rows = new List<Dictionary<string, object>>();
                                skip = 0; shortPages = 0;
                                continue;
                            }
                        }
                        if (expected < 0) expected = CountOf(entity);
                    }
                }
                catch (OdataNotFoundException) { throw; }
                catch (OdataDeniedException) { throw; }   // отказ в доступе — страница ни при чём
                catch (Exception)
                {
                    // Страница уменьшается, а не сущность теряется (К6): при меньшей
                    // странице появляется постраничность, а с ней обязателен $orderby,
                    // поэтому начинаем сущность заново, а не продолжаем с середины.
                    if (page <= _cfg.PageMin) throw;
                    page = Math.Max(_cfg.PageMin, page / 4);
                    order = (expected < 0 || expected > page) ? (_meta.OrderBy(entity) ?? "") : "";
                    rows = new List<Dictionary<string, object>>();
                    skip = 0; shortPages = 0; first = true;
                    Log.Line("    " + entity + ": страница уменьшена до " + page
                             + " — 1С не отдала крупную");
                    continue;
                }
                if (v.Count == 0) break;
                foreach (object o in v)
                {
                    IDictionary<string, object> d = o as IDictionary<string, object>;
                    if (d != null) rows.Add(new Dictionary<string, object>(d));
                }
                skip += v.Count;
                Progress.Rows(rows.Count);   // ход внутри крупной сущности
                if (v.Count < page)
                {
                    shortPages++;
                    if (expected >= 0 && rows.Count >= expected) break;
                    if (expected < 0 && shortPages > 1) break;
                }
            }
            return rows;
        }

        // Проба версий (порт пробы load_entity_delta): $select=Ref_Key,DataVersion,
        // та же дисциплина страниц. null — проба неполная/не удалась: дельта отменяется.
        internal Dictionary<string, string> ProbeVersions(string entity)
        {
            int expected = -1, top = _cfg.PageSize, skip = 0;
            bool first = true;
            Dictionary<string, string> probe = new Dictionary<string, string>();
            while (true)
            {
                Dictionary<string, string> prm = new Dictionary<string, string>();
                prm["$format"] = "json";
                prm["$select"] = "Ref_Key,DataVersion";
                prm["$top"] = top.ToString(CultureInfo.InvariantCulture);
                prm["$skip"] = skip.ToString(CultureInfo.InvariantCulture);
                if (first) prm["$inlinecount"] = "allpages";
                if (!first && (expected < 0 || expected > top)) prm["$orderby"] = "Ref_Key";
                IList page;
                try
                {
                    Dictionary<string, object> doc = FetchPageDoc(entity, prm);
                    page = ValueOf(doc);
                    if (first)
                    {
                        first = false;
                        expected = ExpectedOf(doc);
                        if (expected < 0) expected = CountOf(entity);
                        if (page.Count >= top && (expected < 0 || expected > top))
                        {
                            probe = new Dictionary<string, string>();
                            skip = 0;
                            continue;
                        }
                    }
                }
                catch (OdataNotFoundException) { throw; }
                catch (OdataDeniedException) { throw; }   // отказ в доступе — страница ни при чём
                catch (Exception)
                {
                    if (top <= _cfg.PageMin) return null;
                    top = Math.Max(_cfg.PageMin, top / 4);
                    probe = new Dictionary<string, string>();
                    skip = 0; first = true;
                    continue;
                }
                if (page.Count == 0) break;
                foreach (object o in page)
                {
                    IDictionary<string, object> d = o as IDictionary<string, object>;
                    if (d == null) continue;
                    object rk, dv;
                    if (!d.TryGetValue("Ref_Key", out rk) || rk == null) continue;
                    d.TryGetValue("DataVersion", out dv);
                    probe[Convert.ToString(rk, CultureInfo.InvariantCulture)] =
                        dv == null ? "" : Convert.ToString(dv, CultureInfo.InvariantCulture);
                }
                skip += page.Count;
                Progress.Rows(probe.Count);   // ход пробы версий (дельта-путь)
                if (expected >= 0 && probe.Count >= expected) break;
            }
            // Неполная проба — не дельта: живые записи выглядели бы «удалёнными».
            if (expected >= 0 && probe.Count < expected) return null;
            return probe;
        }

        // Дотяжка записи прямым доступом Сущность(guid'…'). 404 — записи уже нет.
        internal Dictionary<string, object> FetchByKey(string entity, string key)
        {
            Dictionary<string, string> prm = new Dictionary<string, string>();
            prm["$format"] = "json";
            Dictionary<string, object> obj = GetJson(entity, prm, key);
            object rk;
            if (obj != null && obj.TryGetValue("Ref_Key", out rk) && rk != null) return obj;
            return null;
        }
    }
}

namespace PacketAgent
{
    // ============================ локальный индекс версий =======================
    // data_dir/index/<entity>.idx — текстовый файл:
    //   #packet-agent-index v1
    //   version_fingerprint=sha256:<hex>     (может быть пустым)
    //   content_fingerprint=sha256:<hex>     (может быть пустым)
    //   Ref_Key\tDataVersion                 (по строке на запись, порядок — сортировка)
    //
    // 🔴 ФОРМУЛЫ ОТПЕЧАТКОВ (зафиксированы в PACKET_CONTRACT.md §5, непрозрачны
    // для приёмника):
    //   version_fingerprint = sha256( UTF8( "Ref_Key\tDataVersion\n" ... ) ),
    //     строки в порядке сортировки Ref_Key (ordinal), DataVersion отсутствует → "";
    //   content_fingerprint = sha256( CSV-байты полного прочтения ): заголовок +
    //     строки ровно в том виде, в каком агент их пишет (К5), порядок строк —
    //     порядок чтения fetch_all (при постраничности — $orderby по объявленному
    //     ключу, что делает порядок стабильным).
    // Потеря/порча индекса → полное прочтение сущности (контракт §10).
    internal sealed class EntityIndex
    {
        internal Dictionary<string, string> Versions = new Dictionary<string, string>();
        internal string VersionFp = "";
        internal string ContentFp = "";

        internal static string PathOf(string dataDir, string entity)
        {
            return Path.Combine(dataDir, "index", entity + ".idx");
        }

        internal static EntityIndex Load(string dataDir, string entity)
        {
            string path = PathOf(dataDir, entity);
            if (!File.Exists(path)) return null;
            try
            {
                EntityIndex idx = new EntityIndex();
                foreach (string line in File.ReadAllLines(path, Encoding.UTF8))
                {
                    if (line.Length == 0 || line.StartsWith("#", StringComparison.Ordinal)) continue;
                    if (line.StartsWith("version_fingerprint=", StringComparison.Ordinal))
                    {
                        idx.VersionFp = line.Substring("version_fingerprint=".Length);
                        continue;
                    }
                    if (line.StartsWith("content_fingerprint=", StringComparison.Ordinal))
                    {
                        idx.ContentFp = line.Substring("content_fingerprint=".Length);
                        continue;
                    }
                    int tab = line.IndexOf('\t');
                    if (tab <= 0) continue;
                    idx.Versions[line.Substring(0, tab)] = line.Substring(tab + 1);
                }
                return idx;
            }
            catch (Exception e)
            {
                Log.Line("индекс " + entity + " не читается (" + e.Message + ") — полное прочтение");
                return null;
            }
        }

        // Атомарная замена: temp + move (File.Replace на одном томе).
        internal static void SaveAtomic(string dataDir, string entity,
                                        Dictionary<string, string> versions,
                                        string versionFp, string contentFp)
        {
            string path = PathOf(dataDir, entity);
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            string tmp = path + ".tmp";
            List<string> keys = versions != null
                ? new List<string>(versions.Keys) : new List<string>();
            keys.Sort(StringComparer.Ordinal);
            using (StreamWriter w = new StreamWriter(tmp, false, Fmt.NoBom))
            {
                w.NewLine = "\n";
                w.WriteLine("#packet-agent-index v1");
                w.WriteLine("version_fingerprint=" + (versionFp ?? ""));
                w.WriteLine("content_fingerprint=" + (contentFp ?? ""));
                foreach (string k in keys)
                    w.WriteLine(k + "\t" + (versions[k] ?? ""));
            }
            if (File.Exists(path)) File.Replace(tmp, path, null);
            else File.Move(tmp, path);
        }

        internal static string VersionFingerprint(Dictionary<string, string> versions)
        {
            List<string> keys = new List<string>(versions.Keys);
            keys.Sort(StringComparer.Ordinal);
            MemoryStream ms = new MemoryStream();
            byte[] buf = new byte[65536];
            foreach (string k in keys)
                Fmt.WriteRaw(ms, buf, k + "\t" + (versions[k] ?? "") + "\n");
            return "sha256:" + HashHex(ms.ToArray());
        }

        internal static string HashHex(byte[] bytes)
        {
            using (SHA256 sha = SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(bytes))
                    .Replace("-", "").ToLowerInvariant();
        }
    }

    // ============================ состояние агента ==============================
    // data_dir/state.json: seq последнего отправленного пакета, config_version,
    // отпечаток $metadata, флаги resync/full_done. Pubkey сервера здесь НЕ живёт —
    // его место вместе с контуром в config.json (ServerConfig).
    internal sealed class AgentState
    {
        internal long Seq;
        internal long ConfigVersion;
        internal string MetadataFingerprint = "";
        internal string SkippedFp = "";     // отпечаток набора пропущенных сущностей (видимость п. 13)
        internal bool Resync;
        internal bool FullDone;
        // Доставка подтверждена приёмником (smoke). Без флага «state.json есть»
        // неотличим от «smoke упал» (замер 09.08: 401 → пакет снят, state записан,
        // установщик пропустил повторный smoke — канал недоказан навсегда).
        internal bool SmokeOk;

        string _path;   // присваивается в Load, дальше только Save

        internal static AgentState Load(string dataDir)
        {
            AgentState st = new AgentState();
            st._path = Path.Combine(dataDir, "state.json");
            if (!File.Exists(st._path)) return st;
            try
            {
                Dictionary<string, object> d = Json.Obj(File.ReadAllText(st._path, Encoding.UTF8));
                st.Seq = GetLong(d, "seq");
                st.ConfigVersion = GetLong(d, "config_version");
                object v;
                if (d.TryGetValue("metadata_fingerprint", out v) && v != null)
                    st.MetadataFingerprint = Convert.ToString(v, CultureInfo.InvariantCulture);
                if (d.TryGetValue("skipped_fp", out v) && v != null)
                    st.SkippedFp = Convert.ToString(v, CultureInfo.InvariantCulture);
                st.Resync = GetBool(d, "resync");
                st.FullDone = GetBool(d, "full_done");
                st.SmokeOk = GetBool(d, "smoke_ok");
            }
            catch (Exception e)
            {
                Log.Line("state.json не читается (" + e.Message + ") — работаем с нуля");
            }
            return st;
        }

        static long GetLong(Dictionary<string, object> d, string k)
        {
            object v;
            if (!d.TryGetValue(k, out v) || v == null) return 0;
            try { return Convert.ToInt64(v, CultureInfo.InvariantCulture); }
            catch { return 0; }
        }

        static bool GetBool(Dictionary<string, object> d, string k)
        {
            object v;
            if (!d.TryGetValue(k, out v) || v == null) return false;
            return v is bool && (bool)v;
        }

        internal void Save()
        {
            Dictionary<string, object> d = new Dictionary<string, object>();
            d["seq"] = Seq;
            d["config_version"] = ConfigVersion;
            d["metadata_fingerprint"] = MetadataFingerprint;
            d["skipped_fp"] = SkippedFp;
            d["resync"] = Resync;
            d["full_done"] = FullDone;
            d["smoke_ok"] = SmokeOk;
            Directory.CreateDirectory(Path.GetDirectoryName(_path));
            string tmp = _path + ".tmp";
            File.WriteAllText(tmp, Json.Ser(d), Fmt.NoBom);
            if (File.Exists(_path)) File.Replace(tmp, _path, null);
            else File.Move(tmp, _path);
        }
    }

    // ============================ сохранённый конфиг сервера ====================
    // data_dir/config.json — ПОСЛЕДНИЙ ПОЛНЫЙ конфиг с приёмника (entities, params,
    // config_version, recipient_pubkey). Зачем: приёмник отвечает «304-подобно»
    // ({"config_version": N} без entities), когда версия не изменилась, — без снимка
    // на диске агент после рестарта/переустановки оставался без контура навсегда
    // (живой E2E 07.08). Pubkey сервера тоже здесь — ротация через /agent/config.
    internal sealed class ServerConfig
    {
        internal long ConfigVersion;
        internal List<string> Entities = new List<string>();
        internal Dictionary<string, object> Params = new Dictionary<string, object>();
        internal string RecipientPubkey = "";

        internal static string PathOf(string dataDir)
        {
            return Path.Combine(dataDir, "config.json");
        }

        internal static ServerConfig Load(string dataDir)
        {
            string path = PathOf(dataDir);
            if (!File.Exists(path)) return null;
            try
            {
                Dictionary<string, object> d = Json.Obj(File.ReadAllText(path, Encoding.UTF8));
                ServerConfig c = new ServerConfig();
                c.ConfigVersion = Receiver.Long(d, "config_version", 0);
                c.Entities = Receiver.StrList(d, "entities");
                object pv;
                IDictionary<string, object> prm =
                    d.TryGetValue("params", out pv) ? pv as IDictionary<string, object> : null;
                if (prm != null)
                    foreach (KeyValuePair<string, object> kv in prm) c.Params[kv.Key] = kv.Value;
                c.RecipientPubkey = Receiver.Str(d, "recipient_pubkey") ?? "";
                return c;
            }
            catch (Exception e)
            {
                Log.Line("config.json не читается (" + e.Message + ") — конфиг будет запрошен полностью");
                return null;
            }
        }

        // Полный ответ /agent/config (с ключом entities) → снимок. entities может
        // быть и пустым массивом — это авторитетный «контур пуст», а не короткий ответ.
        internal static ServerConfig FromDoc(Dictionary<string, object> doc)
        {
            ServerConfig c = new ServerConfig();
            c.ConfigVersion = Receiver.Long(doc, "config_version", 0);
            c.Entities = Receiver.StrList(doc, "entities");
            object pv;
            IDictionary<string, object> prm =
                doc.TryGetValue("params", out pv) ? pv as IDictionary<string, object> : null;
            if (prm != null)
                foreach (KeyValuePair<string, object> kv in prm) c.Params[kv.Key] = kv.Value;
            c.RecipientPubkey = Receiver.Str(doc, "recipient_pubkey") ?? "";
            return c;
        }

        internal void Save(string dataDir)
        {
            Dictionary<string, object> d = new Dictionary<string, object>();
            d["config_version"] = ConfigVersion;
            d["entities"] = Entities.ToArray();
            d["params"] = Params;
            d["recipient_pubkey"] = RecipientPubkey;
            string path = PathOf(dataDir);
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            string tmp = path + ".tmp";
            File.WriteAllText(tmp, Json.Ser(d), Fmt.NoBom);
            if (File.Exists(path)) File.Replace(tmp, path, null);
            else File.Move(tmp, path);
        }
    }

    // ============================ клиент приёмника ==============================
    internal sealed class ReceiverException : Exception
    {
        internal readonly string Code;
        internal readonly int HttpStatus;
        internal ReceiverException(string code, int status)
            : base("приёмник: " + code + " (HTTP " + status + ")")
        {
            Code = code;
            HttpStatus = status;
        }
    }

    internal sealed class Receiver
    {
        readonly Cfg _cfg;

        internal Receiver(Cfg cfg) { _cfg = cfg; }

        // Единственная фабрика HTTPS-запросов к приёмнику: config, manifest, chunks,
        // status — все идут отсюда, клиентский сертификат mTLS прикрепляется здесь
        // же (OData к локальному IIS идёт по HTTP и сертификата не требует, поэтому
        // OData.NewRequest его сознательно не получает).
        // 5xx/таймаут/обрыв — экспоненциальная пауза и повтор; 4xx — код приёмника
        // пробрасывается наверх (bad_auth/stale_seq/... виден в логе).
        internal byte[] Request(string method, string path, byte[] body)
        {
            string url = _cfg.ReceiverUrl + path;
            for (int attempt = 0; ; attempt++)
            {
                try
                {
                    HttpWebRequest req = (HttpWebRequest)WebRequest.Create(url);
                    req.Method = method;
                    req.Headers["Authorization"] = "Bearer " + _cfg.Token;
                    if (Mtls.Current != null)
                        req.ClientCertificates.Add(Mtls.Current);
                    req.Timeout = C.ReceiverTimeoutSeconds * 1000;
                    req.ReadWriteTimeout = C.ReceiverTimeoutSeconds * 1000;
                    if (body != null)
                    {
                        req.ContentType = "application/octet-stream";
                        req.ContentLength = body.Length;
                        using (Stream s = req.GetRequestStream()) s.Write(body, 0, body.Length);
                    }
                    using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                    using (Stream s = resp.GetResponseStream())
                    using (MemoryStream ms = new MemoryStream())
                    {
                        s.CopyTo(ms);
                        return ms.ToArray();
                    }
                }
                catch (WebException we)
                {
                    // Сервер отверг клиентский сертификат на рукопожатии: это НЕ
                    // сетевая ошибка и не 5xx — повторять бессмысленно, а для разбора
                    // отличие важно, поэтому отдельная строка и отдельный код.
                    if (we.Status == WebExceptionStatus.SecureChannelFailure)
                    {
                        OData.CloseResp(we);
                        Log.Line("сервер не принял клиентский сертификат "
                                 + "(TLS handshake failure): " + we.Message);
                        throw new ReceiverException("mtls_handshake_failure", 0);
                    }
                    HttpWebResponse resp = we.Response as HttpWebResponse;
                    if (resp != null && (int)resp.StatusCode < 500)
                    {
                        string code = "http_" + (int)resp.StatusCode;
                        try
                        {
                            using (StreamReader r = new StreamReader(resp.GetResponseStream(), Encoding.UTF8))
                            {
                                Dictionary<string, object> d = Json.Obj(r.ReadToEnd());
                                object e;
                                if (d != null && d.TryGetValue("error", out e) && e != null)
                                    code = Convert.ToString(e, CultureInfo.InvariantCulture);
                            }
                        }
                        catch { }
                        int st = (int)resp.StatusCode;
                        resp.Close();
                        throw new ReceiverException(code, st);
                    }
                    OData.CloseResp(we);
                    if (attempt >= C.ReceiverRetryMax)
                        throw new ReceiverException("receiver_unreachable: " + we.Message, 0);
                    int pause = C.BackoffBaseSeconds * (1 << attempt);
                    Log.Line("приёмник недоступен (" + we.Message + "), повтор через " + pause + " с");
                    Thread.Sleep(pause * 1000);
                }
            }
        }

        internal Dictionary<string, object> GetJson(string path)
        {
            return Json.Obj(Encoding.UTF8.GetString(Request("GET", path, null)));
        }

        internal Dictionary<string, object> GetConfig(long configVersion)
        {
            return GetJson("/v1/agent/config?base_id=" + OData.Q(_cfg.BaseId)
                + "&config_version=" + configVersion.ToString(CultureInfo.InvariantCulture)
                + "&agent_version=" + OData.Q(C.Version));
        }

        // Отчёт хода такта (Progress): сознательно НЕ через Request — у того повторы с
        // экспоненциальной паузой, а отчёт обязан быть дешёвым и необязательным. Одна
        // попытка, короткий таймаут, исключений не бросает. null — доставлен;
        // "reject" — приёмник отказал (4xx: старая версия без ручки, нет права), звонить
        // дальше бессмысленно; "net" — сеть/5xx, попробуем позже и реже.
        internal string PostProgress(byte[] body)
        {
            try
            {
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create(
                    _cfg.ReceiverUrl + "/v1/agent/progress?base_id=" + OData.Q(_cfg.BaseId));
                req.Method = "POST";
                req.Headers["Authorization"] = "Bearer " + _cfg.Token;
                if (Mtls.Current != null)
                    req.ClientCertificates.Add(Mtls.Current);
                req.Timeout = C.ProgressTimeoutSeconds * 1000;
                req.ReadWriteTimeout = C.ProgressTimeoutSeconds * 1000;
                req.ContentType = "application/json";
                req.ContentLength = body.Length;
                using (Stream s = req.GetRequestStream()) s.Write(body, 0, body.Length);
                using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse()) { }
                return null;
            }
            catch (WebException we)
            {
                HttpWebResponse resp = we.Response as HttpWebResponse;
                int st = resp != null ? (int)resp.StatusCode : 0;
                OData.CloseResp(we);
                return st > 0 && st < 500 ? "reject" : "net";
            }
            catch (Exception) { return "net"; }
        }

        internal void PutManifest(string pkgShort, byte[] ageBytes)
        {
            Request("PUT", "/v1/package/" + OData.Q(_cfg.BaseId) + "/"
                    + OData.Q(pkgShort) + "/manifest", ageBytes);
        }

        internal void PutChunk(string pkgShort, string name, byte[] bytes)
        {
            Request("PUT", "/v1/package/" + OData.Q(_cfg.BaseId) + "/"
                    + OData.Q(pkgShort) + "/chunk/" + OData.Q(name), bytes);
        }

        internal Dictionary<string, object> GetStatus(string pkgShort)
        {
            return GetJson("/v1/package/" + OData.Q(_cfg.BaseId) + "/"
                           + OData.Q(pkgShort) + "/status");
        }

        internal static string Str(Dictionary<string, object> d, string key)
        {
            object v;
            return d != null && d.TryGetValue(key, out v) && v != null
                ? Convert.ToString(v, CultureInfo.InvariantCulture) : null;
        }

        internal static List<string> StrList(Dictionary<string, object> d, string key)
        {
            List<string> res = new List<string>();
            object v;
            if (d == null || !d.TryGetValue(key, out v) || v == null) return res;
            IList l = v as IList;
            if (l == null) return res;
            foreach (object o in l) res.Add(Convert.ToString(o, CultureInfo.InvariantCulture));
            return res;
        }

        internal static long Long(Dictionary<string, object> d, string key, long dflt)
        {
            object v;
            if (d == null || !d.TryGetValue(key, out v) || v == null) return dflt;
            try { return Convert.ToInt64(v, CultureInfo.InvariantCulture); }
            catch { return dflt; }
        }
    }
}

namespace PacketAgent
{
    // ============================ результат по сущности =========================
    internal sealed class EntityResult
    {
        internal string Name, Op;                 // full | full_entity | delta | gone_only
        internal List<string> Cols;               // сырые имена полей (до safe_col)
        internal List<Dictionary<string, object>> Rows;
        internal List<string> Key = new List<string>();   // объявленный ключ ($metadata)
        internal Dictionary<string, string> NewVersions;  // null — версии в индексе не менять
        internal string VersionFp, ContentFp;             // null — не менять
        internal byte[] CsvFull;                          // null — данных нет (gone_only)
    }

    // ============================ сборка и отправка пакета ======================
    internal sealed class Tact
    {
        readonly Cfg _cfg;
        readonly string _exeDir;
        AgentState _state;
        ServerConfig _savedConf;   // последний полный конфиг с диска (config.json)
        ServerConfig _conf;        // действующий конфиг этого такта
        Receiver _rx;
        OData _odata;
        Meta _meta;
        byte[] _metaBytes;

        internal Tact(Cfg cfg, string exeDir)
        {
            _cfg = cfg;
            _exeDir = exeDir;
            _state = AgentState.Load(cfg.DataDir);
            _savedConf = ServerConfig.Load(cfg.DataDir);
            _rx = new Receiver(cfg);
            _odata = new OData(cfg, null);
        }

        // Pubkey: действующий конфиг такта → сохранённый config.json → agent.ini.
        string Pubkey
        {
            get
            {
                if (_conf != null && !string.IsNullOrEmpty(_conf.RecipientPubkey))
                    return _conf.RecipientPubkey;
                if (_savedConf != null && !string.IsNullOrEmpty(_savedConf.RecipientPubkey))
                    return _savedConf.RecipientPubkey;
                return _cfg.RecipientPubkey;
            }
        }

        // Действующий режим упаковки: pubkey (из agent.ini или присланный сервером)
        // нет → plain (пилот): zstd остаётся, age снимается.
        bool PlainMode { get { return string.IsNullOrEmpty(Pubkey); } }
        string ModeName { get { return PlainMode ? "plain (пилот)" : "age"; } }

        // Источник $metadata (решение 11.08): metadata_file задан — читаем
        // синтетический файл установщика вместо HTTP (у клиента на проде
        // $metadata по HTTP отвечает 500 — баг платформы 8.3.27 при большом
        // составе публикации, а сущности читаются). Парсеру Meta.Parse нужны
        // только EntityType/Key/Property — формат файла тот же XML, вся
        // дальнейшая механика (отпечаток, metaChanged, служебный чанк) идёт
        // от байт и от источника не зависит.
        byte[] LoadMetaBytes()
        {
            if (string.IsNullOrEmpty(_cfg.MetadataFile))
                return _odata.GetMetadata();
            if (!File.Exists(_cfg.MetadataFile))
                throw new InvalidDataException("metadata_file задан, но файла нет: "
                                               + _cfg.MetadataFile);
            byte[] bytes = File.ReadAllBytes(_cfg.MetadataFile);
            if (bytes.Length == 0)
                throw new InvalidDataException("metadata_file пуст: " + _cfg.MetadataFile);
            return bytes;
        }

        // ---------------- zstd / age (штатные CLI рядом с агентом) --------------
        static void RunTool(string exe, string args)
        {
            ProcessStartInfo psi = new ProcessStartInfo(exe, args);
            psi.UseShellExecute = false;
            psi.RedirectStandardError = true;
            psi.CreateNoWindow = true;
            Process p = Process.Start(psi);
            string err = p.StandardError.ReadToEnd();
            p.WaitForExit();
            if (p.ExitCode != 0)
                throw new InvalidOperationException(
                    Path.GetFileName(exe) + " вернул " + p.ExitCode + ": " + err.Trim());
        }

        // Имя файла чанка в очереди — как _chunk_filename приёмника: служебные
        // чанки (metadata/gone/index/log) без вставки «.csv». Plain-режим (пилот):
        // те же имена без суффикса «.age» — приёмник различает режимы по магии
        // файла (age-encryption.org/ vs zstd 28 B5 2F FD), имена чанков в
        // манифесте и в missing не меняются.
        string ChunkFileName(string name)
        {
            bool service = name == "metadata" || name == "gone" || name == "index"
                           || name == "log";
            return name + (service ? ".zst" : ".csv.zst") + (PlainMode ? "" : ".age");
        }

        // Тело манифеста для PUT: plain — сам manifest.json, age — manifest.json.age.
        string ManifestBodyPath(string queueDir)
        {
            return Path.Combine(queueDir, PlainMode ? "manifest.json" : "manifest.json.age");
        }

        // plain: zstd -3; age: zstd -3 -> age -r recipient (контракт §3-4).
        Dictionary<string, object> WriteChunk(string queueDir, string name, byte[] plain)
        {
            string plainDir = Path.Combine(queueDir, "plain");
            Directory.CreateDirectory(plainDir);
            bool service = name == "metadata" || name == "gone" || name == "index"
                           || name == "log";
            string fp = Path.Combine(plainDir, service ? name : name + ".csv");
            string fz = fp + ".zst";
            File.WriteAllBytes(fp, plain);
            RunTool(Path.Combine(_exeDir, "zstd.exe"),
                    "-3 -q -f -o \"" + fz + "\" \"" + fp + "\"");
            string enc = Path.Combine(queueDir, ChunkFileName(name));
            if (PlainMode)
            {
                if (File.Exists(enc)) File.Delete(enc);
                File.Move(fz, enc);
            }
            else
            {
                RunTool(Path.Combine(_exeDir, "age.exe"),
                        "-r " + Pubkey + " -o \"" + enc + "\" \"" + fz + "\"");
                TryDelete(fz);
            }
            byte[] encBytes = File.ReadAllBytes(enc);
            Dictionary<string, object> e = new Dictionary<string, object>();
            e["name"] = name;
            e["bytes_plain"] = plain.Length;
            e["sha256_plain"] = EntityIndex.HashHex(plain);
            // В plain-режиме sha256_enc/bytes_enc — от zst-файла (как пришёл).
            e["bytes_enc"] = encBytes.Length;
            e["sha256_enc"] = EntityIndex.HashHex(encBytes);
            TryDelete(fp);
            return e;
        }

        static void TryDelete(string path)
        {
            try { if (File.Exists(path)) File.Delete(path); }
            catch { }
        }

        static string Rand8()
        {
            byte[] b = new byte[4];
            using (RNGCryptoServiceProvider rng = new RNGCryptoServiceProvider())
                rng.GetBytes(b);
            return BitConverter.ToString(b).Replace("-", "").ToLowerInvariant();
        }

        // Разбивка крупной сущности на серию чанков: граница по строкам, заголовок
        // повторяется в каждой части (apply читает каждый чанк со своим header и
        // склеивает UNION ALL), entity_part "i/n" в записи chunks (контракт §6).
        static List<KeyValuePair<int, int>> SplitRows(EntityResult res, long limit)
        {
            List<KeyValuePair<int, int>> parts = new List<KeyValuePair<int, int>>();
            long header = Flatten.CsvBytes(res.Cols, res.Rows, 0, 0).LongLength;
            int from = 0;
            long size = header;
            for (int i = 0; i < res.Rows.Count; i++)
            {
                long rowLen = Flatten.CsvBytes(res.Cols, res.Rows, i, i + 1).LongLength - header;
                if (size + rowLen > limit && i > from)
                {
                    parts.Add(new KeyValuePair<int, int>(from, i));
                    from = i;
                    size = header;
                }
                size += rowLen;
            }
            parts.Add(new KeyValuePair<int, int>(from, res.Rows.Count));
            return parts;
        }

        // ------------------------------ главный такт ----------------------------
        internal bool Run()
        {
            Progress.Begin(_rx, _cfg.ProgressSeconds);
            // Незавершённый пакет прошлого такта — сначала довозим его (догрузка).
            string queueRoot = Path.Combine(_cfg.DataDir, "queue");
            if (Directory.Exists(queueRoot))
            {
                string[] pending = Directory.GetDirectories(queueRoot);
                Array.Sort(pending, StringComparer.Ordinal);
                if (pending.Length > 0)
                {
                    // Режим очереди виден по суффиксу .age (манифест или любой чанк —
                    // обрыв мог случиться между записью manifest.json и шагом age).
                    // Собрана в ДРУГОМ режиме (конфиг сменили между тактами) — молча не
                    // догружаем: снимаем и пересобираем пакет заново этим же тактом.
                    bool queueIsAge = File.Exists(Path.Combine(pending[0], "manifest.json.age"))
                        || Directory.GetFiles(pending[0], "*.age").Length > 0;
                    if (queueIsAge != PlainMode)
                    {
                        Log.Line("незавершённый пакет " + Path.GetFileName(pending[0]) + " — довозка");
                        return ResumePackage(pending[0]);
                    }
                    Log.Line("очередь " + Path.GetFileName(pending[0]) + " собрана в режиме "
                             + (queueIsAge ? "age" : "plain") + ", а конфиг теперь " + ModeName
                             + " — очередь снята, пакет пересобирается заново");
                    DropQueue(pending[0]);
                }
            }

            // (1) конфиг сервера: контур сущностей + параметры + pubkey.
            // Опрашиваем с версией СОХРАНЁННОГО config.json: короткий ответ
            // (304-подобный, без entities) → работаем на снимке с диска.
            long ask = _savedConf != null ? _savedConf.ConfigVersion : 0;
            // Действующий pubkey ДО этого такта — для детекта ротации (контракт §3).
            string prevPub = _savedConf != null && !string.IsNullOrEmpty(_savedConf.RecipientPubkey)
                ? _savedConf.RecipientPubkey : _cfg.RecipientPubkey;
            Dictionary<string, object> cfgDoc = _rx.GetConfig(ask);
            if (cfgDoc.ContainsKey("entities"))
            {
                _conf = ServerConfig.FromDoc(cfgDoc);   // полная выдача — персистим
                _conf.Save(_cfg.DataDir);
                _savedConf = _conf;
            }
            else if (_savedConf != null && _savedConf.Entities.Count > 0)
            {
                _conf = _savedConf;
            }
            else
            {
                // Fail-closed: короткий ответ, а сохранённого контура нет — нельзя
                // принять «пусто» за «контур пуст». Принудительно полная выдача.
                Log.Line("приёмник дал короткий ответ, а сохранённого контура нет "
                         + "— повторный запрос с config_version=0");
                Dictionary<string, object> doc0 = _rx.GetConfig(0);
                if (doc0.ContainsKey("entities"))
                {
                    _conf = ServerConfig.FromDoc(doc0);
                    if (_conf.Entities.Count > 0)
                    {
                        _conf.Save(_cfg.DataDir);
                        _savedConf = _conf;
                    }
                }
                if (_conf == null || _conf.Entities.Count == 0)
                {
                    Log.Line("ОШИБКА: приёмник не отдал контур (ни по config_version=" + ask
                             + ", ни по 0) — такт пропущен");
                    return false;   // ненормальная ситуация сервера, не «пустой контур»
                }
            }
            long newCv = _conf.ConfigVersion;
            List<string> entities = _conf.Entities;
            if (_conf.Params.Count > 0)
            {
                _cfg.PageSize = (int)Receiver.Long(_conf.Params, "page_size", _cfg.PageSize);
                _cfg.TactSeconds = (int)Receiver.Long(_conf.Params, "tact_seconds", _cfg.TactSeconds);
                int cmb = (int)Receiver.Long(_conf.Params, "chunk_mb", _cfg.ChunkMb);
                _cfg.ChunkMb = Math.Max(C.ChunkMbMin, Math.Min(C.ChunkMbMax, cmb));
            }
            // Ротация pubkey (контракт §3): новое место хранения — config.json.
            if (!string.IsNullOrEmpty(_conf.RecipientPubkey) && _conf.RecipientPubkey != prevPub)
                Log.Line("приёмник прислал новый recipient pubkey — применён");
            if (entities.Count == 0)
            {
                // Авторитетный пустой контур: полная выдача с пустым entities.
                // 🔴 Пустой контур + неотправленный снимок $metadata = ТУПИК НАВСЕГДА
                // (живой прогон ERP 12.08, klient-1). Контур на сервере собирает глаз
                // onboard по снимку $metadata, снимок привозит пакет kind=meta — а этот
                // такт выходил РАНЬШЕ, чем до снимка доходило дело: «контур пуст —
                // нечего отправлять» каждые 20 минут, и так до вмешательства человека
                // (остановить демона, позвать --smoke руками). Ручной работы у клиента
                // быть не должно, поэтому такт сам чинит причину: снимок не подтверждён
                // приёмником — отправляем его, следующий такт получит готовый контур.
                _state.ConfigVersion = newCv;
                _state.Save();
                bool metaSent = false;
                try
                {
                    _metaBytes = LoadMetaBytes();
                    _meta = Meta.Parse(_metaBytes);
                    // Отпечаток совпал — снимок уже доехал и onboard дал пустой контур:
                    // это НЕ тупик, а решение сервера. Повторно снимок не шлём.
                    if (_state.MetadataFingerprint != _meta.Fingerprint)
                    {
                        Log.Line("контур пуст, а снимок $metadata приёмником не подтверждён "
                                 + "— отправляю kind=meta: контур соберётся на сервере");
                        metaSent = SendPackage("meta", new List<EntityResult>(),
                                               new List<KeyValuePair<string, string>>(),
                                               true, newCv, null, _state.SkippedFp);
                    }
                }
                catch (Exception e)
                {
                    Log.Line("контур пуст, снимок $metadata прочитать не удалось: " + e.Message);
                }
                if (!metaSent) Log.Line("контур пуст — нечего отправлять");
                ProcessOutbox();   // логи из outbox не зависят от контура
                return true;
            }

            // $metadata: кэш + отпечаток; изменился — служебный чанк в пакете.
            // Источник — HTTP или файл установщика (манифестный режим, LoadMetaBytes).
            _metaBytes = LoadMetaBytes();
            _meta = Meta.Parse(_metaBytes);
            _odata.Meta = _meta;
            try
            {
                Directory.CreateDirectory(Path.Combine(_cfg.DataDir, "cache"));
                File.WriteAllBytes(Path.Combine(_cfg.DataDir, "cache", "metadata.xml"), _metaBytes);
            }
            catch (Exception e) { Log.Line("кэш metadata.xml не записан: " + e.Message); }
            bool metaChanged = _state.MetadataFingerprint != _meta.Fingerprint;
            bool firstRun = _state.Resync || !_state.FullDone;
            Log.Line("такт: сущностей " + entities.Count + (firstRun ? ", ПОЛНАЯ заливка" : "")
                     + (metaChanged ? ", $metadata изменился" : ""));
            Progress.Kind(firstRun ? "full" : "delta", _state.Seq + 1);

            // (2) сбор изменений
            List<EntityResult> results = new List<EntityResult>();
            List<KeyValuePair<string, string>> gone = new List<KeyValuePair<string, string>>();
            List<KeyValuePair<string, string>> skipped = new List<KeyValuePair<string, string>>();
            Dictionary<string, bool> ownerSilent = new Dictionary<string, bool>();
            entities.Sort(StringComparer.Ordinal);   // владелец — префикс имени части → раньше
            int entityNo = 0;
            foreach (string e in entities)
            {
                Progress.Entity(e, ++entityNo, entities.Count);
                try { ProcessEntity(e, firstRun, results, gone, ownerSilent); }
                catch (OdataNotFoundException nfx)
                {
                    // Сущности нет в составе OData (уровень сущности, не ключа):
                    // «не опубликовано», а не «запрещено» (ресерч 4.1, код 8).
                    skipped.Add(new KeyValuePair<string, string>(e, "not_published: " + nfx.Message));
                    Log.Line("    " + e + ": ПРОПУЩЕНА [not_published] (" + nfx.Message + ")");
                }
                catch (OdataDeniedException dex)
                {
                    // Классифицированный отказ (ресерч 4.4). auth_failed — глобально
                    // (веб-сервер не пускает вообще) — такт бессмыслен, фаталим.
                    if (dex.Reason == "auth_failed") throw;
                    if (dex.Reason == "rls_or_no_right" || dex.Reason == "rls_error")
                    {
                        // Фолбэк ступени 1: allowedOnly=true — отдать легально
                        // читаемое подмножество вместо полного пропуска; 401 и там —
                        // значит нет ролевого права «Чтение» на объект (no_read_right).
                        try
                        {
                            _odata.AllowedOnly = true;
                            ProcessEntity(e, firstRun, results, gone, ownerSilent);
                            skipped.Add(new KeyValuePair<string, string>(e,
                                "rls_filtered: прочитано ЧАСТИЧНО — только записи, разрешённые RLS (" + dex.Message + ")"));
                            Log.Line("    " + e + ": ЧАСТИЧНО [rls_filtered] — отдано разрешённое подмножество");
                            continue;
                        }
                        catch (OdataDeniedException)
                        {
                            skipped.Add(new KeyValuePair<string, string>(e, "no_read_right: " + dex.Message));
                            Log.Line("    " + e + ": ПРОПУЩЕНА [no_read_right] (" + dex.Message + ")");
                        }
                        catch (Exception ex2)
                        {
                            skipped.Add(new KeyValuePair<string, string>(e, ex2.Message));
                            Log.Line("    " + e + ": ПРОПУЩЕНА (" + ex2.Message + ")");
                        }
                        finally { _odata.AllowedOnly = false; }
                        continue;
                    }
                    skipped.Add(new KeyValuePair<string, string>(e, dex.Reason + ": " + dex.Message));
                    Log.Line("    " + e + ": ПРОПУЩЕНА [" + dex.Reason + "] (" + dex.Message + ")");
                }
                catch (Exception ex)
                {
                    // Сущность не прочиталась (сбой 1С/сети): пропускаем с ВИДИМОЙ
                    // отметкой — в журнал и в manifest пакета. п. 13 TARGET:
                    // недопустима МОЛЧАЛИВАЯ потеря; показанная — допустима.
                    // Индекс не трогаем — следующий такт попробует снова.
                    skipped.Add(new KeyValuePair<string, string>(e, ex.Message));
                    Log.Line("    " + e + ": ПРОПУЩЕНА (" + ex.Message + ")");
                }
            }

            // (4) ноль изменений — пакет НЕ шлём (контракт §7); исключение — изменился
            // набор пропущенных: один пакет-уведомление, чтобы сервер увидел состав.
            // Отпечаток сравнивается и при ПУСТОМ новом наборе (живой прогон ЗУП
            // 11.08: права починились, skipped обнулился, а сервер показывал
            // вчерашний skipped.json — такт «изменений нет» пакета не отправлял).
            // Переход в пустой набор шлём тоже, секцией skipped из нуля записей
            // (приёмник такой пакет принимает: _validate_manifest посторонних
            // секций не режет, apply работает по наличию секций, kind игнорирует).
            // «Уже сообщено» — только когда набор пуст и раньше ничего не уходило.
            bool anyData = results.Count > 0 || gone.Count > 0;
            bool sendMeta = firstRun || metaChanged;
            string skipFp = EntityIndex.HashHex(Encoding.UTF8.GetBytes(string.Join("\n",
                skipped.ConvertAll(kv => kv.Key + "\t" + kv.Value).ToArray())));
            bool skipChanged = skipFp != _state.SkippedFp
                               && (skipped.Count > 0 || _state.SkippedFp.Length > 0);
            if (!anyData && !sendMeta && !skipChanged)
            {
                Log.Line("изменений нет — пакет не отправляется"
                         + (skipped.Count > 0 ? " (пропущенных: " + skipped.Count + " — уже сообщено)" : ""));
                _state.ConfigVersion = newCv;
                _state.Save();
                ProcessOutbox();   // логи из outbox едут и «пустым» тактом
                return true;
            }
            string kind = firstRun ? "full" : (anyData ? "delta" : "meta");

            // (5)-(7) пакет: чанки, крипто, отправка, индекс ПОСЛЕ applied/verified (К2)
            bool sent = SendPackage(kind, results, gone, sendMeta, newCv, skipped, skipFp);
            ProcessOutbox();   // после основной работы — довозка логов из outbox
            return sent;
        }

        void ProcessEntity(string e, bool firstRun,
                           List<EntityResult> results,
                           List<KeyValuePair<string, string>> gone,
                           Dictionary<string, bool> ownerSilent)
        {
            string owner = _meta.OwnerOf(e);
            if (owner != null)
            {
                bool silent;
                // Тихий владелец: дельта владельца пуста → его табличные части не читаем.
                if (ownerSilent.TryGetValue(owner, out silent) && silent)
                {
                    Log.Line("    " + e + ": владелец " + owner + " не менялся — часть не читаем");
                    return;
                }
            }
            EntityIndex idx = null;
            if (!firstRun && _meta.HasVersions(e))
            {
                Dictionary<string, string> ver1c = _odata.ProbeVersions(e);
                idx = EntityIndex.Load(_cfg.DataDir, e);
                if (ver1c != null && idx != null)
                {
                    List<string> changed = new List<string>();
                    foreach (KeyValuePair<string, string> kv in ver1c)
                    {
                        string old;
                        if (!idx.Versions.TryGetValue(kv.Key, out old) || old != kv.Value)
                            changed.Add(kv.Key);
                    }
                    List<string> goneK = new List<string>();
                    foreach (string k in idx.Versions.Keys)
                        if (!ver1c.ContainsKey(k)) goneK.Add(k);
                    if (changed.Count == 0 && goneK.Count == 0)
                    {
                        ownerSilent[e] = true;
                        return;
                    }
                    ownerSilent[e] = false;
                    List<Dictionary<string, object>> fetched = new List<Dictionary<string, object>>();
                    Dictionary<string, string> fetchedOk = new Dictionary<string, string>();
                    foreach (string k in changed)
                    {
                        Dictionary<string, object> obj = null;
                        try { obj = _odata.FetchByKey(e, k); }
                        catch (OdataNotFoundException) { goneK.Add(k); continue; } // удалили между пробой и тягой
                        if (obj != null) { fetched.Add(obj); fetchedOk[k] = ver1c[k]; }
                    }
                    List<Dictionary<string, object>> flat = Flatten.Rows(fetched, e, _meta);
                    EntityResult res = new EntityResult();
                    res.Name = e;
                    res.Key = _meta.DeclaredKey(e);
                    // Индекс — только реально применённое (К2): старое минус gone
                    // плюс успешно вытянутые версии; невытянутые повторятся завтра.
                    Dictionary<string, string> nv = new Dictionary<string, string>(idx.Versions);
                    foreach (string k in goneK) nv.Remove(k);
                    foreach (KeyValuePair<string, string> kv in fetchedOk) nv[kv.Key] = kv.Value;
                    res.NewVersions = nv;
                    res.VersionFp = EntityIndex.VersionFingerprint(nv);
                    if (flat.Count > 0)
                    {
                        res.Op = "delta";
                        res.Rows = flat;
                        res.Cols = Flatten.UnionCols(flat);
                        res.CsvFull = Flatten.CsvBytes(res.Cols, flat, 0, flat.Count);
                    }
                    else res.Op = "gone_only";
                    results.Add(res);
                    foreach (string k in goneK)
                        gone.Add(new KeyValuePair<string, string>(e, k));
                    Log.Line("    " + e + ": дельта changed=" + changed.Count + " gone=" + goneK.Count);
                    return;
                }
                Log.Line("    " + e + ": проба версий неполная или индекса нет — полное прочтение");
            }

            // Полное прочтение: firstRun, сущность без версий, fallback, табличная часть.
            List<Dictionary<string, object>> rows = _odata.FetchAll(e);
            List<Dictionary<string, object>> flatAll = Flatten.Rows(rows, e, _meta);
            if (flatAll.Count == 0)
            {
                Log.Line("    " + e + ": пустая сущность");
                ownerSilent[e] = true;
                return;
            }
            List<string> cols = Flatten.UnionCols(flatAll);
            byte[] csv = Flatten.CsvBytes(cols, flatAll, 0, flatAll.Count);
            string contentFp = "sha256:" + EntityIndex.HashHex(csv);
            string op;
            if (firstRun) op = "full";
            else if (owner != null) op = "full_entity";   // владелец менялся — шлём часть
            else
            {
                if (idx == null) idx = EntityIndex.Load(_cfg.DataDir, e);
                if (idx != null && idx.ContentFp == contentFp)
                {
                    ownerSilent[e] = true;   // К1: прочитали, сравнили — не изменилось
                    Log.Line("    " + e + ": содержимое не изменилось (отпечаток К1)");
                    return;
                }
                op = "full_entity";
            }
            EntityResult res2 = new EntityResult();
            res2.Name = e;
            res2.Op = op;
            res2.Cols = cols;
            res2.Rows = flatAll;
            res2.CsvFull = csv;
            res2.Key = _meta.DeclaredKey(e);
            res2.ContentFp = contentFp;
            if (_meta.HasVersions(e))
            {
                // Версии для индекса берём свежей пробой (дёшево) — иначе следующий
                // такт счёл бы всю сущность изменившейся.
                Dictionary<string, string> pr = _odata.ProbeVersions(e);
                if (pr != null)
                {
                    res2.NewVersions = pr;
                    res2.VersionFp = EntityIndex.VersionFingerprint(pr);
                }
            }
            results.Add(res2);
            ownerSilent[e] = false;
            Log.Line("    " + e + ": " + op + ", строк " + flatAll.Count);
        }

        // Сборка пакета в очередь + отправка. План обновления индекса пишется ДО
        // отправки (plan.json) — чтобы довозка после обрыва закончила тем же К2.
        bool SendPackage(string kind, List<EntityResult> results,
                         List<KeyValuePair<string, string>> gone,
                         bool sendMeta, long newCv,
                         List<KeyValuePair<string, string>> skipped, string skipFp)
        {
            long seq = _state.Seq + 1;
            string pkgShort = seq.ToString("D6", CultureInfo.InvariantCulture) + "-" + Rand8();
            string queueDir = Path.Combine(_cfg.DataDir, "queue", pkgShort);
            Directory.CreateDirectory(queueDir);

            List<Dictionary<string, object>> chunkEntries = new List<Dictionary<string, object>>();
            Dictionary<string, List<string>> entityChunks = new Dictionary<string, List<string>>();
            long limit = (long)_cfg.ChunkMb * 1024 * 1024;
            int chunkNo = 0;
            foreach (EntityResult res in results)
            {
                entityChunks[res.Name] = new List<string>();
                if (res.CsvFull == null) continue;
                List<KeyValuePair<int, int>> parts = res.CsvFull.LongLength <= limit
                    ? new List<KeyValuePair<int, int>> { new KeyValuePair<int, int>(0, res.Rows.Count) }
                    : SplitRows(res, limit);
                for (int i = 0; i < parts.Count; i++)
                {
                    chunkNo++;
                    string name = "chunk-" + chunkNo.ToString("D5", CultureInfo.InvariantCulture);
                    byte[] bytes = Flatten.CsvBytes(res.Cols, res.Rows, parts[i].Key, parts[i].Value);
                    Dictionary<string, object> entry = WriteChunk(queueDir, name, bytes);
                    entry["entity"] = res.Name;
                    entry["rows"] = parts[i].Value - parts[i].Key;
                    if (parts.Count > 1)
                        entry["entity_part"] = (i + 1) + "/" + parts.Count;
                    chunkEntries.Add(entry);
                    entityChunks[res.Name].Add(name);
                }
            }
            if (gone.Count > 0)
            {
                List<Dictionary<string, object>> g = new List<Dictionary<string, object>>();
                foreach (KeyValuePair<string, string> kv in gone)
                {
                    Dictionary<string, object> r = new Dictionary<string, object>();
                    r["entity"] = kv.Key;
                    r["ref_key"] = kv.Value;
                    g.Add(r);
                }
                byte[] bytes = Flatten.CsvBytes(
                    new List<string> { "entity", "ref_key" }, g, 0, g.Count);
                Dictionary<string, object> entry = WriteChunk(queueDir, "gone", bytes);
                entry["rows"] = gone.Count;
                chunkEntries.Add(entry);
            }
            if (sendMeta)
            {
                Dictionary<string, object> entry = WriteChunk(queueDir, "metadata", _metaBytes);
                entry["rows"] = 0;
                chunkEntries.Add(entry);
            }

            // Манифест (PACKET_CONTRACT §5)
            Dictionary<string, object> m = new Dictionary<string, object>();
            m["manifest_version"] = C.ManifestVersion;
            m["package_id"] = _cfg.BaseId + "/" + pkgShort;
            m["base_id"] = _cfg.BaseId;
            m["seq"] = seq;
            m["kind"] = kind;
            m["created_utc"] = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture);
            m["agent_version"] = C.Version;
            List<object> ents = new List<object>();
            foreach (EntityResult res in results)
            {
                Dictionary<string, object> e = new Dictionary<string, object>();
                e["name"] = res.Name;
                e["op"] = res.Op;
                e["rows"] = res.CsvFull == null ? 0 : res.Rows.Count;
                e["chunks"] = entityChunks[res.Name].ToArray();
                e["key"] = res.Key.ToArray();
                if (res.VersionFp != null) e["version_fingerprint"] = res.VersionFp;
                if (res.ContentFp != null) e["content_fingerprint"] = res.ContentFp;
                ents.Add(e);
            }
            m["entities"] = ents.ToArray();
            if (gone.Count > 0)
            {
                List<string> ge = new List<string>();
                HashSet<string> seen = new HashSet<string>();
                foreach (KeyValuePair<string, string> kv in gone)
                    if (seen.Add(kv.Key)) ge.Add(kv.Key);
                Dictionary<string, object> gd = new Dictionary<string, object>();
                gd["entities"] = ge.ToArray();
                gd["chunks"] = new string[] { "gone" };
                m["gone"] = gd;
            }
            Dictionary<string, object> md = new Dictionary<string, object>();
            md["included"] = sendMeta;
            if (sendMeta)
            {
                md["fingerprint"] = _meta.Fingerprint;
                md["chunks"] = new string[] { "metadata" };
            }
            m["metadata"] = md;
            // Секция skipped — ВСЕГДА, и пустой: «пропущенных больше нет» — такой
            // же факт для сервера, как и новый состав (ЗУП 11.08: права починились,
            // а skipped.json на сервере застыл). Apply реагирует на наличие секции.
            if (skipped != null)
            {
                List<object> sk = new List<object>();
                foreach (KeyValuePair<string, string> kv in skipped)
                {
                    Dictionary<string, object> r = new Dictionary<string, object>();
                    r["entity"] = kv.Key;
                    r["error"] = kv.Value;
                    sk.Add(r);
                }
                m["skipped"] = sk.ToArray();
            }
            m["chunks"] = chunkEntries.ToArray();

            File.WriteAllText(Path.Combine(queueDir, "manifest.json"), Json.Ser(m), Fmt.NoBom);
            if (!PlainMode)
                RunTool(Path.Combine(_exeDir, "age.exe"),
                        "-r " + Pubkey + " -o \"" + Path.Combine(queueDir, "manifest.json.age")
                        + "\" \"" + Path.Combine(queueDir, "manifest.json") + "\"");

            // План обновления индекса (К2) — применится только после applied/verified.
            Dictionary<string, object> plan = new Dictionary<string, object>();
            plan["config_version"] = newCv;
            plan["metadata_fingerprint"] = sendMeta ? _meta.Fingerprint : null;
            plan["skipped_fp"] = skipFp;
            plan["mark_full_done"] = kind == "full";
            Dictionary<string, object> pe = new Dictionary<string, object>();
            foreach (EntityResult res in results)
            {
                Dictionary<string, object> d = new Dictionary<string, object>();
                d["versions"] = res.NewVersions;
                d["version_fp"] = res.VersionFp;
                d["content_fp"] = res.ContentFp;
                pe[res.Name] = d;
            }
            plan["entities"] = pe;
            File.WriteAllText(Path.Combine(queueDir, "plan.json"), Json.Ser(plan), Fmt.NoBom);

            _state.Seq = seq;   // seq растёт только на отправленных пакетах
            _state.Save();
            Progress.Chunks(chunkEntries.Count);
            Log.Line("пакет " + pkgShort + " kind=" + kind + ", режим " + ModeName
                     + ": сущностей " + results.Count
                     + ", gone " + gone.Count + ", чанков " + chunkEntries.Count
                     + (sendMeta ? ", +metadata" : ""));
            return UploadAndFinish(pkgShort, queueDir);
        }

        // Отправка: манифест → чанки (повторы допустимы) → status до verified/applied.
        bool UploadAndFinish(string pkgShort, string queueDir)
        {
            string bodyPath = ManifestBodyPath(queueDir);
            if (!File.Exists(bodyPath))
            {
                if (PlainMode)
                {
                    Log.Line("очередь " + pkgShort + " битая: нет manifest.json — снята");
                    DropQueue(queueDir);
                    return false;
                }
                // age-режим: .age не успел собраться (обрыв) — собираем из manifest.json.
                RunTool(Path.Combine(_exeDir, "age.exe"),
                        "-r " + Pubkey + " -o \"" + bodyPath + "\" \""
                        + Path.Combine(queueDir, "manifest.json") + "\"");
            }
            try
            {
                _rx.PutManifest(pkgShort, File.ReadAllBytes(bodyPath));
            }
            catch (ReceiverException e)
            {
                if (e.Code.IndexOf("stale_seq", StringComparison.Ordinal) >= 0)
                    return StaleSeq(queueDir);
                Log.Line("манифест отклонён: " + e.Code + " — пакет снят, индекс не тронут");
                DropQueue(queueDir);
                return false;
            }
            string final = WaitFinal(pkgShort, queueDir);
            string state = final, error = null;
            int bar = final.IndexOf('|');
            if (bar >= 0) { state = final.Substring(0, bar); error = final.Substring(bar + 1); }
            if (state == "verified" || state == "applied")
            {
                FinalizePackage(pkgShort, queueDir);
                return true;
            }
            if (state == "rejected" || state == "quarantined")
            {
                if (error != null && error.IndexOf("stale_seq", StringComparison.Ordinal) >= 0)
                    return StaleSeq(queueDir);
                // Карантин: пакет НЕ повторяем — ждём решения, следующий такт с новым seq.
                Log.Line("пакет " + pkgShort + " " + state + " (" + error
                         + ") — не повторяем, индекс не тронут");
                DropQueue(queueDir);
                return false;
            }
            // timeout/no_such_package и прочие сбои: очередь остаётся, довозим
            // следующим тактом.
            Log.Line("пакет " + pkgShort + " не подтверждён (" + state
                     + (error != null ? " " + error : "") + ") — довозка следующим тактом");
            return false;
        }

        // Опрос status с догрузкой missing до финального состояния.
        string WaitFinal(string pkgShort, string queueDir)
        {
            int waited = 0, rounds = 0;
            while (true)
            {
                if (++rounds > 2000) return "timeout|";
                Dictionary<string, object> st;
                try { st = _rx.GetStatus(pkgShort); }
                catch (ReceiverException e) { return e.Code + "|"; }
                string state = Receiver.Str(st, "state") ?? "";
                if (state == "receiving")
                {
                    List<string> missing = Receiver.StrList(st, "missing");
                    int sent = 0;
                    foreach (string name in missing)
                    {
                        string f = Path.Combine(queueDir, ChunkFileName(name));
                        if (File.Exists(f))
                        {
                            _rx.PutChunk(pkgShort, name, File.ReadAllBytes(f));
                            sent++;
                            Progress.ChunkSent(sent);
                        }
                    }
                    if (sent > 0) continue;   // проверка синхронная в status
                    if (missing.Count > 0)
                        return "missing_local|";   // приёмник ждёт чанки, которых нет в очереди
                }
                else
                {
                    string err = Receiver.Str(st, "error");
                    return state + "|" + (err ?? "");
                }
                if (waited >= C.StatusWaitSeconds) return "timeout|";
                Thread.Sleep(C.StatusPollSeconds * 1000);
                waited += C.StatusPollSeconds;
            }
        }

        // К2: индекс обновляется ПОСЛЕ applied/verified, затем очередь удаляется.
        void FinalizePackage(string pkgShort, string queueDir)
        {
            Dictionary<string, object> plan =
                Json.Obj(File.ReadAllText(Path.Combine(queueDir, "plan.json"), Encoding.UTF8));
            object eo;
            if (plan.TryGetValue("entities", out eo))
            {
                IDictionary<string, object> ents = eo as IDictionary<string, object>;
                if (ents != null)
                    foreach (KeyValuePair<string, object> kv in ents)
                    {
                        IDictionary<string, object> d = kv.Value as IDictionary<string, object>;
                        if (d == null) continue;
                        EntityIndex idx = EntityIndex.Load(_cfg.DataDir, kv.Key);
                        Dictionary<string, string> versions =
                            idx != null ? idx.Versions : new Dictionary<string, string>();
                        object vv;
                        if (d.TryGetValue("versions", out vv) && vv != null)
                        {
                            IDictionary<string, object> vd = vv as IDictionary<string, object>;
                            if (vd != null)
                            {
                                versions = new Dictionary<string, string>();
                                foreach (KeyValuePair<string, object> p in vd)
                                    versions[p.Key] = p.Value == null ? ""
                                        : Convert.ToString(p.Value, CultureInfo.InvariantCulture);
                            }
                        }
                        string vfp = Receiver.Str(new Dictionary<string, object>(d), "version_fp");
                        string cfp = Receiver.Str(new Dictionary<string, object>(d), "content_fp");
                        if (vfp == null && idx != null) vfp = idx.VersionFp;
                        if (cfp == null && idx != null) cfp = idx.ContentFp;
                        EntityIndex.SaveAtomic(_cfg.DataDir, kv.Key, versions, vfp, cfp);
                    }
            }
            _state.ConfigVersion = Receiver.Long(plan, "config_version", _state.ConfigVersion);
            string mfp = Receiver.Str(plan, "metadata_fingerprint");
            if (mfp != null) _state.MetadataFingerprint = mfp;
            string sfp = Receiver.Str(plan, "skipped_fp");
            if (sfp != null) _state.SkippedFp = sfp;
            object mfd;
            if (plan.TryGetValue("mark_full_done", out mfd) && mfd is bool && (bool)mfd)
            {
                _state.FullDone = true;
                _state.Resync = false;
            }
            _state.Save();
            DropQueue(queueDir);
            Log.Line("пакет " + pkgShort + " verified/applied — индекс обновлён, очередь снята");
        }

        // stale_seq: наш seq отстал от приёмника. Скачок вперёд и полный resync;
        // индекс не трогаем — пакет не применялся.
        bool StaleSeq(string queueDir)
        {
            _state.Resync = true;
            _state.Seq += C.StaleSeqJump;
            _state.Save();
            DropQueue(queueDir);
            Log.Line("приёмник: stale_seq — seq увеличен на " + C.StaleSeqJump
                     + ", следующий такт — полный resync");
            return false;
        }

        static void DropQueue(string queueDir)
        {
            try { Directory.Delete(queueDir, true); }
            catch (Exception e) { Log.Line("очередь " + queueDir + " не удалена: " + e.Message); }
        }

        // Довозка незавершённого пакета: статус → missing → только их.
        bool ResumePackage(string queueDir)
        {
            string pkgShort = Path.GetFileName(queueDir);
            Dictionary<string, object> st;
            try { st = _rx.GetStatus(pkgShort); }
            catch (ReceiverException e)
            {
                if (e.Code == "no_such_package")
                {
                    // Приёмник пакета не знает (не доехал манифест): шлём сначала.
                    string bodyPath = ManifestBodyPath(queueDir);
                    if (File.Exists(bodyPath))
                    {
                        try { _rx.PutManifest(pkgShort, File.ReadAllBytes(bodyPath)); }
                        catch (ReceiverException e2)
                        {
                            if (e2.Code.IndexOf("stale_seq", StringComparison.Ordinal) >= 0)
                                return StaleSeq(queueDir);
                            Log.Line("довозка: манифест отклонён: " + e2.Code);
                            DropQueue(queueDir);
                            return false;
                        }
                    }
                    else
                    {
                        Log.Line("довозка: нет " + Path.GetFileName(bodyPath) + " — очередь битая, снята");
                        DropQueue(queueDir);
                        return false;
                    }
                }
                else return false;   // приёмник недоступен — следующим тактом
            }
            return UploadAndFinish(pkgShort, queueDir);
        }

        // ------------------------------ smoke (AGENT_TZ §4) ----------------------
        // Пакет kind=meta с настоящим $metadata: в витрине безобиден и полезен.
        // true — только при подтверждённой доставке (verified/applied).
        internal bool Smoke()
        {
            string queueRoot = Path.Combine(_cfg.DataDir, "queue");
            if (Directory.Exists(queueRoot) && Directory.GetDirectories(queueRoot).Length > 0)
            {
                Log.Line("smoke: есть незавершённый пакет — сначала довозка штатным демоном");
                return false;
            }
            _metaBytes = LoadMetaBytes();   // HTTP или файл установщика (манифестный режим)
            _meta = Meta.Parse(_metaBytes);
            long seq = _state.Seq + 1;
            string pkgShort = seq.ToString("D6", CultureInfo.InvariantCulture) + "-" + Rand8();
            string queueDir = Path.Combine(queueRoot, pkgShort);
            Directory.CreateDirectory(queueDir);

            List<Dictionary<string, object>> chunkEntries = new List<Dictionary<string, object>>();
            Dictionary<string, object> entry = WriteChunk(queueDir, "metadata", _metaBytes);
            entry["rows"] = 0;
            chunkEntries.Add(entry);

            Dictionary<string, object> m = new Dictionary<string, object>();
            m["manifest_version"] = C.ManifestVersion;
            m["package_id"] = _cfg.BaseId + "/" + pkgShort;
            m["base_id"] = _cfg.BaseId;
            m["seq"] = seq;
            m["kind"] = "meta";
            m["created_utc"] = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture);
            m["agent_version"] = C.Version;
            m["entities"] = new object[0];
            Dictionary<string, object> md = new Dictionary<string, object>();
            md["included"] = true;
            md["fingerprint"] = _meta.Fingerprint;
            md["chunks"] = new string[] { "metadata" };
            m["metadata"] = md;
            m["chunks"] = chunkEntries.ToArray();
            File.WriteAllText(Path.Combine(queueDir, "manifest.json"), Json.Ser(m), Fmt.NoBom);
            if (!PlainMode)
                RunTool(Path.Combine(_exeDir, "age.exe"),
                        "-r " + Pubkey + " -o \"" + Path.Combine(queueDir, "manifest.json.age")
                        + "\" \"" + Path.Combine(queueDir, "manifest.json") + "\"");

            Dictionary<string, object> plan = new Dictionary<string, object>();
            plan["config_version"] = _state.ConfigVersion;
            plan["metadata_fingerprint"] = _meta.Fingerprint;
            plan["mark_full_done"] = false;
            plan["entities"] = new Dictionary<string, object>();
            File.WriteAllText(Path.Combine(queueDir, "plan.json"), Json.Ser(plan), Fmt.NoBom);

            _state.Seq = seq;
            _state.Save();
            Log.Line("smoke: пакет " + pkgShort + " kind=meta, режим " + ModeName + " — отправка");
            bool ok = UploadAndFinish(pkgShort, queueDir);
            if (ok) { _state.SmokeOk = true; _state.Save(); }
            Log.Line(ok ? "smoke: доставка подтверждена приёмником"
                        : "smoke: доставка НЕ подтверждена");
            return ok;
        }

        // ------------------------------ outbox --------------------------------
        // Каталог <packet dir>\outbox (рядом с agent.ini): установщик и CLI
        // --send-log кладут сюда КОПИИ логов, демон довозит их своим тактом.
        // До outbox (живой прогон ЗУП 11.08) лог установки уходил только CLI
        // --send-log, который отказывал при занятом single-instance mutex, а
        // первичная синхронизация держит mutex часами, — лог не уходил никогда.
        // Вызов — в конце Run() после основной работы (все ветки выхода).
        // seq: доставка идёт из того же процесса, что боевые пакеты, и тем же
        // счётчиком _state.Seq + 1 с фиксацией ДО отправки — монотонность seq
        // сохраняется сама, отдельного счётчика лог-пакетам не нужно.
        internal int ProcessOutbox()
        {
            string outbox = Path.Combine(_exeDir, "outbox");
            if (!Directory.Exists(outbox)) return 0;
            string[] files = Directory.GetFiles(outbox);
            if (files.Length == 0) return 0;
            string queueRoot = Path.Combine(_cfg.DataDir, "queue");
            if (Directory.Exists(queueRoot) && Directory.GetDirectories(queueRoot).Length > 0)
            {
                Log.Line("outbox: файлов " + files.Length
                         + ", но есть незавершённый пакет — доставка логов следующим тактом");
                return 0;
            }
            Array.Sort(files, StringComparer.Ordinal);
            int sent = 0;
            foreach (string f in files)
            {
                // Пустой файл нести на сервер нечего — убираем, чтобы не крутить
                // его каждый такт.
                if (new FileInfo(f).Length == 0)
                {
                    Log.Line("outbox: " + Path.GetFileName(f) + " пуст — удалён без отправки");
                    TryDelete(f);
                    continue;
                }
                if (!DeliverOutboxFile(f)) break;   // причина уже в журнале
                sent++;
            }
            return sent;
        }

        // Доставка одного файла из outbox: успех (verified/applied) — копия
        // удаляется; неудача (сеть, занятая очередь, отказ приёмника) — файл
        // остаётся до следующего такта. false — и дальше по outbox не идём:
        // при неудаче либо очередь осталась на довозку (сеть), либо приёмник
        // отклонил пакет — обоим случаям повтор следующим тактом, а не штурм
        // остальных файлов этим же тактом.
        internal bool DeliverOutboxFile(string path)
        {
            string queueRoot = Path.Combine(_cfg.DataDir, "queue");
            if (Directory.Exists(queueRoot) && Directory.GetDirectories(queueRoot).Length > 0)
            {
                Log.Line("outbox: есть незавершённый пакет — сначала довозка, "
                         + Path.GetFileName(path) + " остаётся до следующего такта");
                return false;
            }
            bool ok;
            try { ok = SendLogBody(path); }
            catch (Exception e)
            {
                Log.Line("outbox: " + Path.GetFileName(path) + " — сбой (" + e.Message
                         + "), остаётся до следующего такта");
                return false;
            }
            if (!ok)
            {
                Log.Line("outbox: " + Path.GetFileName(path)
                         + " — доставка не подтверждена, остаётся до следующего такта");
                return false;
            }
            TryDelete(path);   // verified/applied — копия в outbox больше не нужна
            return true;
        }

        // ------------------------------ лог-пакет ------------------------------
        // Общее тело отправки лог-файла для CLI --send-log и outbox-такта демона:
        // пакет с одним служебным чанком `log` (договорённость с приёмником: имя
        // чанка ровно "log", секция log в манифесте — по образцу metadata/gone,
        // kind приёмник игнорирует), seq, чанк log, UploadAndFinish. Проверка
        // незавершённой очереди — на вызывающем (DeliverOutboxFile).
        // seq: тот же монотонный счётчик, что у боевых пакетов, — _state.Seq + 1
        // с фиксацией ДО отправки, как smoke/SendPackage. Конфликта с боевыми
        // пакетами нет: seq только растёт и двигается одним процессом (снаружи
        // single-instance mutex). Ответ stale_seq разбирает общий StaleSeq:
        // скачок на StaleSeqJump + resync — безопасно и для лог-пакета.
        // true — только при подтверждённой доставке (verified/applied).
        bool SendLogBody(string path)
        {
            if (!File.Exists(path))
            {
                Log.Line("send-log: файла нет: " + path);
                return false;
            }
            // Читаем с FileShare.ReadWrite (кейс K5, 11.08): лог установщика ещё
            // открыт его писателем — File.ReadAllBytes (FileShare.Read) получал
            // «файл используется другим процессом», и лог не уходил на сервер.
            byte[] body;
            using (FileStream fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            {
                body = new byte[fs.Length];
                int off = 0;
                while (off < body.Length)
                {
                    int n = fs.Read(body, off, body.Length - off);
                    if (n <= 0) break;
                    off += n;
                }
                if (off < body.Length) Array.Resize(ref body, off);
            }
            if (body.Length == 0)
            {
                Log.Line("send-log: файл пуст — не отправляем: " + path);
                return false;
            }
            string queueRoot = Path.Combine(_cfg.DataDir, "queue");
            long seq = _state.Seq + 1;
            string pkgShort = seq.ToString("D6", CultureInfo.InvariantCulture) + "-" + Rand8();
            string queueDir = Path.Combine(queueRoot, pkgShort);
            Directory.CreateDirectory(queueDir);

            List<Dictionary<string, object>> chunkEntries = new List<Dictionary<string, object>>();
            Dictionary<string, object> entry = WriteChunk(queueDir, "log", body);
            entry["rows"] = 0;
            chunkEntries.Add(entry);

            Dictionary<string, object> m = new Dictionary<string, object>();
            m["manifest_version"] = C.ManifestVersion;
            m["package_id"] = _cfg.BaseId + "/" + pkgShort;
            m["base_id"] = _cfg.BaseId;
            m["seq"] = seq;
            m["kind"] = "log";
            m["created_utc"] = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture);
            m["agent_version"] = C.Version;
            m["entities"] = new object[0];
            // Чей это лог и когда писался — на сервере видно из манифеста.
            Dictionary<string, object> lg = new Dictionary<string, object>();
            lg["source"] = Path.GetFileName(path);
            lg["source_modified_utc"] = File.GetLastWriteTimeUtc(path)
                .ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture);
            lg["fingerprint"] = "sha256:" + EntityIndex.HashHex(body);
            lg["chunks"] = new string[] { "log" };
            m["log"] = lg;
            m["chunks"] = chunkEntries.ToArray();
            File.WriteAllText(Path.Combine(queueDir, "manifest.json"), Json.Ser(m), Fmt.NoBom);
            if (!PlainMode)
                RunTool(Path.Combine(_exeDir, "age.exe"),
                        "-r " + Pubkey + " -o \"" + Path.Combine(queueDir, "manifest.json.age")
                        + "\" \"" + Path.Combine(queueDir, "manifest.json") + "\"");

            // plan.json — пустой (индекс и отпечатки не меняются): нужен, чтобы
            // довозка оборванного лог-пакета штатным демоном прошла тем же К2.
            Dictionary<string, object> plan = new Dictionary<string, object>();
            plan["config_version"] = _state.ConfigVersion;
            plan["metadata_fingerprint"] = null;
            plan["mark_full_done"] = false;
            plan["entities"] = new Dictionary<string, object>();
            File.WriteAllText(Path.Combine(queueDir, "plan.json"), Json.Ser(plan), Fmt.NoBom);

            _state.Seq = seq;
            _state.Save();
            Log.Line("send-log: пакет " + pkgShort + " (" + Path.GetFileName(path)
                     + ", " + body.Length + " байт), режим " + ModeName + " — отправка");
            bool ok = UploadAndFinish(pkgShort, queueDir);
            Log.Line(ok ? "send-log: доставка подтверждена приёмником"
                        : "send-log: доставка НЕ подтверждена");
            return ok;
        }
    }
}

namespace PacketAgent
{
    // ============================ CLI (AGENT_TZ §7) =============================
    //   packet-agent.exe --version                      версия, код 0
    //   packet-agent.exe --smoke                        пробная посылка kind=meta,
    //                                                   код 0 только при verified
    //   packet-agent.exe --send-log <path>              копия файла в outbox +
    //                                                   немедленная доставка, если
    //                                                   mutex свободен; недоставленное
    //                                                   довозит демон своим тактом
    //   packet-agent.exe                                демон тактов
    //   packet-agent.exe --flatten <page.json> <e> <out.csv>   служебный режим
    //                                                   golden-пробы (К5)
    //   второй экземпляр — сразу код 0 (watchdog планировщика дёргает каждые 5 мин)
    internal static class Program
    {
        static int Main(string[] args)
        {
            try { Console.OutputEncoding = Encoding.UTF8; } catch { }
            // TLS 1.2 принудительно: enum Tls12 появился в .NET 4.5, а компилируем
            // мы 4.0 — поэтому числом (3072), а не SecurityProtocolType.Tls12.
            ServicePointManager.SecurityProtocol |= (SecurityProtocolType)3072;
            string exeDir = Path.GetDirectoryName(
                System.Reflection.Assembly.GetExecutingAssembly().Location);

            if (args.Length == 1 && args[0] == "--version")
            {
                Console.WriteLine("packet-agent " + C.Version);
                return 0;
            }
            if (args.Length == 4 && args[0] == "--flatten")
                return FlattenMode(args[1], args[2], args[3]);
            if (args.Length == 1 && args[0] == "--smoke")
            {
                Mutex single = AcquireSingle(exeDir);
                if (single == null)
                {
                    // 🔴 НЕ код 0 (живой прогон ERP 12.08): установщик читал нулевой код
                    // как «доставка подтверждена» и печатал зелёную строку, хотя смоук
                    // не выполнялся вовсе — ложно-зелёная установка, снимок $metadata на
                    // сервер не уезжал. Правило «второй экземпляр выходит с 0» (§7) — про
                    // ДЕМОНА, которого сторож дёргает каждые 5 минут; для смоука молчание
                    // неотличимо от успеха, поэтому отдельный код и внятная строка.
                    Console.Error.WriteLine("smoke: работает демон (single-instance) — пробная "
                        + "посылка НЕ выполнена; остановите задачу «1C Packet Agent» и повторите");
                    return 3;
                }
                using (single) return SmokeMode(exeDir);
            }
            if (args.Length == 2 && args[0] == "--send-log")
            {
                // Outbox (дефект живого прогона ЗУП 11.08): сначала копия в outbox —
                // доставку гарантирует демон своим тактом. Прежняя схема (только
                // немедленная отправка под mutex) отказывала всю первичную
                // синхронизацию: mutex занят часами, и код 1 установщик/человек
                // принимал за «не судьба».
                string staged = StageToOutbox(exeDir, args[1]);
                if (staged == null) return 1;
                Mutex single = AcquireSingle(exeDir);
                if (single == null)
                {
                    Console.WriteLine("send-log: работает демон — файл поставлен в outbox, "
                                      + "демон довезёт своим тактом: " + staged);
                    return 0;
                }
                // Mutex свободен — немедленная попытка доставки из outbox.
                using (single) return SendLogMode(exeDir, staged);
            }
            if (args.Length == 0)
            {
                Mutex single = AcquireSingle(exeDir);
                if (single == null) return 0;
                using (single) return DaemonMode(exeDir);
            }
            Console.Error.WriteLine("использование: packet-agent.exe "
                + "[--version | --smoke | --send-log <path> | --flatten <page.json> <entity> <out.csv>]");
            return 2;
        }

        // Single-instance через named Mutex; имя привязано к каталогу установки.
        static Mutex AcquireSingle(string exeDir)
        {
            string suffix = EntityIndex.HashHex(
                Encoding.UTF8.GetBytes(exeDir.ToLowerInvariant())).Substring(0, 16);
            foreach (string scope in new string[] { @"Global\", @"Local\" })
            {
                try
                {
                    bool created;
                    Mutex m = new Mutex(true, scope + "1c-packet-agent-" + suffix, out created);
                    if (created) return m;
                    m.Close();
                    return null;
                }
                catch (UnauthorizedAccessException) { }
            }
            return null;
        }

        static Cfg LoadCfg(string exeDir)
        {
            Cfg cfg = Cfg.Load(Path.Combine(exeDir, "agent.ini"));
            Log.Init(cfg.LogDir);
            return cfg;
        }

        // Демон тактов: неуспешный такт — запись в журнал (при выходе — код 1),
        // демон продолжает со следующего такта; пауза между тактами — из конфига
        // сервера, при серии сбоев — экспоненциальная (не чаще такта).
        static int DaemonMode(string exeDir)
        {
            try
            {
                Cfg cfg = LoadCfg(exeDir);
                string certErr = Mtls.LoadFor(cfg.ClientCertThumbprint);
                if (certErr != null)
                {
                    Log.Line("mTLS: " + certErr);
                    Console.Error.WriteLine("packet-agent: mTLS: " + certErr);
                    return 2;   // приёмник не пропустит, но причина названа до сети
                }
                Log.Line("mTLS: клиентский сертификат " + Mtls.Current.Thumbprint
                         + " (" + Mtls.Current.Subject + ")");
                Log.Line("packet-agent " + C.Version + " — демон тактов, база "
                         + cfg.BaseId + ", данные " + cfg.DataDir
                         + ", упаковка " + (cfg.Plain ? "plain (пилот)" : "age"));
                int failures = 0;
                while (true)
                {
                    try
                    {
                        bool ok = new Tact(cfg, exeDir).Run();
                        Progress.Done(ok);
                        failures = 0;
                    }
                    catch (Exception e)
                    {
                        failures++;
                        Progress.Fail(e.Message);
                        Log.Line("ТАКТ НЕ УДАЛСЯ: " + e.Message);
                    }
                    int sleep = cfg.TactSeconds;
                    if (failures > 0)
                        sleep = Math.Min(cfg.TactSeconds, 30 * (1 << Math.Min(failures, 5)));
                    Thread.Sleep(sleep * 1000);
                }
            }
            catch (Exception e)
            {
                Log.Line("критическая ошибка демона: " + e.Message);
                Console.Error.WriteLine("packet-agent: " + e.Message);
                return 1;
            }
        }

        // --smoke: пакет kind=meta с настоящим $metadata; код 0 только при
        // подтверждённой доставке, код приёмника печатается (установщик переводит
        // его в строку по AGENT_TZ §6).
        static int SmokeMode(string exeDir)
        {
            Cfg cfg;
            try { cfg = LoadCfg(exeDir); }
            catch (Exception e)
            {
                Console.Error.WriteLine("smoke: конфиг: " + e.Message);
                return 1;
            }
            string certErr = Mtls.LoadFor(cfg.ClientCertThumbprint);
            if (certErr != null)
            {
                Log.Line("smoke: mTLS: " + certErr);
                Console.Error.WriteLine("smoke: mTLS: " + certErr);
                return 2;
            }
            try
            {
                bool ok = new Tact(cfg, exeDir).Smoke();
                return ok ? 0 : 1;
            }
            catch (ReceiverException e)
            {
                Log.Line("smoke: ошибка приёмника: " + e.Code);
                Console.Error.WriteLine("smoke: ошибка приёмника: " + e.Code);
                return 1;
            }
            catch (Exception e)
            {
                Log.Line("smoke: сбой: " + e.Message);
                Console.Error.WriteLine("smoke: сбой: " + e.Message);
                return 1;
            }
        }

        // Копия файла в outbox рядом с agent.ini. Имя — как у источника: повторная
        // постановка того же лога затирает недоставленную копию (свежая важнее).
        // null — не получилось (причина напечатана).
        static string StageToOutbox(string exeDir, string path)
        {
            try
            {
                if (!File.Exists(path))
                {
                    Console.Error.WriteLine("send-log: файла нет: " + path);
                    return null;
                }
                string outbox = Path.Combine(exeDir, "outbox");
                Directory.CreateDirectory(outbox);
                string dst = Path.Combine(outbox, Path.GetFileName(path));
                File.Copy(path, dst, true);
                return dst;
            }
            catch (Exception e)
            {
                Console.Error.WriteLine("send-log: не удалось положить файл в outbox: " + e.Message);
                return null;
            }
        }

        // --send-log <path>: копия файла уже лежит в outbox (её путь передал Main),
        // здесь — немедленная попытка доставки под свободным mutex; код 0 только
        // при подтверждённой доставке (verified/applied), как у smoke. Не вышло
        // (очередь занята, сеть) — файл остаётся в outbox, довезёт демон. Секреты —
        // только из agent.ini (LoadCfg), в консоль/журнал они не попадают
        // (Log.AddSecret).
        static int SendLogMode(string exeDir, string path)
        {
            Cfg cfg;
            try { cfg = LoadCfg(exeDir); }
            catch (Exception e)
            {
                Console.Error.WriteLine("send-log: конфиг: " + e.Message);
                return 1;
            }
            string certErr = Mtls.LoadFor(cfg.ClientCertThumbprint);
            if (certErr != null)
            {
                Log.Line("send-log: mTLS: " + certErr);
                Console.Error.WriteLine("send-log: mTLS: " + certErr);
                return 2;
            }
            try
            {
                bool ok = new Tact(cfg, exeDir).DeliverOutboxFile(path);
                if (!ok)
                    Console.WriteLine("send-log: сейчас не доставлен — файл остаётся в outbox, "
                                      + "демон довезёт своим тактом");
                return ok ? 0 : 1;
            }
            catch (ReceiverException e)
            {
                Log.Line("send-log: ошибка приёмника: " + e.Code);
                Console.Error.WriteLine("send-log: ошибка приёмника: " + e.Code
                                        + " — файл остаётся в outbox, довезёт демон");
                return 1;
            }
            catch (Exception e)
            {
                Log.Line("send-log: сбой: " + e.Message);
                Console.Error.WriteLine("send-log: сбой: " + e.Message);
                return 1;
            }
        }

        // --flatten: разворот сохранённой страницы OData тем же кодом, что боевая
        // выгрузка. Точка golden-пробы (work/packet/golden/probe.cmd, fc /b).
        // $metadata — из metadata.xml рядом со страницей (снимок витрины).
        static int FlattenMode(string pagePath, string entity, string outPath)
        {
            try
            {
                string metaPath = Path.Combine(
                    Path.GetDirectoryName(Path.GetFullPath(pagePath)), "metadata.xml");
                if (!File.Exists(metaPath))
                {
                    Console.Error.WriteLine("flatten: нет metadata.xml рядом со страницей: " + metaPath);
                    return 2;
                }
                Meta meta = Meta.Parse(File.ReadAllBytes(metaPath));
                Dictionary<string, object> doc = Json.Obj(File.ReadAllText(pagePath, Encoding.UTF8));
                object v;
                IList rows = doc.TryGetValue("value", out v) ? v as IList : null;
                if (rows == null)
                {
                    Console.Error.WriteLine("flatten: в странице нет массива value");
                    return 2;
                }
                List<Dictionary<string, object>> flat = Flatten.Rows(rows, entity, meta);
                List<string> cols = Flatten.UnionCols(flat);
                File.WriteAllBytes(outPath, Flatten.CsvBytes(cols, flat, 0, flat.Count));
                Console.WriteLine(entity + ": " + flat.Count + " строк -> " + outPath);
                return 0;
            }
            catch (Exception e)
            {
                Console.Error.WriteLine("flatten: " + e.Message);
                return 2;
            }
        }
    }
}
