// Program.cs — setup-1c-odata: автоматическая настройка Windows-стороны «второго мозга».
// Делает всё, кроме создания пользователя-читателя в 1С (это осознанно оставлено человеку).
// C# 5 (csc.exe из .NET Framework).
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Win32;

namespace Oc1c
{
    internal class Opts
    {
        public string BasePath, ConnStr;
        public string BaseName;             // имя из списка запуска 1С (ibases.v8i) — для подсказок человеку
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
        public string UbuntuHost;           // IP/имя сервера аналитики (Ubuntu) — проверка связи с Windows
        public int UbuntuPort = 22;         // TCP-порт для пробы (на стенде SSH)
        public bool Unattended;
        public bool SkipScope;
        public bool Force;
        public bool AutoResume;
        public string LogPath;
        // Блок 2: агент пакетного транспорта (AGENT_TZ.md)
        public string PacketSetupPath;      // --packet-setup: packet-setup.json от Ubuntu
        public string PacketKit;            // --packet-kit: каталог комплекта (по умолчанию — рядом с exe)
        public string PacketDir;            // --packet-dir: куда ставить (по умолчанию C:\1c\packet)
        public bool SkipPacket;             // --skip-packet: не ставить агента даже при наличии комплекта
    }

    internal static class Program
    {
        const int TOTAL = 14;
        internal const int EXIT_OK = 0, EXIT_ARGS = 5, EXIT_NOTADMIN = 2, EXIT_PREREQ = 3, EXIT_STEP = 4,
                  EXIT_REBOOT = 10, EXIT_VERIFY = 20, EXIT_PACKET = 30;

        static int Main(string[] argv)
        {
            int rc = MainInner(argv);
            // Запуск двойным кликом: при ошибке окно исчезало вместе с текстом —
            // «после выбора базы окно закрылось и всё» (прогон владельца 07.08).
            // А при УСПЕХЕ окно закрывалось сразу после «Готово» и выглядело как
            // вылет (прогон 08.08). Поэтому пауза теперь в обоих случаях.
            // Ждём именно Esc: буферизованный Enter от прошлых вводов пролетал
            // ReadLine мгновенно, и окно закрывалось снова (прогон 07.08, вечер).
            if (!Console.IsInputRedirected)
            {
                try
                {
                    Console.WriteLine();
                    if (rc != EXIT_OK) Console.WriteLine("Код выхода: " + rc + ".");
                    Console.WriteLine("Нажмите Esc для закрытия окна…");
                    while (Console.ReadKey(true).Key != ConsoleKey.Escape) { }
                }
                catch { }
            }
            return rc;
        }

        static int MainInner(string[] argv)
        {
            try { Console.OutputEncoding = Encoding.UTF8; }
            catch { }
            // И ввод тоже: conhost отдаёт Unicode, без этого ReadLine декодирует
            // русские имена пользователей 1С в OEM — «Администратор (ФедоровБМ)»
            // превращался в мусор, и 1С честно отвечала «неверный пароль»
            // (прогон владельца 09.08; в логе 08.08 — «Ифидщифидщ»).
            try { Console.InputEncoding = Encoding.UTF8; }
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

            // Прицепленный пакет (один exe): комплект слота + webext-ячейки.
            int pl = Payload.Extract();
            if (pl > 0) Log.File("прицепленный пакет распакован во временную папку: файлов " + pl);

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
            Log.Con("Настройка Windows-стороны: 1С -> IIS -> OData (только чтение) для сервера аналитики.");
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
            {
                Log.Warn("система ждёт перезагрузки (" + why + ")");
                Log.Fix("перезагрузите Windows и запустите установщик снова — иначе компоненты IIS могут не примениться");
            }
            Log.Info("PowerShell: " + Ps.Exe(false));

            // Префлайт системы: нагрузка CPU/RAM (до любых изменений)
            int cpuPct; long ramFree, ramTotal;
            Log.Info("замеряю нагрузку ПК (CPU/RAM, ~1 с)...");
            Win.SampleLoad(out cpuPct, out ramFree, out ramTotal);
            if (cpuPct >= 0 || ramFree >= 0)
            {
                string load = "CPU " + (cpuPct < 0 ? "?" : cpuPct + "%") +
                              ", RAM свободно " + (ramFree < 0 ? "?" : ramFree + " МБ") +
                              (ramTotal > 0 ? " из " + ramTotal + " МБ" : "");
                Log.Info(load);
                if (cpuPct >= 85)
                    Log.Warn("высокая загрузка CPU (" + cpuPct + "%) — закройте лишние программы или повторите позже (иначе возможны таймауты COM/бэкапа)");
                if (ramFree >= 0 && ramFree < 256)
                {
                    Log.Err("мало свободной памяти (" + ramFree + " МБ) — установка небезопасна");
                    Log.Fix("освободите память (закройте программы) и повторите");
                    return EXIT_PREREQ;
                }
                if (ramFree >= 0 && ramFree < 512)
                    Log.Warn("мало свободной RAM (" + ramFree + " МБ) — рекомендуется ≥512 МБ");
            }
            else Log.Warn("не удалось замерить нагрузку CPU/RAM — продолжаю без этой проверки");

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
            // Самолечение: файлы модуля могут быть на месте, но повреждены
            // (замер 09.08 — в bin лежали куски exe от битой распаковки пакета).
            string hdet;
            if (Steps.HealWebextFromPayload(plat, out hdet)) Log.Ok(hdet);
            else if (hdet.Length > 0) Log.Warn("самолечение модуля веб-сервера: " + hdet);
            if (!plat.HasWeb && !Ctx.DryRun)
            {
                // Сначала пробуем доустановить сами: ячейка пакета → дистрибутив
                // (Steps.TryInstallWebServerExt). Только потом — ручной туториал.
                string wdet;
                if (Steps.TryInstallWebServerExt(plat, out wdet))
                    Log.Ok("модуль расширения веб-сервера доустановлен программой: " + wdet);
                else if (wdet.Length > 0)
                    Log.Warn("автодоустановка модуля веб-сервера не удалась: " + wdet);
            }
            if (!plat.HasWeb)
            {
                if (Ctx.DryRun) { Log.Sim("веб-модуля нет — в боевом режиме доустановила бы сама (пакет/дистрибутив)"); }
                Log.Err("в выбранной платформе НЕТ модуля расширения веб-сервера (bin\\wsisapi.dll)");
                string tut = Steps.WebModuleTutorial(plat);
                Log.Con("");
                Log.Con(new string('-', 74));
                Log.Con(tut);
                Log.Con(new string('-', 74));
                SaveTextBesideLog("1c-odata-добавить-веб-модуль.txt", tut);
                return EXIT_PREREQ;
            }
            Log.Ok("платформа " + plat.Version + " (" + (plat.X86 ? "x86" : "x64") + "), веб-модуль есть" +
                   (plat.HasCom ? ", COM-коннектор есть" : ", COM-коннектор НЕ найден"));
            if (!plat.HasCom)
            {
                Log.Warn("нет comcntr.dll — программа не сможет задать состав OData сама");
                Log.Fix("добавьте «Модули расширения COM» тем же способом «Изменить» в установке платформы — потом перезапустите эту программу");
            }

            // ---------- 3. база 1С
            Log.Step(3, TOTAL, "База 1С");
            if (string.IsNullOrEmpty(o.BasePath) && string.IsNullOrEmpty(o.ConnStr))
            {
                if (o.Unattended)
                {
                    Log.Err("не указана база: --base <путь> или --connstr \"Srvr=...;Ref=...;\"");
                    return EXIT_ARGS;
                }
                List<FoundBase> found = Steps.FindFileBases(@"C:\1c\bases");
                if (found.Count == 0)
                {
                    Log.Err("файловые базы не найдены ни в реестре баз 1С (ibases.v8i), ни в C:\\1c\\bases");
                    Log.Fix("укажите путь явно: --base \"C:\\путь\\к\\базе\" (каталог с файлом 1Cv8.1CD) или зарегистрируйте базу в списке 1cestart");
                    return EXIT_ARGS;
                }
                Log.Con("       Найденные базы (имена — как в стартовом окне 1С):");
                for (int i = 0; i < found.Count; i++)
                    Log.Con("         " + (i + 1) + ") " + (string.IsNullOrEmpty(found[i].Name)
                        ? found[i].Dir + "   (в стартовом списке 1С её нет — найдена на диске)"
                        : found[i].Name + "   [" + found[i].Dir + "]"));
                int num = 0;
                {
                    // Крутим вопрос, пока не выбрано верно или отмена: пользователь
                    // может ввести название, пустое, буквы (прогоны 07.08).
                    while (true)
                    {
                        Console.Write("       Введите НОМЕР базы из списка (1-" + found.Count + ") и нажмите Enter (Q — отмена): ");
                        string ans = (Console.ReadLine() ?? "").Trim();
                        if (string.Equals(ans, "q", StringComparison.OrdinalIgnoreCase))
                        { Log.Err("выбор базы отменён пользователем"); return EXIT_ARGS; }
                        if (int.TryParse(ans, out num) && num >= 1 && num <= found.Count) break;
                        Console.WriteLine("       Нужен номер цифрой от 1 до " + found.Count + " (не название). Вы ввели: «" + ans + "»");
                    }
                }
                o.BasePath = found[num - 1].Dir;
                o.BaseName = found[num - 1].Name;
                Log.File("выбрана база: " + o.BasePath + (string.IsNullOrEmpty(o.BaseName) ? "" : " (в списке 1С: " + o.BaseName + ")"));
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

            // Префлайт места: бэкап ещё может отмениться (Q на учётке админа) — если уже
            // --skip-scope/--no-backup, запас под бэкап не требуем.
            bool willBackup = !o.SkipScope && !o.NoBackup && bref.IsFile;
            string diskSum;
            if (!Steps.PrefightDisk(bref, o.BackupDir, o.Dir, Path.GetDirectoryName(Log.Path), willBackup, out diskSum))
                return EXIT_PREREQ;
            Log.Info(diskSum);

            // Ранняя проверка связи с сервером Ubuntu (если задан)
            if (!string.IsNullOrEmpty(o.UbuntuHost))
            {
                string tcpDetail;
                if (Win.TcpReachable(o.UbuntuHost, o.UbuntuPort, 3000, out tcpDetail))
                    Log.Ok("связь с сервером аналитики: " + tcpDetail);
                else
                {
                    Log.Warn("нет TCP-связи с сервером аналитики: " + tcpDetail);
                    Log.Fix("проверьте сеть/VPN/маршрут до " + o.UbuntuHost +
                            " с этой машины должен быть доступен сервер аналитики). Продолжаю настройку IIS;");
                    Log.Fix("без сети сервер не сможет забирать OData, даже если публикация локально ок.");
                }
                if (string.IsNullOrEmpty(o.OpenFirewall))
                {
                    // netsh remoteip принимает только IP: DNS-имя резолвим (разбор 07.08).
                    string fwHost = o.UbuntuHost;
                    try
                    {
                        System.Net.IPAddress ip;
                        if (!System.Net.IPAddress.TryParse(fwHost, out ip))
                        {
                            System.Net.IPAddress[] addrs = System.Net.Dns.GetHostAddresses(fwHost);
                            for (int ai = 0; ai < addrs.Length; ai++)
                                if (addrs[ai].AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork)
                                { fwHost = addrs[ai].ToString(); break; }
                        }
                    }
                    catch { /* оставляем как было — SuggestFirewallCidr вернёт null для не-IP */ }
                    o.OpenFirewall = Win.SuggestFirewallCidr(fwHost);
                    Log.Info("брандмауэр: для входа к IIS:80 предложен remoteip=" + o.OpenFirewall +
                             " (из --ubuntu-host; переопределите --open-firewall при необходимости)");
                }
            }

            // ---------- 4. компоненты IIS
            Log.Step(4, TOTAL, "Компоненты IIS");
            string detail;
            int iis = Steps.EnsureIis(out detail);
            if (iis < 0) { Log.Err(detail); Log.Fix("проверьте доступ к источнику компонентов (Windows Update/WSUS или дистрибутив: dism /source / Install-WindowsFeature -Source) и повторите"); return EXIT_STEP; }
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
            if (!Steps.Publish(plat, bref, o.Site, o.Alias, o.Dir, o.Force, out detail))
            {
                // На машине с несколькими базами алиас по умолчанию может быть занят
                // другой базой — в интерактиве спрашиваем новый, а не умираем (07.08).
                if (!o.Unattended && !Console.IsInputRedirected && !o.Force)
                {
                    while (true)
                    {
                        Console.Write("       Алиас «" + o.Alias + "» занят другой базой. Введите другой алиас (латиницей, например «" +
                                      SafeAlias(bref) + "») или Q для отмены: ");
                        string na = (Console.ReadLine() ?? "").Trim().Trim('/');
                        if (string.Equals(na, "q", StringComparison.OrdinalIgnoreCase)) return EXIT_STEP;
                        if (Regex.IsMatch(na, "^[A-Za-z0-9_-]+$")) { o.Alias = na; o.Dir = @"C:\inetpub\" + na; break; }
                        Console.WriteLine("       Алиас — только латинские буквы, цифры, - и _. Вы ввели: «" + na + "»");
                    }
                    if (!Steps.Publish(plat, bref, o.Site, o.Alias, o.Dir, o.Force, out detail)) return EXIT_STEP;
                }
                else return EXIT_STEP;
            }
            if (detail.StartsWith("уже")) Log.Skip(detail); else Log.Ok(detail);

            // ---------- 7. включение OData
            Log.Step(7, TOTAL, "Включение интерфейса OData (default.vrd)");
            if (!Steps.EnableODataInVrd(o.Dir, out detail)) return EXIT_STEP;
            if (detail.StartsWith("standardOdata уже")) Log.Skip(detail); else Log.Ok(detail);
            // Доп. рубеж: даже если шаг «уже был true», перечитываем (грабля Н-3).
            if (!Ctx.DryRun || File.Exists(Steps.VrdPath(o.Dir)))
            {
                string vchk;
                if (!Steps.IsODataEnabledInVrd(o.Dir, out vchk))
                {
                    Log.Err("проверка default.vrd провалена: " + vchk);
                    return EXIT_STEP;
                }
            }

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

            // ---------- состав OData: решаем ДО бэкапа (иначе зря копируем гигабайты, если админ откажется)
            string scopeErr;
            List<string> scopeKeys = Steps.ExpandScope(o.Scope, out scopeErr);
            if (scopeKeys == null)
            {
                Log.Err(scopeErr);
                Log.Fix("допустимо: default | analytics | all | список через запятую (см. --help)");
                return EXIT_ARGS;
            }
            if (!o.SkipScope && string.IsNullOrEmpty(o.AdminUser) && !Ctx.DryRun)
            {
                if (o.Unattended)
                {
                    Log.Err("не заданы учётные данные администратора 1С для шага 12 (состав OData)");
                    Log.Fix("либо --admin-user + --admin-password-env, либо --skip-scope " +
                            "(тогда состав задаёт администратор 1С вручную — программа напечатает инструкцию)");
                    return EXIT_ARGS;
                }
                if (!plat.HasCom)
                {
                    Log.Warn("COM-коннектора нет — состав задать не смогу (см. подсказку выше про «Модули расширения COM»)");
                    o.SkipScope = true;
                }
                else if (!AskScopeChoice(o, bref, scopeKeys)) o.SkipScope = true;
            }
            if (!o.SkipScope && !plat.HasCom && !Ctx.DryRun)
            {
                Log.Err("автоматический состав OData требует comcntr.dll, его нет");
                Log.Fix("добавьте модуль COM (см. туториал веб-модуля) или запустите с --skip-scope");
                SaveTextBesideLog("1c-odata-добавить-веб-модуль.txt", Steps.WebModuleTutorial(plat));
                return EXIT_PREREQ;
            }

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
                Log.Skip("состав в базе не меняется — задаёт администратор 1С вручную (инструкция ниже, в итоге)");
                Log.Info("состав хранится В БАЗЕ и переживает перепубликацию/переустановку IIS");
            }
            else
            {
            Log.Info("разделы: " + string.Join(", ", scopeKeys.ToArray()));

            int cur, added;
            string roles;
            bool comOk = false;
            if (string.IsNullOrEmpty(o.AdminUser) && Ctx.DryRun)
            {
                Log.Skip("проверка состава OData пропущена — не заданы учётные данные администратора 1С");
            }
            else
            {
                // Интерактив: неверный пароль админа 1С — не смерть, а повторный ввод
                // (прогон владельца 07.08: «ввёл неверный пароль и программа закрылась»).
                int attempts = 0;
                while (true)
                {
                    comOk = Steps.SetOdataComposition(plat, bref, o.AdminUser, o.AdminPassword, scopeKeys, true,
                                                      o.ReaderUser, out cur, out added, out roles);
                    if (comOk) break;
                    attempts++;
                    if (o.Unattended || Console.IsInputRedirected || attempts >= 3) return EXIT_STEP;
                    Console.Write("       Не получилось. Enter — ввести пароль ещё раз, Q — прервать: ");
                    string a = (Console.ReadLine() ?? "").Trim();
                    if (string.Equals(a, "q", StringComparison.OrdinalIgnoreCase)) return EXIT_STEP;
                    Console.Write("       Пользователь 1С с полными правами (Enter = " + o.AdminUser + "): ");
                    string u2 = (Console.ReadLine() ?? "").Trim();
                    if (u2.Length > 0) o.AdminUser = u2;
                    o.AdminPassword = Win.ReadPassword("Пароль пользователя " + o.AdminUser + " (ввод скрыт)");
                    Log.AddSecret(o.AdminPassword);
                }
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
                        if (auth.Collections > 0)
                        {
                            Log.Ok("под «" + vu + "» -> 200, сущностей в OData: " + auth.Collections);
                            // Живая проба ДАННЫХ: 200 на корне бывает и при пустом
                            // составе/битой публикации (прогон 07.08 — smoke был
                            // «зелёным» при всех 404). Читаем первую сущность.
                            string probeDetail;
                            if (Steps.ProbeDataRead(url, vu, vp, out probeDetail)) Log.Ok(probeDetail);
                            else
                            {
                                Log.Err(probeDetail);
                                Log.Fix("состав OData пуст или читателю нет прав на данные: задайте состав (шаг 12, без --skip-scope) и проверьте профиль читателя");
                                verifyExit = EXIT_VERIFY;
                            }
                        }
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
                        else if (auth.Status == 500) Log.Fix("ошибка 1С/IIS. По коду из строки выше: 0x800700c1 — разрядность пула/dll; 0x8007007e — wsisapi.dll битая или нет её зависимостей; 0x80070005 — права на каталог базы/bin платформы; прочее — лицензия. Полное тело ответа — в логе");
                        verifyExit = EXIT_VERIFY;
                    }
                }
                else Log.Skip("проверка с авторизацией пропущена (не заданы учётные данные)");

                if (!string.IsNullOrEmpty(o.ExternalUrl))
                {
                    Steps.HttpProbe ext = Steps.Probe(o.ExternalUrl, vu, vp, 180000);
                    if (ext.Ok) Log.Ok("внешний адрес (через роутер) отвечает: " + o.ExternalUrl);
                    else
                    {
                        Log.Warn("внешний адрес с ЭТОЙ машины не отвечает (HTTP " + ext.Status + "): " + o.ExternalUrl);
                        Log.Fix("часто это hairpin NAT: Windows не достучится до себя через роутер. Проверка с сервера: curl -s -o NUL -w %{http_code} " + o.ExternalUrl + "  (ожидается 401 без пароля). Также проверьте проброс и --open-firewall.");
                        // Запасная проверка: прямой LAN этой машины (как если бы Ubuntu был в той же сети)
                        string lip = PreferLanIp(Win.LocalIPv4());
                        if (lip != null && lip.IndexOf('<') < 0)
                        {
                            string direct = "http://" + lip + "/" + o.Alias + "/odata/standard.odata/";
                            Steps.HttpProbe d = Steps.Probe(direct, null, null, 30000);
                            if (d.Status == 401 || d.Ok)
                                Log.Ok("прямой HTTP к IIS на " + lip + " отвечает (HTTP " + d.Status + ") — канал на машине жив");
                            else
                                Log.Warn("прямой HTTP к IIS на " + lip + " тоже не ок (HTTP " + d.Status + ")");
                        }
                    }
                }
            }

            // ---------- брандмауэр (по запросу)
            if (!string.IsNullOrEmpty(o.OpenFirewall))
            {
                Log.Con("");
                Log.Con("[доп.] Брандмауэр Windows");
                if (Steps.OpenFirewall(o.OpenFirewall, out detail)) Log.Ok(detail);
            }

            // ---------- 14. расширение чтения (роль AIReadAll)
            // Мягкий шаг: фейл НЕ валит установку (предупреждение внутри), КС-база — пропуск.
            Log.Step(14, TOTAL, "Расширение чтения (роль AIReadAll)");
            if (!Steps.InstallAiExtension(plat, bref, o, pool, out detail)) return EXIT_STEP;
            if (detail.StartsWith("пропущено")) Log.Skip(detail); else if (detail.Length > 0) Log.Ok(detail);

            // ---------- блок 2: агент пакетного транспорта (только при наличии комплекта)
            int packetExit = PacketSteps.Run(o, bref, url, plat);

            Report(o, bref, plat, pool, url, scopeKeys);
            ClearResume();
            return packetExit != EXIT_OK ? packetExit : verifyExit;
        }

        // Предложение алиса из имени базы: только латиница/цифры (URL-safe).
        static string SafeAlias(BaseRef b)
        {
            string d = b.IsFile ? Path.GetFileName(b.Dir.TrimEnd('\\')) : b.Name;
            if (string.IsNullOrEmpty(d)) return "base1c";
            StringBuilder sb = new StringBuilder();
            foreach (char c in d) sb.Append(char.IsLetterOrDigit(c) && c < 128 ? c : '_');
            string s = sb.ToString().Trim('_');
            return s.Length == 0 ? "base1c" : s;
        }

        // ================================================================= учётка администратора
        // Состав OData задаёт только программа (решение владельца 09.08: ручного
        // варианта «задам сам в Конфигураторе» нет — человеку ничего не поручаем).
        // Возвращает true всегда; false — только отмена (Q).
        static bool AskScopeChoice(Opts o, BaseRef b, List<string> scopeKeys)
        {
            Log.Head("СОСТАВ OData — задаст программа");
            Log.Con("Нужно указать, какие объекты базы видны через OData API (только чтение).");
            Log.Con("Без этого шага OData отдаёт ПУСТОЙ список — сервер аналитики не увидит данных.");
            if (scopeKeys.Count >= Steps.ScopeMap.Count)
            {
                Log.Con("Программа откроет ВСЕ разделы (справочники, документы, регистры, перечисления и т.д.):");
                Log.Con("    сервер аналитики строит витрину по полным метаданным базы —");
                Log.Con("    состав обязан её покрывать, иначе выгрузка падает на недоступных разделах.");
            }
            else
            {
                Log.Con("Программа откроет разделы:");
                for (int i = 0; i < scopeKeys.Count; i++) Log.Con("    - " + Steps.ScopeLabel(scopeKeys[i]));
            }
            Log.Con("");
            Log.Con("Для этого один раз нужна учётка администратора 1С (пользователь с полными правами):");
            Log.Con("    пароль нужен платформе 1С один раз, локально на этой машине;");
            Log.Con("    вводится скрыто (звёздочки), по сети не передаётся, в логе маскируется;");
            Log.Con("    перед записью будет автоматический бэкап базы. Данные документов не меняются —");
            Log.Con("    только список объектов, видимых через OData.");
            Log.Con("");
            Console.Write("       Пользователь 1С с полными правами (Enter = Администратор, Q — отмена): ");
            string u = (Console.ReadLine() ?? "").Trim();
            if (string.Equals(u, "q", StringComparison.OrdinalIgnoreCase)) { Log.Skip("отмена администратором"); return false; }
            o.AdminUser = u.Length == 0 ? "Администратор" : u;
            o.AdminPassword = Win.ReadPassword("Пароль пользователя " + o.AdminUser + " (ввод скрыт)");
            Log.AddSecret(o.AdminPassword);
            if (string.IsNullOrEmpty(o.AdminPassword))
            {
                Log.Warn("пароль пуст — попробую подключиться без пароля");
            }
            return true;
        }

        // Предпочтительный LAN IP для подсказок: не VPN (10.8), не APIPA (169.254).
        static string PreferLanIp(List<string> ips)
        {
            string fallback = "<ip-этой-машины>";
            string any = null;
            for (int i = 0; i < ips.Count; i++)
            {
                string ip = ips[i].Split(' ')[0];
                if (ip.StartsWith("169.254")) continue;
                if (any == null) any = ip;
                // VPN WireGuard/стандартные туннели — хуже для проброса IIS
                if (ip.StartsWith("10.8.") || ip.StartsWith("10.7.")) continue;
                return ip;
            }
            return any != null ? any : fallback;
        }

        static void SaveTextBesideLog(string fileName, string text)
        {
            try
            {
                string dir = Path.GetDirectoryName(Log.Path);
                if (string.IsNullOrEmpty(dir)) dir = @"C:\1c\logs";
                if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);
                string mf = Path.Combine(dir, fileName);
                File.WriteAllText(mf, text, new UTF8Encoding(true));
                Log.Con("Инструкция сохранена в файл: " + mf);
            }
            catch (Exception e) { Log.File("не сохранил " + fileName + ": " + e.Message); }
        }

        // ================================================================= итоговый отчёт
        static void Report(Opts o, BaseRef b, Platform p, string pool, string url, List<string> scopeKeys)
        {
            Log.Head("ИТОГ");
            // Канал пакетов поднят — всё доказано (проба данных, доставка, задачи):
            // финал одним словом (решение владельца 07.08). Подробности — в логе.
            if (PacketSteps.Installed && !Ctx.DryRun)
            {
                Log.Con("Готово.");
                Log.Con("Полный лог: " + Log.Path);
                return;
            }
            if (Ctx.DryRun) Log.Con("Режим проверки: ничего не менялось. Для настройки запустите без --check.");
            else Log.Con(Ctx.Changed ? "Настройка выполнена." : "Всё уже было настроено — изменений не потребовалось.");
            if (Log.Warnings > 0) Log.Con("Предупреждений: " + Log.Warnings + " (см. выше и в логе).");

            // Если состав OData оставлен администратору — печатаем и сохраняем точную инструкцию.
            if (o.SkipScope && !Ctx.DryRun)
            {
                string manual = Steps.ManualScopeInstructions(b, o.Alias, scopeKeys);
                Log.Con("");
                Log.Con(new string('-', 74));
                Log.Con(manual);
                Log.Con(new string('-', 74));
                SaveTextBesideLog("1c-odata-ручная-настройка.txt", manual);
                Log.Con("(можно переслать тому, у кого есть пароль администратора 1С)");
            }

            Log.Con("");
            Log.Con("ОСТАЛОСЬ СДЕЛАТЬ РУКАМИ (осознанно не автоматизируется):");
            if (o.SkipScope && !Ctx.DryRun)
                Log.Con("  0) Задать состав OData в Конфигураторе — инструкция выше (без этого данных не будет).");
            Log.Con("  1) Создать в 1С пользователя-читателя:");
            Log.Con("     1С:Предприятие -> Администрирование (в УТ — «НСИ и администрирование»)");
            Log.Con("     -> Настройки пользователей и прав -> Пользователи");
            Log.Con("     - сначала должен существовать пользователь с полными правами (администратор);");
            Log.Con("     - затем создать «" + (string.IsNullOrEmpty(o.ReaderUser) ? "ai_reader" : o.ReaderUser) + "», задать пароль;");
            Log.Con("     - ОБЯЗАТЕЛЬНО включить галку «Вход в приложение разрешён» — без неё 1С");
            Log.Con("       не создаёт пользователя информационной базы (замер 08.08: карточка есть, входа нет);");
            Log.Con("     - права ТОЛЬКО на чтение: карточка -> «Права доступа» -> «Включить в группу»;");
            Log.Con("       нет группы чтения — «Группы доступа» -> Создать -> Профиль «Только просмотр»;");
            Log.Con("       нет и профиля (УТ/КА не поставляют его) — «Профили групп доступа» -> Создать:");
            Log.Con("       роли поиском по словам «Базовые права», «Запуск», «Использование», «Отчеты»,");
            Log.Con("       «Подсистема», «Просмотр», «Раздел», «Чтение» (выделить -> «Включить выделенные роли»);");
            Log.Con("     - запомнить пароль — он понадобится при настройке сервера аналитики.");
            Log.Con("  2) Сеть: сервер аналитики должен доставать эту машину по HTTP:80 (часто через");
            Log.Con("     проброс на роутере, например 8080 -> 80). Укажите --ubuntu-host и");
            Log.Con("     --external-url, чтобы установщик проверил путь.");

            List<string> ips = Win.LocalIPv4();
            if (ips.Count > 0)
            {
                Log.Con("");
                Log.Con("     IP-адреса этой машины (Windows):");
                for (int i = 0; i < ips.Count; i++) Log.Con("       " + ips[i]);
            }

            string lanIp = PreferLanIp(ips);

            // Предпочтительный ODG_UPSTREAM: внешний URL (как видит Ubuntu), иначе прямой LAN.
            string upstream;
            if (!string.IsNullOrEmpty(o.ExternalUrl))
            {
                upstream = o.ExternalUrl.TrimEnd('/');
                // external-url часто с хвостом / — ODG без завершающего слэша ок
                if (upstream.EndsWith("/odata/standard.odata", StringComparison.OrdinalIgnoreCase) ||
                    upstream.IndexOf("/odata/standard.odata", StringComparison.OrdinalIgnoreCase) >= 0)
                { /* уже полный путь */ }
                else if (!upstream.EndsWith("standard.odata", StringComparison.OrdinalIgnoreCase))
                    upstream = upstream.TrimEnd('/') + "/" + o.Alias + "/odata/standard.odata";
            }
            else
                upstream = "http://" + lanIp + "/" + o.Alias + "/odata/standard.odata";

            StringBuilder h = new StringBuilder();
            h.AppendLine("# Данные для сервера Ubuntu (/etc/1c-odata-gateway.env)");
            h.AppendLine("# Сформировано setup-1c-odata " + Ctx.ToolVersion + " " + DateTime.Now.ToString("yyyy-MM-dd HH:mm"));
            h.AppendLine("ODG_UPSTREAM=" + upstream);
            h.AppendLine("ODG_USER=" + (string.IsNullOrEmpty(o.ReaderUser) ? "ai_reader" : o.ReaderUser));
            h.AppendLine("ODG_PASS=<пароль пользователя-читателя>");
            h.AppendLine("#");
            if (!string.IsNullOrEmpty(o.UbuntuHost))
                h.AppendLine("# Сервер аналитики (проверка с Windows): " + o.UbuntuHost + ":" + o.UbuntuPort);
            h.AppendLine("# Прямой LAN этой машины: http://" + lanIp + "/" + o.Alias + "/odata/standard.odata");
            h.AppendLine("# Если Ubuntu ходит через роутер — типичный стенд:");
            h.AppendLine("# ODG_UPSTREAM=http://<роутер>:<порт>/" + o.Alias + "/odata/standard.odata");
            h.AppendLine("#   (проброс <роутер>:<порт> -> " + lanIp + ":80)");
            h.AppendLine("#");
            h.AppendLine("# Локальная проверка на этой машине: " + url);
            h.AppendLine("# База: " + b.Display);
            h.AppendLine("# Платформа: " + p.Version + " (" + (p.X86 ? "x86" : "x64") + "), пул IIS: " + pool);

            Log.Con("");
            if (PacketSteps.Installed)
            {
                // Канал пакетов поднят: сервер получает всё через приёмник сам
                // (конфиг — GET /agent/config), передавать ничего не нужно
                // (решение владельца 07.08). Секреты комплекта с машины стёрты.
                Log.Con("КАНАЛ ПАКЕТОВ ПОДНЯТ: сервер аналитики получает всё через приёмник "
                        + (string.IsNullOrEmpty(PacketSteps.ReceiverUrl) ? "" : PacketSteps.ReceiverUrl + " ")
                        + "сам,");
                Log.Con("передавать ничего не нужно. Секреты комплекта с машины стёрты (agent.ini — под ACL).");
            }
            else
            {
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
            }

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

        // Секреты в resume/RunOnce НЕ пишем: resume.txt лежит в ProgramData (чтение
        // всем пользователям), RunOnce — в реестре (разбор 07.08). После ребута
        // продолжение спросит пароль заново, если он понадобится (состав OData).
        static readonly string[] SecretArgs = new string[] {
            "--admin-password", "--reader-password", "--admin-password-env", "--reader-password-env" };

        static string SanitizedCmdLine(bool skipAutoResume)
        {
            string[] a = Environment.GetCommandLineArgs();
            StringBuilder sb = new StringBuilder();
            sb.Append("\"" + a[0] + "\"");
            for (int i = 1; i < a.Length; i++)
            {
                if (skipAutoResume && a[i] == "--auto-resume") continue;
                bool secret = false;
                for (int j = 0; j < SecretArgs.Length; j++)
                    if (a[i] == SecretArgs[j]) { secret = true; break; }
                if (secret) { i++; continue; }   // пропускаем и значение
                // кавычка внутри значения ломала склейку команды (разбор 07.08)
                sb.Append(" \"" + a[i].Replace("\"", "") + "\"");
            }
            return sb.ToString().Trim();
        }

        static void SaveResume(Opts o)
        {
            try
            {
                string d = Path.GetDirectoryName(ResumeFile);
                if (!Directory.Exists(d)) Directory.CreateDirectory(d);
                File.WriteAllText(ResumeFile, SanitizedCmdLine(false), new UTF8Encoding(true));
                Log.Con("Команда для повторного запуска сохранена: " + ResumeFile + " (без паролей)");
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
                using (RegistryKey k = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, Win.RegView())
                        .OpenSubKey(@"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce", true))
                {
                    if (k != null) { k.SetValue("Setup1COData", SanitizedCmdLine(true)); Log.Ok("после перезагрузки настройка продолжится автоматически (RunOnce)"); }
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
                    case "--skip-packet": o.SkipPacket = true; need = false; break;
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
                    case "--ubuntu-host": o.UbuntuHost = v; break;
                    case "--ubuntu-port":
                        {
                            int up;
                            if (!int.TryParse(v, out up) || up < 1 || up > 65535)
                                return "--ubuntu-port должен быть числом 1..65535";
                            o.UbuntuPort = up;
                            break;
                        }
                    case "--log": o.LogPath = v; break;
                    case "--packet-setup": o.PacketSetupPath = v; break;
                    case "--packet-kit": o.PacketKit = v; break;
                    case "--packet-dir": o.PacketDir = v; break;
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
                // Блокнот Win10 сохраняет ANSI по умолчанию — читаем UTF-8 строго,
                // при невалидном UTF-8 откатываемся на системную ANSI (разбор 07.08).
                string[] lines;
                try
                {
                    lines = File.ReadAllLines(path, new UTF8Encoding(false, true));
                }
                catch (DecoderFallbackException)
                {
                    lines = File.ReadAllLines(path, Encoding.Default);
                }
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
                        case "ubuntu-host": o.UbuntuHost = v; break;
                        case "ubuntu-port":
                            {
                                int up;
                                if (int.TryParse(v, out up) && up >= 1 && up <= 65535) o.UbuntuPort = up;
                                break;
                            }
                        case "no-backup": if (v == "1" || v.ToLowerInvariant() == "true") o.NoBackup = true; break;
                        case "packet-setup": o.PacketSetupPath = v; break;
                        case "packet-kit": o.PacketKit = v; break;
                        case "packet-dir": o.PacketDir = v; break;
                        case "skip-packet": if (v == "1" || v.ToLowerInvariant() == "true") o.SkipPacket = true; break;
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
  1  права администратора + префлайт системы (перезагрузка, CPU/RAM)
  2  платформа 1С: веб-модуль (wsisapi.dll) и COM; при отсутствии — полный туториал «Изменить»
  3  база + префлайт места на дисках; при --ubuntu-host — проверка TCP до сервера аналитики
  4  устанавливает недостающие компоненты IIS (при необходимости попросит перезагрузку)
  5  включает службу W3SVC (автозапуск)
  6  публикует базу в IIS (webinst)
  7  включает OData в default.vrd и ПЕРЕЧИТЫВАЕТ файл (enable обязан быть true)
  8  создаёт ОТДЕЛЬНЫЙ пул приложений нужной разрядности и отключает выгрузку по простою
  9  разрешает модуль 1С в ISAPI-ограничениях IIS
 10  выдаёт IIS права на каталог файловой базы
 11  резервная копия базы (перед изменением состава)
 12  состав OData: два варианта — пароль админа ИЛИ ручной туториал (--skip-scope)
 13  проверка HTTP + при необходимости брандмауэр для подсети сервера
 14  расширение чтения AIReadOnly (роль AIReadAll; только файловые базы; фейл не валит установку)

РУКАМИ ОСТАЁТСЯ: создать в 1С пользователя-читателя (ai_reader) с нужными правами.

ПРИМЕРЫ:
  setup-1c-odata.exe --check --ubuntu-host <ip-сервера>
      префлайт + план (НИЧЕГО не меняет), проверка связи с сервером аналитики

  setup-1c-odata.exe --base ""C:\1c\bases\<база>"" --ubuntu-host <ip-сервера> ^
                     --external-url http://<роутер>:<порт>/1c/odata/standard.odata/
      настройка + брандмауэр подсеть сервера + правильный ODG_UPSTREAM

  setup-1c-odata.exe --base ""C:\1c\bases\<база>"" --admin-user Администратор
      обычная настройка; перед составом — выбор варианта 1 или 2

  setup-1c-odata.exe --base ""C:\1c\bases\<база>"" --skip-scope --reader-user ai_reader
      без пароля админа: IIS/OData, состав — вручную по туториалу

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
  --ubuntu-host <ip/имя>   сервер аналитики: проверка TCP с этой машины + подсказка firewall
  --ubuntu-port <порт>     порт пробы (по умолчанию 22 — SSH)
  --open-firewall <сеть>   разрешить входящий TCP/80 с подсети, например 10.0.0.0/24
                           (если не задан, но задан --ubuntu-host — берётся его /24)
  --verify-url <url>       адрес для локальной проверки (по умолчанию http://localhost/<alias>/odata/standard.odata/)
  --external-url <url>     внешний путь (через роутер); попадёт в ODG_UPSTREAM
  --force                  перепубликовать поверх чужой публикации в том же каталоге
  --check                  режим проверки: ничего не менять, только показать
  --yes                    не задавать подтверждений
  --unattended             полностью без вопросов (все данные — ключами/конфигом)
  --skip-scope             не трогать состав OData вовсе (технический флаг: состав уже
                           задан администратором базы заранее)
  --auto-resume            продолжить автоматически после перезагрузки (RunOnce)
  --config <файл>          файл настроек ключ=значение (см. setup-1c-odata.example.ini)
  --log <файл>             путь к логу (по умолчанию C:\1c\logs\setup-1c-odata_<дата>.log)

БЛОК 2 — КАНАЛ ПЕРЕДАЧИ ДАННЫХ (активен, когда рядом с exe лежит комплект
  packet-setup.json + packet-agent.exe + age.exe + zstd.exe; комплект выдаётся один раз на базу):
  --packet-setup <файл>    путь к packet-setup.json (по умолчанию — рядом с exe)
  --packet-kit <каталог>   каталог комплекта, если он не рядом с exe
  --packet-dir <путь>      куда ставить агента (по умолчанию C:\1c\packet)
  --skip-packet            не устанавливать агента, даже если комплект есть
  Блок: префлайт (исходящий HTTPS на приёмник, место, целостность комплекта) ->
  установка в C:\1c\packet + agent.ini (права только админам/SYSTEM) -> автозапуск
  планировщиком -> пробная посылка. Код 0 — только при подтверждённой доставке.

КОДЫ ВОЗВРАТА:
  0   успех
  2   запущено без прав администратора
  3   не выполнены предусловия (нет платформы / веб-модуля / базы / мало RAM)
  4   ошибка на шаге настройки
  5   ошибка в аргументах
  10  установлены компоненты IIS — нужна перезагрузка, затем запустить снова
  20  настройка выполнена, но итоговая проверка не прошла
  30  агент пакетного транспорта: установка или пробная посылка не подтверждена
");
        }
    }
}
