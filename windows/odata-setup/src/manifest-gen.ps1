# manifest-gen.ps1 — генератор синтетического $metadata (EDM XML) из метаданных 1С через COM.
#
# Зачем: у части баз платформа отдаёт HTTP 500 на корень OData и $metadata
# (баг построителя модели при большом составе), а запросы к сущностям работают.
# Установщик генерирует $metadata сам обходом метаданных через COM, агент и
# сервер потребляют файл вместо HTTP. Формы (ключи, типы Edm.*, Nullable)
# откалиброваны по живому $metadata УТ 11 и снимку ERP (work/packet/golden).
#
# Переменные окружения:
#   OC1C_PROGID       — ProgID коннектора (по умолчанию V83.COMConnector)
#   OC1C_CONNSTR      — строка подключения с кредами (File="...";Usr="...";Pwd="...")
#   OC1C_MANIFEST_OUT — путь выходного XML
#   OC1C_EXCLUDE      — ";" -разделённые полные имена объектов для пропуска
#                       (Справочник.Х или Catalog_Х), может быть пусто
#
# Маркеры конца: ENTITY-COUNT=n, SET-COUNT=n, RESULT=OK / ERROR=<текст> + exit 1.
# Сбой одного объекта не роняет прогон: печатается SKIP=<полное имя>|<причина>.
# База только читается. Каждый тег выводится одной строкой (потребители — регексы).
$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

# ==== параметры ====
$PROGID  = $env:OC1C_PROGID
if (-not $PROGID) { $PROGID = "V83.COMConnector" }
$CONNSTR = $env:OC1C_CONNSTR
$OUT     = $env:OC1C_MANIFEST_OUT
$EXCLUDE = $env:OC1C_EXCLUDE
if (-not $CONNSTR -or -not $OUT) {
    "ERROR=задайте OC1C_CONNSTR (строка подключения с кредами) и OC1C_MANIFEST_OUT (путь XML)"
    exit 1
}

# ==== COM-коннектор; при x86-платформе на x64-ОС — самоперезапуск в 32-бит PS ====
$connector = $null
try { $connector = New-Object -ComObject $PROGID } catch {}
if (-not $connector) {
    $w = 'C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe'
    if ([Environment]::Is64BitProcess -and (Test-Path $w) -and $env:OC1C_MANIFEST_X86 -ne '1') {
        $env:OC1C_MANIFEST_X86 = '1'
        & $w -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath
        exit $LASTEXITCODE
    }
    "ERROR=COM-объект $PROGID не создан"
    exit 1
}

$GP = [Reflection.BindingFlags]::GetProperty -bor [Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::Instance
$IM = [Reflection.BindingFlags]::InvokeMethod -bor [Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::Instance
# П — свойство (рус. имя, затем англ.), М — метод. Имена свойств квалификаторов —
# только английские (живой замер 11.08: рус. Длина через InvokeMember не читается).
function P($o, $n) { return [__ComObject].InvokeMember($n, $GP, $null, $o, @()) }
function PE($o, $ru, $en) { try { return P $o $ru } catch { return P $o $en } }
function M($o, $n, $a) { return [__ComObject].InvokeMember($n, $IM, $null, $o, $a) }
function ME($o, $ru, $en, $a) { try { return M $o $ru $a } catch { return M $o $en $a } }
function Coll-Count($c) { if (-not $c) { return 0 }; return [int](ME $c "Количество" "Count" @()) }
# строковое представление значения (системные enum метаданных, примитивные типы)
function Str($v) { if ($null -eq $v) { return "" }; try { return [string](M $ib "String" @($v)) } catch { return "" } }
# полное имя объекта метаданных
function Full-Name($o) { return [string](ME $o "ПолноеИмя" "FullName" @()) }

try { $ib = $connector.Connect($CONNSTR) } catch { "ERROR=подключение: " + $_.Exception.Message; exit 1 }
$md = P $ib "Метаданные"
"CONNECTED"

# ==== состав стандартного интерфейса OData (что реально публикуется) ====
$comp = $null
try { $comp = M $ib "ПолучитьСоставСтандартногоИнтерфейсаOData" @() } catch {
    try { $comp = M $ib "GetStandardODataInterfaceContent" @() } catch {}
}
if (-not $comp) { "ERROR=состав стандартного интерфейса OData не получен"; exit 1 }

$excludeSet = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
foreach ($e in (($EXCLUDE -replace ',', ';') -split ';')) { if ($e.Trim()) { [void]$excludeSet.Add($e.Trim()) } }

# классы метаданных → префикс сущности OData
$prefix = @{
    "Справочник"="Catalog"; "Документ"="Document"; "ЖурналДокументов"="DocumentJournal";
    "Константа"="Constant"; "РегистрСведений"="InformationRegister";
    "РегистрНакопления"="AccumulationRegister"; "РегистрБухгалтерии"="AccountingRegister";
    "РегистрРасчета"="CalculationRegister"; "ПланСчетов"="ChartOfAccounts";
    "ПланВидовХарактеристик"="ChartOfCharacteristicTypes";
    "ПланВидовРасчета"="ChartOfCalculationTypes"; "ПланОбмена"="ExchangePlan";
    "БизнесПроцесс"="BusinessProcess"; "Задача"="Task"
}

# ==== буферы вывода ====
$sb = New-Object System.Text.StringBuilder
$script:sets = New-Object System.Collections.Generic.List[string]   # имена EntitySet (порядок = порядок сущностей)
$script:cts  = New-Object System.Collections.Generic.List[object]  # ComplexType: @(имя, строки свойств)
$script:entityCount = 0
$script:skipCount = 0
$script:curFn = ""
$script:curEnt = ""
$script:enumSeen = @{}   # замеченные представления системных enum (для калибровки)

function Add-Line($s) { [void]$sb.Append($s).Append("`n") }

# числовой тип EDM по квалификаторам.
# Калибровка 11.08 (стенд, УТ 11, живой $metadata): 65 уникальных описаний типов
# (разрядность 1..25, точность 0..9) — дробные всегда Edm.Double, целые с
# разрядностью ≤4 → Edm.Int16, остальные → Edm.Int64. Edm.Int32 в типах свойств
# платформа 8.3.27 не использует вовсе (в файле встречается только в EnumType).
$script:numT16 = 4
if ($env:OC1C_NUM_T16) { $script:numT16 = [int]$env:OC1C_NUM_T16 }
function Get-NumberEdm($dig, $fr) {
    if ($fr -gt 0) { return "Edm.Double" }
    if ($dig -le $script:numT16) { return "Edm.Int16" }
    return "Edm.Int64"
}

# ==== маппинг типа реквизита (ОписаниеТипов) в свойства EDM ====
# Результат — хеш:
#   main   : список @(@(имя, edm-тип)) — основные свойства (на позиции реквизита)
#   tail   : список имён свойств <Имя>_Type (Edm.String, в конце EntityType)
#   stream : список имён свойств Edm.Stream (ХранилищеЗначения, после tail)
#   composite: есть составной (не ХранилищеЗначения) тип → OpenType="true"
#   keyMain: имя основного свойства (для ключа: Имя или Имя_Key)
#   keyTail: дополнительные key-поля составного типа (<Имя>_Type)
# Кэш по внутреннему представлению ОписаниеТипов — одинаковые типы не разбираются дважды.
$script:typeCache = @{}
function Map-Attr($attr, $baseName) {
    $td = $null
    try { $td = P $attr "Тип" } catch { try { $td = P $attr "Type" } catch {} }
    if (-not $td) {
        # тип не читается (например графа журнала) — строковое свойство
        return @{ main=@(,@($baseName, "Edm.String")); tail=@(); stream=@(); composite=$false; keyMain=$baseName; keyTail=@() }
    }
    $vsi = ""
    try { $vsi = ([string](M $ib "ValueToStringInternal" @($td))) -replace '\s+', '' } catch {}
    if ($vsi -and $script:typeCache.ContainsKey($vsi)) {
        $c = $script:typeCache[$vsi]
        return Rebind-Map $c $baseName
    }
    $refs = @()    # классы ссылочных типов (Справочник/Документ/Перечисление/...)
    $prims = @()   # примитивы: string/number/bool/date/uuid
    $hv = $false   # ХранилищеЗначения
    $types = $null
    try { $types = M $td "Типы" @() } catch { try { $types = M $td "Types" @() } catch {} }
    foreach ($t in $types) {
        # точка маршрута бизнес-процесса — не GUID-ссылка, в OData уходит строкой
        $ts = Str $t
        if ($ts -like "*(точка маршрута)*" -or $ts -like "*(route point)*") { $prims += "string"; continue }
        $mo = $null
        try { $mo = M $md "НайтиПоТипу" @($t) } catch { try { $mo = M $md "FindByType" @($t) } catch {} }
        if ($mo) {
            $refs += ((Full-Name $mo) -split '\.')[0]
        } else {
            $ps = $ts
            switch -regex ($ps) {
                '^(Строка|String)$'                 { $prims += "string"; break }
                '^(Число|Number)$'                  { $prims += "number"; break }
                '^(Булево|Boolean)$'                { $prims += "bool"; break }
                '^(Дата|Date)$'                     { $prims += "date"; break }
                '^(Уникальный идентификатор|UUID|Guid|Unique identifier)' { $prims += "uuid"; break }
                '^(Хранилище значения|ХранилищеЗначения|Value ?[Ss]torage)' { $hv = $true; break }
                '^Null$'                            { break }  # Null на представление не влияет
                default                             { $prims += "string"; break }  # Тип, ТочкаМаршрута и пр. → строка
            }
        }
    }
    $res = @{ main=@(); tail=@(); stream=@(); composite=$false; keyMain=""; keyTail=@() }
    $n = $refs.Count + $prims.Count
    if ($hv -and $n -eq 0) {
        # ХранилищеЗначения: три свойства — Base64Data на позиции, _Type и Stream в хвосте
        $res.main   = ,@("~B64~", "Edm.Binary")
        $res.tail   = ,@("~T~")
        $res.stream = ,@("~S~")
        $res.keyMain = "~B64~"
    } elseif ($hv -or $n -gt 1) {
        # составной тип: строковое представление + <Имя>_Type
        $res.main = ,@("~M~", "Edm.String")
        $res.tail = ,@("~T~")
        $res.composite = $true
        $res.keyMain = "~M~"
        $res.keyTail = ,@("~T~")
    } elseif ($n -eq 1) {
        if ($refs.Count -eq 1) {
            if ($refs[0] -eq "Перечисление" -or $refs[0] -eq "Enum") {
                $res.main = ,@("~M~", "Edm.String")
            } else {
                $res.main = ,@("~K~", "Edm.Guid")
            }
        } else {
            switch ($prims[0]) {
                "string" { $res.main = ,@("~M~", "Edm.String") }
                "bool"   { $res.main = ,@("~M~", "Edm.Boolean") }
                "date"   { $res.main = ,@("~M~", "Edm.DateTime") }
                "uuid"   { $res.main = ,@("~M~", "Edm.Guid") }
                "number" {
                    $dig = 0; $fr = 0
                    try { $qn = P $td "NumberQualifiers"; $dig = [int](P $qn "Digits"); $fr = [int](P $qn "FractionDigits") } catch {}
                    # калибровочный вывод для diff-харнеса (OC1C_MANIFEST_DEBUG_NUM=1)
                    if ($env:OC1C_MANIFEST_DEBUG_NUM -eq '1') {
                        [Console]::Out.WriteLine("NUM|" + $script:curEnt + "|" + $baseName + "|" + $dig + "|" + $fr)
                    }
                    $res.main = ,@("~M~", (Get-NumberEdm $dig $fr))
                }
            }
        }
        $res.keyMain = $res.main[0][0]
    } else {
        # пустое описание типов — строковое свойство
        $res.main = ,@("~M~", "Edm.String")
        $res.keyMain = "~M~"
    }
    if ($vsi) { $script:typeCache[$vsi] = $res }
    return Rebind-Map $res $baseName
}
# подстановка реального имени в шаблонные метки (~M~ — Имя, ~K~ — Имя_Key,
# ~T~ — Имя_Type, ~B64~ — Имя_Base64Data, ~S~ — Имя)
function Rebind-Map($res, $name) {
    $r = @{ main=@(); tail=@(); stream=@(); composite=$res.composite; keyMain=""; keyTail=@() }
    foreach ($m in $res.main) {
        $nm = $m[0]
        if ($nm -eq "~K~") { $nm = $name + "_Key" }
        elseif ($nm -eq "~M~" -or $nm -eq "~S~") { $nm = $name }
        elseif ($nm -eq "~B64~") { $nm = $name + "_Base64Data" }
        $r.main += ,@($nm, $m[1])
    }
    foreach ($t in $res.tail) { $r.tail += ,($name + "_Type") }
    foreach ($s in $res.stream) { $r.stream += ,($name) }
    $r.keyMain = if ($res.keyMain -eq "~K~") { $name + "_Key" } elseif ($res.keyMain -eq "~B64~") { $name + "_Base64Data" } else { $name }
    foreach ($t in $res.keyTail) { $r.keyTail += ,($name + "_Type") }
    return $r
}

# ==== вывод EntityType ====
# $props — список @(@(имя, тип, nullable)); key-поля обязаны быть с nullable=false (заботой вызывающего)
function Emit-Entity($name, $keyNames, $props, $openType) {
    if ($openType) { Add-Line ("`t`t<EntityType Name=`"" + $name + "`" OpenType=`"true`">") }
    else { Add-Line ("`t`t<EntityType Name=`"" + $name + "`">") }
    if ($keyNames.Count -gt 0) {
        Add-Line "`t`t`t<Key>"
        foreach ($k in $keyNames) { Add-Line ("`t`t`t`t<PropertyRef Name=`"" + $k + "`"/>") }
        Add-Line "`t`t`t</Key>"
    }
    foreach ($p in $props) { Add-Line ("`t`t`t<Property Name=`"" + $p[0] + "`" Type=`"" + $p[1] + "`" Nullable=`"" + $p[2] + "`"/>") }
    Add-Line "`t`t</EntityType>"
    $script:sets.Add($name)
    $script:entityCount++
}
# ComplexType (RowType табличных частей и наборов записей; потребители не читают — для валидности XML)
function Add-ComplexType($name, $props) {
    $lines = @()
    foreach ($p in $props) { $lines += ("`t`t`t<Property Name=`"" + $p[0] + "`" Type=`"" + $p[1] + "`" Nullable=`"" + $p[2] + "`"/>") }
    $script:cts.Add(@($name, $lines))
}

# ==== сборка списка свойств объекта из коллекции реквизитов ====
# Возвращает хеш: props (готовые строки-записи), open (bool), keyMain/keyTail списков для ключей.
# $nullInKey — имена свойств, попадающих в ключ (их Nullable=false).
function Collect-Attrs($coll, $keySet, $suffix) {
    $props = @(); $tails = @(); $streams = @(); $open = $false
    $keyMains = @(); $keyTails = @()
    if (-not $coll) { return @{ props=$props; tails=$tails; streams=$streams; open=$open; keyMains=$keyMains; keyTails=$keyTails } }
    foreach ($a in $coll) {
        $an = [string](P $a "Имя")
        if ($suffix) { $an = $an + $suffix }
        $mp = Map-Attr $a $an
        foreach ($m in $mp.main) {
            $nul = if ($keySet -and $keySet.Contains($m[0])) { "false" } else { "true" }
            $props += ,@($m[0], $m[1], $nul)
        }
        foreach ($t in $mp.tail) {
            $nul = if ($keySet -and $keySet.Contains($t)) { "false" } else { "true" }
            $tails += ,@($t, $nul)
        }
        foreach ($s in $mp.stream) { $streams += ,@($s, "Edm.Stream", "true") }
        if ($mp.composite) { $open = $true }
        $keyMains += $mp.keyMain
        foreach ($kt in $mp.keyTail) { $keyTails += $kt }
    }
    return @{ props=$props; tails=$tails; streams=$streams; open=$open; keyMains=$keyMains; keyTails=$keyTails }
}

# ==== табличная часть: отдельный EntityType + RowType + Collection у владельца ====
function Emit-TabSection($ownerName, $tsMeta) {
    $tsName = [string](P $tsMeta "Имя")
    $en = $ownerName + "_" + $tsName
    $saveEnt = $script:curEnt
    $script:curEnt = $en
    $keySet = New-Object 'System.Collections.Generic.HashSet[string]'
    [void]$keySet.Add("Ref_Key"); [void]$keySet.Add("LineNumber")
    $ca = Collect-Attrs (P $tsMeta "Реквизиты") $null $null
    $script:curEnt = $saveEnt
    $props = @(,@("Ref_Key","Edm.Guid","false")) + @(,@("LineNumber","Edm.Int64","false")) + $ca.props
    foreach ($t in $ca.tails) { $props += ,@($t[0], "Edm.String", $t[1]) }
    foreach ($s in $ca.streams) { $props += ,$s }
    Emit-Entity $en @("Ref_Key","LineNumber") $props $ca.open
    Add-ComplexType ($en + "_RowType") $props
    $ct = "Collection(StandardODATA." + $en + "_RowType)"
    return @($tsName, $ct, "true")
}

# ==== регистраторы регистров (сколько документов пишут в регистр) ====
# один регистратор → Recorder_Key (Edm.Guid), несколько → Recorder + Recorder_Type
$script:recorders = $null
function Build-Recorders {
    $script:recorders = @{}
    foreach ($doc in (P $md "Документы")) {
        $dn = [string](P $doc "Имя")
        $dv = $null; try { $dv = P $doc "Движения" } catch {}
        if (-not $dv) { continue }
        foreach ($mv in $dv) {
            $fn = ""
            try { $fn = Full-Name $mv } catch { continue }
            if (-not $script:recorders.ContainsKey($fn)) { $script:recorders[$fn] = New-Object System.Collections.Generic.List[string] }
            $script:recorders[$fn].Add($dn)
        }
    }
}

# ==== базовый EntityType регистра, подчинённого регистратору ====
function Emit-RegisterBase($en, $rowTypeName) {
    $ri = $script:recorderInfo
    $coll = "Collection(StandardODATA." + $rowTypeName + ")"
    $key = @(); $props = @(); $tails = @()
    if ($ri.composite) {
        $key = @("Recorder", "Recorder_Type")
        $props += ,@("Recorder", "Edm.String", "false")
        $props += ,@("RecordSet", $coll, "false")
        $tails += ,@("Recorder_Type", "false")
    } else {
        $key = @("Recorder_Key")
        $props += ,@("Recorder_Key", "Edm.Guid", "false")
        $props += ,@("RecordSet", $coll, "false")
    }
    foreach ($t in $tails) { $props += ,@($t[0], "Edm.String", $t[1]) }
    Emit-Entity $en $key $props $ri.composite
}
# информация о регистраторе: composite + имена полей для ключа/свойств
function Get-RecorderInfo($fullName) {
    $lst = $script:recorders[$fullName]
    $composite = (-not $lst) -or ($lst.Count -ne 1)
    return @{ composite=$composite }
}

# ==== системное enum метаданных → строка с учётом представлений ====
function Enum-Val($o, $propRu, $propEn) {
    $v = $null
    try { $v = P $o $propRu } catch { try { $v = P $o $propEn } catch { return "" } }
    $s = Str $v
    if ($s -and -not $script:enumSeen.ContainsKey($propRu + "=" + $s)) {
        $script:enumSeen[$propRu + "=" + $s] = 1
        # напрямую в консоль, минуя выходной поток — иначе строка попадёт в возврат функции
        [Console]::Out.WriteLine("ENUMVAL $propRu=[$s]")
    }
    return $s
}

# ==== эмиттеры по видам объектов ====

# тип EDM для стандартного Кода (ТипКода=Число → числовой)
function Get-CodeEdm($o) {
    $tk = Enum-Val $o "ТипКода" "CodeType"
    if ($tk -like "*Число*" -or $tk -like "*Number*") {
        $l = 0; try { $l = [int](PE $o "ДлинаКода" "CodeLength") } catch {}
        return Get-NumberEdm $l 0
    }
    return "Edm.String"
}
# тип EDM для стандартного Номера (ТипНомера=Число → числовой)
function Get-NumberEdmStd($o) {
    $tk = Enum-Val $o "ТипНомера" "NumberType"
    if ($tk -like "*Число*" -or $tk -like "*Number*") {
        $l = 0; try { $l = [int](PE $o "ДлинаНомера" "NumberLength") } catch {}
        return Get-NumberEdm $l 0
    }
    return "Edm.String"
}

function Emit-CatalogLike($o, $en, $kind) {
    # общий каркас ссылочных объектов
    $props = @(); $tails = @(); $streams = @(); $open = $false
    $props += ,@("Ref_Key", "Edm.Guid", "false")
    if ($kind -in @("Catalog", "ChartOfCharacteristicTypes", "ChartOfCalculationTypes", "ChartOfAccounts")) {
        $props += ,@("Predefined", "Edm.Boolean", "true")
        $props += ,@("PredefinedDataName", "Edm.String", "true")
    }
    $props += ,@("DataVersion", "Edm.String", "true")
    $descLen = 0; try { $descLen = [int](PE $o "ДлинаНаименования" "DescriptionLength") } catch {}
    $codeLen = 0; try { $codeLen = [int](PE $o "ДлинаКода" "CodeLength") } catch {}
    $numLen = 0; try { $numLen = [int](PE $o "ДлинаНомера" "NumberLength") } catch {}
    # иерархия
    $hier = $false
    try { $hier = [bool](P $o "Иерархический") } catch { try { $hier = [bool](P $o "Hierarchical") } catch {} }
    # у плана счетов Parent_Key идёт до Description/Code (форма из эталона ERP)
    if ($kind -eq "ChartOfAccounts" -and $hier) { $props += ,@("Parent_Key", "Edm.Guid", "true") }
    if ($kind -eq "ExchangePlan") {
        if ($codeLen -gt 0) { $props += ,@("Code", (Get-CodeEdm $o), "true") }
        if ($descLen -gt 0) { $props += ,@("Description", "Edm.String", "true") }
    } elseif ($kind -in @("Catalog", "ChartOfCharacteristicTypes", "ChartOfCalculationTypes", "ChartOfAccounts")) {
        if ($descLen -gt 0) { $props += ,@("Description", "Edm.String", "true") }
        if ($codeLen -gt 0) { $props += ,@("Code", (Get-CodeEdm $o), "true") }
    } elseif ($kind -eq "Task") {
        if ($descLen -gt 0) { $props += ,@("Description", "Edm.String", "true") }
        if ($numLen -gt 0) { $props += ,@("Number", (Get-NumberEdmStd $o), "true") }
        $props += ,@("Date", "Edm.DateTime", "true")
    } elseif ($kind -eq "BusinessProcess") {
        if ($numLen -gt 0) { $props += ,@("Number", (Get-NumberEdmStd $o), "true") }
        $props += ,@("Date", "Edm.DateTime", "true")
    }
    if ($hier -and $kind -ne "ChartOfAccounts") {
        $props += ,@("Parent_Key", "Edm.Guid", "true")
        # IsFolder: у справочников — только при иерархии групп и элементов;
        # у ПВХ/ПВР — всегда при иерархии; у плана счетов не бывает (замеры 11.08)
        if ($kind -eq "Catalog") {
            $vh = Enum-Val $o "ВидИерархии" "HierarchyType"
            if ($vh -like "*Групп*" -or $vh -like "*Folders*") { $props += ,@("IsFolder", "Edm.Boolean", "true") }
        } else {
            $props += ,@("IsFolder", "Edm.Boolean", "true")
        }
    }
    # владельцы справочников: свойство Владельцы через COM недоступно (замер 11.08,
    # платформа 8.3.27 x86 отдаёт пустую коллекцию) — Owner/Owner_Key не генерируются,
    # задокументированное расхождение
    if ($kind -eq "ChartOfAccounts") {
        $props += ,@("Order", "Edm.String", "true")
        $props += ,@("OffBalance", "Edm.Boolean", "true")
    }
    $props += ,@("DeletionMark", "Edm.Boolean", "true")
    if ($kind -eq "ChartOfAccounts") { $props += ,@("Type", "Edm.String", "true") }
    if ($kind -eq "ChartOfCharacteristicTypes") { $props += ,@("ValueType", "StandardODATA.TypeDescription", "true") }
    if ($kind -eq "ExchangePlan") {
        $props += ,@("SentNo", "Edm.Int64", "true")
        $props += ,@("ReceivedNo", "Edm.Int64", "true")
        $props += ,@("ExchangeDate", "Edm.DateTime", "true")
    }
    if ($kind -eq "BusinessProcess") {
        $props += ,@("Completed", "Edm.Boolean", "true")
        $props += ,@("Started", "Edm.Boolean", "true")
        $props += ,@("HeadTask_Key", "Edm.Guid", "true")
    }
    if ($kind -eq "Task") {
        $props += ,@("BusinessProcess", "Edm.String", "true")
        $props += ,@("RoutePoint", "Edm.String", "true")
        $props += ,@("Executed", "Edm.Boolean", "true")
        $tails += ,@("BusinessProcess_Type", "true")
        $tails += ,@("RoutePoint_Type", "true")
        $open = $true
    }
    # реквизиты (у задачи сначала реквизиты адресации)
    $colls = @()
    if ($kind -eq "Task") { $colls += "РеквизитыАдресации" }
    $colls += "Реквизиты"
    foreach ($cn in $colls) {
        $coll = $null; try { $coll = P $o $cn } catch {}
        if ($coll) {
            $ca = Collect-Attrs $coll $null $null
            $props += $ca.props
            foreach ($t in $ca.tails) { $tails += ,@($t[0], $t[1]) }
            $streams += $ca.streams
            if ($ca.open) { $open = $true }
        }
    }
    # признаки учёта плана счетов — булевы свойства
    if ($kind -eq "ChartOfAccounts") {
        try { foreach ($pa in (P $o "ПризнакиУчета")) { $props += ,@([string](P $pa "Имя"), "Edm.Boolean", "true") } } catch {}
    }
    # разделитель данных (SaaS): свойство после реквизитов, в ключ не входит
    $sep = Get-SeparatorFor $script:curFn
    if ($sep) { $props += ,@($sep.name, $sep.type, "true") }
    # табличные части
    $tch = $null; try { $tch = P $o "ТабличныеЧасти" } catch {}
    if ($tch) { foreach ($ts in $tch) { $props += ,(Emit-TabSection $en $ts) } }
    # план счетов: виды субконто — ComplexType ExtDimensionTypes (без EntityType)
    if ($kind -eq "ChartOfAccounts") {
        $ctProps = @(,@("LineNumber","Edm.Int64","true")) + ,@("ExtDimensionType_Key","Edm.Guid","true") + ,@("Predefined","Edm.Boolean","true") + ,@("TurnoversOnly","Edm.Boolean","true")
        try { foreach ($pa in (P $o "ПризнакиУчетаСубконто")) { $ctProps += ,@([string](P $pa "Имя"), "Edm.Boolean", "true") } } catch {}
        Add-ComplexType ($en + "_ExtDimensionTypes") $ctProps
        $ct = "Collection(StandardODATA." + $en + "_ExtDimensionTypes)"
        $props += ,@("ExtDimensionTypes", $ct, "true")
    }
    foreach ($t in $tails) { $props += ,@($t[0], "Edm.String", $t[1]) }
    foreach ($s in $streams) { $props += ,$s }
    Emit-Entity $en @("Ref_Key") $props $open
}

function Emit-Document($o, $en) {
    $props = @(,@("Ref_Key","Edm.Guid","false")) + ,@("DataVersion","Edm.String","true")
    $numLen = 0; try { $numLen = [int](PE $o "ДлинаНомера" "NumberLength") } catch {}
    if ($numLen -gt 0) { $props += ,@("Number", (Get-NumberEdmStd $o), "true") }
    $props += ,@("Date", "Edm.DateTime", "true")
    $props += ,@("DeletionMark", "Edm.Boolean", "true")
    $props += ,@("Posted", "Edm.Boolean", "true")
    $tails = @(); $streams = @(); $open = $false
    $ca = Collect-Attrs (P $o "Реквизиты") $null $null
    $props += $ca.props
    foreach ($t in $ca.tails) { $tails += ,@($t[0], $t[1]) }
    $streams += $ca.streams
    if ($ca.open) { $open = $true }
    # разделитель данных (SaaS): свойство после реквизитов, в ключ не входит
    $sep = Get-SeparatorFor $script:curFn
    if ($sep) { $props += ,@($sep.name, $sep.type, "true") }
    $tch = $null; try { $tch = P $o "ТабличныеЧасти" } catch {}
    if ($tch) { foreach ($ts in $tch) { $props += ,(Emit-TabSection $en $ts) } }
    foreach ($t in $tails) { $props += ,@($t[0], "Edm.String", $t[1]) }
    foreach ($s in $streams) { $props += ,$s }
    Emit-Entity $en @("Ref_Key") $props $open
}

function Emit-Journal($o, $en) {
    $props = @(,@("Ref","Edm.String","false")) + ,@("Type","Edm.String","true")
    $props += ,@("Date", "Edm.DateTime", "true")
    $props += ,@("DeletionMark", "Edm.Boolean", "true")
    $props += ,@("Number", "Edm.String", "true")
    $props += ,@("Posted", "Edm.Boolean", "true")
    $tails = @(); $streams = @(); $open = $true   # Ref составной — OpenType всегда
    # тип графы через COM напрямую не читается (замер 11.08): восстанавливаем как
    # объединение внутренних представлений (VSI) типов одноимённых реквизитов
    # регистрируемых документов; >1 различного описания типов → составное
    # (строка + _Type — замер 11.08: Организация/СуммаДокумента реестра торговых
    # документов), не нашлось ни одного → строка
    $docAttrs = @()   # список хешей имя->реквизит для каждого регистрируемого документа
    $rd = $null; try { $rd = P $o "РегистрируемыеДокументы" } catch { try { $rd = P $o "RegisteringDocuments" } catch {} }
    if ($rd) {
        foreach ($d in $rd) {
            $attrs = @{}
            try { foreach ($a in (P $d "Реквизиты")) { $attrs[[string](P $a "Имя")] = $a } } catch {}
            $docAttrs += ,$attrs
        }
    }
    $gr = $null; try { $gr = P $o "Графы" } catch { try { $gr = P $o "Columns" } catch {} }
    if ($gr) {
        foreach ($g in $gr) {
            $gn = [string](P $g "Имя")
            $seen = @{}
            $first = $null
            foreach ($attrs in $docAttrs) {
                if ($attrs.ContainsKey($gn)) {
                    $a = $attrs[$gn]
                    $v = ""
                    try { $v = ([string](M $ib "ValueToStringInternal" @((P $a "Тип")))) -replace '\s+','' } catch {}
                    if (-not $seen.ContainsKey($v)) { $seen[$v] = 1; if (-not $first) { $first = $a } }
                }
            }
            if (-not $first) { $chosen = @{ main=@(,@($gn,"Edm.String")); tail=@(); stream=@(); composite=$false } }
            elseif ($seen.Count -gt 1) {
                $chosen = @{ main=@(,@($gn,"Edm.String")); tail=@($gn + "_Type"); stream=@(); composite=$true }
            } else { $chosen = Map-Attr $first $gn }
            foreach ($m in $chosen.main) { $props += ,@($m[0], $m[1], "true") }
            foreach ($t in $chosen.tail) { $tails += ,@($t, "true") }
            foreach ($s in $chosen.stream) { $streams += ,@($s, "Edm.Stream", "true") }
        }
    }
    $tails += ,@("Ref_Type", "false")
    foreach ($t in $tails) { $props += ,@($t[0], "Edm.String", $t[1]) }
    foreach ($s in $streams) { $props += ,$s }
    Emit-Entity $en @("Ref", "Ref_Type") $props $open
}

function Emit-Constant($o, $en) {
    $mp = Map-Attr $o "Value"
    $props = @()
    foreach ($m in $mp.main) { $props += ,@($m[0], $m[1], "true") }
    # разделённые константы (SaaS): ключ — разделитель вместо SurrogateKey,
    # свойство-разделитель идёт сразу за Value (форма из живого $metadata УТ 11)
    $key = @("SurrogateKey")
    $sep = Get-SeparatorFor $script:curFn
    if ($sep) {
        $key = @($sep.name)
        $props += ,@($sep.name, $sep.type, "false")
    } else {
        $props += ,@("SurrogateKey", "Edm.Int16", "false")
    }
    foreach ($t in $mp.tail) { $props += ,@($t, "Edm.String", "true") }
    foreach ($s in $mp.stream) { $props += ,@($s, "Edm.Stream", "true") }
    Emit-Entity $en $key $props $mp.composite
}
# Разделители данных (SaaS): общие реквизиты с РазделениеДанных=Разделять.
# Разделённым считается объект, входящий в состав разделителя с Использование=Использовать
# (значение Авто разделение не включает — замер 11.08 на УТ 11: иначе разделёнными
# выглядели бы все 665 констант вместо 9). Возвращает @{name;type} или $null.
$script:separators = $null
function Get-SeparatorFor($fullName) {
    if ($null -eq $script:separators) {
        $script:separators = @{}
        try {
            foreach ($cr in (P $md "ОбщиеРеквизиты")) {
                $sep = Enum-Val $cr "РазделениеДанных" "DataSeparation"
                if ($sep -notlike "*Разделять*" -and $sep -notlike "*Separat*") { continue }
                if ($sep -like "*Не*разделять*" -or $sep -like "*Not*") { continue }
                $sn = [string](P $cr "Имя")
                $smp = Map-Attr $cr $sn
                $st = "Edm.Int64"
                if ($smp.main.Count -gt 0) { $st = $smp.main[0][1] }
                # Автоиспользование=Использовать: составные элементы с Авто считаются
                # используемыми, НО платформа показывает такой разделитель в OData только
                # у планов обмена (замер 11.08, УТ 11: 19/19 планов с Авто получили
                # ОбластьДанныхОсновныеДанные, а 187 документов/317 справочников с Авто —
                # нет). Явное Использование=Использовать показывается у любого вида.
                $auto = Enum-Val $cr "Автоиспользование" "AutoUse"
                $autoUse = ($auto -like "*Использовать*" -or $auto -like "*Use*") -and ($auto -notlike "*Не*")
                $cont = $null; try { $cont = P $cr "Состав" } catch {}
                if (-not $cont) { continue }
                foreach ($el in $cont) {
                    try {
                        $use = Enum-Val $el "Использование" "Use"
                        $used = ($use -eq "Использовать" -or $use -eq "Use")
                        $emo = $null; try { $emo = P $el "Метаданные" } catch { try { $emo = P $el "Metadata" } catch {} }
                        if (-not $used -and $autoUse -and $emo) {
                            $cls = ((Full-Name $emo) -split '\.')[0]
                            if (($use -like "*Авто*" -or $use -like "*Auto*") -and ($cls -eq "ПланОбмена" -or $cls -eq "ExchangePlan")) { $used = $true }
                        }
                        if (-not $used) { continue }
                        $emo = $null; try { $emo = P $el "Метаданные" } catch { try { $emo = P $el "Metadata" } catch {} }
                        if ($emo) {
                            $fn = Full-Name $emo
                            $script:separators[$fn] = @{ name=$sn; type=$st }
                        }
                    } catch {}
                }
            }
        } catch { $script:separators = @{} }
    }
    if ($script:separators.ContainsKey($fullName)) { return $script:separators[$fullName] }
    return $null
}

function Emit-InformationRegister($o, $en) {
    $mode = Enum-Val $o "РежимЗаписи" "WriteMode"
    $subordinate = ($mode -like "*Подчинение*" -or $mode -like "*Subordinat*")
    $per = Enum-Val $o "ПериодичностьРегистраСведений" "InformationRegisterPeriodicity"
    $periodic = ($per -ne "" -and $per -notlike "*Непериодич*" -and $per -notlike "*Nonperiod*")
    $recPos = ($per -like "*Позици*Регистратор*" -or $per -like "*RecorderPosition*" -or $per -like "*Recorder*")
    if (-not $subordinate) {
        # независимый: плоская сущность, ключ = [Период?] + измерения (+ их _Type)
        $keySet = New-Object 'System.Collections.Generic.HashSet[string]'
        $dims = P $o "Измерения"
        $dimNames = @(); $dimTails = @()
        foreach ($d in $dims) {
            $dn = [string](P $d "Имя")
            $mp = Map-Attr $d $dn
            $dimNames += $mp.keyMain
            foreach ($kt in $mp.keyTail) { $dimTails += $kt }
        }
        if ($periodic) { [void]$keySet.Add("Period") }
        foreach ($n in $dimNames) { [void]$keySet.Add($n) }
        foreach ($n in $dimTails) { [void]$keySet.Add($n) }
        $props = @(); $open = $false
        if ($periodic) { $props += ,@("Period", "Edm.DateTime", "false") }
        $tails = @(); $streams = @()
        foreach ($cn in @("Измерения", "Ресурсы", "Реквизиты")) {
            $coll = $null; try { $coll = P $o $cn } catch {}
            if (-not $coll) { continue }
            $ca = Collect-Attrs $coll $keySet $null
            $props += $ca.props
            foreach ($t in $ca.tails) { $tails += ,@($t[0], $t[1]) }
            $streams += $ca.streams
            if ($ca.open) { $open = $true }
        }
        # разделитель (SaaS) / SurrogateKey: свойство — после реквизитов, до хвостов _Type
        $sep = Get-SeparatorFor $script:curFn
        $key = @()
        if ($periodic) { $key += "Period" }
        $key += $dimNames
        if ($sep) { $key += $sep.name; $props += ,@($sep.name, $sep.type, "false") }
        $key += $dimTails
        # независимый регистр без измерений и периода: ключ — SurrogateKey (форма из живого $metadata)
        if ($key.Count -eq 0) {
            $key = @("SurrogateKey")
            $props += ,@("SurrogateKey", "Edm.Int16", "false")
        }
        foreach ($t in $tails) { $props += ,@($t[0], "Edm.String", $t[1]) }
        foreach ($s in $streams) { $props += ,$s }
        Emit-Entity $en $key $props $open
    } else {
        # подчинённый: базовый (набор записей) + RecordType
        if ($null -eq $script:recorders) { Build-Recorders }
        $script:recorderInfo = Get-RecorderInfo ("РегистрСведений." + ($en -replace '^InformationRegister_', ''))
        $ri = $script:recorderInfo
        Emit-RegisterBase $en ($en + "_RowType")
        # RecordType
        $rt = $en + "_RecordType"
        $recMain = if ($ri.composite) { "Recorder" } else { "Recorder_Key" }
        $keySet = New-Object 'System.Collections.Generic.HashSet[string]'
        if ($recPos) { [void]$keySet.Add($recMain); if ($ri.composite) { [void]$keySet.Add("Recorder_Type") } }
        if ($periodic) { [void]$keySet.Add("Period") }
        $dimNames = @(); $dimTails = @()
        foreach ($d in (P $o "Измерения")) {
            $dn = [string](P $d "Имя")
            $mp = Map-Attr $d $dn
            $dimNames += $mp.keyMain
            foreach ($kt in $mp.keyTail) { $dimTails += $kt; [void]$keySet.Add($kt) }
            [void]$keySet.Add($mp.keyMain)
        }
        $props = @()
        $props += ,@($recMain, $(if ($ri.composite) { "Edm.String" } else { "Edm.Guid" }), $(if ($recPos) { "false" } else { "true" }))
        if ($periodic) { $props += ,@("Period", "Edm.DateTime", "false") }
        $props += ,@("LineNumber", "Edm.Int64", "true")
        $props += ,@("Active", "Edm.Boolean", "true")
        $tails = @(); $streams = @()
        foreach ($cn in @("Измерения", "Ресурсы", "Реквизиты")) {
            $coll = $null; try { $coll = P $o $cn } catch {}
            if (-not $coll) { continue }
            $ca = Collect-Attrs $coll $keySet $null
            $props += $ca.props
            foreach ($t in $ca.tails) { $tails += ,@($t[0], $t[1]) }
            $streams += $ca.streams
        }
        if ($ri.composite) { $tails = @(,@("Recorder_Type", $(if ($recPos) { "false" } else { "true" }))) + $tails }
        foreach ($t in $tails) { $props += ,@($t[0], "Edm.String", $t[1]) }
        foreach ($s in $streams) { $props += ,$s }
        $key = @()
        if ($recPos) { $key += $recMain }
        if ($periodic) { $key += "Period" }
        $key += $dimNames
        if ($recPos -and $ri.composite) { $key += "Recorder_Type" }
        $key += $dimTails
        Emit-Entity $rt $key $props $true
        Add-ComplexType ($en + "_RowType") $props
    }
}

function Emit-MovementRegister($o, $en, $kind) {
    # РегистрНакопления / РегистрБухгалтерии / РегистрРасчета: база + RecordType
    if ($null -eq $script:recorders) { Build-Recorders }
    $clsRu = @{ "AccumulationRegister"="РегистрНакопления"; "AccountingRegister"="РегистрБухгалтерии"; "CalculationRegister"="РегистрРасчета" }[$kind]
    $script:recorderInfo = Get-RecorderInfo ($clsRu + "." + ($en -replace "^${kind}_", ""))
    $ri = $script:recorderInfo
    Emit-RegisterBase $en ($en + "_RowType")
    $rt = $en + "_RecordType"
    $recMain = if ($ri.composite) { "Recorder" } else { "Recorder_Key" }
    $key = @($recMain, "LineNumber")
    if ($ri.composite) { $key += "Recorder_Type" }
    $keySet = New-Object 'System.Collections.Generic.HashSet[string]'
    foreach ($k in $key) { [void]$keySet.Add($k) }
    $props = @()
    $props += ,@($recMain, $(if ($ri.composite) { "Edm.String" } else { "Edm.Guid" }), "false")
    $props += ,@("Period", "Edm.DateTime", "true")
    $props += ,@("LineNumber", "Edm.Int64", "false")
    $props += ,@("Active", "Edm.Boolean", "true")
    if ($kind -eq "AccumulationRegister") {
        $vr = Enum-Val $o "ВидРегистра" "RegisterKind"
        if ($vr -like "*Остатки*" -or $vr -like "*Balance*") { $props += ,@("RecordType", "Edm.String", "true") }
    }
    if ($kind -eq "AccountingRegister") {
        $corr = $false; try { $corr = [bool](PE $o "Корреспонденция" "Correspondence") } catch {}
        if ($corr) { $props += ,@("AccountDr_Key", "Edm.Guid", "true"); $props += ,@("AccountCr_Key", "Edm.Guid", "true") }
        else { $props += ,@("Account_Key", "Edm.Guid", "true") }
    }
    $tails = @(); $streams = @()
    if ($kind -eq "AccountingRegister") {
        # измерения/ресурсы: балансовые — как есть, небалансовые — пары Dr/Cr
        foreach ($cn in @("Измерения", "Ресурсы")) {
            $coll = $null; try { $coll = P $o $cn } catch {}
            if (-not $coll) { continue }
            foreach ($a in $coll) {
                $bal = $false; try { $bal = [bool](PE $a "Балансовый" "Balanced") } catch {}
                $suffixes = if ($bal) { @($null) } else { @("Dr", "Cr") }
                foreach ($sfx in $suffixes) {
                    $an = [string](P $a "Имя") + $sfx
                    $mp = Map-Attr $a $an
                    foreach ($m in $mp.main) { $props += ,@($m[0], $m[1], "true") }
                    foreach ($t in $mp.tail) { $tails += ,@($t, "true") }
                    foreach ($s in $mp.stream) { $streams += ,@($s, "Edm.Stream", "true") }
                }
            }
        }
        $ca = Collect-Attrs (P $o "Реквизиты") $null $null
        $props += $ca.props
        foreach ($t in $ca.tails) { $tails += ,@($t[0], $t[1]) }
        $streams += $ca.streams
    } else {
        foreach ($cn in @("Измерения", "Ресурсы", "Реквизиты")) {
            $coll = $null; try { $coll = P $o $cn } catch {}
            if (-not $coll) { continue }
            $ca = Collect-Attrs $coll $null $null
            $props += $ca.props
            foreach ($t in $ca.tails) { $tails += ,@($t[0], $t[1]) }
            $streams += $ca.streams
        }
    }
    if ($ri.composite) { $tails = @(,@("Recorder_Type", "false")) + $tails }
    foreach ($t in $tails) { $props += ,@($t[0], "Edm.String", $t[1]) }
    foreach ($s in $streams) { $props += ,$s }
    Emit-Entity $rt $key $props $true
    Add-ComplexType ($en + "_RowType") $props
}

# ==== статические ComplexType-справочники (их читают ссылки вида StandardODATA.TypeDescription) ====
function Emit-HelperComplexTypes {
    $helpers = @(
        @("TypeDescription", @(
            @("Types", "Collection(Edm.String)", "false"),
            @("NumberQualifiers", "StandardODATA.NumberQualifiers", "false"),
            @("StringQualifiers", "StandardODATA.StringQualifiers", "false"),
            @("DateQualifiers", "StandardODATA.DateQualifiers", "false"),
            @("BinaryDataQualifiers", "StandardODATA.BinaryDataQualifiers", "false"))),
        @("NumberQualifiers", @(
            @("AllowedSign", "Edm.String", "false"),
            @("Digits", "Edm.Int16", "false"),
            @("FractionDigits", "Edm.Int16", "false"))),
        @("StringQualifiers", @(
            @("AllowedLength", "Edm.String", "false"),
            @("Length", "Edm.Int64", "false"))),
        @("DateQualifiers", @(@("DateFractions", "Edm.String", "false"))),
        @("BinaryDataQualifiers", @(
            @("AllowedLength", "Edm.String", "false"),
            @("Length", "Edm.Int64", "false")))
    )
    foreach ($h in $helpers) { Add-ComplexType $h[0] $h[1] }
}

# ==== шапка XML ====
Add-Line '<?xml version="1.0" encoding="UTF-8"?>'
Add-Line '<edmx:Edmx xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx" Version="1.0">'
Add-Line "`t<edmx:DataServices xmlns:m=`"http://schemas.microsoft.com/ado/2007/08/dataservices/metadata`" m:DataServiceVersion=`"3.0`" m:MaxDataServiceVersion=`"3.0`">"
Add-Line "`t`t<Schema xmlns=`"http://schemas.microsoft.com/ado/2009/11/edm`" Namespace=`"StandardODATA`">"

# ==== основной цикл по составу ====
$t0 = Get-Date
$i = 0
foreach ($o in $comp) {
    $i++
    $fn = ""
    try { $fn = Full-Name $o } catch { $fn = "" }
    if (-not $fn) { "SKIP=(объект #$i)|нет полного имени"; $script:skipCount++; continue }
    $parts = $fn -split '\.'
    $cls = $parts[0]; $nm = $parts[1]
    if ($cls -eq "Перечисление" -or $cls -eq "Enum") { continue }  # перечисления сущностями не публикуются
    if (-not $prefix.ContainsKey($cls)) { "SKIP=$fn|неподдерживаемый класс"; $script:skipCount++; continue }
    $en = $prefix[$cls] + "_" + $nm
    if ($excludeSet.Contains($fn) -or $excludeSet.Contains($en)) { continue }
    $script:curFn = $fn
    $script:curEnt = $en
    if (($i % 200) -eq 0) { "... $i объектов, $([int]((Get-Date) - $t0).TotalSeconds) c" }
    try {
        switch ($prefix[$cls]) {
            "Catalog"                    { Emit-CatalogLike $o $en "Catalog"; break }
            "Document"                   { Emit-Document $o $en; break }
            "DocumentJournal"            { Emit-Journal $o $en; break }
            "Constant"                   { Emit-Constant $o $en; break }
            "InformationRegister"        { Emit-InformationRegister $o $en; break }
            "AccumulationRegister"       { Emit-MovementRegister $o $en "AccumulationRegister"; break }
            "AccountingRegister"         { Emit-MovementRegister $o $en "AccountingRegister"; break }
            "CalculationRegister"        { Emit-MovementRegister $o $en "CalculationRegister"; break }
            "ChartOfAccounts"            { Emit-CatalogLike $o $en "ChartOfAccounts"; break }
            "ChartOfCharacteristicTypes" { Emit-CatalogLike $o $en "ChartOfCharacteristicTypes"; break }
            "ChartOfCalculationTypes"    { Emit-CatalogLike $o $en "ChartOfCalculationTypes"; break }
            "ExchangePlan"               { Emit-CatalogLike $o $en "ExchangePlan"; break }
            "BusinessProcess"            { Emit-CatalogLike $o $en "BusinessProcess"; break }
            "Task"                       { Emit-CatalogLike $o $en "Task"; break }
        }
    } catch {
        $msg = $_.Exception.Message
        if ($msg.Length -gt 120) { $msg = $msg.Substring(0, 120) }
        "SKIP=$fn|$($msg -replace "`r?`n", ' ')"
        $script:skipCount++
    }
}

# ==== ComplexType (потребители не читают — для валидности ссылок Collection(...)) ====
Emit-HelperComplexTypes
foreach ($ct in $script:cts) {
    Add-Line ("`t`t<ComplexType Name=`"" + $ct[0] + "`">")
    foreach ($ln in $ct[1]) { Add-Line $ln }
    Add-Line "`t`t</ComplexType>"
}

# ==== контейнер с EntitySet (бутстреп-контур сервера читает их) ====
Add-Line "`t`t<EntityContainer Name=`"EnterpriseV8`" m:IsDefaultEntityContainer=`"true`">"
foreach ($s in $script:sets) { Add-Line ("`t`t`t<EntitySet Name=`"" + $s + "`" EntityType=`"StandardODATA." + $s + "`"/>") }
Add-Line "`t`t</EntityContainer>"
Add-Line "`t`t</Schema>"
Add-Line "`t</edmx:DataServices>"
Add-Line "</edmx:Edmx>"

[IO.File]::WriteAllBytes($OUT, [byte[]](0xEF,0xBB,0xBF) + [Text.Encoding]::UTF8.GetBytes($sb.ToString()))
"ENTITY-COUNT=$($script:entityCount)"
"SET-COUNT=$($script:sets.Count)"
"SKIP-COUNT=$($script:skipCount)"
"ELAPSED=$([int]((Get-Date) - $t0).TotalSeconds)s"
"RESULT=OK"
exit 0
