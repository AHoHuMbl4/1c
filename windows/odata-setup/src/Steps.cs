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
        // Короткое имя для подсказок человеку («базы X», а не «этой базы»).
        public string Title { get { return IsFile ? Path.GetFileName(Dir.TrimEnd('\\')) : Name; } }
    }

    // Найденная файловая база: путь + имя из списка запуска 1С (ibases.v8i).
    // Имя — то, что человек видит в стартовом окне 1cestart; показывать путь
    // вместо имени — путаница (прогон владельца 08.08: в списке «buh_test» и
    // «buh_test (Бухгалтерия - test)», а установщик писал C:\1c\bases\...).
    internal class FoundBase
    {
        public string Name;              // имя (имена) из ibases.v8i; null — база найдена только сканом
        public string Dir;
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
                // Каталоги платформы: 1cv8 (обычная) и 1cv8t (учебная), в Program Files
                // и в профиле пользователя (1cestart ставит в %LOCALAPPDATA%\1C).
                string[] env = new string[] { "ProgramW6432", "ProgramFiles(x86)", "ProgramFiles" };
                string[] sub = new string[] { "1cv8", "1cv8t" };
                for (int i = 0; i < env.Length; i++)
                {
                    string pf = Environment.GetEnvironmentVariable(env[i]);
                    if (string.IsNullOrEmpty(pf)) continue;
                    for (int j = 0; j < sub.Length; j++)
                    {
                        string c = Path.Combine(pf, sub[j]);
                        if (Directory.Exists(c) && !roots.Contains(c)) roots.Add(c);
                    }
                }
                string lad = Environment.GetEnvironmentVariable("LOCALAPPDATA");
                if (!string.IsNullOrEmpty(lad))
                {
                    for (int j = 0; j < sub.Length; j++)
                    {
                        string c = Path.Combine(Path.Combine(lad, "1C"), sub[j]);
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

        // Универсальный поиск баз (матрица «любая база», 07.08): не один захардкоженный
        // каталог стенда, а штатный реестр баз 1С пользователя — ibases.v8i (то, что
        // видит 1cestart, с ИМЕНАМИ из стартового окна), плюс скан типового каталога
        // как запасной путь.
        public static List<FoundBase> FindFileBases(string scanRoot)
        {
            List<FoundBase> res = RegisteredBases();
            List<string> scan = ScanFileBases(scanRoot);
            for (int i = 0; i < scan.Count; i++)
            {
                string d = scan[i];
                bool known = false;
                for (int k = 0; k < res.Count; k++)
                    if (string.Equals(res[k].Dir, d, StringComparison.OrdinalIgnoreCase)) { known = true; break; }
                if (!known) res.Add(new FoundBase { Name = null, Dir = d });
            }
            return res;
        }

        // %APPDATA%\1C\1CEStart\ibases.v8i: секции [<имя в стартовом окне>] со строкой
        // Connect=File="C:\путь\к\базе"; Несколько секций могут указывать на ОДИН каталог
        // (у владельца: «buh_test» и «buh_test (Бухгалтерия - test)» → один путь) — тогда
        // это одна база, показываем оба имени через « / ».
        static List<FoundBase> RegisteredBases()
        {
            List<FoundBase> res = new List<FoundBase>();
            try
            {
                string appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
                string v8i = Path.Combine(appData, @"1C\1CEStart\ibases.v8i");
                if (!File.Exists(v8i)) return res;
                string txt = File.ReadAllText(v8i, Encoding.UTF8);
                string cur = null;
                string[] lines = txt.Split('\n');
                for (int i = 0; i < lines.Length; i++)
                {
                    string line = lines[i].Trim();
                    if (line.StartsWith("[") && line.EndsWith("]") && line.Length > 2)
                    { cur = line.Substring(1, line.Length - 2); continue; }
                    Match m = Regex.Match(line, "^Connect\\s*=\\s*File\\s*=\\s*\"([^\"]+)\"", RegexOptions.IgnoreCase);
                    if (!m.Success) continue;
                    string dir = m.Groups[1].Value;
                    if (!Directory.Exists(dir) || !File.Exists(Path.Combine(dir, "1Cv8.1CD"))) continue;
                    FoundBase ex = null;
                    for (int k = 0; k < res.Count; k++)
                        if (string.Equals(res[k].Dir, dir, StringComparison.OrdinalIgnoreCase)) { ex = res[k]; break; }
                    if (ex == null) res.Add(new FoundBase { Name = cur, Dir = dir });
                    else if (!string.IsNullOrEmpty(cur))
                    {
                        // Сравнение ТОЛЬКО по целым именам через « / »: подстрока
                        // ошибочно глотала «buh_test» внутри «buh_test (…тест)».
                        bool has = false;
                        string[] parts = (ex.Name ?? "").Split(new string[] { " / " }, StringSplitOptions.None);
                        for (int p = 0; p < parts.Length; p++)
                            if (string.Equals(parts[p], cur, StringComparison.OrdinalIgnoreCase)) { has = true; break; }
                        if (!has) ex.Name = string.IsNullOrEmpty(ex.Name) ? cur : cur + " / " + ex.Name;
                    }
                }
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
            // Своя метка в имени: ротация ниже трогает ТОЛЬКО копии этой программы и никогда —
            // чужие бэкапы (например, от windows/scripts/backup-1c.ps1, у которых имя без метки).
            string dst = Path.Combine(backupDir, Path.GetFileName(src) + "_setup-odata_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".zip");
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
                RotateBackups(backupDir, Path.GetFileName(src), 3);
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

        // Держим последние N копий, СОЗДАННЫХ ЭТОЙ ПРОГРАММОЙ (метка _setup-odata_ в имени).
        // Чужие бэкапы не трогаем никогда: на живом стенде ротация по общему шаблону снесла
        // копию, сделанную другим скриптом. Больше такого быть не может.
        static void RotateBackups(string backupDir, string baseName, int keep)
        {
            try
            {
                string[] files = Directory.GetFiles(backupDir, baseName + "_setup-odata_*.zip");
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
        // Server SKU: InstallationType = "Server" / "Server Core" (HKLM\...\CurrentVersion).
        static bool IsServerSku()
        {
            try
            {
                object v = Microsoft.Win32.Registry.GetValue(
                    @"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion", "InstallationType", "");
                return (v ?? "").ToString().StartsWith("Server", StringComparison.OrdinalIgnoreCase);
            }
            catch { return false; }
        }

        // Server Core: консоли управления (GUI) нет и не ставится — её пропускаем.
        static bool IsServerCore()
        {
            try
            {
                object v = Microsoft.Win32.Registry.GetValue(
                    @"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion", "InstallationType", "");
                return string.Equals((v ?? "").ToString(), "Server Core", StringComparison.OrdinalIgnoreCase);
            }
            catch { return false; }
        }

        // Путь Windows Server (2016/2019/2022): роли через ServerManager. Проверяем
        // не только Web-Server: роль может стоять без ISAPI/CGI — тогда 1С не отвечает.
        static int EnsureIisServer(out string detail)
        {
            detail = "";
            bool core = IsServerCore();
            string feats = core
                ? "Web-Server,Web-ISAPI-Ext,Web-ISAPI-Filter,Web-CGI"
                : "Web-Server,Web-ISAPI-Ext,Web-ISAPI-Filter,Web-CGI,Web-Mgmt-Console";
            ExecResult sv = Ps.Run("try{ Import-Module ServerManager -EA Stop; " +
                "$need = @('" + feats.Replace(",", "','") + "'); " +
                "$missing = @(Get-WindowsFeature $need | Where-Object { -not $_.Installed }); " +
                "if ($missing.Count -eq 0) { 'ALLPRESENT' } else { 'MISSING' } } catch { 'NOMODULE' }", false, 180000, null);
            if (sv.Ok && sv.StdOut.IndexOf("ALLPRESENT", StringComparison.OrdinalIgnoreCase) >= 0)
            { detail = "Windows Server: роль Web-Server и ISAPI/CGI уже установлены"; return 0; }
            if (sv.Ok && sv.StdOut.IndexOf("MISSING", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                if (Ctx.DryRun) { Log.Sim("установил бы роли IIS (Install-WindowsFeature " + feats + ")"); return 2; }
                ExecResult ins = Ps.Run("$r=Install-WindowsFeature " + feats + " -ErrorAction Stop; 'RESTART='+$r.RestartNeeded", false, 900000, null);
                if (!ins.Ok) { detail = ins.Tail(3); return -1; }
                detail = "роль Web-Server установлена (Server SKU" + (core ? " Core, без консоли управления" : "") + ")";
                Ctx.Changed = true;
                return ins.StdOut.IndexOf("RESTART=Yes", StringComparison.OrdinalIgnoreCase) >= 0 ? 1 : 2;
            }
            detail = "не удалось определить состояние компонентов IIS";
            return -1;
        }

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
            // Server SKU: имена IIS-* — роли ServerManager, а не optional features.
            // Get-WindowsOptionalFeature по ним на Server кидает «unknown feature»,
            // per-item catch ниже писал Absent, скрипт завершался кодом 0 — и ветка
            // ServerManager не выполнялась НИКОГДА (разбор 07.08). Поэтому Server
            // определяем явно по реестру ДО выбора механизма.
            if (IsServerSku()) return EnsureIisServer(out detail);
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
                // Клиентский путь недоступен — возможно, это Server (или Server Core):
                // пробуем ServerManager. На клиенте без модуля ответит NOMODULE.
                Log.Warn("Get-WindowsOptionalFeature недоступен: " + r.Tail(2));
                return EnsureIisServer(out detail);
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

        // Идемпотентность публикации: сравнение ТОЧНОЕ. Подстрочное «buh» ловило
        // чужую базу «buh2», и установщик шёл дальше с чужим default.vrd (разбор 07.08).
        static bool IbMatches(string ib, BaseRef b)
        {
            if (ib == null) return false;
            string want = b.IsFile ? b.Dir : b.Name;
            if (string.IsNullOrEmpty(want)) return false;
            // ib вида File='C:\1c\bases\ut'; (файловая) или Ref='name'; (клиент-серверная)
            string val = ib.Trim().TrimEnd(';');
            int q1 = val.IndexOf('\'');
            int q2 = val.LastIndexOf('\'');
            if (q1 < 0 || q2 <= q1) return false;
            string inner = val.Substring(q1 + 1, q2 - q1 - 1);
            return string.Equals(inner, want, StringComparison.OrdinalIgnoreCase);
        }

        // default.vrd на диске ≠ приложение в IIS: после переустановки IIS файл
        // остался, а объекта APP нет (стенд 07.08) — «set app» на шаге пула падал
        // с «must use exact identifier for APP object». Создаём приложение, если нет.
        static bool EnsureIisApp(string site, string alias, string dir, out string detail)
        {
            detail = "";
            // 🔴 appcmd list с идентификатором делает НЕТОЧНОЕ совпадение: по
            // «Default Web Site/ut» вернул корневое приложение (замер 07.08) —
            // поэтому сверяем саму строку APP "<site>/<alias>".
            string want = "APP \"" + site + "/" + alias + "\"";
            ExecResult app = Cmd("list app \"" + site + "/" + alias + "\"", 30000);
            if (app.Ok && app.StdOut.IndexOf(want, StringComparison.OrdinalIgnoreCase) >= 0) return true;
            if (Ctx.DryRun) { Log.Sim("создал бы приложение IIS " + site + "/" + alias + " -> " + dir); return true; }
            ExecResult addApp = Cmd("add app /site.name:\"" + site + "\" /path:\"/" + alias + "\" /physicalPath:\"" + dir + "\"", 60000);
            if (!addApp.Ok) { detail = "не создать приложение IIS " + site + "/" + alias + ": " + addApp.Tail(3); return false; }
            Ctx.Changed = true;
            Log.Ok("создано приложение IIS: " + site + "/" + alias + " -> " + dir);
            return true;
        }

        public static bool Publish(Platform p, BaseRef b, string site, string alias, string dir, bool force, out string detail)
        {
            detail = "";
            string vrd = VrdPath(dir);
            if (File.Exists(vrd))
            {
                string ib = VrdIb(vrd);
                if (IbMatches(ib, b))
                {
                    if (!EnsureIisApp(site, alias, dir, out detail)) return false;
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
            if (!EnsureIisApp(site, alias, dir, out detail)) return false;
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

                // Грабля Н-3 (УТ): webinst мог оставить enable=false; мы обязаны ПЕРЕЧИТАТЬ файл.
                string verify;
                if (!IsODataEnabledInVrd(dir, out verify))
                {
                    Log.Err("после записи в default.vrd OData всё ещё выключен: " + verify);
                    Log.Fix("откройте " + vrd + " и убедитесь, что <standardOdata enable=\"true\" .../>");
                    return false;
                }
                detail = "standardOdata enable=\"true\" (проверено перечитыванием файла)";
                return true;
            }
            catch (Exception e) { Log.Err("не удалось изменить " + vrd + ": " + e.Message); return false; }
        }

        // Перечитать default.vrd: enable обязан быть true (иначе «успех» с 404 снаружи).
        public static bool IsODataEnabledInVrd(string dir, out string detail)
        {
            detail = "";
            string vrd = VrdPath(dir);
            if (!File.Exists(vrd)) { detail = "файл не найден: " + vrd; return false; }
            try
            {
                XNamespace ns = "http://v8.1c.ru/8.2/virtual-resource-system";
                XDocument doc = XDocument.Load(vrd);
                XElement od = doc.Root.Element(ns + "standardOdata");
                if (od == null) { detail = "нет узла standardOdata"; return false; }
                XAttribute en = od.Attribute("enable");
                if (en == null || !en.Value.Equals("true", StringComparison.OrdinalIgnoreCase))
                {
                    detail = "enable=\"" + (en == null ? "" : en.Value) + "\"";
                    return false;
                }
                detail = "enable=true";
                return true;
            }
            catch (Exception e) { detail = e.Message; return false; }
        }

        // ============================================================ 8. пул приложений
        static ExecResult Cmd(string args, int ms) { return Proc.Run(AppCmd, args, ms, Proc.Oem, null, null); }

        public static string CurrentAppPool(string site, string alias)
        {
            // appcmd list с идентификатором совпадает НЕТОЧНО (по «Default Web Site/ut»
            // возвращает корневое приложение — замер 07.08): сначала точная проверка
            // существования, и только потом значение пула.
            ExecResult ex = Cmd("list app \"" + site + "/" + alias + "\"", 30000);
            if (!ex.Ok || ex.StdOut.IndexOf("APP \"" + site + "/" + alias + "\"", StringComparison.OrdinalIgnoreCase) < 0)
                return null;
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
                // точное совпадение: appcmd list по неточному имени возвращает чужие объекты
                ExecResult ex = Cmd("list apppool \"" + target + "\"", 30000);
                if (!ex.Ok || ex.StdOut.IndexOf("APPPOOL \"" + target + "\"", StringComparison.OrdinalIgnoreCase) < 0)
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
            // web.config публикации 1С несёт секцию <handlers>: на свежем IIS она
            // заблокирована на уровне сервера — приложение отвечает 500.19
            // 0x80070021 (замер на стенде 07.08). Снимаем блокировку handlers.
            if (!Ctx.DryRun)
            {
                ExecResult un = Cmd("unlock config /section:handlers", 60000);
                if (un.Ok) Log.Ok("секция handlers разблокирована на уровне сервера");
                else Log.Warn("unlock config handlers: " + un.Tail(2));
            }
            else Log.Sim("разблокировал бы секцию handlers на уровне сервера");
            ExecResult list = Cmd("list config /section:isapiCgiRestriction /text:*", 60000);
            bool present = list.Ok && list.StdOut.IndexOf(p.Wsisapi, StringComparison.OrdinalIgnoreCase) >= 0;
            if (present)
            {
                // проверяем, что allowed=true рядом с нашим путём
                string txt = list.StdOut;
                int idx = txt.IndexOf(p.Wsisapi, StringComparison.OrdinalIgnoreCase);
                string tail = txt.Substring(idx, Math.Min(220, txt.Length - idx));
                // appcmd /text:* печатает элементы коллекции как [path='...',allowed='true']
                // — через '=', а не ':' (разбор 07.08): принимаем оба разделителя.
                if (Regex.IsMatch(tail, "allowed\\s*[=:]\\s*\"?true", RegexOptions.IgnoreCase))
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
        // Внимание: речь про СОСТАВ OData, а не про публикацию в IIS (её уже сделал установщик).
        public static string ManualScopeInstructions(BaseRef b, string alias, List<string> scopeKeys)
        {
            StringBuilder s = new StringBuilder();
            s.AppendLine("РУЧНАЯ НАСТРОЙКА СОСТАВА OData — выполняет администратор 1С (~5 минут)");
            s.AppendLine("");
            s.AppendLine("Важно: публикация базы в IIS уже выполнена установщиком. Сейчас нужно только");
            s.AppendLine("указать СОСТАВ — какие объекты базы видны через OData API. Без этого шага");
            s.AppendLine("OData отдаёт ПУСТОЙ список, и сервер аналитики не увидит ни одной таблицы.");
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

        // Полный туториал: добавить веб-модуль БЕЗ «переустановки всей 1С» (способ 1 — Изменить).
        public static string WebModuleTutorial(Platform p)
        {
            StringBuilder s = new StringBuilder();
            s.AppendLine("ДОБАВИТЬ МОДУЛЬ РАСШИРЕНИЯ ВЕБ-СЕРВЕРА (wsisapi.dll) — без сноса 1С");
            s.AppendLine("");
            s.AppendLine("Без этого файла публикация OData в IIS невозможна. Базы, пользователи и");
            s.AppendLine("лицензии НЕ удаляются — нужно только ДОБАВИТЬ компонент платформы.");
            if (p != null)
            {
                s.AppendLine("");
                s.AppendLine("Обнаружена платформа: " + p.Version + "  (" + (p.X86 ? "x86" : "x64") + ")");
                s.AppendLine("Каталог: " + p.Root);
                s.AppendLine("Ожидаемый файл: " + Path.Combine(p.Bin, "wsisapi.dll") + " — СЕЙЧАС ЕГО НЕТ.");
            }
            s.AppendLine("");
            s.AppendLine("СПОСОБ 1 (рекомендуется) — «Изменить» установку:");
            s.AppendLine("  1) Закройте 1С:Предприятие и Конфигуратор на этой машине.");
            s.AppendLine("  2) Панель управления Windows -> Программы и компоненты");
            s.AppendLine("     (или Параметры -> Приложения).");
            s.AppendLine("  3) Найдите «1С:Предприятие 8» нужной версии" +
                         (p != null ? " (" + p.Version + ")" : "") + ".");
            s.AppendLine("  4) Выделите -> кнопка «Изменить» (Change), НЕ «Удалить».");
            s.AppendLine("  5) В списке компонентов включите:");
            s.AppendLine("       • «Модули расширения веб-сервера»  (это wsisapi.dll — обязательно)");
            s.AppendLine("       • «Модули расширения COM»          (нужны, если состав OData");
            s.AppendLine("         будет задавать установщик автоматически; для ручного состава");
            s.AppendLine("         в Конфигураторе COM не обязателен)");
            s.AppendLine("  6) Далее / Установить. Дождитесь конца. Базы не трогаются.");
            s.AppendLine("  7) Проверка: должен появиться файл");
            s.AppendLine("       " + (p != null ? Path.Combine(p.Bin, "wsisapi.dll") : @"...\1cv8\<версия>\bin\wsisapi.dll"));
            s.AppendLine("  8) Снова запустите setup-1c-odata.exe — он продолжит с того же места.");
            s.AppendLine("");
            s.AppendLine("ЗАПАСНЫЕ СПОСОБЫ (если «Изменить» недоступен):");
            s.AppendLine("  • Тихая доустановка из дистрибутива той же версии:");
            s.AppendLine("      msiexec /i \"1CEnterprise 8.msi\" /qn /norestart TRANSFORMS=1049.mst WEBSERVEREXT=1");
            s.AppendLine("  • Поставить рядом другую версию платформы УЖЕ с веб-модулем;");
            s.AppendLine("    установщик сам выберет новейшую с wsisapi.dll, либо укажите");
            s.AppendLine("    --platform-version / --platform-dir.");
            s.AppendLine("");
            s.AppendLine("Не пишите и не делайте «переустановить всю 1С с нуля» — это не требуется.");
            return s.ToString();
        }

        // Оценка места ДО изменений: база + запас под бэкап + публикация/логи.
        // Возвращает false = критично мало (стоп); warnOnly — только предупреждения.
        public static bool PrefightDisk(BaseRef b, string backupDir, string pubDir, string logDir,
                                        bool needBackup, out string summary)
        {
            StringBuilder s = new StringBuilder();
            bool ok = true;
            long baseMb = (b != null && b.IsFile) ? Win.DirSizeMb(b.Dir) : 0;
            long needBackupMb = needBackup && baseMb > 0 ? baseMb + 200 : 0;

            long freeBase = (b != null && b.IsFile) ? Win.FreeSpaceMb(b.Dir) : -1;
            long freeBak = Win.FreeSpaceMb(backupDir);
            long freePub = Win.FreeSpaceMb(string.IsNullOrEmpty(pubDir) ? @"C:\inetpub" : pubDir);
            long freeLog = Win.FreeSpaceMb(string.IsNullOrEmpty(logDir) ? @"C:\1c\logs" : logDir);

            s.Append("база ~" + (baseMb < 0 ? "?" : baseMb.ToString()) + " МБ");
            if (needBackupMb > 0) s.Append("; нужно под бэкап ≥" + needBackupMb + " МБ");
            s.Append("; свободно: ");
            if (freeBase >= 0) s.Append("диск базы " + freeBase + " МБ, ");
            s.Append("бэкап " + (freeBak < 0 ? "?" : freeBak.ToString()) + " МБ, ");
            s.Append("публикация " + (freePub < 0 ? "?" : freePub.ToString()) + " МБ, ");
            s.Append("логи " + (freeLog < 0 ? "?" : freeLog.ToString()) + " МБ");

            if (needBackupMb > 0 && freeBak >= 0 && freeBak < needBackupMb)
            {
                Log.Err("мало места под бэкап: свободно " + freeBak + " МБ, нужно ≥" + needBackupMb + " МБ на " + backupDir);
                Log.Fix("освободите диск, укажите --backup-dir на другой том или --no-backup (если копия уже есть)");
                ok = false;
            }
            if (freePub >= 0 && freePub < 500)
            {
                Log.Warn("мало места на диске публикации IIS (" + freePub + " МБ) — рекомендуется ≥500 МБ");
            }
            if (freeLog >= 0 && freeLog < 100)
            {
                Log.Warn("мало места для логов (" + freeLog + " МБ)");
            }
            summary = s.ToString();
            return ok;
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
                // Проверка факта (ложный «успех» 07.08): перечитываем состав ПОСЛЕ записи.
                s.AppendLine("$af = -1");
                s.AppendLine("try { $c2 = $null; try { $c2 = $ib.ПолучитьСоставСтандартногоИнтерфейсаOData() } catch { $c2 = $ib.GetStandardODataInterfaceContent() }; if($c2 -ne $null){ try { $af = [int]$c2.Количество() } catch { $af = [int]$c2.Count() } } } catch { $af = -1 }");
                s.AppendLine("'AFTER=' + $af");
                s.AppendLine("if($af -eq 0){ throw 'состав OData после записи ПУСТ (0 объектов) — запись не применилась' }");
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

        // Состояние прав «только чтение» в конкретной базе (прогон 08.08: в УТ/КА
        // поставляемого профиля «Только просмотр» НЕТ, в БП есть — подсказка обязана
        // идти под эту базу, а не ветвиться текстом):
        //   GROUP   — есть группа доступа с профилем «Только просмотр» (просто включить);
        //   PROFILE — профиль есть, группы нет (создать группу);
        //   NONE    — ни профиля, ни группы (УТ/КА: создать профиль по списку ролей);
        //   null    — определить не удалось (нет COM, нет админ-кредов, не-БСП конфигурация).
        public static string ReaderRightsState(Platform p, BaseRef b, string user, string pwd)
        {
            if (p == null || !p.HasCom || string.IsNullOrEmpty(user) || Ctx.DryRun) return null;
            StringBuilder s = new StringBuilder();
            s.AppendLine("try {");
            s.AppendLine("$connector = New-Object -ComObject $env:OC1C_PROGID");
            s.AppendLine("$ib = $connector.Connect($env:OC1C_CONNSTR)");
            // Пустой() — метод, зовём напрямую (квирк COM 1С: методы — прямо,
            // свойства — через InvokeMember; здесь свойства не нужны вовсе).
            s.AppendLine("$q = $ib.NewObject('Запрос')");
            s.AppendLine("$q.Текст = 'ВЫБРАТЬ ПЕРВЫЕ 1 Т.Ссылка ИЗ Справочник.ГруппыДоступа КАК Т ГДЕ Т.Профиль.Наименование = &Н'");
            s.AppendLine("$q.УстановитьПараметр('Н', 'Только просмотр')");
            s.AppendLine("if (-not $q.Выполнить().Пустой()) { 'STATE=GROUP' } else {");
            s.AppendLine("  $q2 = $ib.NewObject('Запрос')");
            s.AppendLine("  $q2.Текст = 'ВЫБРАТЬ ПЕРВЫЕ 1 Т.Ссылка ИЗ Справочник.ПрофилиГруппДоступа КАК Т ГДЕ Т.Наименование = &Н'");
            s.AppendLine("  $q2.УстановитьПараметр('Н', 'Только просмотр')");
            s.AppendLine("  if (-not $q2.Выполнить().Пустой()) { 'STATE=PROFILE' } else { 'STATE=NONE' }");
            s.AppendLine("}");
            s.AppendLine("} catch { 'ERROR=' + $_.Exception.Message; exit 1 }");
            Dictionary<string, string> env = new Dictionary<string, string>();
            env["OC1C_PROGID"] = p.ProgId;
            env["OC1C_CONNSTR"] = b.ConnStrCom(user, pwd);
            ExecResult r = Ps.Run(s.ToString(), p.X86, 180000, env);
            Match m = Regex.Match(r.StdOut, @"STATE=(GROUP|PROFILE|NONE)");
            if (m.Success) return m.Groups[1].Value;
            Log.File("ReaderRightsState: не определено (" + ComErrorLine(r) + ")");
            return null;
        }

        // Автосоздание пользователя-читателя (решение владельца 08.08: описание + Enter).
        // Пароль — случайный, генерирует установщик: не нужен никому, остаётся только
        // в agent.ini под ACL (строго сильнее ручного). Создаётся пользователь ИБ
        // (скрыт из списка выбора — сервисный), а в БСП-базе — и элемент справочника
        // «Пользователи» со связью по GUID (без него группы доступа его не видят).
        public static bool CreateReaderUser(Platform p, BaseRef b, string adminUser, string adminPwd,
                                            string readerUser, string readerPwd, out string detail)
        {
            detail = "";
            if (p == null || !p.HasCom) { detail = "нет COM-коннектора 1С"; return false; }
            if (string.IsNullOrEmpty(adminUser)) { detail = "нет учётных данных администратора 1С"; return false; }
            if (Ctx.DryRun) { Log.Sim("создал бы пользователя ИБ «" + readerUser + "»"); detail = "симуляция"; return true; }

            StringBuilder s = new StringBuilder();
            s.AppendLine("$GP=[Reflection.BindingFlags]::GetProperty");
            s.AppendLine("$PUT=[Reflection.BindingFlags]::PutDispProperty");
            s.AppendLine("function P($o,$n){ [__ComObject].InvokeMember($n,$GP,$null,$o,@()) }");
            s.AppendLine("try {");
            s.AppendLine("$connector = New-Object -ComObject $env:OC1C_PROGID");
            s.AppendLine("$ib = $connector.Connect($env:OC1C_CONNSTR)");
            s.AppendLine("$users = P $ib 'ПользователиИнформационнойБазы'");
            s.AppendLine("$u = $users.НайтиПоИмени($env:OC1C_READER)");
            s.AppendLine("if ($u -ne $null) { 'RESULT=EXISTS'; exit 0 }");
            s.AppendLine("$u = $users.СоздатьПользователя()");
            s.AppendLine("$u.Имя = $env:OC1C_READER");
            s.AppendLine("$u.ПолноеИмя = $env:OC1C_READER");
            s.AppendLine("$u.АутентификацияСтандартная = $true");
            s.AppendLine("$u.Пароль = $env:OC1C_READER_PWD");
            s.AppendLine("$u.ПоказыватьВСпискеВыбора = $false");   // сервисная учётка — не светится в окне входа
            s.AppendLine("$u.ЗапрещеноИзменятьПароль = $true");
            s.AppendLine("$u.Записать()");
            s.AppendLine("'USER_CREATED=1'");
            // БСП: элемент справочника «Пользователи» со связью по GUID (для групп доступа)
            s.AppendLine("$pm = $null; try { $pm = $ib.NewObject('СправочникМенеджер.Пользователи') } catch { $pm = $null }");
            s.AppendLine("if ($pm -ne $null) {");
            s.AppendLine("  $guid = $u.УникальныйИдентификатор()");
            s.AppendLine("  $q = $ib.NewObject('Запрос')");
            s.AppendLine("  $q.Текст = 'ВЫБРАТЬ ПЕРВЫЕ 1 Т.Ссылка КАК Сс ИЗ Справочник.Пользователи КАК Т ГДЕ Т.ИдентификаторПользователяИБ = &Ид'");
            s.AppendLine("  $q.УстановитьПараметр('Ид', $guid)");
            s.AppendLine("  if ($q.Выполнить().Пустой()) {");
            s.AppendLine("    $cu = $pm.СоздатьЭлемент()");
            s.AppendLine("    $cu.Наименование = $env:OC1C_READER");
            s.AppendLine("    $cu.ИдентификаторПользователяИБ = $guid");
            // Замер 08.08 (guidprobe5-7): без Загрузка=true обработчики БСП при записи
            // ЗАТИРАЮТ ИдентификаторПользователяИБ пустым GUID — элемент есть, связи нет.
            s.AppendLine("    $od = P $cu 'ОбменДанными'");
            s.AppendLine("    [__ComObject].InvokeMember('Загрузка', $PUT, $null, $od, @($true)) | Out-Null");
            s.AppendLine("    $cu.Записать()");
            s.AppendLine("    'CATUSER_CREATED=1'");
            s.AppendLine("  }");
            s.AppendLine("}");
            s.AppendLine("'RESULT=OK'");
            s.AppendLine("} catch { 'ERROR=' + $_.Exception.Message; exit 1 }");

            Dictionary<string, string> env = new Dictionary<string, string>();
            env["OC1C_PROGID"] = p.ProgId;
            env["OC1C_CONNSTR"] = b.ConnStrCom(adminUser, adminPwd);
            env["OC1C_READER"] = readerUser;
            env["OC1C_READER_PWD"] = readerPwd;
            ExecResult r = Ps.Run(s.ToString(), p.X86, 600000, env);
            if (r.All.IndexOf("RESULT=EXISTS") >= 0) { detail = "уже существует"; return true; }
            if (r.All.IndexOf("RESULT=OK") < 0) { detail = "COM: " + ComErrorLine(r); return false; }
            detail = "пользователь ИБ «" + readerUser + "» создан (скрыт из списка входа)" +
                     (r.StdOut.IndexOf("CATUSER_CREATED=1") >= 0 ? ", элемент справочника «Пользователи» создан" : "");
            return true;
        }

        // Автоназначение прав читателю (решение владельца 08.08, «вариант А»): ручной
        // рецепт для УТ/КА/ERP — ~400 галочек ролей, непригоден; установщик уже пишет
        // в базу санкционированно (состав OData), это та же категория. Лестница по факту
        // базы, без имён конфигураций: БСП есть → профиль «Только просмотр» (синонимы:
        // «Только чтение», «Аудитор») найти или создать по префиксам ролей → группа с
        // ним найти или создать → читателя (элемент справочника «Пользователи» по GUID
        // пользователя ИБ) включить. БСП нет → роли напрямую пользователю ИБ.
        // Квирки COM 1С доказаны пробами на стенде 08.08: менеджер — NewObject(
        // 'СправочникМенеджер.X') (через свойство НЕ достаётся), объект — СоздатьЭлемент()
        // (NewObject('СправочникОбъект.X') даёт объект, которому свойства не пишутся),
        // чтение свойств — InvokeMember(GetProperty), запись — прямое присваивание,
        // методы — прямой вызов. GUID-реквизиты БСП: обработчики записи справочника
        // «Пользователи» ЗАТИРАЮТ ИдентификаторПользователяИБ пустым GUID (замер
        // guidprobe5-7: в объекте значение верное, после Записать — пустое) — запись
        // связи только через ОбменДанными.Загрузка=true (InvokeMember, цепочка
        // «.ОбменДанными.Загрузка» в PS недоступна); сам GUID COM-объектом маршалится
        // нормально и в присваивании, и в параметре запроса.
        public static bool EnsureReaderRights(Platform p, BaseRef b, string adminUser, string adminPwd,
                                              string readerUser, out string detail)
        {
            detail = "";
            if (p == null || !p.HasCom) { detail = "нет COM-коннектора 1С"; return false; }
            if (string.IsNullOrEmpty(adminUser)) { detail = "нет учётных данных администратора 1С"; return false; }
            if (Ctx.DryRun) { Log.Sim("назначил бы читателю «" + readerUser + "» права «только чтение»"); detail = "симуляция"; return true; }

            StringBuilder s = new StringBuilder();
            s.AppendLine("$GP=[Reflection.BindingFlags]::GetProperty");
            s.AppendLine("$PUT=[Reflection.BindingFlags]::PutDispProperty");
            s.AppendLine("function P($o,$n){ [__ComObject].InvokeMember($n,$GP,$null,$o,@()) }");
            s.AppendLine("try {");
            s.AppendLine("$connector = New-Object -ComObject $env:OC1C_PROGID");
            s.AppendLine("$ib = $connector.Connect($env:OC1C_CONNSTR)");
            s.AppendLine("$users = P $ib 'ПользователиИнформационнойБазы'");
            s.AppendLine("$u = $users.НайтиПоИмени($env:OC1C_READER)");
            s.AppendLine("if ($u -eq $null) { 'RESULT=READER_NOTFOUND'; exit 0 }");
            s.AppendLine("$md = P $ib 'Метаданные'");
            s.AppendLine("$prefixes = @('Чтение','Просмотр','Базовые','Запуск','Использование','Раздел','Подсистема','Отчеты','Вывод')");
            // Детектор БСП: менеджер справочника профилей создаётся — значит механизм есть.
            s.AppendLine("$pm = $null");
            s.AppendLine("try { $pm = $ib.NewObject('СправочникМенеджер.ПрофилиГруппДоступа') } catch { $pm = $null }");
            s.AppendLine("if ($pm -eq $null) {");
            // --- не-БСП: роли напрямую пользователю ИБ (затирать некому — БСП нет)
            s.AppendLine("  $added = 0");
            s.AppendLine("  foreach ($r in (P $md 'Роли')) {");
            s.AppendLine("    $nm = P $r 'Имя'");
            s.AppendLine("    foreach ($px in $prefixes) { if ($nm.StartsWith($px)) {");
            s.AppendLine("      $has = $false; try { $has = $u.Роли.Содержит($r) } catch {}");
            s.AppendLine("      if (-not $has) { $u.Роли.Добавить($r); $added++ }");
            s.AppendLine("      break } }");
            s.AppendLine("  }");
            s.AppendLine("  if ($added -gt 0) { $u.Записать() }");
            s.AppendLine("  'RESULT=OK'; 'MODE=DIRECT'; 'ROLES=' + $added; exit 0");
            s.AppendLine("}");
            // --- БСП: 1) профиль
            s.AppendLine("$profRef = $null; $profName = ''");
            s.AppendLine("foreach ($nm in @('Только просмотр','Только чтение','Аудитор')) {");
            s.AppendLine("  $q = $ib.NewObject('Запрос')");
            s.AppendLine("  $q.Текст = 'ВЫБРАТЬ ПЕРВЫЕ 1 Т.Ссылка КАК Сс ИЗ Справочник.ПрофилиГруппДоступа КАК Т ГДЕ Т.Наименование = &Н'");
            s.AppendLine("  $q.УстановитьПараметр('Н', $nm)");
            s.AppendLine("  $rr = $q.Выполнить().Выбрать()");
            s.AppendLine("  if ($rr.Следующий()) { $profRef = P $rr 'Сс'; $profName = $nm; break }");
            s.AppendLine("}");
            s.AppendLine("$profileCreated = 0; $rolesInProfile = 0");
            s.AppendLine("if ($profRef -eq $null) {");
            s.AppendLine("  $iomMap = @{}");
            s.AppendLine("  $q = $ib.NewObject('Запрос')");
            s.AppendLine("  $q.Текст = 'ВЫБРАТЬ Т.ПолноеИмя КАК П, Т.Ссылка КАК Сс ИЗ Справочник.ИдентификаторыОбъектовМетаданных КАК Т ГДЕ Т.ПолноеИмя ПОДОБНО &Ш'");
            s.AppendLine("  $q.УстановитьПараметр('Ш', 'Роль.%')");
            s.AppendLine("  $rr = $q.Выполнить().Выбрать()");
            s.AppendLine("  while ($rr.Следующий()) { $iomMap[(P $rr 'П')] = P $rr 'Сс' }");
            s.AppendLine("  $prof = $pm.СоздатьЭлемент()");
            s.AppendLine("  $prof.Наименование = 'Только просмотр'");
            s.AppendLine("  foreach ($r in (P $md 'Роли')) {");
            s.AppendLine("    $nm = P $r 'Имя'");
            s.AppendLine("    foreach ($px in $prefixes) { if ($nm.StartsWith($px)) {");
            s.AppendLine("      $key = 'Роль.' + $nm");
            s.AppendLine("      if ($iomMap.ContainsKey($key)) { $row = $prof.Роли.Добавить(); $row.Роль = $iomMap[$key]; $rolesInProfile++ }");
            s.AppendLine("      break } }");
            s.AppendLine("  }");
            s.AppendLine("  if ($rolesInProfile -eq 0) { throw 'не нашлось ни одной роли чтения для профиля' }");
            s.AppendLine("  $prof.Записать()");
            s.AppendLine("  $profRef = P $prof 'Ссылка'");
            s.AppendLine("  $profName = 'Только просмотр'; $profileCreated = 1");
            s.AppendLine("}");
            // --- БСП: 2) группа с этим профилем
            s.AppendLine("$gm = $ib.NewObject('СправочникМенеджер.ГруппыДоступа')");
            s.AppendLine("$q = $ib.NewObject('Запрос')");
            s.AppendLine("$q.Текст = 'ВЫБРАТЬ ПЕРВЫЕ 1 Т.Ссылка КАК Сс ИЗ Справочник.ГруппыДоступа КАК Т ГДЕ Т.Профиль = &П'");
            s.AppendLine("$q.УстановитьПараметр('П', $profRef)");
            s.AppendLine("$rr = $q.Выполнить().Выбрать()");
            s.AppendLine("$grpRef = $null; $groupCreated = 0");
            s.AppendLine("if ($rr.Следующий()) { $grpRef = P $rr 'Сс' } else {");
            s.AppendLine("  $grp = $gm.СоздатьЭлемент()");
            s.AppendLine("  $grp.Наименование = 'Чтение (AI)'");
            s.AppendLine("  $grp.Профиль = $profRef");
            s.AppendLine("  $grp.Записать()");
            s.AppendLine("  $grpRef = P $grp 'Ссылка'; $groupCreated = 1");
            s.AppendLine("}");
            // --- БСП: 3) элемент справочника «Пользователи» по GUID пользователя ИБ
            s.AppendLine("$guid = $u.УникальныйИдентификатор()");
            s.AppendLine("$q = $ib.NewObject('Запрос')");
            s.AppendLine("$q.Текст = 'ВЫБРАТЬ ПЕРВЫЕ 1 Т.Ссылка КАК Сс ИЗ Справочник.Пользователи КАК Т ГДЕ Т.ИдентификаторПользователяИБ = &Ид'");
            s.AppendLine("$q.УстановитьПараметр('Ид', $guid)");
            s.AppendLine("$rr = $q.Выполнить().Выбрать()");
            s.AppendLine("$catUser = $null");
            s.AppendLine("if ($rr.Следующий()) { $catUser = P $rr 'Сс' } else {");
            // Ремонт (замер 08.08, guidprobe5-7): обработчики БСП при обычной записи
            // затирают ИдентификаторПользователяИБ пустым GUID — элемент версии до
            // правки есть, но связи нет. Ищем по наименованию и перелинковываем
            // записью в режиме ОбменДанными.Загрузка.
            s.AppendLine("  $qn = $ib.NewObject('Запрос')");
            s.AppendLine("  $qn.Текст = 'ВЫБРАТЬ ПЕРВЫЕ 1 Т.Ссылка КАК Сс, Т.ИдентификаторПользователяИБ КАК Ид ИЗ Справочник.Пользователи КАК Т ГДЕ Т.Наименование = &Н'");
            s.AppendLine("  $qn.УстановитьПараметр('Н', $env:OC1C_READER)");
            s.AppendLine("  $rrn = $qn.Выполнить().Выбрать()");
            s.AppendLine("  if ($rrn.Следующий()) {");
            s.AppendLine("    $idStr = $ib.ЗначениеВСтрокуВнутр((P $rrn 'Ид'))");
            s.AppendLine("    if ($idStr -like '*00000000-0000-0000-0000-000000000000}') {");
            s.AppendLine("      $cobj = (P $rrn 'Сс').ПолучитьОбъект()");
            s.AppendLine("      [__ComObject].InvokeMember('ИдентификаторПользователяИБ', $PUT, $null, $cobj, @($guid)) | Out-Null");
            s.AppendLine("      $od = P $cobj 'ОбменДанными'");
            s.AppendLine("      [__ComObject].InvokeMember('Загрузка', $PUT, $null, $od, @($true)) | Out-Null");
            s.AppendLine("      $cobj.Записать()");
            s.AppendLine("      $catUser = P $rrn 'Сс'");
            s.AppendLine("      'RELINKED=1'");
            s.AppendLine("    }");
            s.AppendLine("  }");
            s.AppendLine("}");
            s.AppendLine("if ($catUser -eq $null) { 'RESULT=NO_CAT_USER'; exit 0 }");
            // --- БСП: 4) членство
            s.AppendLine("$q = $ib.NewObject('Запрос')");
            s.AppendLine("$q.Текст = 'ВЫБРАТЬ ПЕРВЫЕ 1 Т.Ссылка КАК Сс ИЗ Справочник.ГруппыДоступа.Пользователи КАК Т ГДЕ Т.Ссылка = &Г И Т.Пользователь = &У'");
            s.AppendLine("$q.УстановитьПараметр('Г', $grpRef); $q.УстановитьПараметр('У', $catUser)");
            s.AppendLine("$memberAdded = 0");
            s.AppendLine("if ($q.Выполнить().Пустой()) {");
            s.AppendLine("  $grpObj = $grpRef.ПолучитьОбъект()");
            s.AppendLine("  $row = $grpObj.Пользователи.Добавить()");
            s.AppendLine("  $row.Пользователь = $catUser");
            s.AppendLine("  $grpObj.Записать()");
            s.AppendLine("  $memberAdded = 1");
            s.AppendLine("}");
            s.AppendLine("'RESULT=OK'; 'MODE=BSP'; 'PROFILE=' + $profName; 'PROFILE_CREATED=' + $profileCreated;");
            s.AppendLine("'GROUP_CREATED=' + $groupCreated; 'MEMBER_ADDED=' + $memberAdded; 'ROLES=' + $rolesInProfile");
            s.AppendLine("} catch { 'ERROR=' + $_.Exception.Message; exit 1 }");

            Dictionary<string, string> env = new Dictionary<string, string>();
            env["OC1C_PROGID"] = p.ProgId;
            env["OC1C_CONNSTR"] = b.ConnStrCom(adminUser, adminPwd);
            env["OC1C_READER"] = readerUser;
            ExecResult r = Ps.Run(s.ToString(), p.X86, 600000, env);

            if (r.All.IndexOf("RESULT=READER_NOTFOUND") >= 0)
            { detail = "пользователя ИБ «" + readerUser + "» в базе нет"; return false; }
            if (r.All.IndexOf("RESULT=NO_CAT_USER") >= 0)
            { detail = "пользователь ИБ есть, но элемента в справочнике «Пользователи» нет — включите его в группу вручную"; return false; }
            if (r.All.IndexOf("RESULT=OK") < 0)
            { detail = "COM: " + ComErrorLine(r); return false; }

            string mode = r.StdOut.IndexOf("MODE=DIRECT") >= 0 ? "DIRECT" : "BSP";
            string roles = ""; Match mro = Regex.Match(r.StdOut, @"ROLES=(\d+)"); if (mro.Success) roles = mro.Groups[1].Value;
            if (mode == "DIRECT")
                detail = "роли чтения назначены пользователю ИБ напрямую (конфигурация без профилей): +" + roles + " ролей";
            else
            {
                string pn = ""; Match mp = Regex.Match(r.StdOut, @"PROFILE=(.*)"); if (mp.Success) pn = mp.Groups[1].Value.Trim();
                bool pc = r.StdOut.IndexOf("PROFILE_CREATED=1") >= 0;
                bool gc = r.StdOut.IndexOf("GROUP_CREATED=1") >= 0;
                bool ma = r.StdOut.IndexOf("MEMBER_ADDED=1") >= 0;
                bool rl = r.StdOut.IndexOf("RELINKED=1") >= 0;
                detail = "профиль «" + pn + "»" + (pc ? " создан (ролей: " + roles + ")" : " уже был") +
                         (gc ? ", группа «Чтение (AI)» создана" : ", группа уже была") +
                         (ma ? ", читатель включён" : ", читатель уже в группе") +
                         (rl ? ", связь элемента справочника восстановлена" : "");
            }
            return true;
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
                    Log.Fix("нужен пользователь 1С с полными правами. Enter оставляет показанное в скобках имя — " +
                            "а это лишь предположение, в базе его может НЕ быть (прогон 08.08: «Администратор» vs " +
                            "«Администратор (ИвановИИ)»). Впечатайте ПОЛНОЕ имя точно как в 1С (Конфигуратор → " +
                            "Администрирование → Пользователи) и его пароль");
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
            // Проверка факта: состав после записи не должен быть пуст (дублирует
            // throw в скрипте — на случай старой платформы без AFTER).
            Match maf = Regex.Match(r.StdOut, @"AFTER=(-?\d+)");
            if (writeMode && maf.Success && int.Parse(maf.Groups[1].Value) == 0)
            {
                Log.Err("состав OData после записи ПУСТ (0 объектов) — запись не применилась");
                return false;
            }
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

        static string HttpGet(string url, string user, string pwd, int timeoutMs, out int status, out string body)
        {
            status = 0; body = "";
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
                    status = (int)resp.StatusCode;
                    using (StreamReader sr = new StreamReader(resp.GetResponseStream(), Encoding.UTF8))
                        body = sr.ReadToEnd();
                }
                return null;
            }
            catch (WebException we)
            {
                HttpWebResponse resp = we.Response as HttpWebResponse;
                if (resp != null) { status = (int)resp.StatusCode; return null; }
                return we.Message;
            }
            catch (Exception e) { return e.Message; }
        }

        // Живая проба ДАННЫХ (прогон 07.08: smoke kind=meta был «зелёным» при ПУСТОМ
        // составе — $metadata доступен всегда): корневой документ → первая сущность
        // состава → GET ?$top=1 под читателем. Пустой состав или не-200 = ошибка.
        public static bool ProbeDataRead(string odataUrl, string user, string pwd, out string detail)
        {
            detail = "";
            string baseUrl = odataUrl.TrimEnd('/') + "/";
            int status; string body;
            string err = HttpGet(baseUrl + "?$format=json", user, pwd, 60000, out status, out body);
            if (err != null) { detail = "OData не отвечает: " + err + " [" + baseUrl + "]"; return false; }
            if (status == 401 || status == 403) { detail = "читатель не авторизуется (HTTP " + status + ") — проверьте пользователя/пароль [" + baseUrl + "]"; return false; }
            if (status == 404) { detail = "публикация не найдена (HTTP 404) — не тот адрес/алиас: " + baseUrl; return false; }
            if (status != 200) { detail = "OData: HTTP " + status + " [" + baseUrl + "]"; return false; }
            Match m = Regex.Match(body, "\"name\"\\s*:\\s*\"([^\"]+)\"", RegexOptions.IgnoreCase);
            if (!m.Success) m = Regex.Match(body, "<collection\\s+href=\"([^\"]+)\"", RegexOptions.IgnoreCase);
            if (!m.Success) { detail = "состав OData ПУСТ — ни одной сущности в корневом документе"; return false; }
            string entity = m.Groups[1].Value;
            int status2; string body2;
            err = HttpGet(baseUrl + entity + "?$top=1&$format=json", user, pwd, 120000, out status2, out body2);
            if (err != null) { detail = "проба данных " + entity + ": " + err; return false; }
            if (status2 != 200)
            {
                // 401 на сущности при 200 на корне = вход выполнен, но прав НЕТ
                // (прогон 08.08: пользователь создан без профиля доступа — владелец
                // читал это как «не тот пароль»). Различаем явно.
                if (status2 == 401 || status2 == 403)
                    detail = "вход выполнен (пароль верный), но у читателя НЕТ ПРАВ на чтение данных — " +
                             "в карточке пользователя на вкладке «Права доступа» включите профиль " +
                             "«Только просмотр» и пересохраните [" + baseUrl + entity + ": HTTP " + status2 + "]";
                else
                    detail = "проба данных " + entity + ": HTTP " + status2 + " — состав не задался или читателю нет прав [" + baseUrl + entity + "]";
                return false;
            }
            detail = "проба данных: " + entity + "?$top=1 -> HTTP 200";
            return true;
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
