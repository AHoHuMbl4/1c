// Sys.cs — инфраструктура: лог, запуск процессов, PowerShell, системные проверки.
// C# 5 (компилятор csc.exe из .NET Framework) — БЕЗ интерполяции строк, ?., nameof, out var.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Security.Principal;
using System.Text;
using Microsoft.Win32;

namespace Oc1c
{
    // ---------------------------------------------------------------- контекст
    internal static class Ctx
    {
        public static bool DryRun;              // --check: ничего не менять
        public static bool AssumeYes;           // --yes: без вопросов
        public static bool Changed;             // хоть что-то реально изменено
        public const string ToolVersion = "1.2.0";
    }

    // ---------------------------------------------------------------- результат внешней команды
    internal class ExecResult
    {
        public int ExitCode;
        public string StdOut = "";
        public string StdErr = "";
        public bool TimedOut;
        public bool Ok { get { return !TimedOut && ExitCode == 0; } }
        public string All { get { return (StdOut + Environment.NewLine + StdErr).Trim(); } }
        public string Tail(int n)
        {
            string s = All;
            if (s.Length == 0) return "(пустой вывод)";
            string[] lines = s.Replace("\r\n", "\n").Split('\n');
            int from = Math.Max(0, lines.Length - n);
            return string.Join(" | ", lines, from, lines.Length - from);
        }
    }

    // ---------------------------------------------------------------- лог (консоль + файл)
    internal static class Log
    {
        static StreamWriter _w;
        static readonly List<string> _secrets = new List<string>();
        public static string Path = "";
        public static int Warnings;

        public static void Init(string path)
        {
            try
            {
                string dir = System.IO.Path.GetDirectoryName(path);
                if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir)) Directory.CreateDirectory(dir);
                _w = new StreamWriter(path, true, new UTF8Encoding(true));
                Path = path;
                File("=== setup-1c-odata " + Ctx.ToolVersion + " === " + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"));
            }
            catch (Exception e) { Console.WriteLine("ВНИМАНИЕ: не удалось открыть лог " + path + ": " + e.Message); }
        }

        public static void AddSecret(string s)
        {
            if (!string.IsNullOrEmpty(s) && s.Length >= 3 && !_secrets.Contains(s)) _secrets.Add(s);
        }

        public static string Mask(string s)
        {
            if (s == null) return "";
            for (int i = 0; i < _secrets.Count; i++) s = s.Replace(_secrets[i], "***");
            return s;
        }

        public static void File(string s)
        {
            if (_w == null) return;
            try { _w.WriteLine(DateTime.Now.ToString("HH:mm:ss") + "  " + Mask(s)); _w.Flush(); }
            catch { }
        }

        static void W(string s, ConsoleColor? c)
        {
            if (c.HasValue) { try { Console.ForegroundColor = c.Value; } catch { } }
            Console.WriteLine(s);
            if (c.HasValue) { try { Console.ResetColor(); } catch { } }
            File(s);
        }

        public static void Con(string s) { W(s, null); }
        public static void Ok(string s) { W("       OK    " + s, ConsoleColor.Green); }
        public static void Skip(string s) { W("       ПРОПУСК " + s, ConsoleColor.DarkGray); }
        public static void Info(string s) { W("       -     " + s, null); }
        public static void Warn(string s) { Warnings++; W("       ВНИМАНИЕ " + s, ConsoleColor.Yellow); }
        public static void Err(string s) { W("       ОШИБКА  " + s, ConsoleColor.Red); }
        public static void Fix(string s) { W("       ЧТО ДЕЛАТЬ: " + s, ConsoleColor.Cyan); }
        public static void Sim(string s) { W("       [СИМУЛЯЦИЯ] " + s, ConsoleColor.Magenta); }

        public static void Step(int n, int total, string title)
        {
            W("", null);
            W("[" + n.ToString().PadLeft(2) + "/" + total + "] " + title, ConsoleColor.White);
        }

        public static void Head(string s)
        {
            W("", null);
            W(new string('=', 74), ConsoleColor.DarkCyan);
            W(s, ConsoleColor.Cyan);
            W(new string('=', 74), ConsoleColor.DarkCyan);
        }
    }

    // ---------------------------------------------------------------- запуск внешних программ
    internal static class Proc
    {
        public static Encoding Oem
        {
            get
            {
                try { return Encoding.GetEncoding(System.Globalization.CultureInfo.CurrentCulture.TextInfo.OEMCodePage); }
                catch { return Encoding.Default; }
            }
        }

        public static ExecResult Run(string exe, string args, int timeoutMs, Encoding enc, string workDir, IDictionary<string, string> extraEnv)
        {
            ExecResult r = new ExecResult();
            if (!System.IO.File.Exists(exe) && exe.IndexOf('\\') >= 0)
            {
                r.ExitCode = -2; r.StdErr = "не найден исполняемый файл: " + exe;
                Log.File("RUN-FAIL: " + r.StdErr);
                return r;
            }
            ProcessStartInfo psi = new ProcessStartInfo(exe, args);
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            if (enc != null) { psi.StandardOutputEncoding = enc; psi.StandardErrorEncoding = enc; }
            if (!string.IsNullOrEmpty(workDir)) psi.WorkingDirectory = workDir;
            if (extraEnv != null)
                foreach (KeyValuePair<string, string> kv in extraEnv) psi.EnvironmentVariables[kv.Key] = kv.Value;

            StringBuilder so = new StringBuilder(), se = new StringBuilder();
            Log.File("RUN: \"" + exe + "\" " + Log.Mask(args));
            try
            {
                using (Process p = new Process())
                {
                    p.StartInfo = psi;
                    p.OutputDataReceived += delegate(object s, DataReceivedEventArgs e) { if (e.Data != null) so.AppendLine(e.Data); };
                    p.ErrorDataReceived += delegate(object s, DataReceivedEventArgs e) { if (e.Data != null) se.AppendLine(e.Data); };
                    p.Start();
                    p.BeginOutputReadLine();
                    p.BeginErrorReadLine();
                    if (!p.WaitForExit(timeoutMs))
                    {
                        try { p.Kill(); } catch { }
                        r.TimedOut = true;
                    }
                    else p.WaitForExit();      // дочитать асинхронные буферы
                    r.ExitCode = r.TimedOut ? -1 : p.ExitCode;
                }
            }
            catch (Exception e)
            {
                r.ExitCode = -3; se.AppendLine("исключение при запуске: " + e.Message);
            }
            r.StdOut = so.ToString();
            r.StdErr = se.ToString();
            Log.File("   exit=" + r.ExitCode + (r.TimedOut ? " (ТАЙМАУТ)" : ""));
            if (r.All.Length > 0) Log.File("   вывод: " + Log.Mask(r.All));
            return r;
        }
    }

    // ---------------------------------------------------------------- PowerShell (нужной разрядности)
    internal static class Ps
    {
        public static string Exe(bool want32bit)
        {
            string win = Environment.GetEnvironmentVariable("windir");
            if (string.IsNullOrEmpty(win)) win = @"C:\Windows";
            string sub;
            if (want32bit)
                sub = Environment.Is64BitOperatingSystem ? "SysWOW64" : "System32";
            else
                sub = (Environment.Is64BitProcess || !Environment.Is64BitOperatingSystem) ? "System32" : "Sysnative";
            return System.IO.Path.Combine(win, sub + @"\WindowsPowerShell\v1.0\powershell.exe");
        }

        // Скрипт передаём -EncodedCommand (UTF-16LE base64): не ломается кириллица и не мешает ExecutionPolicy.
        // Секреты — только через переменные окружения (в командной строке их не видно).
        public static ExecResult Run(string script, bool want32bit, int timeoutMs, IDictionary<string, string> env)
        {
            string prelude =
                "$ErrorActionPreference='Stop';" +
                "$ProgressPreference='SilentlyContinue';" +
                "try{[Console]::OutputEncoding=[Text.Encoding]::UTF8}catch{};";
            string b64 = Convert.ToBase64String(Encoding.Unicode.GetBytes(prelude + script));
            return Proc.Run(Exe(want32bit),
                "-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand " + b64,
                timeoutMs, Encoding.UTF8, null, env);
        }
    }

    // ---------------------------------------------------------------- системные проверки
    internal static class Win
    {
        public static bool IsAdmin()
        {
            try
            {
                WindowsIdentity id = WindowsIdentity.GetCurrent();
                WindowsPrincipal p = new WindowsPrincipal(id);
                return p.IsInRole(WindowsBuiltInRole.Administrator);
            }
            catch { return false; }
        }

        // Вид реестра под разрядность ОС: Registry64 на 32-битной Windows не
        // поддержан (бросает) — там правильный вид Default (матрица ОС 07.08).
        public static RegistryView RegView()
        {
            return Environment.Is64BitOperatingSystem ? RegistryView.Registry64 : RegistryView.Default;
        }

        public static string RegStr(string subKey, string name)
        {
            try
            {
                using (RegistryKey k = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegView()).OpenSubKey(subKey))
                {
                    if (k == null) return null;
                    object v = k.GetValue(name);
                    return v == null ? null : v.ToString();
                }
            }
            catch { return null; }
        }

        public static string OsDescription()
        {
            string p = RegStr(@"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "ProductName");
            string b = RegStr(@"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "CurrentBuild");
            string d = RegStr(@"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "DisplayVersion");
            string s = (p == null ? "Windows" : p);
            if (!string.IsNullOrEmpty(d)) s += " " + d;
            if (!string.IsNullOrEmpty(b)) s += " (build " + b + ")";
            return s + (Environment.Is64BitOperatingSystem ? " x64" : " x86");
        }

        public static bool PendingReboot(out string why)
        {
            why = "";
            try
            {
                using (RegistryKey b = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegView()))
                {
                    if (b.OpenSubKey(@"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending") != null)
                    { why = "Component Based Servicing"; return true; }
                    if (b.OpenSubKey(@"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired") != null)
                    { why = "Windows Update"; return true; }
                    using (RegistryKey sm = b.OpenSubKey(@"SYSTEM\CurrentControlSet\Control\Session Manager"))
                    {
                        if (sm != null)
                        {
                            object v = sm.GetValue("PendingFileRenameOperations");
                            if (v != null)
                            {
                                string[] arr = v as string[];
                                if (arr != null && arr.Length > 0) { why = "PendingFileRenameOperations"; return true; }
                            }
                        }
                    }
                }
            }
            catch { }
            return false;
        }

        // Разрядность PE-файла: x86 / x64 — чтобы понять разрядность платформы 1С.
        public static string PeMachine(string file)
        {
            try
            {
                using (FileStream fs = new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                using (BinaryReader br = new BinaryReader(fs))
                {
                    fs.Seek(0x3C, SeekOrigin.Begin);
                    int off = br.ReadInt32();
                    if (off <= 0 || off > fs.Length - 6) return "?";
                    fs.Seek(off, SeekOrigin.Begin);
                    if (br.ReadUInt32() != 0x00004550) return "?";     // сигнатура "PE\0\0"
                    ushort m = br.ReadUInt16();
                    if (m == 0x014c) return "x86";
                    if (m == 0x8664) return "x64";
                    return "0x" + m.ToString("X4");
                }
            }
            catch { return "?"; }
        }

        public static List<string> LocalIPv4()
        {
            List<string> res = new List<string>();
            try
            {
                NetworkInterface[] ifs = NetworkInterface.GetAllNetworkInterfaces();
                for (int i = 0; i < ifs.Length; i++)
                {
                    NetworkInterface ni = ifs[i];
                    if (ni.OperationalStatus != OperationalStatus.Up) continue;
                    if (ni.NetworkInterfaceType == NetworkInterfaceType.Loopback) continue;
                    foreach (UnicastIPAddressInformation ua in ni.GetIPProperties().UnicastAddresses)
                        if (ua.Address.AddressFamily == AddressFamily.InterNetwork)
                            res.Add(ua.Address.ToString() + "  (" + ni.Name + ")");
                }
            }
            catch { }
            return res;
        }

        public static long FreeSpaceMb(string path)
        {
            try
            {
                string root = System.IO.Path.GetPathRoot(System.IO.Path.GetFullPath(path));
                DriveInfo di = new DriveInfo(root);
                return di.AvailableFreeSpace / 1024 / 1024;
            }
            catch { return -1; }
        }

        public static long DirSizeMb(string path)
        {
            try
            {
                long total = 0;
                string[] files = Directory.GetFiles(path, "*", SearchOption.AllDirectories);
                for (int i = 0; i < files.Length; i++)
                {
                    try { total += new FileInfo(files[i]).Length; } catch { }
                }
                return total / 1024 / 1024;
            }
            catch { return -1; }
        }

        // Нагрузка ПК: CPU% и RAM. Через PowerShell (без лишних сборок). -1 = не удалось замерить.
        public static void SampleLoad(out int cpuPct, out long ramFreeMb, out long ramTotalMb)
        {
            cpuPct = -1; ramFreeMb = -1; ramTotalMb = -1;
            string script =
                "$os = Get-CimInstance Win32_OperatingSystem; " +
                "$free = [int]($os.FreePhysicalMemory/1024); $total = [int]($os.TotalVisibleMemorySize/1024); " +
                // Имена счётчиков Get-Counter локализованы (на ru-Windows путь
                // '\Processor(_Total)\% Processor Time' невалиден — разбор 07.08),
                // поэтому CPU берём из CIM — локаленезависимо.
                "$cpu = -1; try { $cpu = [int]((Get-CimInstance Win32_Processor | " +
                "Measure-Object -Property LoadPercentage -Average).Average) } catch {}; " +
                "Write-Output ('LOAD cpu=' + $cpu + ' ram_free_mb=' + $free + ' ram_total_mb=' + $total)";
            ExecResult r = Ps.Run(script, false, 30000, null);
            if (!r.Ok && r.All.IndexOf("LOAD ") < 0) return;
            try
            {
                System.Text.RegularExpressions.Match m = System.Text.RegularExpressions.Regex.Match(
                    r.All, @"LOAD cpu=(-?\d+)\s+ram_free_mb=(-?\d+)\s+ram_total_mb=(-?\d+)");
                if (!m.Success) return;
                cpuPct = int.Parse(m.Groups[1].Value);
                ramFreeMb = long.Parse(m.Groups[2].Value);
                ramTotalMb = long.Parse(m.Groups[3].Value);
            }
            catch { }
        }

        // TCP-проверка: достучимся ли с этой машины до хоста (например Ubuntu-сервер аналитики).
        public static bool TcpReachable(string host, int port, int timeoutMs, out string detail)
        {
            detail = "";
            if (string.IsNullOrEmpty(host)) { detail = "хост не задан"; return false; }
            try
            {
                using (TcpClient c = new TcpClient())
                {
                    IAsyncResult ar = c.BeginConnect(host, port, null, null);
                    if (!ar.AsyncWaitHandle.WaitOne(timeoutMs))
                    {
                        try { c.Close(); } catch { }
                        detail = host + ":" + port + " — нет ответа за " + timeoutMs + " мс";
                        return false;
                    }
                    c.EndConnect(ar);
                    detail = host + ":" + port + " — TCP OK";
                    return true;
                }
            }
            catch (Exception e)
            {
                detail = host + ":" + port + " — " + e.Message;
                return false;
            }
        }

        // Из «192.168.56.42» → «192.168.56.0/24» для правила брандмауэра (вход к IIS с подсети сервера).
        public static string SuggestFirewallCidr(string host)
        {
            if (string.IsNullOrEmpty(host)) return null;
            string h = host.Trim();
            // если уже CIDR — как есть
            if (h.IndexOf('/') >= 0) return h;
            IPAddress ip;
            if (!IPAddress.TryParse(h, out ip)) return h + "/32";
            byte[] b = ip.GetAddressBytes();
            if (b.Length != 4) return h + "/32";
            return b[0] + "." + b[1] + "." + b[2] + ".0/24";
        }

        public static bool Confirm(string question)
        {
            if (Ctx.AssumeYes) return true;
            Console.Write("       " + question + " [y/N]: ");
            string a = Console.ReadLine();
            bool yes = a != null && (a.Trim().ToLowerInvariant() == "y" || a.Trim().ToLowerInvariant() == "yes" ||
                                     a.Trim().ToLowerInvariant() == "д" || a.Trim().ToLowerInvariant() == "да");
            Log.File("ВОПРОС: " + question + " -> " + (yes ? "ДА" : "НЕТ"));
            return yes;
        }

        public static string ReadPassword(string prompt)
        {
            Console.Write("       " + prompt + ": ");
            StringBuilder sb = new StringBuilder();
            while (true)
            {
                ConsoleKeyInfo k;
                try { k = Console.ReadKey(true); }
                catch { return Console.ReadLine(); }      // ввод перенаправлен — читаем обычной строкой
                if (k.Key == ConsoleKey.Enter) { Console.WriteLine(); break; }
                if (k.Key == ConsoleKey.Backspace) { if (sb.Length > 0) { sb.Length--; Console.Write("\b \b"); } continue; }
                if (char.IsControl(k.KeyChar)) continue;
                sb.Append(k.KeyChar);
                Console.Write("*");
            }
            return sb.ToString();
        }
    }
}
