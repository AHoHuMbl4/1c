// Program.cs — setup-1c-odata: автоматическая настройка Windows-стороны «второго мозга».
// Делает всё, кроме создания пользователя-читателя в 1С (это осознанно оставлено человеку).
// C# 5 (csc.exe из .NET Framework).
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Microsoft.Win32;

namespace Oc1c
{
    internal class Opts
    {
        public string BasePath, ConnStr;
        public string Site = "Default Web Site";
        public string Alias = "1c";
        public string Dir;
        public string AdminUser, AdminPassword;
        public string ReaderUser, ReaderPassword;
        public string Scope = "default";
        public string AppPool = "1c-odata";
        public bool UseDefaultPool;
        public string PlatformVersion, PlatformDir;
        public string BackupDir = @"C:\1c\backups";
        public bool NoBackup;
        public string OpenFirewall;
        public string VerifyUrl, ExternalUrl;
        public bool Unattended;
        public bool SkipScope;
        public bool Force;
        public bool AutoResume;
        public string LogPath;
    }

    internal static class Program
    {
        const int TOTAL = 13;
        const int EXIT_OK = 0, EXIT_ARGS = 5, EXIT_NOTADMIN = 2, EXIT_PREREQ = 3, EXIT_STEP = 4,
                  EXIT_REBOOT = 10, EXIT_VERIFY = 20;

        static int Main(string[] argv)
        {
            try { Console.OutputEncoding = Encoding.UTF8; }
            catch { }

            Opts o = new Opts();
            string err = ParseArgs(argv, o);
            if (err == "HELP") { Help(); return EXIT_OK; }
            if (err != null) { Console.WriteLine("ОШИБКА В АРГУМЕНТАХ: " + err); Console.WriteLine("Подсказка: setup-1c-odata.exe --help"); return EXIT_ARGS; }

            string logPath = o.LogPath;
            if (string.IsNullOrEmpty(logPath))
            {
                string dir = @"C:\1c\logs";
                try { if (!Directory.Exists(dir)) Directory.CreateDirectory(dir); }
                catch { dir = Path.GetTempPath(); }
                logPath = Path.Combine(dir, "setup-1c-odata_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".log");
            }
            Log.Init(logPath);
            Log.AddSecret(o.AdminPassword);
            Log.AddSecret(o.ReaderPassword);

            try { return Run(o); }
            catch (Exception e)
            {
                Log.Err("непредвиденная ошибка: " + e.Message);
                Log.File(e.ToString());
                Log.Con("");
                Log.Con("Полный лог: " + Log.Path);
                return EXIT_STEP;
            }
        }

        // ================================================================= основной сценарий
        static int Run(Opts o)
        {
            Log.Head("setup-1c-odata " + Ctx.ToolVersion + (Ctx.DryRun ? "   [РЕЖИМ ПРОВЕРКИ — НИЧЕГО НЕ МЕНЯЕТСЯ]" : ""));
            Log.Con("Настройка Windows-стороны: 1С -> IIS -> OData (только чтение) для сервера Ubuntu.");
            Log.Con("Лог: " + Log.Path);

            // ---------- 1. окружение и права
            Log.Step(1, TOTAL, "Окружение и права администратора");
            Log.Info(Win.OsDescription());
            if (!Win.IsAdmin())
            {
                Log.Err("программа запущена БЕЗ прав администратора");
                Log.Fix("правый клик по setup-1c-odata.exe -> «Запуск от имени администратора»");
                return EXIT_NOTADMIN;
            }
            Log.Ok("права администратора есть");
            string why;
            if (Win.PendingReboot(out why))
                Log.Warn("система ждёт перезагрузки (" + why + ") — установка компонентов может не примениться");
            Log.Info("PowerShell: " + Ps.Exe(false));

            // ---------- 2. платформа 1С
            Log.Step(2, TOTAL, "Платформа 1С");
            List<Platform> plats = Steps.FindPlatforms(o.PlatformDir);
            if (plats.Count == 0)
            {
                Log.Err("платформа 1С:Предприятие не найдена");
                Log.Fix("установите платформу 1С (обязательно с компонентом «Модули расширения веб-сервера»), " +
                        "либо укажите каталог: --platform-dir \"C:\\Program Files (x86)\\1cv8\"");
                return EXIT_PREREQ;
            }
            Platform plat = null;
            if (!string.IsNullOrEmpty(o.PlatformVersion))
            {
                for (int i = 0; i < plats.Count; i++) if (plats[i].Version == o.PlatformVersion) plat = plats[i];
                if (plat == null)
                {
                    Log.Err("версия платформы " + o.PlatformVersion + " не найдена");
                    for (int i = 0; i < plats.Count; i++) Log.Info("доступна: " + plats[i].ToString());
                    return EXIT_PREREQ;
                }
            }
            else
            {
                // берём самую новую, у которой есть веб-модуль
                for (int i = 0; i < plats.Count && plat == null; i++) if (plats[i].HasWeb) plat = plats[i];
                if (plat == null) plat = plats[0];
            }
            for (int i = 0; i < plats.Count; i++) Log.Info((plats[i] == plat ? "выбрана: " : "найдена: ") + plats[i].ToString());
            if (!plat.HasWeb)
            {
                Log.Err("в выбранной платформе НЕТ модуля расширения веб-сервера (bin\\wsisapi.dll)");
                Log.Fix("перезапустите установщик платформы 1С и включите «Модули расширения веб-сервера». " +
                        "Тихая установка: msiexec /i \"1CEnterprise 8.msi\" /qn /norestart TRANSFORMS=1049.mst WEBSERVEREXT=1");
                return EXIT_PREREQ;
            }
            Log.Ok("платформа " + plat.Version + " (" + (plat.X86 ? "x86" : "x64") + "), веб-модуль есть" +
                   (plat.HasCom ? ", COM-коннектор есть" : ", COM-коннектор НЕ найден"));

            // ---------- 3. база 1С
            Log.Step(3, TOTAL, "База 1С");
            if (string.IsNullOrEmpty(o.BasePath) && string.IsNullOrEmpty(o.ConnStr))
            {
                if (o.Unattended)
                {
                    Log.Err("не указана база: --base <путь> или --connstr \"Srvr=...;Ref=...;\"");
                    return EXIT_ARGS;
                }
                List<string> found = Steps.ScanFileBases(@"C:\1c\bases");
                if (found.Count == 0)
                {
                    Log.Err("файловые базы в C:\\1c\\bases не найдены");
                    Log.Fix("укажите путь явно: --base \"C:\\путь\\к\\базе\" (каталог с файлом 1Cv8.1CD)");
                    return EXIT_ARGS;
                }
                Log.Con("       Найденные базы:");
                for (int i = 0; i < found.Count; i++) Log.Con("         " + (i + 1) + ") " + found[i]);
                Console.Write("       Выберите номер базы: ");
                string ans = Console.ReadLine();
                int num;
                if (!int.TryParse(ans == null ? "" : ans.Trim(), out num) || num < 1 || num > found.Count)
                { Log.Err("некорректный выбор"); return EXIT_ARGS; }
                o.BasePath = found[num - 1];
                Log.File("выбрана база: " + o.BasePath);
            }
            BaseRef bref = Steps.ResolveBase(o.BasePath, o.ConnStr);
            if (bref == null)
            {
                Log.Err("не разобрать строку соединения: " + o.ConnStr);
                Log.Fix("формат: --connstr \"Srvr='сервер';Ref='имя_базы';\" или --base \"C:\\путь\\к\\базе\"");
                return EXIT_ARGS;
            }
            if (bref.IsFile)
            {
                if (!Directory.Exists(bref.Dir)) { Log.Err("каталог базы не существует: " + bref.Dir); return EXIT_PREREQ; }
                if (!File.Exists(Path.Combine(bref.Dir, "1Cv8.1CD")))
                {
                    Log.Err("в каталоге нет файла 1Cv8.1CD — это не файловая база 1С: " + bref.Dir);
                    Log.Fix("укажите каталог, в котором лежит 1Cv8.1CD");
                    return EXIT_PREREQ;
                }
            }
            Log.Ok(bref.Display);
            if (string.IsNullOrEmpty(o.Dir)) o.Dir = Path.Combine(@"C:\inetpub", o.Alias);

            // ---------- 4. компоненты IIS
            Log.Step(4, TOTAL, "Компоненты IIS");
            string detail;
            int iis = Steps.EnsureIis(out detail);
            if (iis < 0) { Log.Err(detail); Log.Fix("проверьте, что Windows позволяет установку компонентов (не Home-редакция с урезанным IIS), и повторите"); return EXIT_STEP; }
            if (iis == 1)
            {
                Log.Warn(detail);
                Log.Con("");
                Log.Head("НУЖНА ПЕРЕЗАГРУЗКА WINDOWS");
                Log.Con("Компоненты IIS установлены, но применятся только после перезагрузки.");
                Log.Con("После перезагрузки ЗАПУСТИТЕ ЭТОТ ЖЕ ФАЙЛ СНОВА — он продолжит с этого места.");
                SaveResume(o);
                if (o.AutoResume) RegisterRunOnce();
                return EXIT_REBOOT;
            }
            Log.Ok(detail);

            // ---------- 5. служба W3SVC
            Log.Step(5, TOTAL, "Служба веб-сервера (W3SVC)");
            if (!Steps.EnsureW3svc(out detail)) { Log.Err(detail); return EXIT_STEP; }
            Log.Ok(detail);

            // ---------- 6. публикация базы
            Log.Step(6, TOTAL, "Публикация базы в IIS");
            if (!Steps.Publish(plat, bref, o.Site, o.Alias, o.Dir, o.Force, out detail)) return EXIT_STEP;
            if (detail.StartsWith("уже")) Log.Skip(detail); else Log.Ok(detail);

            // ---------- 7. включение OData
            Log.Step(7, TOTAL, "Включение интерфейса OData (default.vrd)");
            if (!Steps.EnableODataInVrd(o.Dir, out detail)) return EXIT_STEP;
            if (detail.StartsWith("standardOdata уже")) Log.Skip(detail); else Log.Ok(detail);

            // ---------- 8. пул приложений
            Log.Step(8, TOTAL, "Пул приложений IIS");
            if (!Steps.EnsureAppPool(plat, o.Site, o.Alias, o.AppPool, o.UseDefaultPool, out detail)) return EXIT_STEP;
            string pool = o.UseDefaultPool ? (Steps.CurrentAppPool(o.Site, o.Alias) ?? "DefaultAppPool") : o.AppPool;
            Log.Ok(detail);

            // ---------- 9. разрешение ISAPI
            Log.Step(9, TOTAL, "Разрешение на модуль 1С (ISAPI)");
            if (!Steps.EnsureIsapiAllowed(plat, out detail)) return EXIT_STEP;
            Log.Ok(detail);

            // ---------- 10. права на каталог базы
            Log.Step(10, TOTAL, "Права IIS на каталог базы");
            if (!Steps.GrantAcl(bref, pool, out detail)) return EXIT_STEP;
            Log.Ok(detail);

            // ---------- 11. бэкап (перед единственным изменением в базе — составом OData)
            Log.Step(11, TOTAL, "Резервная копия базы (перед изменением состава OData)");
            if (o.SkipScope) Log.Skip("состав OData не меняется (--skip-scope) => база не изменится => бэкап не нужен");
            else if (o.NoBackup) Log.Warn("бэкап отключён ключом --no-backup (на ваш риск)");
            else if (!bref.IsFile) Log.Warn("клиент-серверная база — файловый бэкап невозможен, сделайте копию средствами кластера/СУБД");
            else if (Ctx.DryRun) Log.Sim("создал бы zip-бэкап базы в " + o.BackupDir);
            else if (!Steps.BackupZip(bref, o.BackupDir))
            {
                Log.Err("бэкап не удался — состав OData менять НЕ буду (правило: перед изменением базы всегда бэкап)");
                Log.Fix("исправьте причину выше либо запустите с --no-backup, если копия уже сделана вручную");
                return EXIT_STEP;
            }

            // ---------- 12. состав OData (через COM)
            Log.Step(12, TOTAL, "Состав интерфейса OData (какие объекты отдавать)");
            if (o.SkipScope)
            {
                Log.Skip("шаг отключён ключом --skip-scope (состав в базе оставлен как есть)");
                Log.Info("состав хранится В БАЗЕ и переживает перепубликацию; задать/изменить: " +
                         "перезапуск с --admin-user/--admin-password и нужным --scope");
            }
            else
            {
            string scopeErr;
            List<string> scopeKeys = Steps.ExpandScope(o.Scope, out scopeErr);
            if (scopeKeys == null)
            {
                Log.Err(scopeErr);
                Log.Fix("допустимо: default | analytics | all | список через запятую (см. --help)");
                return EXIT_ARGS;
            }
            Log.Info("разделы: " + string.Join(", ", scopeKeys.ToArray()));

            if (string.IsNullOrEmpty(o.AdminUser) && !o.Unattended && !Ctx.DryRun)
            {
                Console.Write("       Пользователь 1С с полными правами (Enter — без авторизации): ");
                o.AdminUser = (Console.ReadLine() ?? "").Trim();
                if (o.AdminUser.Length > 0)
                {
                    o.AdminPassword = Win.ReadPassword("Пароль этого пользователя");
                    Log.AddSecret(o.AdminPassword);
                }
            }

            int cur, added;
            string roles;
            bool comOk = false;
            if (string.IsNullOrEmpty(o.AdminUser) && Ctx.DryRun)
            {
                Log.Skip("проверка состава OData пропущена — не заданы учётные данные администратора 1С");
            }
            else
            {
                comOk = Steps.SetOdataComposition(plat, bref, o.AdminUser, o.AdminPassword, scopeKeys, true,
                                                  o.ReaderUser, out cur, out added, out roles);
                if (!comOk) return EXIT_STEP;
                if (cur >= 0) Log.Info("состав до запуска: " + cur + " объектов");
                if (added > 0) Log.Ok("состав OData задан: " + added + " объектов");
                else if (!Ctx.DryRun) Log.Skip("состав не менялся");

                if (!string.IsNullOrEmpty(o.ReaderUser))
                {
                    if (roles == "__NOTFOUND__")
                    {
                        Log.Warn("пользователь-читатель «" + o.ReaderUser + "» в базе НЕ найден");
                        Log.Fix("создайте его вручную (это единственный ручной шаг) — см. итог ниже");
                    }
                    else if (roles != null)
                    {
                        // В типовых на БСП профиль «Только просмотр» разворачивается в сотни ролей —
                        // в консоли показываем сводку, полный список уходит в лог.
                        string[] rr = roles.Length == 0 ? new string[0] : roles.Split(',');
                        Log.File("полный список ролей «" + o.ReaderUser + "»: " + roles);
                        if (rr.Length > 6)
                        {
                            string head = string.Join(",", rr, 0, 6).Trim();
                            Log.Info("ролей у «" + o.ReaderUser + "»: " + rr.Length + " (полный список в логе). Первые: " + head + " …");
                        }
                        else Log.Info("роли пользователя «" + o.ReaderUser + "»: " + (roles.Length == 0 ? "(нет)" : roles));
                        string rl = roles.ToLowerInvariant();
                        if (rl.Contains("полныеправа") || rl.Contains("fullaccess") ||
                            rl.Contains("администратор") || rl.Contains("administrator"))
                        {
                            Log.Warn("у пользователя-читателя есть АДМИНИСТРАТИВНАЯ роль — это нарушает режим «только чтение»!");
                            Log.Fix("оставьте ему только профиль «Только просмотр» и уберите административные роли");
                        }
                    }
                }
            }
            }   // конец блока --skip-scope

            // ---------- 13. проверка
            Log.Step(13, TOTAL, "Проверка: отвечает ли OData");
            Steps.RecyclePool(pool);
            Steps.StartPool(pool);
            string url = string.IsNullOrEmpty(o.VerifyUrl)
                ? "http://localhost/" + o.Alias + "/odata/standard.odata/"
                : o.VerifyUrl;
            Log.Info("адрес: " + url);

            int verifyExit = EXIT_OK;
            if (Ctx.DryRun && !File.Exists(Steps.VrdPath(o.Dir)))
            {
                Log.Skip("публикации ещё нет — проверка невозможна в режиме --check");
            }
            else
            {
                // 1) без учётных данных — ожидаем 401 (значит авторизация работает)
                Steps.HttpProbe anon = Steps.Probe(url, null, null, 180000);
                if (anon.Status == 401) Log.Ok("без пароля -> 401 (авторизация включена)");
                else if (anon.Status == 200)
                {
                    Log.Warn("без пароля -> 200: база отдаёт данные ЛЮБОМУ (в базе нет пользователей?)");
                    Log.Fix("заведите в базе пользователей (администратора и читателя) — иначе OData открыт всем в сети");
                }
                else if (anon.Status == 0) Log.Warn("нет ответа: " + anon.Error);
                else Log.Info("без пароля -> HTTP " + anon.Status);

                // 2) с учётными данными — ожидаем 200 и непустой список сущностей
                // Под читателем проверяем, только если известен ЕГО пароль. Иначе — под администратором:
                // иначе указание одного лишь --reader-user (для проверки ролей) давало бы ложный провал 401.
                bool useReader = !string.IsNullOrEmpty(o.ReaderUser) && !string.IsNullOrEmpty(o.ReaderPassword);
                if (!useReader && !string.IsNullOrEmpty(o.ReaderUser))
                    Log.Info("пароль читателя не задан — проверяю под администратором (роли читателя проверены на шаге 12)");
                string vu = useReader ? o.ReaderUser : o.AdminUser;
                string vp = useReader ? o.ReaderPassword : o.AdminPassword;
                if (!string.IsNullOrEmpty(vu))
                {
                    Steps.HttpProbe auth = Steps.Probe(url, vu, vp, 180000);
                    if (auth.Ok)
                    {
                        if (auth.Collections > 0) Log.Ok("под «" + vu + "» -> 200, сущностей в OData: " + auth.Collections);
                        else
                        {
                            Log.Warn("под «" + vu + "» -> 200, но список сущностей ПУСТ");
                            Log.Fix("состав OData не задан: перезапустите с --admin-user/--admin-password (шаг 12)");
                            verifyExit = EXIT_VERIFY;
                        }
                    }
                    else
                    {
                        Log.Err("под «" + vu + "» -> HTTP " + auth.Status + " " + (auth.Error == null ? "" : auth.Error));
                        if (auth.Status == 401) Log.Fix("неверный пароль этого пользователя 1С");
                        else if (auth.Status == 404) Log.Fix("проверьте адрес публикации (--alias) и что база опубликована");
                        else if (auth.Status == 503) Log.Fix("пул приложений остановлен: appcmd start apppool \"" + pool + "\"");
                        else if (auth.Status == 500) Log.Fix("ошибка 1С/IIS: разрядность пула, права на каталог базы или лицензия — см. лог");
                        verifyExit = EXIT_VERIFY;
                    }
                }
                else Log.Skip("проверка с авторизацией пропущена (не заданы учётные данные)");

                if (!string.IsNullOrEmpty(o.ExternalUrl))
                {
                    Steps.HttpProbe ext = Steps.Probe(o.ExternalUrl, vu, vp, 180000);
                    if (ext.Ok) Log.Ok("внешний адрес (через роутер) отвечает: " + o.ExternalUrl);
                    else { Log.Warn("внешний адрес не отвечает (HTTP " + ext.Status + "): " + o.ExternalUrl); Log.Fix("проверьте проброс порта на роутере и брандмауэр Windows"); }
                }
            }

            // ---------- брандмауэр (по запросу)
            if (!string.IsNullOrEmpty(o.OpenFirewall))
            {
                Log.Con("");
                Log.Con("[доп.] Брандмауэр Windows");
                if (Steps.OpenFirewall(o.OpenFirewall, out detail)) Log.Ok(detail);
            }

            Report(o, bref, plat, pool, url);
            ClearResume();
            return verifyExit;
        }

        // ================================================================= итоговый отчёт
        static void Report(Opts o, BaseRef b, Platform p, string pool, string url)
        {
            Log.Head("ИТОГ");
            if (Ctx.DryRun) Log.Con("Режим проверки: ничего не менялось. Для настройки запустите без --check.");
            else Log.Con(Ctx.Changed ? "Настройка выполнена." : "Всё уже было настроено — изменений не потребовалось.");
            if (Log.Warnings > 0) Log.Con("Предупреждений: " + Log.Warnings + " (см. выше и в логе).");

            Log.Con("");
            Log.Con("ОСТАЛОСЬ СДЕЛАТЬ РУКАМИ (осознанно не автоматизируется):");
            Log.Con("  1) Создать в 1С пользователя-читателя:");
            Log.Con("     1С:Предприятие -> Администрирование -> Настройки пользователей и прав -> Пользователи");
            Log.Con("     - сначала должен существовать пользователь с полными правами (администратор);");
            Log.Con("     - затем создать «" + (string.IsNullOrEmpty(o.ReaderUser) ? "ai_reader" : o.ReaderUser) + "» с профилем «Только просмотр»;");
            Log.Con("     - запомнить пароль — он понадобится серверу Ubuntu.");
            Log.Con("  2) На роутере пробросить порт на эту машину (порт 80), например 6003 -> 80.");

            List<string> ips = Win.LocalIPv4();
            if (ips.Count > 0)
            {
                Log.Con("");
                Log.Con("     IP-адреса этой машины (для проброса):");
                for (int i = 0; i < ips.Count; i++) Log.Con("       " + ips[i]);
            }

            string lanIp = "<ip-этой-машины>";
            for (int i = 0; i < ips.Count; i++)
            {
                string ip = ips[i].Split(' ')[0];
                if (!ip.StartsWith("169.254")) { lanIp = ip; break; }
            }

            StringBuilder h = new StringBuilder();
            h.AppendLine("# Данные для сервера Ubuntu (/etc/1c-odata-gateway.env)");
            h.AppendLine("# Сформировано setup-1c-odata " + Ctx.ToolVersion + " " + DateTime.Now.ToString("yyyy-MM-dd HH:mm"));
            h.AppendLine("ODG_UPSTREAM=http://" + lanIp + "/" + o.Alias + "/odata/standard.odata");
            h.AppendLine("ODG_USER=" + (string.IsNullOrEmpty(o.ReaderUser) ? "ai_reader" : o.ReaderUser));
            h.AppendLine("ODG_PASS=<пароль пользователя-читателя>");
            h.AppendLine("#");
            h.AppendLine("# Если Ubuntu ходит через роутер — подставьте адрес роутера и проброшенный порт, например:");
            h.AppendLine("# ODG_UPSTREAM=http://192.168.56.1:6003/" + o.Alias + "/odata/standard.odata");
            h.AppendLine("#");
            h.AppendLine("# Локальная проверка на этой машине: " + url);
            h.AppendLine("# База: " + b.Display);
            h.AppendLine("# Платформа: " + p.Version + " (" + (p.X86 ? "x86" : "x64") + "), пул IIS: " + pool);

            Log.Con("");
            Log.Con("ПЕРЕДАТЬ АДМИНИСТРАТОРУ UBUNTU:");
            Log.Con(h.ToString());

            try
            {
                string dir = Path.GetDirectoryName(Log.Path);
                string f = Path.Combine(dir, "1c-odata-connection.txt");
                if (!Ctx.DryRun)
                {
                    File.WriteAllText(f, h.ToString(), new UTF8Encoding(true));
                    Log.Con("Сохранено в файл: " + f);
                }
            }
            catch (Exception e) { Log.File("не удалось сохранить connection-файл: " + e.Message); }

            Log.Con("Полный лог: " + Log.Path);
        }

        // ================================================================= возобновление после перезагрузки
        static string ResumeFile
        {
            get
            {
                string d = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "1c-odata-setup");
                return Path.Combine(d, "resume.txt");
            }
        }

        static void SaveResume(Opts o)
        {
            try
            {
                string d = Path.GetDirectoryName(ResumeFile);
                if (!Directory.Exists(d)) Directory.CreateDirectory(d);
                string[] a = Environment.GetCommandLineArgs();
                StringBuilder sb = new StringBuilder();
                for (int i = 0; i < a.Length; i++) sb.Append("\"" + a[i] + "\" ");
                File.WriteAllText(ResumeFile, sb.ToString().Trim(), new UTF8Encoding(true));
                Log.Con("Команда для повторного запуска сохранена: " + ResumeFile);
            }
            catch (Exception e) { Log.File("не сохранил resume: " + e.Message); }
        }

        static void ClearResume()
        {
            try { if (File.Exists(ResumeFile)) File.Delete(ResumeFile); }
            catch { }
        }

        static void RegisterRunOnce()
        {
            try
            {
                string[] a = Environment.GetCommandLineArgs();
                StringBuilder sb = new StringBuilder();
                sb.Append("\"" + a[0] + "\"");
                for (int i = 1; i < a.Length; i++)
                    if (a[i] != "--auto-resume") sb.Append(" \"" + a[i] + "\"");
                using (RegistryKey k = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64)
                        .OpenSubKey(@"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce", true))
                {
                    if (k != null) { k.SetValue("Setup1COData", sb.ToString()); Log.Ok("после перезагрузки настройка продолжится автоматически (RunOnce)"); }
                }
            }
            catch (Exception e) { Log.Warn("не удалось включить авто-продолжение: " + e.Message); }
        }

        // ================================================================= аргументы
        static string ParseArgs(string[] a, Opts o)
        {
            List<string> args = new List<string>(a);
            // --config подмешиваем первым, аргументы командной строки важнее
            for (int i = 0; i < args.Count - 1; i++)
                if (args[i] == "--config")
                {
                    string e = LoadConfig(args[i + 1], o);
                    if (e != null) return e;
                }

            for (int i = 0; i < args.Count; i++)
            {
                string k = args[i];
                string v = (i + 1 < args.Count) ? args[i + 1] : null;
                bool need = true;
                switch (k)
                {
                    case "--help": case "-h": case "/?": return "HELP";
                    case "--check": Ctx.DryRun = true; need = false; break;
                    case "--yes": case "-y": Ctx.AssumeYes = true; need = false; break;
                    case "--unattended": o.Unattended = true; Ctx.AssumeYes = true; need = false; break;
                    case "--skip-scope": o.SkipScope = true; need = false; break;
                    case "--force": o.Force = true; need = false; break;
                    case "--no-backup": o.NoBackup = true; need = false; break;
                    case "--use-default-pool": o.UseDefaultPool = true; need = false; break;
                    case "--auto-resume": o.AutoResume = true; need = false; break;
                    case "--base": o.BasePath = v; break;
                    case "--connstr": o.ConnStr = v; break;
                    case "--site": o.Site = v; break;
                    case "--alias": o.Alias = v; break;
                    case "--dir": o.Dir = v; break;
                    case "--admin-user": o.AdminUser = v; break;
                    case "--admin-password": o.AdminPassword = v; break;
                    case "--admin-password-env": o.AdminPassword = Environment.GetEnvironmentVariable(v); break;
                    case "--reader-user": o.ReaderUser = v; break;
                    case "--reader-password": o.ReaderPassword = v; break;
                    case "--reader-password-env": o.ReaderPassword = Environment.GetEnvironmentVariable(v); break;
                    case "--scope": o.Scope = v; break;
                    case "--app-pool": o.AppPool = v; break;
                    case "--platform-version": o.PlatformVersion = v; break;
                    case "--platform-dir": o.PlatformDir = v; break;
                    case "--backup-dir": o.BackupDir = v; break;
                    case "--open-firewall": o.OpenFirewall = v; break;
                    case "--verify-url": o.VerifyUrl = v; break;
                    case "--external-url": o.ExternalUrl = v; break;
                    case "--log": o.LogPath = v; break;
                    case "--config": break;               // уже обработан
                    default:
                        if (k.StartsWith("--")) return "неизвестный ключ " + k;
                        need = false; break;
                }
                if (need)
                {
                    if (v == null) return "у ключа " + k + " не указано значение";
                    i++;
                }
            }
            if (!string.IsNullOrEmpty(o.BasePath) && !string.IsNullOrEmpty(o.ConnStr))
                return "укажите либо --base, либо --connstr, но не оба";
            return null;
        }

        static string LoadConfig(string path, Opts o)
        {
            try
            {
                if (!File.Exists(path)) return "файл конфигурации не найден: " + path;
                string[] lines = File.ReadAllLines(path, Encoding.UTF8);
                for (int i = 0; i < lines.Length; i++)
                {
                    string l = lines[i].Trim();
                    if (l.Length == 0 || l.StartsWith("#") || l.StartsWith(";")) continue;
                    int eq = l.IndexOf('=');
                    if (eq <= 0) continue;
                    string k = l.Substring(0, eq).Trim().ToLowerInvariant();
                    string v = l.Substring(eq + 1).Trim();
                    switch (k)
                    {
                        case "base": o.BasePath = v; break;
                        case "connstr": o.ConnStr = v; break;
                        case "site": o.Site = v; break;
                        case "alias": o.Alias = v; break;
                        case "dir": o.Dir = v; break;
                        case "admin-user": o.AdminUser = v; break;
                        case "admin-password": o.AdminPassword = v; break;
                        case "reader-user": o.ReaderUser = v; break;
                        case "reader-password": o.ReaderPassword = v; break;
                        case "scope": o.Scope = v; break;
                        case "app-pool": o.AppPool = v; break;
                        case "platform-version": o.PlatformVersion = v; break;
                        case "backup-dir": o.BackupDir = v; break;
                        case "open-firewall": o.OpenFirewall = v; break;
                        case "external-url": o.ExternalUrl = v; break;
                        case "no-backup": if (v == "1" || v.ToLowerInvariant() == "true") o.NoBackup = true; break;
                    }
                }
                return null;
            }
            catch (Exception e) { return "не прочитать конфигурацию " + path + ": " + e.Message; }
        }

        // ================================================================= справка
        static void Help()
        {
            Console.WriteLine(@"
setup-1c-odata " + Ctx.ToolVersion + @" — автоматическая настройка Windows-стороны «второго мозга».

ЧТО ДЕЛАЕТ (по шагам, всё повторно безопасно — можно запускать сколько угодно раз):
  1  проверяет права администратора, версию Windows, ожидание перезагрузки
  2  находит платформу 1С и проверяет наличие модуля веб-сервера (wsisapi.dll) и COM-коннектора
  3  проверяет базу (файловую или клиент-серверную)
  4  устанавливает недостающие компоненты IIS (при необходимости попросит перезагрузку)
  5  включает службу W3SVC (автозапуск)
  6  публикует базу в IIS (webinst)
  7  включает интерфейс OData в default.vrd
  8  создаёт ОТДЕЛЬНЫЙ пул приложений нужной разрядности и отключает выгрузку по простою
  9  разрешает модуль 1С в ISAPI-ограничениях IIS
 10  выдаёт IIS права на каталог файловой базы
 11  делает резервную копию базы (перед единственным изменением в ней)
 12  задаёт состав OData (какие объекты отдавать) через COM
 13  проверяет по HTTP: без пароля -> 401, с паролем -> 200 и список сущностей

РУКАМИ ОСТАЁТСЯ ТОЛЬКО ОДНО: создать в 1С пользователя с профилем «Только просмотр».

ПРИМЕРЫ:
  setup-1c-odata.exe --check
      посмотреть, что будет сделано (НИЧЕГО не меняет)

  setup-1c-odata.exe --base ""C:\1c\bases\buh_test"" --admin-user Администратор
      обычная настройка (пароль спросит скрытно), состав OData = справочники + документы

  setup-1c-odata.exe --base ""C:\1c\bases\buh_test"" --admin-user Администратор ^
                     --scope analytics --reader-user ai_reader
      состав с регистрами (обороты/остатки — нужны для аналитики) + проверка пользователя-читателя

  setup-1c-odata.exe --connstr ""Srvr='srv1c';Ref='erp';"" --admin-user Администратор --unattended ^
                     --admin-password-env PWD1C
      клиент-серверная база, без вопросов, пароль из переменной окружения

КЛЮЧИ:
  --base <путь>            каталог файловой базы (где лежит 1Cv8.1CD)
  --connstr <строка>       клиент-серверная база: ""Srvr='сервер';Ref='база';""
  --alias <имя>            имя публикации в IIS (по умолчанию 1c) -> /1c/odata/standard.odata
  --dir <путь>             каталог публикации (по умолчанию C:\inetpub\<alias>)
  --site <имя>             сайт IIS (по умолчанию ""Default Web Site"")
  --admin-user <имя>       пользователь 1С с полными правами (нужен только для состава OData)
  --admin-password <пар>   пароль (лучше не указывать в командной строке — спросит скрытно)
  --admin-password-env <V> взять пароль из переменной окружения V
  --reader-user <имя>      пользователь-читатель: проверить, что создан и без админ-ролей
  --reader-password <пар>  его пароль — тогда финальная проверка пойдёт именно под ним
  --scope <набор>          default (справочники+документы) | analytics (+регистры, планы счетов,
                           перечисления) | all | список через запятую, например:
                           catalogs,documents,accumulation-registers,information-registers
  --app-pool <имя>         имя отдельного пула (по умолчанию 1c-odata)
  --use-default-pool       не создавать отдельный пул (не рекомендуется)
  --platform-version <в>   какую версию платформы использовать (по умолчанию — новейшая с веб-модулем)
  --platform-dir <путь>    нестандартный каталог установки платформы
  --backup-dir <путь>      куда класть бэкап (по умолчанию C:\1c\backups)
  --no-backup              не делать бэкап (только если копия уже есть)
  --open-firewall <сеть>   разрешить входящий TCP/80 с подсети, например 192.168.56.0/24
  --verify-url <url>       адрес для локальной проверки (по умолчанию http://localhost/<alias>/odata/standard.odata/)
  --external-url <url>     дополнительно проверить путь снаружи (через роутер)
  --force                  перепубликовать поверх чужой публикации в том же каталоге
  --check                  режим проверки: ничего не менять, только показать
  --yes                    не задавать подтверждений
  --unattended             полностью без вопросов (все данные — ключами/конфигом)
  --skip-scope             не трогать состав OData (шаг 12). Нужен, когда состав в базе уже задан
                           и пароля администратора 1С под рукой нет: состав хранится В БАЗЕ и
                           переживает перепубликацию
  --auto-resume            продолжить автоматически после перезагрузки (RunOnce)
  --config <файл>          файл настроек ключ=значение (см. setup-1c-odata.example.ini)
  --log <файл>             путь к логу (по умолчанию C:\1c\logs\setup-1c-odata_<дата>.log)

КОДЫ ВОЗВРАТА:
  0   успех
  2   запущено без прав администратора
  3   не выполнены предусловия (нет платформы / веб-модуля / базы)
  4   ошибка на шаге настройки
  5   ошибка в аргументах
  10  установлены компоненты IIS — нужна перезагрузка, затем запустить снова
  20  настройка выполнена, но итоговая проверка не прошла
");
        }
    }
}
