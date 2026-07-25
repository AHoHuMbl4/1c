// Steps.cs — шаги настройки: платформа, база, бэкап, IIS, публикация, VRD, пул, права,
// состав OData (COM), проверка HTTP. Каждый шаг идемпотентен и умеет режим --check (ничего не менять).
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Text;
using System.Text.RegularExpressions;
using System.Xml.Linq;

namespace Oc1c
{
    // ---------------------------------------------------------------- платформа 1С
    internal class Platform
    {
        public string Version;
        public string Root;
        public string Bin;
        public string V8Exe, Webinst, Wsisapi, Comcntr;
        public bool X86;
        public int[] Ver = new int[4];
        public bool HasWeb { get { return Wsisapi != null; } }
        public bool HasCom { get { return Comcntr != null; } }
        public string ProgId { get { return "V" + Ver[0] + Ver[1] + ".COMConnector"; } }
        public override string ToString()
        {
            return Version + " (" + (X86 ? "x86" : "x64") + ") " + Root;
        }
    }

    // ---------------------------------------------------------------- ссылка на базу
    internal class BaseRef
    {
        public bool IsFile;
        public string Dir;                 // файловая база
        public string Srvr, Name;          // клиент-серверная

        public string ConnStrPlain
        {
            get
            {
                if (IsFile) return "File='" + Dir + "';";
                return "Srvr='" + Srvr + "';Ref='" + Name + "';";
            }
        }
        public string ConnStrCom(string usr, string pwd)
        {
            string s = ConnStrPlain;
            if (!string.IsNullOrEmpty(usr)) s += "Usr=\"" + usr + "\";Pwd=\"" + (pwd == null ? "" : pwd) + "\";";
            return s;
        }
        public string Display { get { return IsFile ? ("файловая: " + Dir) : ("клиент-серверная: " + Srvr + " / " + Name); } }
    }

    internal static class Steps
    {
        public static string AppCmd
        {
            get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "inetsrv\\appcmd.exe"); }
        }

        // ============================================================ 1. платформа 1С
        public static List<Platform> FindPlatforms(string explicitDir)
        {
            List<Platform> res = new List<Platform>();
            List<string> roots = new List<string>();
            if (!string.IsNullOrEmpty(explicitDir)) roots.Add(explicitDir);
            else
            {
                string[] env = new string[] { "ProgramW6432", "ProgramFiles(x86)", "ProgramFiles" };
                for (int i = 0; i < env.Length; i++)
                {
                    string pf = Environment.GetEnvironmentVariable(env[i]);
                    if (!string.IsNullOrEmpty(pf))
                    {
                        string c = Path.Combine(pf, "1cv8");
                        if (Directory.Exists(c) && !roots.Contains(c)) roots.Add(c);
                    }
                }
            }

            for (int i = 0; i < roots.Count; i++)
            {
                string root = roots[i];
                string[] dirs;
                try { dirs = Directory.GetDirectories(root); }
                catch { continue; }
                for (int j = 0; j < dirs.Length; j++)
                {
                    string name = Path.GetFileName(dirs[j]);
                    Match m = Regex.Match(name, @"^(\d+)\.(\d+)\.(\d+)\.(\d+)$");
                    if (!m.Success) continue;                       // common / conf / прочее — пропускаем
                    string bin = Path.Combine(dirs[j], "bin");
                    string v8 = Path.Combine(bin, "1cv8.exe");
                    if (!File.Exists(v8)) continue;

                    Platform p = new Platform();
                    p.Version = name;
                    p.Root = dirs[j];
                    p.Bin = bin;
                    p.V8Exe = v8;
                    for (int k = 0; k < 4; k++) p.Ver[k] = int.Parse(m.Groups[k + 1].Value);
                    string w = Path.Combine(bin, "webinst.exe"); p.Webinst = File.Exists(w) ? w : null;
                    string i2 = Path.Combine(bin, "wsisapi.dll"); p.Wsisapi = File.Exists(i2) ? i2 : null;
                    string c2 = Path.Combine(bin, "comcntr.dll"); p.Comcntr = File.Exists(c2) ? c2 : null;
                    p.X86 = Win.PeMachine(v8) == "x86";
                    res.Add(p);
                }
            }
            res.Sort(delegate(Platform a, Platform b)
            {
                for (int k = 0; k < 4; k++) if (a.Ver[k] != b.Ver[k]) return b.Ver[k].CompareTo(a.Ver[k]);
                return 0;
            });
            return res;
        }

        // ============================================================ 2. база
        public static BaseRef ResolveBase(string basePath, string connStr)
        {
            if (!string.IsNullOrEmpty(connStr))
            {
                BaseRef b = new BaseRef();
                Match f = Regex.Match(connStr, "File\\s*=\\s*[\"']?([^\"';]+)", RegexOptions.IgnoreCase);
                if (f.Success) { b.IsFile = true; b.Dir = f.Groups[1].Value.Trim(); return b; }
                Match s = Regex.Match(connStr, "Srvr\\s*=\\s*[\"']?([^\"';]+)", RegexOptions.IgnoreCase);
                Match r = Regex.Match(connStr, "Ref\\s*=\\s*[\"']?([^\"';]+)", RegexOptions.IgnoreCase);
                if (s.Success && r.Success)
                {
                    b.IsFile = false; b.Srvr = s.Groups[1].Value.Trim(); b.Name = r.Groups[1].Value.Trim(); return b;
                }
                return null;
            }
            if (!string.IsNullOrEmpty(basePath))
            {
                BaseRef b = new BaseRef();
                b.IsFile = true;
                b.Dir = Path.GetFullPath(basePath.TrimEnd('\\'));
                return b;
            }
            return null;
        }

        public static List<string> ScanFileBases(string root)
        {
            List<string> res = new List<string>();
            try
            {
                if (!Directory.Exists(root)) return res;
                string[] dirs = Directory.GetDirectories(root);
                for (int i = 0; i < dirs.Length; i++)
                    if (File.Exists(Path.Combine(dirs[i], "1Cv8.1CD"))) res.Add(dirs[i]);
            }
            catch { }
            return res;
        }

        // ============================================================ 3. бэкап (правило проекта)
        public static bool BackupZip(BaseRef b, string backupDir)
        {
            string src = b.Dir;
            long sizeMb = Win.DirSizeMb(src);
            long freeMb = Win.FreeSpaceMb(backupDir);
            Log.Info("размер базы ~" + (sizeMb < 0 ? "?" : sizeMb.ToString()) + " МБ, свободно на диске бэкапа " +
                     (freeMb < 0 ? "?" : freeMb.ToString()) + " МБ");
            if (sizeMb > 0 && freeMb > 0 && freeMb < sizeMb)
            {
                Log.Err("на диске бэкапа мало места (" + freeMb + " МБ < размера базы " + sizeMb + " МБ)");
                Log.Fix("освободите место, укажите другой --backup-dir или запустите с --no-backup (на свой риск)");
                return false;
            }
            string dst = Path.Combine(backupDir, Path.GetFileName(src) + "_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".zip");
            if (Ctx.DryRun) { Log.Sim("создал бы бэкап " + dst); return true; }
            bool mainOk = false;                      // попал ли в архив сам файл базы 1Cv8.1CD
            try
            {
                if (!Directory.Exists(backupDir)) Directory.CreateDirectory(backupDir);
                using (FileStream zs = new FileStream(dst, FileMode.Create, FileAccess.Write))
                using (ZipArchive zip = new ZipArchive(zs, ZipArchiveMode.Create))
                {
                    string[] files = Directory.GetFiles(src, "*", SearchOption.AllDirectories);
                    for (int i = 0; i < files.Length; i++)
                    {
                        string rel = files[i].Substring(src.Length).TrimStart('\\');
                        if (IsTransient(rel)) { Log.File("служебный файл не архивируем: " + rel); continue; }
                        try
                        {
                            // FileShare.ReadWrite — файлы базы могут быть открыты сеансами 1С
                            using (FileStream fs = new FileStream(files[i], FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                            {
                                ZipArchiveEntry e = zip.CreateEntry(rel, CompressionLevel.Fastest);
                                using (Stream es = e.Open()) fs.CopyTo(es);
                            }
                            if (rel.Equals("1Cv8.1CD", StringComparison.OrdinalIgnoreCase)) mainOk = true;
                        }
                        catch (Exception ex) { Log.Warn("файл пропущен в бэкапе (" + rel + "): " + ex.Message); }
                    }
                }
                // Без главного файла копия бесполезна — тогда менять базу НЕЛЬЗЯ.
                if (!mainOk)
                {
                    Log.Err("в бэкап не попал главный файл базы 1Cv8.1CD — копия непригодна");
                    Log.Fix("закройте сеансы 1С (включая веб-клиент) и повторите, либо сделайте копию сами " +
                            "(Конфигуратор -> Администрирование -> Выгрузить информационную базу) и запустите с --no-backup");
                    try { File.Delete(dst); } catch { }
                    return false;
                }
                Ctx.Changed = true;
                Log.Ok("бэкап: " + dst + " (" + (new FileInfo(dst).Length / 1024 / 1024) + " МБ)");
                RotateBackups(backupDir, Path.GetFileName(src), 5);
                return true;
            }
            catch (Exception e)
            {
                Log.Err("бэкап не создан: " + e.Message);
                return false;
            }
        }

        // Служебные файлы 1С: блокировки, временные, каталог сеансов. В копии им не место —
        // они всегда заняты работающими сеансами и данных не содержат. Молча пропускаем,
        // чтобы предупреждения оставались только про НАСТОЯЩИЕ проблемы.
        static bool IsTransient(string rel)
        {
            string low = rel.ToLowerInvariant();
            if (low.StartsWith("1cv8temp\\") || low.IndexOf("\\1cv8temp\\") >= 0) return true;
            if (low.EndsWith(".cfl") || low.EndsWith(".tmp") || low.EndsWith(".lck")) return true;
            if (low.StartsWith("1cv8tmp.") || low.StartsWith("1cv8snc.")) return true;
            return false;
        }

        // Держим последние N копий этой базы — иначе повторные запуски забьют диск (база может быть в гигабайтах).
        static void RotateBackups(string backupDir, string baseName, int keep)
        {
            try
            {
                string[] files = Directory.GetFiles(backupDir, baseName + "_*.zip");
                if (files.Length <= keep) return;
                Array.Sort(files, delegate(string a, string b)
                {
                    return File.GetLastWriteTimeUtc(b).CompareTo(File.GetLastWriteTimeUtc(a));
                });
                for (int i = keep; i < files.Length; i++)
                {
                    try { File.Delete(files[i]); Log.Info("удалён старый бэкап: " + Path.GetFileName(files[i])); }
                    catch (Exception e) { Log.File("не удалить старый бэкап " + files[i] + ": " + e.Message); }
                }
            }
            catch (Exception e) { Log.File("ротация бэкапов пропущена: " + e.Message); }
        }

        // ============================================================ 4. компоненты IIS
        static readonly string[] IisRequired = new string[] {
            "IIS-WebServerRole","IIS-WebServer","IIS-CommonHttpFeatures","IIS-StaticContent","IIS-DefaultDocument",
            "IIS-HttpErrors","IIS-RequestFiltering","IIS-Security","IIS-ISAPIExtensions","IIS-ISAPIFilter","IIS-CGI",
            "IIS-WebServerManagementTools","IIS-ManagementConsole"
        };
        static readonly string[] IisOptional = new string[] { "IIS-HttpLogging", "IIS-HttpCompressionStatic" };

        // Возвращает: 0 — всё на месте; 1 — включили, нужен ребут; 2 — включили без ребута; -1 — ошибка
        public static int EnsureIis(out string detail)
        {
            detail = "";
            StringBuilder sb = new StringBuilder();
            sb.AppendLine("$names=@('" + string.Join("','", IisRequired) + "','" + string.Join("','", IisOptional) + "')");
            sb.AppendLine("$out=@()");
            sb.AppendLine("foreach($n in $names){");
            sb.AppendLine("  try{ $f=Get-WindowsOptionalFeature -Online -FeatureName $n -ErrorAction Stop; $out+=($n+'='+$f.State) }");
            sb.AppendLine("  catch{ $out+=($n+'=Absent') } }");
            sb.AppendLine("$out -join \"`n\"");
            ExecResult r = Ps.Run(sb.ToString(), false, 300000, null);
            if (!r.Ok)
            {
                // Windows Server: возможен путь через ServerManager
                Log.Warn("Get-WindowsOptionalFeature недоступен: " + r.Tail(2));
                ExecResult sv = Ps.Run("try{ Import-Module ServerManager -EA Stop; (Get-WindowsFeature Web-Server).Installed }catch{ 'NOMODULE' }", false, 120000, null);
                if (sv.Ok && sv.StdOut.IndexOf("True", StringComparison.OrdinalIgnoreCase) >= 0)
                { detail = "Windows Server: роль Web-Server уже установлена"; return 0; }
                if (sv.Ok && sv.StdOut.IndexOf("False", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    if (Ctx.DryRun) { Log.Sim("установил бы роль Web-Server (Install-WindowsFeature)"); return 2; }
                    ExecResult ins = Ps.Run("$r=Install-WindowsFeature Web-Server,Web-ISAPI-Ext,Web-ISAPI-Filter,Web-CGI,Web-Basic-Auth,Web-Mgmt-Console -ErrorAction Stop; 'RESTART='+$r.RestartNeeded", false, 900000, null);
                    if (!ins.Ok) { detail = ins.Tail(3); return -1; }
                    detail = "роль Web-Server установлена (Server SKU)";
                    Ctx.Changed = true;
                    return ins.StdOut.IndexOf("RESTART=Yes", StringComparison.OrdinalIgnoreCase) >= 0 ? 1 : 2;
                }
                detail = "не удалось определить состояние компонентов IIS";
                return -1;
            }

            List<string> missing = new List<string>();
            List<string> pending = new List<string>();
            string[] lines = r.StdOut.Replace("\r\n", "\n").Split('\n');
            Dictionary<string, string> state = new Dictionary<string, string>();
            for (int i = 0; i < lines.Length; i++)
            {
                string l = lines[i].Trim();
                int eq = l.IndexOf('=');
                if (eq <= 0) continue;
                string k = l.Substring(0, eq), v = l.Substring(eq + 1);
                state[k] = v;
            }
            for (int i = 0; i < IisRequired.Length; i++)
            {
                string v;
                if (!state.TryGetValue(IisRequired[i], out v)) v = "Absent";
                if (v.StartsWith("EnablePending", StringComparison.OrdinalIgnoreCase)) pending.Add(IisRequired[i]);
                else if (!v.Equals("Enabled", StringComparison.OrdinalIgnoreCase)) missing.Add(IisRequired[i]);
            }
            List<string> missOpt = new List<string>();
            for (int i = 0; i < IisOptional.Length; i++)
            {
                string v;
                if (state.TryGetValue(IisOptional[i], out v) && !v.Equals("Enabled", StringComparison.OrdinalIgnoreCase)) missOpt.Add(IisOptional[i]);
            }

            if (pending.Count > 0)
            {
                detail = "компоненты ждут перезагрузки: " + string.Join(", ", pending.ToArray());
                return 1;
            }
            if (missing.Count == 0)
            {
                detail = "все обязательные компоненты включены" + (missOpt.Count > 0 ? " (необязательные выключены: " + string.Join(", ", missOpt.ToArray()) + ")" : "");
                return 0;
            }

            Log.Info("не хватает компонентов IIS: " + string.Join(", ", missing.ToArray()));
            if (Ctx.DryRun) { Log.Sim("включил бы: " + string.Join(", ", missing.ToArray()) + " (может потребоваться перезагрузка)"); detail = "симуляция"; return 2; }

            List<string> toEnable = new List<string>(missing);
            toEnable.AddRange(missOpt);
            string ps = "$r=Enable-WindowsOptionalFeature -Online -All -NoRestart -FeatureName " +
                        string.Join(",", toEnable.ToArray()) + " -ErrorAction Stop; 'RESTART=' + $r.RestartNeeded";
            ExecResult en = Ps.Run(ps, false, 1800000, null);
            if (!en.Ok) { detail = "не удалось включить компоненты: " + en.Tail(4); return -1; }
            Ctx.Changed = true;
            detail = "включено: " + string.Join(", ", toEnable.ToArray());
            return en.StdOut.IndexOf("RESTART=True", StringComparison.OrdinalIgnoreCase) >= 0 ? 1 : 2;
        }

        // ============================================================ 5. служба W3SVC
        public static bool EnsureW3svc(out string detail)
        {
            detail = "";
            string start = Win.RegStr(@"SYSTEM\CurrentControlSet\Services\W3SVC", "Start");
            if (start == null) { detail = "служба W3SVC не зарегистрирована (IIS не установлен?)"; return false; }

            ExecResult q = Proc.Run("sc.exe", "query W3SVC", 30000, Proc.Oem, null, null);
            bool running = q.All.IndexOf("RUNNING", StringComparison.OrdinalIgnoreCase) >= 0 ||
                           q.All.IndexOf("РАБОТАЕТ", StringComparison.OrdinalIgnoreCase) >= 0;
            bool auto = start == "2";

            if (running && auto) { detail = "запущена, тип запуска: Автоматически"; return true; }
            if (Ctx.DryRun) { Log.Sim("перевёл бы W3SVC в Автоматически и запустил"); detail = "симуляция"; return true; }

            if (!auto)
            {
                ExecResult c = Proc.Run("sc.exe", "config W3SVC start= auto", 30000, Proc.Oem, null, null);
                if (!c.Ok) Log.Warn("не удалось выставить автозапуск W3SVC: " + c.Tail(2)); else Ctx.Changed = true;
            }
            if (!running)
            {
                ExecResult s = Proc.Run("sc.exe", "start W3SVC", 60000, Proc.Oem, null, null);
                if (!s.Ok && s.All.IndexOf("1056") < 0)
                {
                    detail = "не удалось запустить W3SVC: " + s.Tail(2);
                    return false;
                }
                Ctx.Changed = true;
            }
            detail = "служба приведена в состояние: Автоматически + запущена";
            return true;
        }

        // ============================================================ 6. публикация базы (webinst)
        public static string VrdPath(string dir) { return Path.Combine(dir, "default.vrd"); }

        public static string VrdIb(string vrd)
        {
            try
            {
                XDocument d = XDocument.Load(vrd);
                XAttribute a = d.Root.Attribute("ib");
                return a == null ? null : a.Value;
            }
            catch { return null; }
        }

        public static bool Publish(Platform p, BaseRef b, string site, string alias, string dir, bool force, out string detail)
        {
            detail = "";
            string vrd = VrdPath(dir);
            if (File.Exists(vrd))
            {
                string ib = VrdIb(vrd);
                string want = b.IsFile ? b.Dir : b.Name;
                if (ib != null && want != null && ib.IndexOf(want, StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    detail = "уже опубликовано (" + vrd + ")";
                    return true;
                }
                if (!force)
                {
                    Log.Err("каталог публикации " + dir + " занят другой базой: ib=" + ib);
                    Log.Fix("укажите другой --alias/--dir или добавьте --force для перепубликации");
                    return false;
                }
                Log.Warn("перепубликация поверх существующей (--force): ib=" + ib);
            }

            if (p.Webinst == null)
            {
                Log.Err("не найден webinst.exe в " + p.Bin);
                Log.Fix("переустановите платформу 1С с компонентом «Модули расширения веб-сервера» (WEBSERVEREXT=1)");
                return false;
            }
            if (!p.HasWeb)
            {
                Log.Err("не найден wsisapi.dll в " + p.Bin + " — модуль расширения веб-сервера НЕ установлен");
                Log.Fix("запустите установщик платформы 1С и добавьте «Модули расширения веб-сервера»; " +
                        "тихо: msiexec /i \"1CEnterprise 8.msi\" /qn WEBSERVEREXT=1 TRANSFORMS=1049.mst");
                return false;
            }

            if (Ctx.DryRun) { Log.Sim("опубликовал бы базу: webinst -publish -iis -wsdir " + alias + " -dir " + dir); detail = "симуляция"; return true; }

            try { if (!Directory.Exists(dir)) Directory.CreateDirectory(dir); }
            catch (Exception e) { Log.Err("не создать каталог публикации " + dir + ": " + e.Message); return false; }

            string args = "-publish -iis -wsdir " + alias + " -dir \"" + dir + "\" -connstr \"" + b.ConnStrPlain + "\"";
            ExecResult r = Proc.Run(p.Webinst, args, 180000, Proc.Oem, p.Bin, null);
            if (!File.Exists(vrd))
            {
                Log.Err("публикация не удалась (exit=" + r.ExitCode + "): " + r.Tail(4));
                Log.Fix("проверьте: запуск от администратора; IIS установлен; путь к базе доступен; " +
                        "в логе полный вывод webinst — " + Log.Path);
                return false;
            }
            Ctx.Changed = true;
            detail = "опубликовано: " + site + "/" + alias + " -> " + dir;
            return true;
        }

        // ============================================================ 7. включить OData в default.vrd
        public static bool EnableODataInVrd(string dir, out string detail)
        {
            detail = "";
            string vrd = VrdPath(dir);
            if (!File.Exists(vrd))
            {
                // в режиме проверки публикации ещё нет — это нормально
                if (Ctx.DryRun) { Log.Sim("включил бы standardOdata enable=\"true\" (после публикации)"); detail = "симуляция"; return true; }
                Log.Err("не найден " + vrd); return false;
            }
            XNamespace ns = "http://v8.1c.ru/8.2/virtual-resource-system";
            XDocument doc;
            try { doc = XDocument.Load(vrd, LoadOptions.PreserveWhitespace); }
            catch (Exception e) { Log.Err("не разобрать " + vrd + ": " + e.Message); return false; }

            XElement od = doc.Root.Element(ns + "standardOdata");
            bool already = od != null && od.Attribute("enable") != null &&
                           od.Attribute("enable").Value.Equals("true", StringComparison.OrdinalIgnoreCase);
            if (already) { detail = "standardOdata уже enable=\"true\""; return true; }

            if (Ctx.DryRun) { Log.Sim("включил бы standardOdata enable=\"true\" в " + vrd); detail = "симуляция"; return true; }

            try
            {
                string bak = vrd + ".bak-" + DateTime.Now.ToString("yyyyMMdd_HHmmss");
                File.Copy(vrd, bak, false);
                Log.Info("резервная копия vrd: " + bak);

                if (od == null)
                {
                    od = new XElement(ns + "standardOdata",
                        new XAttribute("enable", "true"),
                        new XAttribute("reuseSessions", "autouse"),
                        new XAttribute("sessionMaxAge", "20"),
                        new XAttribute("poolSize", "10"),
                        new XAttribute("poolTimeout", "5"));
                    doc.Root.Add(od);
                }
                else od.SetAttributeValue("enable", "true");

                doc.Save(vrd);
                Ctx.Changed = true;
                detail = "standardOdata enable=\"true\"";
                return true;
            }
            catch (Exception e) { Log.Err("не удалось изменить " + vrd + ": " + e.Message); return false; }
        }

        // ============================================================ 8. пул приложений
        static ExecResult Cmd(string args, int ms) { return Proc.Run(AppCmd, args, ms, Proc.Oem, null, null); }

        public static string CurrentAppPool(string site, string alias)
        {
            ExecResult r = Cmd("list app \"" + site + "/" + alias + "\" /text:applicationPool", 30000);
            if (!r.Ok) return null;
            string s = r.StdOut.Trim();
            return s.Length == 0 ? null : s;
        }

        public static bool EnsureAppPool(Platform p, string site, string alias, string pool, bool useDefault, out string detail)
        {
            detail = "";
            string cur = CurrentAppPool(site, alias);
            string target = useDefault ? (cur == null ? "DefaultAppPool" : cur) : pool;

            if (!useDefault)
            {
                ExecResult ex = Cmd("list apppool \"" + target + "\"", 30000);
                if (!ex.Ok || ex.StdOut.Trim().Length == 0)
                {
                    if (Ctx.DryRun) Log.Sim("создал бы пул приложений " + target);
                    else
                    {
                        ExecResult add = Cmd("add apppool /name:\"" + target + "\" /managedRuntimeVersion:\"\" /managedPipelineMode:Integrated /autoStart:true", 60000);
                        if (!add.Ok) { Log.Err("не создать пул " + target + ": " + add.Tail(3)); return false; }
                        Ctx.Changed = true;
                        Log.Ok("создан отдельный пул приложений: " + target);
                    }
                }
                if (cur != null && cur != target)
                {
                    if (Ctx.DryRun) Log.Sim("перевёл бы приложение " + site + "/" + alias + " в пул " + target);
                    else
                    {
                        ExecResult mv = Cmd("set app \"" + site + "/" + alias + "\" /applicationPool:\"" + target + "\"", 60000);
                        if (!mv.Ok) { Log.Err("не перевести приложение в пул " + target + ": " + mv.Tail(3)); return false; }
                        Ctx.Changed = true;
                        Log.Ok("приложение переведено в пул " + target + " (было: " + cur + ")");
                    }
                }
            }

            // разрядность пула — строго по разрядности платформы 1С
            string want32 = p.X86 ? "true" : "false";
            ExecResult st = Cmd("list apppool \"" + target + "\" /text:enable32BitAppOnWin64", 30000);
            string cur32 = st.Ok ? st.StdOut.Trim().ToLowerInvariant() : "";
            if (cur32 != want32)
            {
                if (Ctx.DryRun) Log.Sim("выставил бы enable32BitAppOnWin64=" + want32 + " (платформа " + (p.X86 ? "x86" : "x64") + ")");
                else
                {
                    ExecResult s32 = Cmd("set apppool \"" + target + "\" /enable32BitAppOnWin64:" + want32, 60000);
                    if (!s32.Ok) { Log.Err("не выставить разрядность пула: " + s32.Tail(3)); return false; }
                    Ctx.Changed = true;
                    Log.Ok("разрядность пула: enable32BitAppOnWin64=" + want32 + " (платформа " + (p.X86 ? "x86" : "x64") + ")");
                }
            }

            // прод-настройки: не выгружать пул (первый запрос OData «прогревается» долго)
            if (!Ctx.DryRun)
            {
                ExecResult warm = Cmd("set apppool \"" + target + "\" /processModel.idleTimeout:00:00:00 /recycling.periodicRestart.time:00:00:00 /autoStart:true", 60000);
                if (!warm.Ok) Log.Warn("не удалось отключить выгрузку пула по простою: " + warm.Tail(2));
                ExecResult sm = Cmd("set apppool \"" + target + "\" /startMode:AlwaysRunning", 60000);
                if (!sm.Ok) Log.File("startMode:AlwaysRunning недоступен (старый IIS) — не критично");
            }
            else Log.Sim("отключил бы выгрузку пула по простою (idleTimeout=0, без периодического перезапуска)");

            detail = "пул: " + target;
            return true;
        }

        public static void StartPool(string pool)
        {
            if (Ctx.DryRun) return;
            Cmd("start apppool \"" + pool + "\"", 60000);
        }

        public static void RecyclePool(string pool)
        {
            if (Ctx.DryRun) { Log.Sim("перезапустил бы пул " + pool); return; }
            ExecResult r = Cmd("recycle apppool \"" + pool + "\"", 60000);
            if (!r.Ok) Cmd("start apppool \"" + pool + "\"", 60000);
        }

        // ============================================================ 9. разрешение ISAPI на wsisapi.dll
        public static bool EnsureIsapiAllowed(Platform p, out string detail)
        {
            detail = "";
            if (!p.HasWeb) { detail = "wsisapi.dll отсутствует"; return false; }
            ExecResult list = Cmd("list config /section:isapiCgiRestriction /text:*", 60000);
            bool present = list.Ok && list.StdOut.IndexOf(p.Wsisapi, StringComparison.OrdinalIgnoreCase) >= 0;
            if (present)
            {
                // проверяем, что allowed=true рядом с нашим путём
                string txt = list.StdOut;
                int idx = txt.IndexOf(p.Wsisapi, StringComparison.OrdinalIgnoreCase);
                string tail = txt.Substring(idx, Math.Min(220, txt.Length - idx));
                if (Regex.IsMatch(tail, "allowed\\s*:\\s*\"?true", RegexOptions.IgnoreCase))
                { detail = "разрешение ISAPI уже есть"; return true; }

                if (Ctx.DryRun) { Log.Sim("включил бы allowed=true для " + p.Wsisapi); detail = "симуляция"; return true; }
                ExecResult up = Cmd("set config /section:isapiCgiRestriction /[path='" + p.Wsisapi + "'].allowed:true /commit:apphost", 60000);
                if (!up.Ok) { Log.Err("не включить разрешение ISAPI: " + up.Tail(3)); return false; }
                Ctx.Changed = true;
                detail = "разрешение ISAPI включено";
                return true;
            }

            if (Ctx.DryRun) { Log.Sim("добавил бы разрешение ISAPI для " + p.Wsisapi); detail = "симуляция"; return true; }
            ExecResult add = Cmd("set config /section:isapiCgiRestriction /+\"[path='" + p.Wsisapi +
                                 "',allowed='true',description='1C Web-service Extension']\" /commit:apphost", 60000);
            if (!add.Ok) { Log.Err("не добавить разрешение ISAPI: " + add.Tail(3)); return false; }
            Ctx.Changed = true;
            detail = "разрешение ISAPI добавлено";
            return true;
        }

        // ============================================================ 10. права на каталог файловой базы
        public static bool GrantAcl(BaseRef b, string pool, out string detail)
        {
            detail = "";
            if (!b.IsFile) { detail = "клиент-серверная база — права на каталог не нужны"; return true; }
            if (Ctx.DryRun) { Log.Sim("выдал бы права Modify на " + b.Dir + " для IIS AppPool\\" + pool + ", IIS_IUSRS, IUSR"); detail = "симуляция"; return true; }

            // Уже выдавали? Проверяем по идентификатору пула — он язык-нейтрален ("IIS APPPOOL\<имя>").
            // Без этой проверки icacls /T гонялся бы по всей базе при каждом запуске и «изменения» считались бы ложно.
            ExecResult have = Proc.Run("icacls.exe", "\"" + b.Dir + "\"", 60000, Proc.Oem, null, null);
            if (have.Ok && have.StdOut.IndexOf("APPPOOL\\" + pool, StringComparison.OrdinalIgnoreCase) >= 0)
            { detail = "права уже выданы (пул " + pool + ")"; return true; }

            string[] who = new string[] { "IIS AppPool\\" + pool, "*S-1-5-32-568", "*S-1-5-17" }; // пул, IIS_IUSRS, IUSR (SID — не зависят от локали)
            bool allOk = true;
            for (int i = 0; i < who.Length; i++)
            {
                ExecResult r = Proc.Run("icacls.exe", "\"" + b.Dir + "\" /grant \"" + who[i] + ":(OI)(CI)M\" /T /C /Q", 300000, Proc.Oem, null, null);
                if (!r.Ok) { Log.Warn("права для " + who[i] + " выданы не полностью: " + r.Tail(2)); allOk = false; }
            }
            Ctx.Changed = true;
            detail = allOk ? "права Modify выданы (пул, IIS_IUSRS, IUSR)" : "права выданы частично — см. лог";
            return true;
        }

        // ============================================================ 11. состав OData (COM)
        public static readonly Dictionary<string, string> ScopeMap = BuildScopeMap();
        static Dictionary<string, string> BuildScopeMap()
        {
            Dictionary<string, string> m = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            m["catalogs"] = "Справочники,Catalogs";
            m["documents"] = "Документы,Documents";
            m["accumulation-registers"] = "РегистрыНакопления,AccumulationRegisters";
            m["information-registers"] = "РегистрыСведений,InformationRegisters";
            m["accounting-registers"] = "РегистрыБухгалтерии,AccountingRegisters";
            m["calculation-registers"] = "РегистрыРасчета,CalculationRegisters";
            m["charts-of-accounts"] = "ПланыСчетов,ChartsOfAccounts";
            m["charts-of-characteristic-types"] = "ПланыВидовХарактеристик,ChartsOfCharacteristicTypes";
            m["charts-of-calculation-types"] = "ПланыВидовРасчета,ChartsOfCalculationTypes";
            m["enums"] = "Перечисления,Enums";
            m["constants"] = "Константы,Constants";
            m["exchange-plans"] = "ПланыОбмена,ExchangePlans";
            m["business-processes"] = "БизнесПроцессы,BusinessProcesses";
            m["tasks"] = "Задачи,Tasks";
            m["document-journals"] = "ЖурналыДокументов,DocumentJournals";
            return m;
        }

        public static List<string> ExpandScope(string scope, out string error)
        {
            error = null;
            List<string> keys = new List<string>();
            string s = (scope == null ? "" : scope.Trim().ToLowerInvariant());
            if (s == "" || s == "default")
            {
                keys.Add("catalogs"); keys.Add("documents");
            }
            else if (s == "analytics")
            {
                keys.AddRange(new string[] { "catalogs", "documents", "accumulation-registers", "information-registers",
                                             "accounting-registers", "charts-of-accounts", "enums" });
            }
            else if (s == "all")
            {
                foreach (KeyValuePair<string, string> kv in ScopeMap) keys.Add(kv.Key);
            }
            else
            {
                string[] parts = s.Split(',');
                for (int i = 0; i < parts.Length; i++)
                {
                    string k = parts[i].Trim();
                    if (k.Length == 0) continue;
                    if (!ScopeMap.ContainsKey(k)) { error = "неизвестный раздел состава OData: " + k; return null; }
                    keys.Add(k);
                }
                if (keys.Count == 0) { error = "пустой --scope"; return null; }
            }
            return keys;
        }

        static readonly Dictionary<string, string> ScopeRu = BuildScopeRu();

        // Человеческое имя раздела — для экранов, которые читает администратор 1С.
        public static string ScopeLabel(string key)
        {
            string ru;
            if (ScopeRu.TryGetValue(key, out ru)) return ru + " (" + key + ")";
            return key;
        }
        static Dictionary<string, string> BuildScopeRu()
        {
            Dictionary<string, string> m = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            m["catalogs"] = "Справочники";
            m["documents"] = "Документы";
            m["accumulation-registers"] = "Регистры накопления (обороты и остатки)";
            m["information-registers"] = "Регистры сведений";
            m["accounting-registers"] = "Регистры бухгалтерии";
            m["calculation-registers"] = "Регистры расчёта";
            m["charts-of-accounts"] = "Планы счетов";
            m["charts-of-characteristic-types"] = "Планы видов характеристик";
            m["charts-of-calculation-types"] = "Планы видов расчёта";
            m["enums"] = "Перечисления";
            m["constants"] = "Константы";
            m["exchange-plans"] = "Планы обмена";
            m["business-processes"] = "Бизнес-процессы";
            m["tasks"] = "Задачи";
            m["document-journals"] = "Журналы документов";
            return m;
        }

        // Точная инструкция для администратора 1С, если он не хочет вводить пароль в программу.
        public static string ManualScopeInstructions(BaseRef b, string alias, List<string> scopeKeys)
        {
            StringBuilder s = new StringBuilder();
            s.AppendLine("РУЧНАЯ НАСТРОЙКА СОСТАВА OData — выполняет администратор 1С (~5 минут)");
            s.AppendLine("");
            s.AppendLine("Зачем это нужно: без этого шага OData отдаёт ПУСТОЙ список объектов, и сервер");
            s.AppendLine("аналитики не увидит ни одной таблицы. Всё остальное уже настроено программой.");
            s.AppendLine("");
            s.AppendLine("0) СНАЧАЛА КОПИЯ БАЗЫ (обязательно):");
            s.AppendLine("   Конфигуратор -> Администрирование -> «Выгрузить информационную базу...»");
            s.AppendLine("   -> сохранить файл .dt в надёжное место.");
            s.AppendLine("");
            s.AppendLine("1) Открыть Конфигуратор для базы:");
            s.AppendLine("   " + (b.IsFile ? b.Dir : (b.Srvr + " / " + b.Name)));
            s.AppendLine("   (1С:Предприятие -> выбрать базу в списке -> кнопка «Конфигуратор»,");
            s.AppendLine("    войти пользователем с полными правами)");
            s.AppendLine("");
            s.AppendLine("2) Меню «Администрирование» -> «Состав стандартного интерфейса OData...»");
            s.AppendLine("");
            s.AppendLine("3) В открывшемся окне отметить флажками объекты, которые можно отдавать");
            s.AppendLine("   наружу (доступ будет ТОЛЬКО на чтение — под пользователем-читателем):");
            for (int i = 0; i < scopeKeys.Count; i++)
            {
                string ru;
                if (!ScopeRu.TryGetValue(scopeKeys[i], out ru)) ru = scopeKeys[i];
                s.AppendLine("     - " + ru);
            }
            s.AppendLine("   Отмечать можно как весь раздел целиком, так и отдельные объекты —");
            s.AppendLine("   что не отмечено, наружу не отдаётся вообще.");
            s.AppendLine("");
            s.AppendLine("4) Нажать «ОК». Состав сохраняется В САМОЙ БАЗЕ: он переживает");
            s.AppendLine("   перепубликацию, переустановку IIS и перенос на другой сервер.");
            s.AppendLine("");
            s.AppendLine("5) ПРОВЕРКА (любой из способов):");
            s.AppendLine("   а) открыть в браузере: http://localhost/" + alias + "/odata/standard.odata/");
            s.AppendLine("      ввести логин/пароль любого пользователя 1С -> должен прийти НЕПУСТОЙ");
            s.AppendLine("      список (много строк вида <collection href=\"...\">);");
            s.AppendLine("   б) снова запустить программу с ключом --skip-scope — шаг 13 покажет,");
            s.AppendLine("      сколько сущностей отдаёт OData (должно быть больше нуля).");
            return s.ToString();
        }

        // Скрипт COM: read — только прочитать текущий состав; write — установить.
        static string ComScript(bool write, bool checkReader)
        {
            // ВАЖНО (проверено на живом стенде): методы COM-объектов 1С зовём ПРЯМО ($o.Метод(...)).
            // Через [__ComObject].InvokeMember вызов ломается, когда аргумент — тоже COM-объект
            // (например $arr.Добавить(<объект метаданных>)). Свойства, наоборот, отдаются только
            // через InvokeMember(GetProperty) — это платформенный квирк, не наша прихоть.
            // Всё завёрнуто в try/catch с выводом 'ERROR=' в stdout: иначе PowerShell отдаёт
            // ошибку в stderr в виде CLIXML, и текст причины теряется.
            StringBuilder s = new StringBuilder();
            s.AppendLine("$GP=[Reflection.BindingFlags]::GetProperty");
            s.AppendLine("function P($o,$n){ [__ComObject].InvokeMember($n,$GP,$null,$o,@()) }");
            s.AppendLine("function PAny($o,$names){ $last=''; foreach($n in $names){ try { return (P $o $n) } catch { $last=$_.Exception.Message } } throw ('нет свойства ' + ($names -join '/') + ': ' + $last) }");
            s.AppendLine("try {");
            s.AppendLine("$connector = New-Object -ComObject $env:OC1C_PROGID");
            s.AppendLine("$ib = $connector.Connect($env:OC1C_CONNSTR)");
            s.AppendLine("$cur = -1");
            s.AppendLine("try {");
            s.AppendLine("  $c = $null");
            s.AppendLine("  try { $c = $ib.ПолучитьСоставСтандартногоИнтерфейсаOData() } catch { $c = $ib.GetStandardODataInterfaceContent() }");
            s.AppendLine("  if($c -ne $null){ try { $cur = [int]$c.Количество() } catch { $cur = [int]$c.Count() } }");
            s.AppendLine("} catch { $cur = -1 }");
            s.AppendLine("'CURRENT=' + $cur");
            if (checkReader)
            {
                s.AppendLine("try {");
                s.AppendLine("  $users = PAny $ib @('ПользователиИнформационнойБазы','InfoBaseUsers')");
                s.AppendLine("  $u = $null");
                s.AppendLine("  try { $u = $users.НайтиПоИмени($env:OC1C_READER) } catch { $u = $users.FindByName($env:OC1C_READER) }");
                s.AppendLine("  if($u -eq $null){ 'READER=NOTFOUND' } else {");
                s.AppendLine("    $roles = PAny $u @('Роли','Roles'); $rn=@()");
                s.AppendLine("    foreach($r in $roles){ try { $rn += (PAny $r @('Имя','Name')) } catch {} }");
                s.AppendLine("    'READER=FOUND'; 'ROLES=' + ($rn -join ', ') }");
                s.AppendLine("} catch { 'READER=ERROR:' + $_.Exception.Message }");
            }
            if (write)
            {
                s.AppendLine("$md = PAny $ib @('Metadata','Метаданные')");
                s.AppendLine("$arr = $null");
                s.AppendLine("try { $arr = $ib.NewObject('Array') } catch { $arr = $ib.NewObject('Массив') }");
                s.AppendLine("$added = 0; $skipped = @(); $addRu = $null");
                s.AppendLine("foreach($grp in ($env:OC1C_COLLECTIONS -split ';')){");
                s.AppendLine("  if(-not $grp){ continue }");
                s.AppendLine("  $coll = $null");
                s.AppendLine("  foreach($n in ($grp -split ',')){ try { $coll = P $md $n; break } catch {} }");
                s.AppendLine("  if($coll -eq $null){ $skipped += $grp; continue }");
                s.AppendLine("  foreach($o in $coll){");
                s.AppendLine("    if($addRu -eq $null){ try { $arr.Добавить($o); $addRu = $true } catch { $arr.Add($o); $addRu = $false } }");
                s.AppendLine("    elseif($addRu){ $arr.Добавить($o) } else { $arr.Add($o) }");
                s.AppendLine("    $added++ }");
                s.AppendLine("}");
                s.AppendLine("if($skipped.Count -gt 0){ 'SKIPPED=' + ($skipped -join ' ') }");
                s.AppendLine("if($added -eq 0){ throw 'в конфигурации не найдено ни одного объекта для публикации в OData' }");
                s.AppendLine("try { $ib.УстановитьСоставСтандартногоИнтерфейсаOData($arr) } catch { $ib.SetStandardODataInterfaceContent($arr) }");
                s.AppendLine("'ADDED=' + $added");
            }
            s.AppendLine("'RESULT=OK'");
            s.AppendLine("} catch { 'ERROR=' + $_.Exception.Message; exit 1 }");
            return s.ToString();
        }

        // Чистая строка ошибки: скрипт сам печатает 'ERROR=<текст>' в stdout,
        // потому что stderr от powershell.exe приходит в виде CLIXML и текст причины тонет.
        static string ComErrorLine(ExecResult r)
        {
            Match m = Regex.Match(r.StdOut, @"ERROR=(.+)");
            if (m.Success) return m.Groups[1].Value.Trim();
            return r.Tail(3);
        }

        static string TranslateComError(string raw)
        {
            string t = raw == null ? "" : raw;
            if (t.IndexOf("80040154") >= 0 || t.IndexOf("не зарегистрирован", StringComparison.OrdinalIgnoreCase) >= 0 ||
                t.IndexOf("not registered", StringComparison.OrdinalIgnoreCase) >= 0)
                return "COM-коннектор 1С не зарегистрирован (comcntr.dll)";
            if (t.IndexOf("Идентификация пользователя не выполнена", StringComparison.OrdinalIgnoreCase) >= 0 ||
                t.IndexOf("Неверн", StringComparison.OrdinalIgnoreCase) >= 0 && t.IndexOf("парол", StringComparison.OrdinalIgnoreCase) >= 0)
                return "неверные имя пользователя или пароль администратора 1С";
            if (t.IndexOf("лицензи", StringComparison.OrdinalIgnoreCase) >= 0 || t.IndexOf("license", StringComparison.OrdinalIgnoreCase) >= 0)
                return "не получена лицензия 1С для сеанса COM";
            if (t.IndexOf("заблокирован", StringComparison.OrdinalIgnoreCase) >= 0 || t.IndexOf("монопольн", StringComparison.OrdinalIgnoreCase) >= 0)
                return "база заблокирована (открыт конфигуратор или идёт другая операция)";
            if (t.IndexOf("Конфигурация базы данных не соответствует", StringComparison.OrdinalIgnoreCase) >= 0)
                return "конфигурация БД не обновлена (требуется обновление в конфигураторе)";
            return null;
        }

        // Возвращает true при успехе. current/added — что было и что стало.
        public static bool SetOdataComposition(Platform p, BaseRef b, string user, string pwd, List<string> scopeKeys,
                                               bool writeMode, string readerUser, out int current, out int added, out string roles)
        {
            current = -1; added = 0; roles = null;
            if (!p.HasCom)
            {
                Log.Err("не найден comcntr.dll в " + p.Bin + " — COM-коннектор недоступен");
                Log.Fix("переустановите платформу с компонентом «Модули расширения COM» или укажите другую --platform-version");
                return false;
            }

            List<string> colls = new List<string>();
            for (int i = 0; i < scopeKeys.Count; i++) colls.Add(ScopeMap[scopeKeys[i]]);

            Dictionary<string, string> env = new Dictionary<string, string>();
            env["OC1C_PROGID"] = p.ProgId;
            env["OC1C_CONNSTR"] = b.ConnStrCom(user, pwd);
            env["OC1C_COLLECTIONS"] = string.Join(";", colls.ToArray());
            if (!string.IsNullOrEmpty(readerUser)) env["OC1C_READER"] = readerUser;

            if (writeMode && Ctx.DryRun)
            {
                Log.Sim("установил бы состав OData: " + string.Join(", ", scopeKeys.ToArray()));
                writeMode = false;                        // в режиме проверки только читаем
            }

            string script = ComScript(writeMode, !string.IsNullOrEmpty(readerUser));
            ExecResult r = Ps.Run(script, p.X86, 600000, env);

            if (r.TimedOut)
            {
                Log.Err("COM-подключение к базе не ответило за 10 минут");
                Log.Fix("частая причина: база восстановлена из копии и ждёт ответа на вопрос «Это копия информационной базы?» — " +
                        "зайдите в базу один раз вручную (1С:Предприятие), ответьте на вопрос, затем повторите запуск");
                return false;
            }

            if (r.All.IndexOf("RESULT=OK") < 0)
            {
                string human = TranslateComError(r.All);
                if (human != null && human.StartsWith("COM-коннектор"))
                {
                    // пробуем зарегистрировать коннектор и повторить
                    Log.Warn(human + " — пробую зарегистрировать");
                    if (!Ctx.DryRun)
                    {
                        string win = Environment.GetEnvironmentVariable("windir");
                        string regsvr = Path.Combine(win, (p.X86 && Environment.Is64BitOperatingSystem ? "SysWOW64" : "System32") + "\\regsvr32.exe");
                        ExecResult reg = Proc.Run(regsvr, "/s \"" + p.Comcntr + "\"", 60000, Proc.Oem, p.Bin, null);
                        if (reg.Ok)
                        {
                            Ctx.Changed = true;
                            Log.Ok("comcntr.dll зарегистрирован, повторяю подключение");
                            r = Ps.Run(script, p.X86, 600000, env);
                        }
                        else Log.Err("regsvr32 не смог зарегистрировать " + p.Comcntr + ": " + reg.Tail(2));
                    }
                }
            }

            if (r.All.IndexOf("RESULT=OK") < 0)
            {
                string line = ComErrorLine(r);
                string human = TranslateComError(r.All);
                Log.Err("состав OData не задан: " + (human != null ? human + " (" + line + ")" : line));
                if (human != null && human.StartsWith("неверные"))
                    Log.Fix("проверьте --admin-user/--admin-password (пользователь 1С с полными правами)");
                else if (human != null && human.StartsWith("база заблокирована"))
                    Log.Fix("закройте конфигуратор и сеансы 1С, затем повторите");
                else if (human != null && human.StartsWith("не получена лицензия"))
                    Log.Fix("активируйте лицензию 1С на этой машине (в т.ч. учебную/комьюнити) и повторите");
                else
                    Log.Fix("полный текст ошибки — в логе: " + Log.Path);
                return false;
            }

            Match mc = Regex.Match(r.StdOut, @"CURRENT=(-?\d+)");
            if (mc.Success) current = int.Parse(mc.Groups[1].Value);
            Match ma = Regex.Match(r.StdOut, @"ADDED=(\d+)");
            if (ma.Success) { added = int.Parse(ma.Groups[1].Value); Ctx.Changed = true; }
            Match ms = Regex.Match(r.StdOut, @"SKIPPED=(.+)");
            if (ms.Success) Log.File("разделы, отсутствующие в конфигурации: " + ms.Groups[1].Value);
            Match mr = Regex.Match(r.StdOut, @"ROLES=(.*)");
            if (mr.Success) roles = mr.Groups[1].Value.Trim();
            if (r.StdOut.IndexOf("READER=NOTFOUND") >= 0) roles = "__NOTFOUND__";
            return true;
        }

        // ============================================================ 12. проверка по HTTP
        public class HttpProbe
        {
            public int Status;
            public int Collections = -1;
            public string Error;
            public bool Ok { get { return Status == 200; } }
        }

        public static HttpProbe Probe(string url, string user, string pwd, int timeoutMs)
        {
            HttpProbe pr = new HttpProbe();
            try
            {
                ServicePointManager.Expect100Continue = false;
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create(url);
                req.Method = "GET";
                req.Timeout = timeoutMs;
                req.ReadWriteTimeout = timeoutMs;
                req.UserAgent = "setup-1c-odata/" + Ctx.ToolVersion;
                req.AllowAutoRedirect = false;
                if (!string.IsNullOrEmpty(user))
                    req.Headers["Authorization"] = "Basic " +
                        Convert.ToBase64String(Encoding.UTF8.GetBytes(user + ":" + (pwd == null ? "" : pwd)));

                using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                {
                    pr.Status = (int)resp.StatusCode;
                    using (StreamReader sr = new StreamReader(resp.GetResponseStream(), Encoding.UTF8))
                    {
                        string body = sr.ReadToEnd();
                        pr.Collections = Regex.Matches(body, "<collection\\s+href=", RegexOptions.IgnoreCase).Count;
                        if (pr.Collections == 0)
                        {
                            MatchCollection jm = Regex.Matches(body, "\"name\"\\s*:", RegexOptions.IgnoreCase);
                            if (jm.Count > 0) pr.Collections = jm.Count;
                        }
                    }
                }
            }
            catch (WebException we)
            {
                HttpWebResponse resp = we.Response as HttpWebResponse;
                if (resp != null)
                {
                    pr.Status = (int)resp.StatusCode;
                    try
                    {
                        using (StreamReader sr = new StreamReader(resp.GetResponseStream(), Encoding.UTF8))
                        {
                            string body = sr.ReadToEnd();
                            if (body.Length > 400) body = body.Substring(0, 400);
                            pr.Error = body.Replace("\r", " ").Replace("\n", " ");
                        }
                    }
                    catch { }
                }
                else pr.Error = we.Message;
            }
            catch (Exception e) { pr.Error = e.Message; }
            return pr;
        }

        // ============================================================ 13. брандмауэр (опционально)
        public static bool OpenFirewall(string cidr, out string detail)
        {
            detail = "";
            string rule = "1C OData (IIS 80) для второго мозга";
            ExecResult chk = Proc.Run("netsh.exe", "advfirewall firewall show rule name=\"" + rule + "\"", 60000, Proc.Oem, null, null);
            if (chk.Ok && chk.All.IndexOf("80") >= 0) { detail = "правило уже есть"; return true; }
            if (Ctx.DryRun) { Log.Sim("добавил бы правило брандмауэра для TCP/80 c " + cidr); detail = "симуляция"; return true; }
            ExecResult add = Proc.Run("netsh.exe",
                "advfirewall firewall add rule name=\"" + rule + "\" dir=in action=allow protocol=TCP localport=80 remoteip=" + cidr,
                60000, Proc.Oem, null, null);
            if (!add.Ok) { Log.Warn("правило брандмауэра не добавлено: " + add.Tail(2)); return false; }
            Ctx.Changed = true;
            detail = "разрешён вход TCP/80 с " + cidr;
            return true;
        }
    }
}
