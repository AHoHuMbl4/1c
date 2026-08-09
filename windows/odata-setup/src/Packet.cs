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
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Security.Principal;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;

namespace Oc1c
{
    // ------------------------------------------------------- комплект от Ubuntu
    // packet-setup.json генерируется на Ubuntu один раз на базу:
    // {"base_id":"<база>","token":"…","recipient_pubkey":"age1…","receiver_url":"https://…",
    //  "client_pfx":"client.pfx","client_pfx_password":"…"}   (mTLS, контракт §8)
    internal class PacketSetup
    {
        public string BaseId, Token, RecipientPubkey, ReceiverUrl;
        public string ClientPfx, ClientPfxPassword;   // mTLS: pfx из комплекта → LocalMachine\My
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
            p.ClientPfx = Str(d, "client_pfx");
            p.ClientPfxPassword = Str(d, "client_pfx_password");

            if (string.IsNullOrEmpty(p.BaseId) || !BaseIdRe.IsMatch(p.BaseId))
                return "packet-setup.json: base_id пуст или не вида [a-z0-9_-]+ («" + p.BaseId + "»)";
            if (string.IsNullOrEmpty(p.Token))
                return "packet-setup.json: token пуст — комплект не от этой установки";
            // recipient_pubkey ОБЯЗАТЕЛЕН (решение владельца 07.08: шифрование age с
            // первого пакета, пилот без age отменён). Пустой pubkey — сломанный
            // комплект, а не plain-режим: агент без него шлёт открытые файлы, чего
            // быть не должно.
            if (string.IsNullOrEmpty(p.RecipientPubkey) || !p.RecipientPubkey.StartsWith("age1"))
                return "packet-setup.json: recipient_pubkey пуст или не вида age1… — комплект сломан (шифрование age обязательно)";
            // mTLS (контракт §8): без клиентского сертификата релей не пропускает
            // запрос вовсе — комплект без pfx бесполезен.
            if (string.IsNullOrEmpty(p.ClientPfx))
                return "packet-setup.json: нет client_pfx — релей требует клиентский сертификат (mTLS)";
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
        // Блок поднял канал пакетов — Report тогда не печатает «передайте на Ubuntu»:
        // сервер получает всё через приёмник сам (решение владельца 07.08).
        internal static bool Installed;
        // Адрес приёмника из комплекта — для итогового сообщения (никаких констант
        // нашей инфраструктуры в текстах: комплект — единственный источник).
        internal static string ReceiverUrl;

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
        public static int Run(Opts o, BaseRef bref, string odataUrl, Platform plat)
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
                // Один exe: комплект может быть в прицепленном пакете (Payload).
                string inPayload = Payload.Find("packet-setup.json");
                if (inPayload != null) { kit = Payload.Dir; setupPath = inPayload; }
            }
            if (!File.Exists(setupPath) && string.IsNullOrEmpty(o.PacketSetupPath))
            {
                // Комплекта нет — поведение как у версии 1.1.0: блок не активен.
                Log.Skip("комплект пакетного транспорта не найден (packet-setup.json рядом с exe) — агент не устанавливается");
                return Program.EXIT_OK;
            }

            Log.Head("БЛОК 2: КАНАЛ ПЕРЕДАЧИ ДАННЫХ (автоматическая выгрузка 1С)");
            Log.Con("На эту машину ставится агент: он сам отправляет данные на сервер");
            Log.Con("по защищённому каналу. Открывать порты на этом компьютере НЕ нужно.");

            // ---------- 1. комплект и его валидность
            Log.Step(1, 6, "Комплект установки");
            PacketSetup ps;
            string err = PacketSetup.Load(setupPath, out ps);
            if (err != null)
            {
                Log.Err(err);
                Log.Fix("запросите свежий файл комплекта (packet-setup.json) у администратора сервера аналитики");
                return Program.EXIT_PREREQ;
            }
            Log.AddSecret(ps.Token);
            Log.AddSecret(ps.ClientPfxPassword);
            ReceiverUrl = ps.ReceiverUrl;
            Log.Ok("комплект проверен (база «" + ps.BaseId + "»)");
            Log.File("приёмник: " + ps.ReceiverUrl);

            string agentExe = Path.Combine(kit, "packet-agent.exe");
            string ageExe = Path.Combine(kit, "age.exe");
            string ageKeygenExe = Path.Combine(kit, "age-keygen.exe");
            string zstdExe = Path.Combine(kit, "zstd.exe");
            // age обязателен всегда (решение 07.08), zstd нужен всегда (сжатие — §4).
            // Каждый бинарь — либо файлом рядом с exe, либо вшит ресурсом в сам exe
            // (build.cmd, каталог embed\): тогда установщик — один файл (07.08).
            bool kitOk = true;
            if (!File.Exists(agentExe) && !HasEmbedded("packet-agent.exe")) { Log.Err("в комплекте нет packet-agent.exe (" + kit + ")"); kitOk = false; }
            if (!File.Exists(ageExe) && !HasEmbedded("age.exe")) { Log.Err("в комплекте нет age.exe (" + kit + ")"); kitOk = false; }
            if (!File.Exists(ageKeygenExe) && !HasEmbedded("age-keygen.exe")) { Log.Err("в комплекте нет age-keygen.exe (" + kit + ")"); kitOk = false; }
            if (!File.Exists(zstdExe) && !HasEmbedded("zstd.exe")) { Log.Err("в комплекте нет zstd.exe (" + kit + ")"); kitOk = false; }
            string pfxPath = Path.Combine(kit, ps.ClientPfx);
            // pfx удаляется после импорта (ТЗ §2) — при повторном запуске его нет:
            // это не неполный комплект, если сертификат уже в LocalMachine\My.
            string existingThumb = File.Exists(pfxPath) ? null : FindImportedCertThumb(ps.BaseId);
            if (!File.Exists(pfxPath) && existingThumb == null) { Log.Err("в комплекте нет " + ps.ClientPfx + " (" + kit + ") — mTLS-сертификат, и ранее импортированного сертификата CN=" + ps.BaseId + " не найдено"); kitOk = false; }
            else if (existingThumb != null) Log.Skip(ps.ClientPfx + " уже импортирован ранее (CN=" + ps.BaseId + ", LocalMachine\\My)");
            if (!kitOk)
            {
                Log.Fix("комплект неполный: положите рядом с setup exe файлы packet-agent.exe, age.exe, age-keygen.exe, zstd.exe, " +
                        ps.ClientPfx + " из поставки (возможно, их удалил антивирус — проверьте карантин)");
                return Program.EXIT_PREREQ;
            }
            // --version проверяем у файлов комплекта; вшитые — после извлечения в шаге 4.
            if (File.Exists(zstdExe) && !RunsOk(zstdExe, "--version", "zstd")) kitOk = false;
            if (File.Exists(ageExe) && !RunsOk(ageExe, "--version", "age")) kitOk = false;
            if (!kitOk)
            {
                Log.Fix("комплект неполный или файлы заблокированы антивирусом — переустановите комплект");
                return Program.EXIT_PREREQ;
            }
            if (File.Exists(agentExe)) RunsOk(agentExe, "--version", "packet-agent");   // диагностика в лог, не стоп
            Log.Ok("служебные программы проверены");

            // ---------- 2. защищённое соединение (клиентский сертификат)
            Log.Step(2, 6, "Защищённое соединение (сертификат клиента)");
            string thumbprint = Ctx.DryRun ? null
                : (File.Exists(pfxPath) ? ImportClientCert(pfxPath, ps.ClientPfxPassword) : existingThumb);
            if (!Ctx.DryRun && thumbprint == null)
            {
                Log.Fix("проверьте client_pfx_password в packet-setup.json и что pfx не битый");
                return Program.EXIT_PREREQ;
            }
            if (Ctx.DryRun) Log.Sim("импортировал бы " + ps.ClientPfx + " в LocalMachine\\My, права закрытого ключа — SYSTEM");
            else Log.Ok("защищённое соединение настроено");

            // ---------- 3. префлайт связи, чтения базы и места
            Log.Step(3, 6, "Проверка связи и чтения базы");
            if (!Ctx.DryRun && !HealthOk(ps.ReceiverUrl, thumbprint))
            {
                Log.Fix("проверьте, что с этого компьютера разрешён исходящий интернет (443/TCP) " +
                        "и связь не режется антивирусом/прокси");
                return Program.EXIT_PREREQ;
            }
            if (Ctx.DryRun) Log.Sim("проверил бы https-префлайт приёмника с клиентским сертификатом");

            // Живая проба ДАННЫХ: /health приёмника и $metadata отвечают и при
            // ПУСТОМ составе OData (ложный зелёный smoke 07.08). Читаем первую
            // сущность состава теми же кредами, что пойдут в agent.ini.
            string probeUser = string.IsNullOrEmpty(o.ReaderUser) ? "ai_reader" : o.ReaderUser;
            // Пользователь-читатель: при наличии админских кредов и COM установщик
            // создаёт его САМ (решение владельца 08.08); ручная инструкция — запасной
            // путь. Пробу чтения гоняем, пока не получится. Автоматику не донимаем.
            string probeDetail = "";
            // Имя базы для человека: прежде всего — как в стартовом окне 1С (ibases.v8i),
            // иначе имя каталога/Ref (прогон 08.08: путь вместо имени путал с другой базой).
            string baseName = !string.IsNullOrEmpty(o.BaseName) ? o.BaseName
                            : (bref == null ? null : bref.Title);
            string baseTitle = string.IsNullOrEmpty(baseName) ? "эта база" : ("«" + baseName + "»");
            if (!o.Unattended && !Console.IsInputRedirected && !Ctx.DryRun)
            {
                // Подсказка прав — под ЭТУ базу (решение владельца 08.08): в БП профиль
                // «Только просмотр» поставляется, в УТ/КА — нет; текст должен идти по
                // факту базы, а не ветвиться. Один COM-запрос, кэшируем на весь гейт.
                string rightsState = Steps.ReaderRightsState(plat, bref, o.AdminUser, o.AdminPassword);
                bool rightsFixTried = false;
                bool readerPwdAuto = false;   // пароль сгенерировали мы — не переспрашивать в цикле
                bool gateDone = false;        // автосоздание + проба уже зелёные
                bool readerKnown = false;     // читатель точно есть — инструкция без шагов создания
                // Сначала диагностика и предложение создать читателя САМИ (решение
                // владельца 08.08). До прогона 08.08 инструкция «создайте сами» шла
                // первой и читалась как «программа ничего не делает».
                if (plat != null && plat.HasCom && !string.IsNullOrEmpty(o.AdminUser))
                {
                    string diag0 = DiagnoseReader(plat, bref, o.AdminUser, o.AdminPassword, probeUser, baseTitle, false);
                    readerKnown = (diag0 == "FOUND");
                    if (diag0 == "NOTFOUND" &&
                        OfferAndCreateReader(plat, bref, o, probeUser, odataUrl,
                                             ref rightsFixTried, ref readerPwdAuto, out probeDetail))
                        gateDone = true;
                }
                if (!gateDone)
                {
                Console.WriteLine();
                if (readerKnown)
                {
                    Console.WriteLine("       Читатель «" + probeUser + "» в базе " + baseTitle + " уже есть —");
                    Console.WriteLine("       осталось подтвердить пароль и права ТОЛЬКО на чтение:");
                    Console.WriteLine("         (если его создавала эта программа раньше — пароль никто не знает:");
                    Console.WriteLine("          введите любой, после ошибки я предложу задать новый автоматически)");
                    PrintRightsHint(probeUser, rightsState, "         ");
                }
                else
                {
                Console.WriteLine("       НУЖЕН ПОЛЬЗОВАТЕЛЬ-ЧИТАТЕЛЬ в 1С (единственный ручной шаг):");
                Console.WriteLine("         1) откройте 1С:Предприятие базы " + baseTitle + " под администратором;");
                if (string.IsNullOrEmpty(o.BaseName) && bref != null && bref.IsFile)
                    Console.WriteLine("            (этой базы нет в стартовом списке 1С — добавьте её: в окне запуска кнопка «Добавить» → каталог " + bref.Dir + ")");
                Console.WriteLine("         2) раздел «Администрирование» (в УТ — «НСИ и администрирование») →");
                Console.WriteLine("            Настройки пользователей и прав → Пользователи;");
                Console.WriteLine("         3) создайте пользователя «" + probeUser + "», задайте пароль;");
                Console.WriteLine("            ОБЯЗАТЕЛЬНО: галка «Вход в приложение разрешён» (без неё 1С не создаёт");
                Console.WriteLine("            пользователя базы — запись остаётся только в справочнике) + «Записать и закрыть»;");
                PrintRightsHint(probeUser, rightsState, "         ");
                Console.WriteLine("         5) вернитесь сюда.");
                }
                while (true)
                {
                    // Без этого вопроса проба шла с пустым паролем и крутила цикл
                    // вхолостую (прогон владельца 07.08). Пароль, сгенерированный при
                    // автосоздании, не переспрашиваем — иначе он затирался вводом.
                    if (!readerPwdAuto)
                    {
                        o.ReaderPassword = Win.ReadPassword("Пароль пользователя «" + probeUser + "» (пусто — если без пароля)").Trim();
                        Log.AddSecret(o.ReaderPassword);
                    }
                    Console.WriteLine("       Проверяю доступ к базе… (может занять до минуты)");
                    if (Steps.ProbeDataRead(odataUrl, probeUser, o.ReaderPassword, out probeDetail))
                    { Log.Ok("читатель проверен: чтение базы работает"); Log.File("проба: " + probeDetail); break; }
                    Console.WriteLine("       Пока не читается: " + probeDetail);
                    Log.File("проба чтения («" + probeUser + "»): " + probeDetail);
                    Console.WriteLine("       Проверьте: пароль (раскладка RU/EN!), профиль «Только просмотр», что состав OData задан,");
                    Console.WriteLine("       и что выбрана ИМЕННО та база, для которой выдан комплект («" + ps.BaseId + "»).");
                    // «Нет прав» — подсказка строго под эту базу (см. PrintRightsHint).
                    if (probeDetail.IndexOf("НЕТ ПРАВ", StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        if (rightsState == null && !string.IsNullOrEmpty(o.AdminUser))
                            rightsState = Steps.ReaderRightsState(plat, bref, o.AdminUser, o.AdminPassword);
                        // Вариант А (решение владельца 08.08): пробуем назначить права САМИ
                        // один раз за прогон — ручной рецепт на сотни ролей непригоден.
                        if (!rightsFixTried && !string.IsNullOrEmpty(o.AdminUser) && plat != null && plat.HasCom)
                        {
                            rightsFixTried = true;
                            Console.WriteLine("       Пробую назначить права сам (профиль/группа «Только просмотр»)…");
                            string fixDetail;
                            if (Steps.EnsureReaderRights(plat, bref, o.AdminUser, o.AdminPassword, probeUser, out fixDetail))
                            {
                                Log.File("права читателю: " + fixDetail);
                                Console.WriteLine("       Сделано: " + fixDetail);
                                Console.WriteLine("       Проверяю чтение ещё раз…");
                                if (Steps.ProbeDataRead(odataUrl, probeUser, o.ReaderPassword, out probeDetail))
                                { Log.Ok("читатель проверен: чтение базы работает"); Log.File("проба: " + probeDetail); break; }
                                Console.WriteLine("       Пока не читается: " + probeDetail);
                                Console.WriteLine("       (права могут применяться до минуты — нажмите Enter для повторной проверки)");
                            }
                            else
                            {
                                Console.WriteLine("       Не смог назначить сам: " + fixDetail);
                                PrintRightsHint(probeUser, rightsState, "       ");
                            }
                        }
                        else PrintRightsHint(probeUser, rightsState, "       ");
                    }
                    // Точная диагностика 401 через COM (прогон владельца 08.08: читатель
                    // был создан в ДРУГОЙ базе — в списке запуска 1С открывалась не та).
                    // OData на 401 не различает «нет пользователя» и «неверный пароль»,
                    // а COM по админским кредам — различает. Когда кредов нет (--skip-scope)
                    // админских кредов нет — тогда диагностика по клавише D ниже.
                    bool is401 = probeDetail.IndexOf("не авторизуется", StringComparison.OrdinalIgnoreCase) >= 0;
                    if (is401 && plat != null && plat.HasCom && !string.IsNullOrEmpty(o.AdminUser))
                    {
                        string diag = DiagnoseReader(plat, bref, o.AdminUser, o.AdminPassword, probeUser, baseTitle);
                        // Автосоздание читателя (решение владельца 08.08): описание + Enter.
                        if (diag == "NOTFOUND" &&
                            OfferAndCreateReader(plat, bref, o, probeUser, odataUrl,
                                                 ref rightsFixTried, ref readerPwdAuto, out probeDetail))
                            break;
                        // Читатель есть, но пароль не подходит: если его создавала эта
                        // программа раньше — пароль случайный и неизвестен никому
                        // (прогон 08.08: цикл «введите пароль» был бесполезен).
                        if (diag == "FOUND" &&
                            OfferResetReaderPassword(plat, bref, o, probeUser, odataUrl,
                                                     ref readerPwdAuto, out probeDetail))
                            break;
                    }
                    Console.Write("       Enter — проверить ещё раз, D — найти причину автоматически, Q — прервать: ");
                    string ans = (Console.ReadLine() ?? "").Trim();
                    if (string.Equals(ans, "q", StringComparison.OrdinalIgnoreCase))
                    { Log.Err("прервано пользователем (читатель не подтверждён)"); return Program.EXIT_PREREQ; }
                    if (string.Equals(ans, "d", StringComparison.OrdinalIgnoreCase))
                    {
                        if (plat == null || !plat.HasCom) { Console.WriteLine("       Диагностика недоступна: нет COM-коннектора 1С."); continue; }
                        if (string.IsNullOrEmpty(o.AdminUser))
                        {
                            Console.Write("       Пользователь 1С с полными правами: ");
                            o.AdminUser = (Console.ReadLine() ?? "").Trim();
                            if (o.AdminUser.Length == 0) continue;
                        }
                        o.AdminPassword = Win.ReadPassword("Пароль пользователя " + o.AdminUser + " (ввод скрыт)");
                        Log.AddSecret(o.AdminPassword);
                        DiagnoseReader(plat, bref, o.AdminUser, o.AdminPassword, probeUser, baseTitle);
                    }
                }
                } // !gateDone
            }
            if (!Ctx.DryRun && probeDetail.Length == 0)
            {
                Log.Info("проверяю чтение базы (первая проба может идти до минуты)…");
                if (!Steps.ProbeDataRead(odataUrl, probeUser, o.ReaderPassword, out probeDetail))
                {
                    Log.Err("данные базы не читаются: " + probeDetail);
                    Log.Fix("задайте состав OData и проверьте права пользователя-читателя («" + probeUser + "»)");
                    return Program.EXIT_PREREQ;
                }
            }
            if (!Ctx.DryRun && probeDetail.Length > 0) { Log.Ok("чтение базы работает"); Log.File("проба данных: " + probeDetail); }

            string packetDir = string.IsNullOrEmpty(o.PacketDir) ? @"C:\1c\packet" : o.PacketDir;            string dataDir = Path.Combine(packetDir, "data");
            if (!DiskOk(bref, packetDir)) return Program.EXIT_PREREQ;

            // ---------- 4. установка файлов и agent.ini
            Log.Step(4, 6, "Установка агента в " + packetDir);
            if (Ctx.DryRun)
            {
                Log.Sim("скопировал бы packet-agent.exe, age.exe, age-keygen.exe, zstd.exe в " + packetDir);
                Log.Sim("записал бы agent.ini (база «" + ps.BaseId + "», права — только администраторам и SYSTEM)");
            }
            else if (!StopAgent() || !InstallFiles(kit, packetDir, dataDir, ps, o, odataUrl, thumbprint))
                return Program.EXIT_PACKET;
            else if (File.Exists(pfxPath))
            {
                // pfx с паролем в открытом виде больше не нужен: сертификат в
                // LocalMachine\My, отпечаток — в agent.ini (ТЗ §2).
                try { File.Delete(pfxPath); Log.File(ps.ClientPfx + " удалён после импорта"); }
                catch (Exception e) { Log.Warn("не удалось удалить " + pfxPath + ": " + e.Message); }
            }

            // ---------- 5. автозапуск (планировщик, SYSTEM)
            Log.Step(5, 6, "Автозапуск агента (планировщик задач)");
            if (Ctx.DryRun)
                Log.Sim("создал бы задачи «" + TaskName + "» (при старте системы) и «" + WatchdogName + "» (каждые 5 мин) под SYSTEM");
            else if (!EnsureTasks(packetDir))
                return Program.EXIT_PACKET;

            // ---------- 6. пробная посылка (данные, не «запустилось»)
            Log.Step(6, 6, "Пробная посылка (подтверждение доставки приёмником)");
            // Повторная установка: seq комплекта уже израсходован прежним каналом —
            // smoke упирается в stale_seq, а агент лечит сам (resync полной заливкой,
            // решение владельца 07.08). Поэтому при живом state.json довозку доверяем
            // демону, а не дублируем посылку.
            string stateFile = Path.Combine(dataDir, "state.json");
            if (!Ctx.DryRun && File.Exists(stateFile))
            {
                Log.Skip("повторная установка: канал уже доказан прежним smoke (есть " + stateFile + ") — довозка штатным демоном");
                WipeKitSecrets(kit, setupPath, ps);
                Installed = true;
                return Program.EXIT_OK;
            }
            if (Ctx.DryRun)
            {
                Log.Sim("запустил бы packet-agent.exe --smoke и ждал бы verified от приёмника");
                Log.Ok("блок агента: префлайт пройден (режим проверки — ничего не менялось)");
                return Program.EXIT_OK;
            }
            bool smoked = Smoke(packetDir);
            if (smoked) { WipeKitSecrets(kit, setupPath, ps); Installed = true; }
            return smoked ? Program.EXIT_OK : Program.EXIT_PACKET;
        }

        // Секреты комплекта после установки на машине не нужны: токен и пароль pfx
        // живут в agent.ini под ACL (решение владельца 07.08). Стираем: сам
        // packet-setup.json и остатки клиентского сертификата (pfx/crt/key).
        static void WipeKitSecrets(string kit, string setupPath, PacketSetup ps)
        {
            try
            {
                if (File.Exists(setupPath))
                {
                    File.Delete(setupPath);
                    Log.File("packet-setup.json удалён (токен теперь только в agent.ini под ACL)");
                }
            }
            catch (Exception e) { Log.Warn("не удалось удалить packet-setup.json: " + e.Message); }
            string[] names = { ps.ClientPfx, "client.crt", "client-key.pem" };
            for (int i = 0; i < names.Length; i++)
            {
                try
                {
                    string p = Path.Combine(kit, names[i]);
                    if (File.Exists(p)) { File.Delete(p); Log.File(names[i] + " удалён после импорта"); }
                }
                catch (Exception e) { Log.Warn("не удалось удалить " + names[i] + ": " + e.Message); }
            }
        }

        // ============================================================ префлайт-составляющие
        static bool RunsOk(string exe, string args, string label)
        {
            ExecResult r = Proc.Run(exe, args, 30000, Proc.Oem, null, null);
            // В консоль — одна сводка от вызывающего; детали версий — в лог (для нас).
            if (r.Ok) { Log.File(label + " запускается: " + FirstLine(r.StdOut)); return true; }
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

        // ============================================================ вшитые ресурсы (один exe)
        // build.cmd кладёт бинарии комплекта ресурсами (каталог embed\ рядом с
        // build.cmd): тогда установщик — один файл, а бинарии извлекаются при
        // установке. Файл рядом с exe приоритетнее ресурса (обновление агента
        // без пересборки установщика).
        static bool HasEmbedded(string name)
        {
            string[] names = System.Reflection.Assembly.GetExecutingAssembly().GetManifestResourceNames();
            for (int i = 0; i < names.Length; i++)
                if (string.Equals(names[i], name, StringComparison.OrdinalIgnoreCase)) return true;
            return false;
        }

        static bool ExtractEmbedded(string name, string dest)
        {
            try
            {
                using (Stream s = System.Reflection.Assembly.GetExecutingAssembly().GetManifestResourceStream(name))
                {
                    if (s == null) return false;
                    using (FileStream f = File.Create(dest))
                        s.CopyTo(f);
                }
                return true;
            }
            catch (Exception e)
            {
                Log.Err("не извлекается вшитый " + name + ": " + e.Message);
                return false;
            }
        }

        // ============================================================ mTLS: клиентский сертификат
        // Импорт client.pfx в LocalMachine\My (ТЗ §2). Возвращает отпечаток или null.
        static string ImportClientCert(string pfxPath, string password)
        {
            try
            {
                X509Certificate2 cert = new X509Certificate2(pfxPath, password,
                    X509KeyStorageFlags.MachineKeySet | X509KeyStorageFlags.PersistKeySet);
                X509Store store = new X509Store(StoreName.My, StoreLocation.LocalMachine);
                store.Open(OpenFlags.ReadWrite);
                store.Add(cert);
                store.Close();
                GrantKeyToSystem(cert);
                Log.File("сертификат импортирован в LocalMachine\\My (" + cert.SubjectName.Name +
                         ", отпечаток " + cert.Thumbprint + ")");
                return cert.Thumbprint;
            }
            catch (Exception e)
            {
                Log.Err("импорт " + pfxPath + " не удался: " + e.Message);
                return null;
            }
        }

        // Агент работает под SYSTEM (планировщик) — закрытый ключ в машинном
        // контейнере обязан читаться SYSTEM. По умолчанию у MachineKeys SYSTEM и
        // так имеет полный доступ, но правило добавляем явно — поведение не должно
        // зависеть от умолчаний ОС (ТЗ §2).
        static void GrantKeyToSystem(X509Certificate2 cert)
        {
            try
            {
                RSACryptoServiceProvider rsa = cert.PrivateKey as RSACryptoServiceProvider;
                if (rsa == null) { Log.Warn("закрытый ключ не CSP (CNG) — права SYSTEM проверьте вручную"); return; }
                string keyFile = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
                    @"Microsoft\Crypto\RSA\MachineKeys\" + rsa.CspKeyContainerInfo.UniqueKeyContainerName);
                if (!File.Exists(keyFile)) { Log.Warn("файл закрытого ключа не найден: " + keyFile); return; }
                FileSecurity fs = File.GetAccessControl(keyFile);
                fs.AddAccessRule(new FileSystemAccessRule(
                    new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null),
                    FileSystemRights.Read, AccessControlType.Allow));
                File.SetAccessControl(keyFile, fs);
                Log.File("закрытому ключу выдано чтение для SYSTEM");
            }
            catch (Exception e) { Log.Warn("ACL закрытого ключа не выданы: " + e.Message); }
        }

        // Сертификат базы уже в LocalMachine\My (pfx удалён после прошлой установки —
        // повторный запуск обязан работать без pfx).
        static string FindImportedCertThumb(string baseId)
        {
            try
            {
                X509Store store = new X509Store(StoreName.My, StoreLocation.LocalMachine);
                store.Open(OpenFlags.ReadOnly);
                try
                {
                    foreach (X509Certificate2 c in store.Certificates)
                        if (c.HasPrivateKey && string.Equals(c.SubjectName.Name, "CN=" + baseId, StringComparison.OrdinalIgnoreCase))
                            return c.Thumbprint;
                }
                finally { store.Close(); }
            }
            catch { }
            return null;
        }

        static X509Certificate2 FindClientCert(string thumbprint)
        {
            string norm = (thumbprint ?? "").Replace(" ", "").ToUpperInvariant();
            if (norm.Length == 0) return null;
            StoreLocation[] locs = { StoreLocation.LocalMachine, StoreLocation.CurrentUser };
            for (int i = 0; i < locs.Length; i++)
            {
                X509Store store = new X509Store(StoreName.My, locs[i]);
                try
                {
                    store.Open(OpenFlags.ReadOnly | OpenFlags.OpenExistingOnly);
                    X509Certificate2Collection found = store.Certificates.Find(
                        X509FindType.FindByThumbprint, norm, false);
                    if (found.Count > 0) return found[0];
                }
                catch { }
                finally { store.Close(); }
            }
            return null;
        }

        // Исходящий HTTPS на приёмник: TLS handshake С КЛИЕНТСКИМ СЕРТИФИКАТОМ (mTLS,
        // контракт §8) + GET /health -> packet-server-ok.
        static bool HealthOk(string receiverUrl, string thumbprint)
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
                X509Certificate2 cert = FindClientCert(thumbprint);
                if (cert == null)
                {
                    Log.Err("клиентский сертификат (отпечаток " + thumbprint + ") не найден в хранилище — mTLS невозможен");
                    return false;
                }
                req.ClientCertificates.Add(cert);
                using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                using (StreamReader sr = new StreamReader(resp.GetResponseStream(), Encoding.UTF8))
                {
                    string body = sr.ReadToEnd();
                    if ((int)resp.StatusCode == 200 && body.IndexOf("packet-server-ok") >= 0)
                    {
                        Log.Ok("связь с сервером есть");
                        Log.File("приёмник отвечает: " + url + " -> packet-server-ok (mTLS)");
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
                {
                    Log.Err("нет связи с приёмником: " + we.Message);
                    if (we.Message.IndexOf("SSL/TLS", StringComparison.OrdinalIgnoreCase) >= 0)
                        Log.Fix("TLS-рукопожатие отвергнуто: релей требует клиентский сертификат (mTLS) — проверьте импорт pfx (шаг 2)");
                }
                return false;
            }
            catch (Exception e)
            {
                Log.Err("нет связи с приёмником: " + e.Message);
                return false;
            }
        }

        // Место под данные агента: очередь чанков ≈ размер базы сжатой + индекс версий.
        // COM-диагностика 401 гейта читателя: OData не различает «нет пользователя»
        // и «неверный пароль», а COM по админским кредам — различает (прогоны 08.08).
        // Возвращает "NOTFOUND" / "FOUND" / null (определить не удалось).
        static string DiagnoseReader(Platform plat, BaseRef bref, string adminUser, string adminPwd,
                                     string reader, string baseTitle)
        {
            return DiagnoseReader(plat, bref, adminUser, adminPwd, reader, baseTitle, true);
        }

        // probeFailed=true — вызов после неудачной пробы чтения (тексты про пароль/другую базу);
        // false — упреждающая проверка до инструкций (нейтральные тексты).
        static string DiagnoseReader(Platform plat, BaseRef bref, string adminUser, string adminPwd,
                                     string reader, string baseTitle, bool probeFailed)
        {
            Console.WriteLine("       Смотрю пользователей базы " + baseTitle + "…");
            int curD, addedD; string rolesD;
            if (!Steps.SetOdataComposition(plat, bref, adminUser, adminPwd,
                                           new List<string>(), false, reader, out curD, out addedD, out rolesD))
            { Log.File("диагностика читателя: COM-проверка не удалась (см. ошибку выше)"); return null; }
            if (rolesD == "__NOTFOUND__")
            {
                if (probeFailed)
                {
                    Console.WriteLine("       Диагностика: пользователя «" + reader + "» в базе " + baseTitle +
                                      " НЕТ — вероятно, он создан в другой базе (в списке запуска 1С легко открыть не ту).");
                    Console.WriteLine("       Важно: запись в справочнике «Пользователи» в 1С:Предприятие — НЕ то же самое,");
                    Console.WriteLine("       что пользователь информационной базы. Точный список — в Конфигураторе:");
                    Console.WriteLine("       Администрирование → Пользователи.");
                }
                else Console.WriteLine("       Пользователя «" + reader + "» в базе " + baseTitle + " пока нет.");
                Log.File("диагностика: «" + reader + "» в базе не найден");
                return "NOTFOUND";
            }
            if (rolesD != null)
            {
                if (probeFailed)
                {
                    Console.WriteLine("       Диагностика: пользователь «" + reader + "» в базе ЕСТЬ — значит, не подходит ПАРОЛЬ");
                    Console.WriteLine("       (проверьте раскладку клавиатуры RU/EN) или снята галка «Аутентификация 1С:Предприятия».");
                }
                else Console.WriteLine("       Пользователь «" + reader + "» в базе есть.");
                Log.File("диагностика: «" + reader + "» найден, роли: " + rolesD);
                return "FOUND";
            }
            return null;
        }

        // Автосоздание читателя (решение владельца 08.08; 09.08 — единственный путь,
        // «сделаю сам в 1С» убрано: человеку ничего не поручаем). Описание + Enter,
        // затем создание пользователя, права «Только просмотр» и проба чтения.
        // true — гейт пройден (проба зелёная); false — не вышло (дальше цикл с рецептами).
        static bool OfferAndCreateReader(Platform plat, BaseRef bref, Opts o, string probeUser,
                                         string odataUrl, ref bool rightsFixTried, ref bool readerPwdAuto,
                                         out string probeDetail)
        {
            probeDetail = "";
            Console.WriteLine();
            Console.WriteLine("       Создам пользователя сам. Что будет сделано:");
            Console.WriteLine("       - пользователь 1С «" + probeUser + "» ТОЛЬКО для чтения, скрыт из окна входа;");
            Console.WriteLine("       - пароль — случайный, его не будет знать никто: он останется только");
            Console.WriteLine("         в защищённых настройках агента на этом компьютере;");
            Console.WriteLine("       - профиль «Только просмотр» и группа доступа «Чтение (AI)» с этим пользователем —");
            Console.WriteLine("         если их нет, создам сам; права строго только на чтение.");
            Console.Write("       Enter — продолжить: ");
            Console.ReadLine();
            o.ReaderPassword = GenPassword();
            Log.AddSecret(o.ReaderPassword);
            string cd;
            if (!Steps.CreateReaderUser(plat, bref, o.AdminUser, o.AdminPassword, probeUser, o.ReaderPassword, out cd))
            { Console.WriteLine("       Не смог создать: " + cd); Log.File("автосоздание читателя не удалось: " + cd); return false; }
            readerPwdAuto = true;
            Log.File("читатель создан установщиком: " + cd);
            Console.WriteLine("       " + cd);
            string rd;
            if (Steps.EnsureReaderRights(plat, bref, o.AdminUser, o.AdminPassword, probeUser, out rd))
            { Log.File("права читателю: " + rd); Console.WriteLine("       " + rd); rightsFixTried = true; }
            else Console.WriteLine("       права пока не назначены: " + rd);
            Console.WriteLine("       Проверяю чтение…");
            if (Steps.ProbeDataRead(odataUrl, probeUser, o.ReaderPassword, out probeDetail))
            { Log.Ok("читатель проверен: чтение базы работает"); Log.File("проба: " + probeDetail); return true; }
            Console.WriteLine("       Пока не читается: " + probeDetail + " (Enter — проверить ещё раз)");
            return false;
        }

        // Сброс пароля читателя (прогон 08.08): читатель, созданный прошлым запуском
        // этой программы, имеет случайный пароль, который никто не знает — цикл
        // «введите пароль» в этом случае бесполезен. Enter — задаём новый сами.
        static bool OfferResetReaderPassword(Platform plat, BaseRef bref, Opts o, string probeUser,
                                             string odataUrl, ref bool readerPwdAuto, out string probeDetail)
        {
            probeDetail = "";
            Console.WriteLine();
            Console.WriteLine("       Если «" + probeUser + "» создавала эта программа прошлым запуском —");
            Console.WriteLine("       пароль случайный, его никто не знает. Задам НОВЫЙ случайный:");
            Console.WriteLine("       он останется только в защищённых настройках агента на этом компьютере.");
            Console.Write("       Enter — продолжить: ");
            Console.ReadLine();
            string np = GenPassword();
            string rd;
            if (!Steps.ResetReaderPassword(plat, bref, o.AdminUser, o.AdminPassword, probeUser, np, out rd))
            { Console.WriteLine("       Не смог задать пароль: " + rd); Log.File("сброс пароля читателя не удался: " + rd); return false; }
            o.ReaderPassword = np;
            readerPwdAuto = true;
            Log.AddSecret(np);
            Log.File("сброс пароля читателя: " + rd);
            Console.WriteLine("       Новый пароль задан. Проверяю чтение…");
            if (Steps.ProbeDataRead(odataUrl, probeUser, o.ReaderPassword, out probeDetail))
            { Log.Ok("читатель проверен: чтение базы работает"); Log.File("проба: " + probeDetail); return true; }
            Console.WriteLine("       Пока не читается: " + probeDetail + " (Enter — проверить ещё раз)");
            return false;
        }

        // Случайный пароль читателя (решение владельца 08.08): не знает никто,
        // живёт только в agent.ini под ACL. 36 hex-символов из крипто-ГСЧ.
        static string GenPassword()
        {
            byte[] buf = new byte[18];
            using (var rng = new RNGCryptoServiceProvider()) rng.GetBytes(buf);
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < buf.Length; i++) sb.Append(buf[i].ToString("x2"));
            return sb.ToString();
        }

        // Подсказка прав под конкретную базу (state — Steps.ReaderRightsState,
        // решение владельца 08.08: различия конфигураций определяем, а не перечисляем).
        static void PrintRightsHint(string reader, string state, string pad)
        {
            if (state == "GROUP")
            {
                Console.WriteLine(pad + "4) права ТОЛЬКО на чтение: группа с профилем «Только просмотр» в базе ЕСТЬ —");
                Console.WriteLine(pad + "   карточка пользователя → вкладка «Права доступа» → «Включить в группу» → выберите её;");
            }
            else if (state == "PROFILE")
            {
                Console.WriteLine(pad + "4) права ТОЛЬКО на чтение: профиль «Только просмотр» в базе ЕСТЬ — создайте группу:");
                Console.WriteLine(pad + "   «Группы доступа» → Создать → Профиль «Только просмотр» → в таблицу");
                Console.WriteLine(pad + "   «Пользователи» добавьте «" + reader + "» → «Записать и закрыть»;");
            }
            else if (state == "NONE")
            {
                Console.WriteLine(pad + "4) права ТОЛЬКО на чтение. Готового профиля чтения в этой конфигурации НЕТ");
                Console.WriteLine(pad + "   (Управление торговлей / Комплексная автоматизация не поставляют его) —");
                Console.WriteLine(pad + "   создаём сами, один раз на базу:");
                Console.WriteLine(pad + "   а) «Профили групп доступа» → Создать → в поле «Наименование» напишите:");
                Console.WriteLine(pad + "      Только просмотр   (это НАЗВАНИЕ нового профиля — готового пункта с таким");
                Console.WriteLine(pad + "      именем в списке нет, искать его не надо);");
                Console.WriteLine(pad + "   б) ниже — длинный список ролей с галочками. Вручную не ставьте: над списком");
                Console.WriteLine(pad + "      есть ПОИСК. Введите слово  Чтение  → выделите все найденные (Ctrl+A) →");
                Console.WriteLine(pad + "      «Включить выделенные роли». Повторите для слов: Базовые права, Запуск,");
                Console.WriteLine(pad + "      Использование, Отчеты, Подсистема, Просмотр, Раздел;");
                Console.WriteLine(pad + "   в) «Записать и закрыть»;");
                Console.WriteLine(pad + "   г) «Группы доступа» → Создать → поле «Профиль» = Только просмотр → в таблицу");
                Console.WriteLine(pad + "      «Пользователи» добавьте «" + reader + "» → «Записать и закрыть»;");
            }
            else
            {
                Console.WriteLine(pad + "4) права ТОЛЬКО на чтение (без них пользователь входит, но данных не видит):");
                Console.WriteLine(pad + "   карточка пользователя → «Права доступа» → «Включить в группу» с профилем");
                Console.WriteLine(pad + "   «Только просмотр»; нет группы — создайте её с этим профилем; нет и профиля");
                Console.WriteLine(pad + "   (УТ/КА) — «Профили групп доступа» → Создать: роли поиском по словам");
                Console.WriteLine(pad + "   Базовые права, Запуск, Использование, Отчеты, Подсистема, Просмотр, Раздел, Чтение;");
            }
        }

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
                                 PacketSetup ps, Opts o, string odataUrl, string thumbprint)
        {
            try
            {
                Directory.CreateDirectory(dataDir);
                string[] names = { "packet-agent.exe", "zstd.exe", "age.exe", "age-keygen.exe" };
                for (int i = 0; i < names.Length; i++)
                {
                    string srcExe = Path.Combine(kit, names[i]);
                    string dstExe = Path.Combine(packetDir, names[i]);
                    if (File.Exists(srcExe))
                    {
                        File.Copy(srcExe, dstExe, true);
                        Log.File("установлен " + names[i]);
                    }
                    else if (HasEmbedded(names[i]))
                    {
                        if (!ExtractEmbedded(names[i], dstExe)) return false;
                        // вшитый — проверяем запуск уже на месте (префлайт шага 1 его не видел)
                        if (!RunsOk(dstExe, "--version", names[i])) return false;
                    }
                    else { Log.Skip(names[i] + " нет ни в комплекте, ни вшит — не копирую"); continue; }
                }
                Log.Ok("агент установлен в " + packetDir);
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
            sb.AppendLine("# Агент пакетного транспорта 1С -> сервер аналитики");
            sb.AppendLine("# Создан setup-1c-odata " + Ctx.ToolVersion + " " + DateTime.Now.ToString("yyyy-MM-dd HH:mm"));
            sb.AppendLine("# Права на этот файл: только администраторы и SYSTEM (внутри — токен и пароль читателя).");
            sb.AppendLine("base_id=" + ps.BaseId);
            sb.AppendLine("receiver_url=" + ps.ReceiverUrl);
            sb.AppendLine("token=" + ps.Token);
            sb.AppendLine("recipient_pubkey=" + ps.RecipientPubkey);
            sb.AppendLine("client_cert_thumbprint=" + thumbprint);   // mTLS на релее (контракт §8)
            sb.AppendLine("odata_url=" + odataUrl.TrimEnd('/'));
            sb.AppendLine("odata_user=" + reader);
            sb.AppendLine("odata_password=" + (o.ReaderPassword == null ? "" : o.ReaderPassword));
            sb.AppendLine("data_dir=" + dataDir);
            try
            {
                File.WriteAllText(ini, sb.ToString(), new UTF8Encoding(true));
                RestrictToAdmins(ini);
                Log.Ok("настройки записаны (доступ — только администраторам и службе)");
                Log.File("записан " + ini);
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

        // Перед заменой файлов: живой агент держит packet-agent.exe занятым
        // («файл используется другим процессом» — прогон 07.08). Гасим задачи и
        // процесс; «не запущен» — не ошибка. Прерванный такт не страшен: очередь
        // чанков на диске, довозка штатная (К2).
        static bool StopAgent()
        {
            Proc.Run("schtasks.exe", "/End /TN \"" + TaskName + "\"", 30000, Proc.Oem, null, null);
            Proc.Run("schtasks.exe", "/End /TN \"" + WatchdogName + "\"", 30000, Proc.Oem, null, null);
            ExecResult kill = Proc.Run("taskkill.exe", "/f /im packet-agent.exe", 30000, Proc.Oem, null, null);
            if (kill.Ok) { Log.Info("прежний процесс packet-agent.exe остановлен"); System.Threading.Thread.Sleep(1000); }
            return true;
        }

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
            Log.File("задача «" + TaskName + "»: запуск при старте системы под SYSTEM");
            if (!Schtasks("/Create /F /TN \"" + WatchdogName + "\" /TR \"" + tr + "\" /SC MINUTE /MO 5 /RU SYSTEM /RL HIGHEST"))
                return false;
            Log.File("задача «" + WatchdogName + "»: сторож каждые 5 минут");
            Log.Ok("автозапуск настроен (планировщик задач)");
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
                Log.Ok("проверка доставки пройдена");
                Log.File("доставка подтверждена приёмником: " + FirstLine(r.StdOut));
                Log.Con("Лог агента и его работа — " + Path.Combine(packetDir, "data"));
                return true;
            }
            string tail = r.Tail(4);
            string code = KnownReceiverError(tail);
            // stale_seq: комплект уже работал (seq израсходован) — канал при этом
            // ДОКАЗАН (mTLS+Bearer прошли, приёмник ответил осмысленно), а данные
            // агент зальёт сам полной перезаливкой (решение владельца 07.08).
            // Это не провал установки.
            if (tail.IndexOf("stale_seq", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                Log.Warn("комплект уже использовался (stale_seq) — канал доказан; агент зальёт полную сам (resync)");
                return true;
            }
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
