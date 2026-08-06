// Packet.cs — блок 2: установка агента пакетного транспорта Windows -> Ubuntu.
// ТЗ: work/installer-exe/AGENT_TZ.md; контракт: docs/PACKET_CONTRACT.md (§8 протокол,
// §10 конфиг). Существующие шаги канала OData этот файл не трогает: блок вызывается
// ПОСЛЕ успешной проверки OData и только когда рядом с exe лежит комплект
// (packet-setup.json + packet-agent.exe + age.exe + zstd.exe).
// C# 5 (csc.exe из .NET Framework) — БЕЗ интерполяции строк, ?., nameof, out var.
using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;

namespace Oc1c
{
    // ------------------------------------------------------- комплект от Ubuntu
    // packet-setup.json генерируется на Ubuntu один раз на базу:
    // {"base_id":"ut","token":"…","recipient_pubkey":"age1…","receiver_url":"https://…"}
    internal class PacketSetup
    {
        public string BaseId, Token, RecipientPubkey, ReceiverUrl;
        public string JsonPath;     // откуда прочитан (для лога)

        static readonly Regex BaseIdRe = new Regex("^[a-z0-9_-]+$", RegexOptions.Compiled);

        // null при успехе, иначе текст ошибки (комплект не от этой установки / неполный).
        public static string Load(string path, out PacketSetup ps)
        {
            ps = null;
            if (!File.Exists(path)) return "файл не найден: " + path;
            Dictionary<string, object> d;
            try
            {
                string json = File.ReadAllText(path, Encoding.UTF8);
                d = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(json);
            }
            catch (Exception e) { return "packet-setup.json не читается как JSON: " + e.Message; }
            if (d == null) return "packet-setup.json пуст или не JSON-объект";

            PacketSetup p = new PacketSetup();
            p.JsonPath = path;
            p.BaseId = Str(d, "base_id");
            p.Token = Str(d, "token");
            p.RecipientPubkey = Str(d, "recipient_pubkey");
            p.ReceiverUrl = Str(d, "receiver_url");

            if (string.IsNullOrEmpty(p.BaseId) || !BaseIdRe.IsMatch(p.BaseId))
                return "packet-setup.json: base_id пуст или не вида [a-z0-9_-]+ («" + p.BaseId + "»)";
            if (string.IsNullOrEmpty(p.Token))
                return "packet-setup.json: token пуст — комплект не от этой установки";
            // pubkey необязателен: канал уже шифрован TLS (Windows→FreeBSD) + SSH-туннелем
            // (FreeBSD→Ubuntu) — решение владельца 06.08 «быстро, для пилота». Если поле
            // есть — обязано быть age1… (age-слой добавится позже без смены установщика).
            if (!string.IsNullOrEmpty(p.RecipientPubkey) && !p.RecipientPubkey.StartsWith("age1"))
                return "packet-setup.json: recipient_pubkey не вида age1… («" + p.RecipientPubkey + "»)";
            if (string.IsNullOrEmpty(p.ReceiverUrl) ||
                !p.ReceiverUrl.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
                return "packet-setup.json: receiver_url должен быть https://… («" + p.ReceiverUrl + "»)";
            p.ReceiverUrl = p.ReceiverUrl.TrimEnd('/');
            ps = p;
            return null;
        }

        static string Str(Dictionary<string, object> d, string key)
        {
            object v;
            if (!d.TryGetValue(key, out v) || v == null) return "";
            return v.ToString().Trim();
        }
    }

    internal static class PacketSteps
    {
        // Коды ошибок приёмника (контракт §8) -> понятная строка (ТЗ §6).
        static readonly string[,] ReceiverErrors = new string[,]
        {
            { "unauthorized",       "токен отклонён приёмником — комплект не от этой установки или токен перевыпущен" },
            { "bad_auth",           "токен отклонён приёмником — комплект не от этой установки или токен перевыпущен" },
            { "stale_seq",          "комплект уже использовался (stale_seq) — запросите на сервере новый комплект базы" },
            { "quarantined",        "приёмник перевёл базу в карантин — звоните нам" },
            { "version_unsupported","приёмник не принимает версию манифеста агента — обновите комплект" },
            { "manifest_decrypt_failed", "приёмник не смог расшифровать пакет — ключ комплекта не совпадает с ключом сервера" },
        };

        // Каталог, где лежит сам setup exe, — там же ищем комплект по умолчанию.
        public static string ExeDir()
        {
            try { return Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location); }
            catch { return "."; }
        }

        // ============================================================ главный вход блока
        // Возвращает код выхода: 0 — агент установлен и доставка подтверждена (или блок
        // не активен); EXIT_PREREQ — префлайт; EXIT_PACKET — установка/пробная посылка.
        // odataUrl — локальный адрес OData (agent.ini читает 1С с localhost).
        public static int Run(Opts o, BaseRef bref, string odataUrl)
        {
            if (o.SkipPacket)
            {
                Log.Skip("агент пакетного транспорта отключён ключом --skip-packet");
                return Program.EXIT_OK;
            }
            string kit = string.IsNullOrEmpty(o.PacketKit) ? ExeDir() : o.PacketKit;
            string setupPath = string.IsNullOrEmpty(o.PacketSetupPath)
                ? Path.Combine(kit, "packet-setup.json") : o.PacketSetupPath;
            if (!File.Exists(setupPath) && string.IsNullOrEmpty(o.PacketSetupPath))
            {
                // Комплекта нет — поведение как у версии 1.1.0: блок не активен.
                Log.Skip("комплект пакетного транспорта не найден (packet-setup.json рядом с exe) — агент не устанавливается");
                return Program.EXIT_OK;
            }

            Log.Head("БЛОК 2: АГЕНТ ПАКЕТНОГО ТРАНСПОРТА (Windows -> Ubuntu)");
            Log.Con("Канал: агент на этой машине шлёт зашифрованные пакеты на сервер,");
            Log.Con("сам опрашивает конфиг. Входящие порты на Windows НЕ нужны.");

            // ---------- 1. комплект и его валидность
            Log.Step(1, 5, "Комплект установки (packet-setup.json)");
            PacketSetup ps;
            string err = PacketSetup.Load(setupPath, out ps);
            if (err != null)
            {
                Log.Err(err);
                Log.Fix("комплект генерируется на сервере Ubuntu один раз на базу — запросите свежий packet-setup.json");
                return Program.EXIT_PREREQ;
            }
            Log.AddSecret(ps.Token);
            Log.Ok("база «" + ps.BaseId + "», приёмник " + ps.ReceiverUrl);
            if (string.IsNullOrEmpty(ps.RecipientPubkey))
                Log.Info("комплект без age-ключа: канал шифруется TLS + SSH-туннелем (1c-gate), age добавится позже");

            string agentExe = Path.Combine(kit, "packet-agent.exe");
            string ageExe = Path.Combine(kit, "age.exe");
            string zstdExe = Path.Combine(kit, "zstd.exe");
            // age.exe обязателен, только когда комплект с age-ключом; канал TLS+SSH
            // (пилот без age-слоя) обходится без него. zstd нужен всегда (сжатие — §4).
            bool needAge = !string.IsNullOrEmpty(ps.RecipientPubkey);
            bool kitOk = true;
            if (!File.Exists(agentExe)) { Log.Err("в комплекте нет packet-agent.exe (" + kit + ")"); kitOk = false; }
            if (needAge && !File.Exists(ageExe)) { Log.Err("в комплекте нет age.exe (" + kit + ")"); kitOk = false; }
            if (!File.Exists(zstdExe)) { Log.Err("в комплекте нет zstd.exe (" + kit + ")"); kitOk = false; }
            if (!kitOk)
            {
                Log.Fix("комплект неполный: положите рядом с setup exe файлы packet-agent.exe, zstd.exe" +
                        (needAge ? ", age.exe" : "") +
                        " из поставки (возможно, их удалил антивирус — проверьте карантин)");
                return Program.EXIT_PREREQ;
            }
            if (!RunsOk(zstdExe, "--version", "zstd") ||
                (needAge && !RunsOk(ageExe, "--version", "age")))
            {
                Log.Fix("комплект неполный или файлы заблокированы антивирусом — переустановите комплект");
                return Program.EXIT_PREREQ;
            }
            RunsOk(agentExe, "--version", "packet-agent");   // диагностика в лог, не стоп

            // ---------- 2. префлайт связи и места
            Log.Step(2, 5, "Префлайт: связь с приёмником и место на диске");
            if (!HealthOk(ps.ReceiverUrl))
            {
                Log.Fix("откройте ИСХОДЯЩИЙ 443/TCP на " + HostOf(ps.ReceiverUrl) +
                        " (входящее на Windows не нужно по построению)");
                return Program.EXIT_PREREQ;
            }

            string packetDir = string.IsNullOrEmpty(o.PacketDir) ? @"C:\1c\packet" : o.PacketDir;
            string dataDir = Path.Combine(packetDir, "data");
            if (!DiskOk(bref, packetDir)) return Program.EXIT_PREREQ;

            // ---------- 3. установка файлов и agent.ini
            Log.Step(3, 5, "Установка агента в " + packetDir);
            if (Ctx.DryRun)
            {
                Log.Sim("скопировал бы packet-agent.exe, age.exe, zstd.exe в " + packetDir);
                Log.Sim("записал бы agent.ini (база «" + ps.BaseId + "», права — только администраторам и SYSTEM)");
            }
            else if (!InstallFiles(kit, packetDir, dataDir, ps, o, odataUrl))
                return Program.EXIT_PACKET;

            // ---------- 4. автозапуск (планировщик, SYSTEM)
            Log.Step(4, 5, "Автозапуск агента (планировщик задач)");
            if (Ctx.DryRun)
                Log.Sim("создал бы задачи «" + TaskName + "» (при старте системы) и «" + WatchdogName + "» (каждые 5 мин) под SYSTEM");
            else if (!EnsureTasks(packetDir))
                return Program.EXIT_PACKET;

            // ---------- 5. пробная посылка (данные, не «запустилось»)
            Log.Step(5, 5, "Пробная посылка (подтверждение доставки приёмником)");
            if (Ctx.DryRun)
            {
                Log.Sim("запустил бы packet-agent.exe --smoke и ждал бы verified от приёмника");
                Log.Ok("блок агента: префлайт пройден (режим проверки — ничего не менялось)");
                return Program.EXIT_OK;
            }
            return Smoke(packetDir) ? Program.EXIT_OK : Program.EXIT_PACKET;
        }

        // ============================================================ префлайт-составляющие
        static bool RunsOk(string exe, string args, string label)
        {
            ExecResult r = Proc.Run(exe, args, 30000, Proc.Oem, null, null);
            if (r.Ok) { Log.Ok(label + " запускается: " + FirstLine(r.StdOut)); return true; }
            Log.Err(label + " не запускается (" + exe + "): " + r.Tail(2));
            return false;
        }

        static string FirstLine(string s)
        {
            if (string.IsNullOrEmpty(s)) return "(пустой вывод)";
            string t = s.Replace("\r\n", "\n").Trim();
            int i = t.IndexOf('\n');
            return i < 0 ? t : t.Substring(0, i);
        }

        static string HostOf(string url)
        {
            try { return new Uri(url).Host; } catch { return url; }
        }

        // Исходящий HTTPS на приёмник: TLS handshake + GET /health -> packet-server-ok.
        static bool HealthOk(string receiverUrl)
        {
            string url = receiverUrl + "/health";
            try
            {
                // На .NET 4.x по умолчанию может быть TLS 1.0 — приёмник его не примет.
                try { ServicePointManager.SecurityProtocol = (SecurityProtocolType)3072; } catch { }
                ServicePointManager.Expect100Continue = false;
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create(url);
                req.Method = "GET";
                req.Timeout = 20000;
                req.ReadWriteTimeout = 20000;
                req.UserAgent = "setup-1c-odata/" + Ctx.ToolVersion;
                req.AllowAutoRedirect = false;
                using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                using (StreamReader sr = new StreamReader(resp.GetResponseStream(), Encoding.UTF8))
                {
                    string body = sr.ReadToEnd();
                    if ((int)resp.StatusCode == 200 && body.IndexOf("packet-server-ok") >= 0)
                    {
                        Log.Ok("приёмник отвечает: " + url + " -> packet-server-ok");
                        return true;
                    }
                    Log.Err("приёмник ответил HTTP " + (int)resp.StatusCode + ", но не «packet-server-ok»");
                    return false;
                }
            }
            catch (WebException we)
            {
                HttpWebResponse resp = we.Response as HttpWebResponse;
                if (resp != null)
                    Log.Err("приёмник ответил HTTP " + (int)resp.StatusCode + " на " + url);
                else
                    Log.Err("нет связи с приёмником: " + we.Message);
                return false;
            }
            catch (Exception e)
            {
                Log.Err("нет связи с приёмником: " + e.Message);
                return false;
            }
        }

        // Место под данные агента: очередь чанков ≈ размер базы сжатой + индекс версий.
        static bool DiskOk(BaseRef bref, string packetDir)
        {
            long baseMb = (bref != null && bref.IsFile) ? Win.DirSizeMb(bref.Dir) : 0;
            long needMb = baseMb > 0 ? baseMb / 4 + 256 : 512;
            long free = Win.FreeSpaceMb(packetDir);
            Log.Info("данные агента: оценка ≥" + needMb + " МБ (очередь чанков ≈ база/4 + индекс версий), свободно " +
                     (free < 0 ? "?" : free.ToString()) + " МБ");
            if (free >= 0 && free < needMb)
            {
                Log.Err("мало места под данные агента: свободно " + free + " МБ, нужно ≥" + needMb + " МБ");
                Log.Fix("освободите диск или укажите --packet-dir на другом томе");
                return false;
            }
            Log.Ok("место под данные агента есть");
            return true;
        }

        // ============================================================ установка
        static bool InstallFiles(string kit, string packetDir, string dataDir,
                                 PacketSetup ps, Opts o, string odataUrl)
        {
            try
            {
                Directory.CreateDirectory(dataDir);
                // age.exe может отсутствовать в комплекте без age-слоя — копируем то, что есть.
                string[] names = { "packet-agent.exe", "zstd.exe", "age.exe" };
                for (int i = 0; i < names.Length; i++)
                {
                    string srcExe = Path.Combine(kit, names[i]);
                    if (!File.Exists(srcExe)) { Log.Skip(names[i] + " в комплекте нет — не копирую"); continue; }
                    File.Copy(srcExe, Path.Combine(packetDir, names[i]), true);
                    Log.Ok("установлен " + names[i]);
                }
            }
            catch (Exception e)
            {
                Log.Err("не удалось установить файлы в " + packetDir + ": " + e.Message);
                return false;
            }

            // agent.ini: секреты только в файл (в лог — как ***; Log.AddSecret уже вызван).
            string ini = Path.Combine(packetDir, "agent.ini");
            string reader = string.IsNullOrEmpty(o.ReaderUser) ? "ai_reader" : o.ReaderUser;
            StringBuilder sb = new StringBuilder();
            sb.AppendLine("# Агент пакетного транспорта 1С -> Ubuntu");
            sb.AppendLine("# Создан setup-1c-odata " + Ctx.ToolVersion + " " + DateTime.Now.ToString("yyyy-MM-dd HH:mm"));
            sb.AppendLine("# Права на этот файл: только администраторы и SYSTEM (внутри — токен и пароль читателя).");
            sb.AppendLine("base_id=" + ps.BaseId);
            sb.AppendLine("receiver_url=" + ps.ReceiverUrl);
            sb.AppendLine("token=" + ps.Token);
            if (!string.IsNullOrEmpty(ps.RecipientPubkey))
                sb.AppendLine("recipient_pubkey=" + ps.RecipientPubkey);
            sb.AppendLine("odata_url=" + odataUrl.TrimEnd('/'));
            sb.AppendLine("odata_user=" + reader);
            sb.AppendLine("odata_password=" + (o.ReaderPassword == null ? "" : o.ReaderPassword));
            sb.AppendLine("data_dir=" + dataDir);
            try
            {
                File.WriteAllText(ini, sb.ToString(), new UTF8Encoding(true));
                RestrictToAdmins(ini);
                Log.Ok("записан agent.ini (доступ — только администраторам и службе)");
            }
            catch (Exception e)
            {
                Log.Err("не удалось записать " + ini + ": " + e.Message);
                return false;
            }
            if (string.IsNullOrEmpty(o.ReaderPassword))
            {
                Log.Warn("пароль читателя 1С не задан (--reader-password) — агент не сможет читать OData");
                Log.Fix("запустите установщик с --reader-password, либо впишите пароль в " + ini + " строкой odata_password=");
            }
            Ctx.Changed = true;
            return true;
        }

        // Права на файл с секретами: без наследования, только Administrators и SYSTEM.
        static void RestrictToAdmins(string path)
        {
            FileSecurity fs = new FileSecurity();
            fs.SetAccessRuleProtection(true, false);
            fs.AddAccessRule(new FileSystemAccessRule(
                new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid, null),
                FileSystemRights.FullControl, AccessControlType.Allow));
            fs.AddAccessRule(new FileSystemAccessRule(
                new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null),
                FileSystemRights.FullControl, AccessControlType.Allow));
            File.SetAccessControl(path, fs);
        }

        // ============================================================ автозапуск
        const string TaskName = "1C Packet Agent";
        const string WatchdogName = "1C Packet Agent Watchdog";

        // Служба Windows требует служебного каркаса в самом exe; агент — обычная
        // программа-демон (такт задаётся сервером через конфиг), поэтому автозапуск —
        // планировщиком: задача при старте системы + сторож каждые 5 минут (второй
        // экземпляр агента обязан завершаться сам — контракт CLI агента, AGENT_TZ §7).
        static bool EnsureTasks(string packetDir)
        {
            string agent = Path.Combine(packetDir, "packet-agent.exe");
            string tr = "\"" + agent + "\"";
            if (!Schtasks("/Create /F /TN \"" + TaskName + "\" /TR \"" + tr + "\" /SC ONSTART /RU SYSTEM /RL HIGHEST"))
                return false;
            Log.Ok("задача «" + TaskName + "»: запуск при старте системы под SYSTEM");
            if (!Schtasks("/Create /F /TN \"" + WatchdogName + "\" /TR \"" + tr + "\" /SC MINUTE /MO 5 /RU SYSTEM /RL HIGHEST"))
                return false;
            Log.Ok("задача «" + WatchdogName + "»: сторож каждые 5 минут");
            ExecResult run = Proc.Run("schtasks.exe", "/Run /TN \"" + TaskName + "\"", 60000, Proc.Oem, null, null);
            if (run.Ok) Log.Ok("агент запущен");
            else Log.Warn("агент не стартовал сразу: " + run.Tail(2) + " — запустится сторожем в течение 5 минут");
            return true;
        }

        static bool Schtasks(string args)
        {
            ExecResult r = Proc.Run("schtasks.exe", args, 60000, Proc.Oem, null, null);
            if (r.Ok) { Ctx.Changed = true; return true; }
            Log.Err("планировщик задач отказал: " + r.Tail(2));
            Log.Fix("проверьте, что служба «Планировщик заданий» работает, и повторите");
            return false;
        }

        // ============================================================ пробная посылка
        // Живая проверка связности ДАННЫМИ: агент собирает тестовый пакет и доводит его
        // до verified/applied по протоколу §8 контракта. Код выхода exe — 0 только при
        // подтверждённой доставке (ТЗ §4).
        static bool Smoke(string packetDir)
        {
            string agent = Path.Combine(packetDir, "packet-agent.exe");
            Log.Info("запускаю: packet-agent.exe --smoke (тестовый пакет, ожидание verified)");
            ExecResult r = Proc.Run(agent, "--smoke", 600000, Proc.Oem, packetDir, null);
            if (r.Ok)
            {
                Log.Ok("доставка подтверждена приёмником: " + FirstLine(r.StdOut));
                Log.Con("Лог агента и его работа — " + Path.Combine(packetDir, "data"));
                return true;
            }
            string tail = r.Tail(4);
            string code = KnownReceiverError(tail);
            if (code != null) Log.Err(code);
            else if (r.TimedOut) Log.Err("нет связи с приёмником: пробная посылка не завершилась за 10 минут");
            else Log.Err("пробная посылка не подтверждена: " + tail);
            if (code == null)
                Log.Fix("подробности — в логе агента (" + Path.Combine(packetDir, "data") +
                        "); типовые причины: нет исходящего 443/TCP, токен отклонён, приёмник в карантине");
            return false;
        }

        static string KnownReceiverError(string text)
        {
            if (string.IsNullOrEmpty(text)) return null;
            for (int i = 0; i < ReceiverErrors.GetLength(0); i++)
                if (text.IndexOf(ReceiverErrors[i, 0], StringComparison.OrdinalIgnoreCase) >= 0)
                    return ReceiverErrors[i, 1];
            return null;
        }
    }
}
