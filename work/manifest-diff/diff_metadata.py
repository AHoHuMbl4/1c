#!/usr/bin/env python3
# diff_metadata.py — сравнение двух $metadata (EDM XML) 1С OData.
#
# По каждому EntityType извлекается: множество key-полей и карта prop->type.
# Отчёт: сущности только в одном из файлов, расхождения ключей, расхождения
# свойств (имя/тип), итоговые счётчики. Exit 0 при совпадении.
#
# Использование:
#   python3 diff_metadata.py A.xml B.xml [--ignore "Catalog_X,Document_Y*,..."]
#                                        [--verbose] [--max-show N]
#
# --ignore: список имён сущностей через запятую/точку с запятой; суффикс "*"
#           означает префикс. Игнорируемые сущности исключаются из всех
#           сравнений (документированные исключения).
# --ignore-prop: то же для отдельных свойств — шаблоны сопоставляются со строкой
#           "Сущность.Свойство"; запись "@файл" читает шаблоны из файла
#           (по одному на строку, '#' — комментарий).
#
# Нефатальные категории (печатаются, на exit-код не влияют):
#   KEY-ORDER  — те же key-поля, но в другом порядке;
#   NULLABLE   — совпали имя и тип, различается Nullable.
# Фатальные (exit 1): ONLY-IN-A/B, KEY, PROP-MISS, PROP-TYPE, SET-ONLY-*.
import sys
import xml.etree.ElementTree as ET

EDM = "{http://schemas.microsoft.com/ado/2009/11/edm}"


def parse(path):
    """Возвращает (entities, sets):
    entities: name -> {"key": [имена], "props": {имя: тип}, "nullable": {имя: str}}
    sets:     name -> тип EntityType"""
    tree = ET.parse(path)
    schema = tree.getroot().find(".//" + EDM + "Schema")
    entities = {}
    if schema is None:
        raise SystemExit("в файле %s нет edm:Schema" % path)
    for et in schema.findall(EDM + "EntityType"):
        name = et.get("Name")
        key = [pr.get("Name") for pr in et.findall(EDM + "Key/" + EDM + "PropertyRef")]
        props = {}
        nullable = {}
        for p in et.findall(EDM + "Property"):
            props[p.get("Name")] = p.get("Type")
            nullable[p.get("Name")] = p.get("Nullable")
        entities[name] = {"key": key, "props": props, "nullable": nullable}
    sets = {}
    cont = schema.find(EDM + "EntityContainer")
    if cont is not None:
        for s in cont.findall(EDM + "EntitySet"):
            sets[s.get("Name")] = s.get("EntityType")
    return entities, sets


class Ignore:
    def __init__(self, spec):
        self.exact = set()
        self.prefixes = []
        self.suffixes = []
        for part in (spec or "").replace(";", ",").split(","):
            part = part.strip()
            if not part:
                continue
            if part.endswith("*"):
                self.prefixes.append(part[:-1])
            elif part.startswith("*"):
                self.suffixes.append(part[1:])
            else:
                self.exact.add(part)

    def match(self, name):
        if name in self.exact:
            return True
        if any(name.startswith(p) for p in self.prefixes):
            return True
        return any(name.endswith(s) for s in self.suffixes)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = {}
    for i, a in enumerate(sys.argv[1:]):
        if a == "--ignore":
            opts["ignore"] = sys.argv[i + 2]
        if a == "--ignore-prop":
            opts["ignore_prop"] = sys.argv[i + 2]
    ignore = Ignore(opts.get("ignore", ""))
    # шаблоны свойств; "@файл" — список из файла
    prop_spec = opts.get("ignore_prop", "")
    if "@" in prop_spec:
        parts = []
        for tok in prop_spec.replace(";", ",").split(","):
            tok = tok.strip()
            if tok.startswith("@"):
                for ln in open(tok[1:], encoding="utf-8"):
                    ln = ln.strip()
                    if ln and not ln.startswith("#"):
                        parts.append(ln)
            elif tok:
                parts.append(tok)
        prop_spec = ",".join(parts)
    ignore_prop = Ignore(prop_spec)
    verbose = "--verbose" in sys.argv
    max_show = 50
    if "--max-show" in sys.argv:
        max_show = int(sys.argv[sys.argv.index("--max-show") + 1])

    if len(args) < 2:
        print("usage: diff_metadata.py A.xml B.xml [--ignore ...] [--verbose] [--max-show N]")
        return 2

    ea, sa = parse(args[0])
    eb, sb = parse(args[1])

    ignored = sorted((set(ea) | set(eb)) & {n for n in set(ea) | set(eb) if ignore.match(n)})
    for n in ignored:
        ea.pop(n, None)
        eb.pop(n, None)

    fails = []   # фатальные расхождения
    infos = []   # нефатальные (порядок ключа, Nullable)

    only_a = sorted(set(ea) - set(eb))
    only_b = sorted(set(eb) - set(ea))
    for n in only_a:
        fails.append("ONLY-IN-A %s" % n)
    for n in only_b:
        fails.append("ONLY-IN-B %s" % n)

    for n in sorted(set(ea) & set(eb)):
        a, b = ea[n], eb[n]
        if set(a["key"]) != set(b["key"]):
            fails.append("KEY %s: A={%s} B={%s}" % (
                n, ",".join(a["key"]), ",".join(b["key"])))
        elif a["key"] != b["key"]:
            infos.append("KEY-ORDER %s: A=[%s] B=[%s]" % (
                n, ",".join(a["key"]), ",".join(b["key"])))
        pa, pb = a["props"], b["props"]
        for p in sorted(set(pa) - set(pb)):
            if ignore_prop.match("%s.%s" % (n, p)):
                continue
            fails.append("PROP-MISS-B %s.%s (%s)" % (n, p, pa[p]))
        for p in sorted(set(pb) - set(pa)):
            if ignore_prop.match("%s.%s" % (n, p)):
                continue
            fails.append("PROP-MISS-A %s.%s (%s)" % (n, p, pb[p]))
        for p in sorted(set(pa) & set(pb)):
            if pa[p] != pb[p]:
                if ignore_prop.match("%s.%s" % (n, p)):
                    continue
                fails.append("PROP-TYPE %s.%s: A=%s B=%s" % (n, p, pa[p], pb[p]))
            elif a["nullable"].get(p) != b["nullable"].get(p):
                infos.append("NULLABLE %s.%s: A=%s B=%s" % (
                    n, p, a["nullable"].get(p), b["nullable"].get(p)))

    set_only_a = sorted(set(sa) - set(sb))
    set_only_b = sorted(set(sb) - set(sa))
    for n in set_only_a:
        fails.append("SET-ONLY-IN-A %s" % n)
    for n in set_only_b:
        fails.append("SET-ONLY-IN-B %s" % n)

    show = fails if not verbose else fails + infos
    for line in show[:max_show]:
        print(line)
    if len(show) > max_show:
        print("... ещё %d строк (поднять --max-show)" % (len(show) - max_show))

    print("== ИТОГ ==")
    print("entities: A=%d B=%d (общих %d, проигнорировано %d)" % (
        len(ea), len(eb), len(set(ea) & set(eb)), len(ignored)))
    print("only-in-A=%d only-in-B=%d" % (len(only_a), len(only_b)))
    f_key = sum(1 for f in fails if f.startswith("KEY "))
    f_miss = sum(1 for f in fails if f.startswith("PROP-MISS"))
    f_type = sum(1 for f in fails if f.startswith("PROP-TYPE"))
    print("key-diff=%d prop-miss=%d prop-type=%d set-diff=%d" % (
        f_key, f_miss, f_type, len(set_only_a) + len(set_only_b)))
    print("info: key-order=%d nullable=%d" % (
        sum(1 for f in infos if f.startswith("KEY-ORDER")),
        sum(1 for f in infos if f.startswith("NULLABLE"))))
    if fails:
        print("RESULT=DIFF (%d фатальных расхождений)" % len(fails))
        return 1
    print("RESULT=MATCH")
    return 0


if __name__ == "__main__":
    sys.exit(main())
