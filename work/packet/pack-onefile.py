#!/usr/bin/env python3
# pack-onefile.py <generic.exe> <kit_dir> <webext_dir> <out.exe>
# Прицепляет пакет к exe установщика (решение владельца 09.08: один файл).
# В пакет входят: комплект слота (packet-setup.json, client.pfx из kit_dir)
# и все ячейки webext-хранилища (webext_dir/<версия>/<арх>/...).
# Формат — см. windows/odata-setup/src/Payload.cs (читает сам exe).
import hashlib, json, os, struct, sys

def main():
    if len(sys.argv) != 5:
        print("использование: pack-onefile.py <generic.exe> <kit_dir> <webext_dir> <out.exe>", file=sys.stderr)
        return 2
    exe, kit, webext, out = sys.argv[1:5]
    files = []
    for name in ("packet-setup.json", "client.pfx"):
        p = os.path.join(kit, name)
        if os.path.exists(p):
            files.append((name, p))
    if os.path.isdir(webext):
        for root, _dirs, names in os.walk(webext):
            for n in sorted(names):
                if n in ("index.tsv", "report.txt", "collect.log"):
                    continue
                p = os.path.join(root, n)
                rel = os.path.relpath(p, webext).replace(os.sep, "/")
                files.append(("webext/" + rel, p))
    if not files:
        print("нечего паковать: нет ни комплекта, ни webext", file=sys.stderr)
        return 1
    payload = b""
    entries = []
    for name, path in files:
        data = open(path, "rb").read()
        # h — sha256 содержимого: exe сверяет при распаковке (баг 09.08: чтение
        # не от начала данных давало куски exe; хеш — страховка от порчи файла).
        entries.append({"n": name, "o": len(payload), "l": len(data),
                        "h": hashlib.sha256(data).hexdigest()})
        payload += data
    dirj = json.dumps(entries, separators=(",", ":")).encode("utf-8")
    with open(exe, "rb") as f:
        base = f.read()
    with open(out, "wb") as f:
        f.write(base)
        f.write(payload)
        f.write(dirj)
        f.write(struct.pack("<I", len(dirj)))
        f.write(b"1CAIPKG1")
    print("onefile:", out, os.path.getsize(out), "байт, файлов в пакете:", len(entries))

if __name__ == "__main__":
    sys.exit(main())
