// Payload.cs — прицепленный к exe пакет данных (решение владельца 09.08:
// установщик = ОДИН файл; при запуске пакет распаковывается во временную папку).
//
// Внутри пакета: комплект слота (packet-setup.json, client.pfx) и ячейки
// webext-хранилища (webext/<версия>/<разрядность>/wsisapi.dll + webinst.exe + res).
// Формат (собирается на Ubuntu в onboard-base.sh, пересборка exe НЕ нужна):
//   [байты файлов подряд][JSON-оглавление][uint32 длина оглавления][magic]
// Оглавление: [{"n":"packet-setup.json","o":0,"l":318,"h":"sha256hex"}, …] —
// смещение/длина от начала ДАННЫХ пакета (не файла! данные идут после тела exe),
// h — sha256 содержимого (необязателен; сверка при распаковке, замер 09.08:
// чтение по абсолютному смещению давало куски exe — packet-setup.json «MZ»,
// webinst «несовместим с 64-разрядной Windows», wsisapi → IIS 500).
// Magic — 8 байт "1CAIPKG1" в самом конце файла.
// Пакета нет — поведение прежнее (комплект ищется рядом с exe).
using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;

namespace Oc1c
{
    internal static class Payload
    {
        const string Magic = "1CAIPKG1";

        // Каталог, куда распакован пакет (null — пакета нет). Заполняется Extract().
        internal static string Dir;

        // Ожидаемые sha256 из оглавления (имя -> hex), если пакет их несёт.
        static readonly Dictionary<string, string> Hashes =
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);

        // Ожидаемый sha256 файла пакета (null — пакета нет или хеша в оглавлении нет).
        internal static string ExpectedHash(string rel)
        {
            string h;
            return Hashes.TryGetValue(rel, out h) ? h : null;
        }

        internal static string Sha256Hex(string path)
        {
            using (SHA256 s = SHA256.Create())
            using (FileStream f = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                return BitConverter.ToString(s.ComputeHash(f)).Replace("-", "").ToLowerInvariant();
        }

        // Распаковать прицепленный пакет во временный каталог. Возвращает число файлов.
        internal static int Extract()
        {
            Dir = null;
            string exe;
            try { exe = System.Reflection.Assembly.GetExecutingAssembly().Location; }
            catch { return 0; }
            try
            {
                using (FileStream fs = new FileStream(exe, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                {
                    if (fs.Length < 12) return 0;
                    fs.Seek(-8, SeekOrigin.End);
                    byte[] mg = new byte[8];
                    fs.Read(mg, 0, 8);
                    if (Encoding.ASCII.GetString(mg) != Magic) return 0;
                    fs.Seek(-12, SeekOrigin.End);
                    byte[] lb = new byte[4];
                    fs.Read(lb, 0, 4);
                    uint dirLen = BitConverter.ToUInt32(lb, 0);
                    if (dirLen <= 0 || dirLen > 64 * 1024 * 1024 || fs.Length < 12 + dirLen) return 0;
                    long payloadEnd = fs.Length - 12 - dirLen;
                    fs.Seek(payloadEnd, SeekOrigin.Begin);
                    byte[] jb = new byte[dirLen];
                    fs.Read(jb, 0, (int)dirLen);
                    string json = Encoding.UTF8.GetString(jb);
                    JavaScriptSerializer ser = new JavaScriptSerializer();
                    List<Dictionary<string, object>> entries =
                        ser.Deserialize<List<Dictionary<string, object>>>(json);
                    if (entries == null || entries.Count == 0) return 0;

                    // Смещения в оглавлении — от начала ДАННЫХ пакета, а данные
                    // идут после тела exe: dataStart = конец пакета − размер данных.
                    // (Баг 09.08: чтение по «o» от начала ФАЙЛА извлекало куски exe.)
                    long dataLen = 0;
                    foreach (Dictionary<string, object> e in entries)
                    {
                        long end = Convert.ToInt64(e["o"]) + Convert.ToInt64(e["l"]);
                        if (end > dataLen) dataLen = end;
                    }
                    long dataStart = payloadEnd - dataLen;
                    if (dataStart < 0) return 0;

                    string dir = Path.Combine(Path.GetTempPath(), "1cai-pkg-" + System.Diagnostics.Process.GetCurrentProcess().Id);
                    Directory.CreateDirectory(dir);
                    int extracted = 0;
                    foreach (Dictionary<string, object> e in entries)
                    {
                        string name = Convert.ToString(e["n"]);
                        long off = Convert.ToInt64(e["o"]);
                        long len = Convert.ToInt64(e["l"]);
                        if (name.IndexOf("..") >= 0 || name.StartsWith("/") || name.StartsWith("\\")) continue;
                        if (off < 0 || len < 0 || dataStart + off + len > payloadEnd) continue;
                        string dest = Path.Combine(dir, name.Replace('/', Path.DirectorySeparatorChar));
                        string dd = Path.GetDirectoryName(dest);
                        if (!string.IsNullOrEmpty(dd)) Directory.CreateDirectory(dd);
                        fs.Seek(dataStart + off, SeekOrigin.Begin);
                        using (FileStream outp = File.Create(dest))
                        {
                            byte[] buf = new byte[65536];
                            long left = len;
                            while (left > 0)
                            {
                                int got = fs.Read(buf, 0, (int)Math.Min(buf.Length, left));
                                if (got <= 0) break;
                                outp.Write(buf, 0, got);
                                left -= got;
                            }
                        }
                        // Контроль целостности: хеш из оглавления (если пакет его
                        // несёт). Битый файл не должен дойти до потребителя — иначе
                        // снова получим «MZ в json» и 500 от IIS (замер 09.08).
                        object hv; string want = e.TryGetValue("h", out hv) ? Convert.ToString(hv) : null;
                        if (!string.IsNullOrEmpty(want))
                        {
                            Hashes[name] = want;
                            string got2;
                            try { got2 = Sha256Hex(dest); } catch { got2 = null; }
                            if (got2 == null || !got2.Equals(want, StringComparison.OrdinalIgnoreCase))
                            {
                                try { File.Delete(dest); } catch { }
                                Log.Warn("пакет: файл " + name + " повреждён (хеш не сошёлся) — пропущен");
                                continue;
                            }
                        }
                        extracted++;
                    }
                    Dir = dir;
                    AppDomain.CurrentDomain.ProcessExit += delegate { try { Directory.Delete(dir, true); } catch { } };
                    return extracted;
                }
            }
            catch { Dir = null; return 0; }
        }

        // Путь к файлу пакета (null, если пакета нет или файла в нём нет).
        internal static string Find(string rel)
        {
            if (Dir == null) return null;
            string p = Path.Combine(Dir, rel.Replace('/', Path.DirectorySeparatorChar));
            return File.Exists(p) ? p : null;
        }
    }
}
