# ai-ext.ps1 — расширение 1С с генерируемой читающей ролью (ступень 2 ресерча).
# Универсально: объекты перечисляются из ЖИВЫХ метаданных базы через COM,
# реальные UUID — из /DumpConfigToFiles -ConfigDumpInfoOnly той же базы,
# шаблоны GeneratedType — частичным дампом (-listFile) по объекту каждого класса,
# режим совместимости и основной язык — из дампа корня конфигурации.
# Права — только Read+View. Конфигурация не меняется (поддержка вендора не трогается).
#
# Порядок: COM-перечисление → ConfigDumpInfo → частичный дамп шаблонов →
# генерация файлов → /LoadConfigFromFiles -Extension → /UpdateDBCfg -Extension
# (обязателен! без него расширение хранится, но не применено — /hs/ даёт 404) →
# снятие БезопасныйРежим+предупреждений через COM (иначе права роли не действуют) →
# vrd (httpServices publishExtensionsByDefault) → HTTP-сервис самоназначения роли →
# контрольные пробы OData до/после.
$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$script:hadFail = $false

# ==== параметры: из переменных окружения (так вызывает установщик) ====
$U = $env:OC1C_EXT_USER          # логин администратора ИБ
$P = $env:OC1C_EXT_PWD           # его пароль (может быть пустым)
$BASE = $env:OC1C_EXT_BASE       # путь к файловой базе, напр. C:\1C-bases\ut_demo
$READER = $env:OC1C_EXT_READER   # пользователь-читатель
$VRD = $env:OC1C_EXT_VRD         # путь к default.vrd публикации (необязательно)
$POOL = $env:OC1C_EXT_POOL       # имя пула IIS (необязательно)
$AGENTINI = $env:OC1C_EXT_AGENTINI  # путь к agent.ini для проб (необязательно)
if (-not $READER) { $READER = "ai_reader" }
if (-not $POOL) { $POOL = "1c-odata" }
if (-not $AGENTINI) { $AGENTINI = 'C:\1c\packet\agent.ini' }
if (-not $U -or -not $BASE) {
    "FATAL: задайте OC1C_EXT_USER / OC1C_EXT_PWD / OC1C_EXT_BASE (логин-пароль администратора ИБ, путь к базе)"
    exit 1
}
# ======================================================================

$ExtName  = "AIReadOnly"
$RoleName = "AIReadAll"

# Алиас публикации (кейс K2, 11.08: при --alias 1ctox пробы уходили на /1c —
# чужую публикацию — и шаг 14 ложно падал с HTTP 401). По умолчанию "1c".
$ALIAS = $env:OC1C_EXT_ALIAS
if (-not $ALIAS) { $ALIAS = "1c" }

$platformExe = Get-ChildItem 'C:\Program Files*\1cv8\*\bin\1cv8.exe' -ErrorAction SilentlyContinue |
    Sort-Object { [version]($_.Parent.Parent.Name) } | Select-Object -Last 1 -ExpandProperty FullName
if (-not $platformExe) { "FATAL: платформа 1С не найдена"; exit 1 }
$isX86 = $platformExe -like "*Program Files (x86)*"
if ($isX86 -and [Environment]::Is64BitProcess) {
    $w = 'C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe'
    & $w -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath
    exit $LASTEXITCODE
}
"PLATFORM: $platformExe"

$GP = [Reflection.BindingFlags]::GetProperty -bor [Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::Instance
$IM = [Reflection.BindingFlags]::InvokeMethod -bor [Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::Instance
$SP = [Reflection.BindingFlags]::SetProperty -bor [Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::Instance
function P($o, $n) { [__ComObject].InvokeMember($n, $GP, $null, $o, @()) }

# пробы OData под читателем (пароль — из agent.ini, если есть; иначе из env)
$odataUser = $READER; $odataPass = ""
if ($env:OC1C_EXT_READER_PWD) { $odataPass = $env:OC1C_EXT_READER_PWD }
if (Test-Path $AGENTINI) {
    foreach ($ln in [IO.File]::ReadAllLines($AGENTINI)) {
        if ($ln -match '^\s*odata_user\s*=\s*(.+)$') { $odataUser = $Matches[1].Trim() }
        if ($ln -match '^\s*odata_password\s*=\s*(.*)$') { $odataPass = $Matches[1].Trim() }
    }
}
"ODATA-USER: $odataUser (пароль из agent.ini: $(if ($odataPass) {'есть'} else {'НЕТ'}))"
$sec = New-Object SecureString; foreach ($ch in $odataPass.ToCharArray()) { $sec.AppendChar($ch) }
$cred = New-Object PSCredential($odataUser, $sec)
function Odata-Probe($entity) {
    try {
        Invoke-WebRequest -Uri "http://localhost/$ALIAS/odata/standard.odata/$entity`?`$top=1" -Credential $cred -UseBasicParsing -TimeoutSec 60 | Out-Null
        return "200"
    } catch {
        $r = $_.Exception.Response
        if ($r) { return [string][int]$r.StatusCode } else { return "ERR:" + $_.Exception.Message.Substring(0, [Math]::Min(60, $_.Exception.Message.Length)) }
    }
}

# классы: русская секция COM, англ. класс, каталог дампа, рус. ед. для НайтиПоПолномуИмени
$sections = @(
    @("Справочники", "Catalog", "Catalogs", "Справочник"),
    @("Документы", "Document", "Documents", "Документ"),
    @("ЖурналыДокументов", "DocumentJournal", "DocumentJournals", "ЖурналДокументов"),
    @("Константы", "Constant", "Constants", "Константа"),
    @("РегистрыСведений", "InformationRegister", "InformationRegisters", "РегистрСведений"),
    @("РегистрыНакопления", "AccumulationRegister", "AccumulationRegisters", "РегистрНакопления"),
    @("РегистрыБухгалтерии", "AccountingRegister", "AccountingRegisters", "РегистрБухгалтерии"),
    @("РегистрыРасчета", "CalculationRegister", "CalculationRegisters", "РегистрРасчета"),
    @("ПланыСчетов", "ChartOfAccounts", "ChartsOfAccounts", "ПланСчетов"),
    @("ПланыВидовХарактеристик", "ChartOfCharacteristicTypes", "ChartsOfCharacteristicTypes", "ПланВидовХарактеристик"),
    @("ПланыВидовРасчета", "ChartOfCalculationTypes", "ChartsOfCalculationTypes", "ПланВидовРасчета"),
    @("ПланыОбмена", "ExchangePlan", "ExchangePlans", "ПланОбмена"),
    @("БизнесПроцессы", "BusinessProcess", "BusinessProcesses", "БизнесПроцесс"),
    @("Задачи", "Task", "Tasks", "Задача")
)

# 1. перечисление метаданных
$connector = New-Object -ComObject "V83.COMConnector"
$ib = $connector.Connect("File=`"$BASE`";Usr=`"$U`";Pwd=`"$P`";")
$md = P $ib "Метаданные"
$objects = New-Object System.Collections.Generic.List[string]
foreach ($s in $sections) {
    try {
        foreach ($o in (P $md $s[0])) { $objects.Add($s[1] + "." + (P $o "Имя")) }
    } catch { "SECTION-SKIP " + $s[0] + ": " + $_.Exception.Message.Substring(0, 60) }
}
"OBJECTS: $($objects.Count)"
if ($objects.Count -eq 0) { "FATAL: метаданные пусты"; exit 1 }

# 2. пробы ДО: первые объекты нескольких классов под читателем
$probeObjs = @()
foreach ($want in @("InformationRegister", "Catalog", "Document", "Constant")) {
    foreach ($o in $objects) { if ($o.StartsWith($want + ".")) { $probeObjs += $o; break } }
}
$before401 = @()
foreach ($o in $probeObjs) {
    $e = $o.Replace(".", "_")
    $code = Odata-Probe $e
    "BEFORE $e -> $code"
    if ($code -ne "200") { $before401 += $o }
}

# 3a. реальные UUID объектов основной конфигурации (ConfigDumpInfoOnly — быстрый
# дамп одной карты id; ExtendedConfigurationObject контролируется при /UpdateDBCfg)
$cdiDir = "$env:TEMP\AIReadOnly-cdi"
Remove-Item $cdiDir -Recurse -Force -ErrorAction SilentlyContinue
$aC = 'DESIGNER',"/F$BASE","/N`"$U`"","/P`"$P`"",'/DumpConfigToFiles',$cdiDir,'-ConfigDumpInfoOnly','/Out',"$env:TEMP\aiext-cdi.log",'/DisableStartupDialogs','/DisableStartupMessages'
$pC = Start-Process -FilePath $platformExe -ArgumentList $aC -Wait -PassThru
"CDI-EXIT=$($pC.ExitCode)"
$cdiFile = "$cdiDir\ConfigDumpInfo.xml"
if (-not (Test-Path $cdiFile)) { "FATAL: ConfigDumpInfo не получен"; exit 1 }
$idMap = @{}
foreach ($mm in [regex]::Matches([IO.File]::ReadAllText($cdiFile), '<Metadata name="([^".]+\.[^".]+)" id="([0-9a-fA-F-]+)"')) {
    $idMap[$mm.Groups[1].Value] = $mm.Groups[2].Value
}
"IDMAP: $($idMap.Count) объектов верхнего уровня"

# 3b. шаблоны GeneratedType + режим совместимости + основной язык:
# частичный дамп по одному объекту каждого класса и корня Configuration
$firstOfClass = @{}
foreach ($o in $objects) { $c = $o.Split('.')[0]; if (-not $firstOfClass.ContainsKey($c)) { $firstOfClass[$c] = $o } }
$listFile = "$env:TEMP\AIReadOnly-pdump-list.txt"
$listContent = (($firstOfClass.Values | Sort-Object) -join "`n") + "`nConfiguration`n"
[IO.File]::WriteAllText($listFile, $listContent, (New-Object System.Text.UTF8Encoding($true)))
$pdump = "$env:TEMP\AIReadOnly-pdump"
Remove-Item $pdump -Recurse -Force -ErrorAction SilentlyContinue
$a0 = 'DESIGNER',"/F$BASE","/N`"$U`"","/P`"$P`"",'/DumpConfigToFiles',$pdump,'-listFile',$listFile,'-format','Hierarchical','/Out',"$env:TEMP\aiext-pdump.log",'/DisableStartupDialogs','/DisableStartupMessages'
$p0 = Start-Process -FilePath $platformExe -ArgumentList $a0 -Wait -PassThru
"PDUMP-EXIT=$($p0.ExitCode)"
if ($p0.ExitCode -ne 0) {
    $lg = [IO.File]::ReadAllText("$env:TEMP\aiext-pdump.log")
    "PDUMP-LOG: " + $lg.Substring(0, [Math]::Min(600, $lg.Length)); exit 1
}
$cfgMainFile = "$pdump\Configuration.xml"
if (-not (Test-Path $cfgMainFile)) { "FATAL: Configuration.xml основной не выгружен"; exit 1 }
$cfgMain = [IO.File]::ReadAllText($cfgMainFile)
$compat = "Version8_3_12"
$mm = [regex]::Match($cfgMain, '<CompatibilityMode>([^<]+)</CompatibilityMode>')
if ($mm.Success) { $compat = $mm.Groups[1].Value }
"COMPAT-USE: $compat"
$mainLang = "Русский"
$mm = [regex]::Match($cfgMain, '<DefaultLanguage>Language\.([^<]+)</DefaultLanguage>')
if ($mm.Success) { $mainLang = $mm.Groups[1].Value }
"LANG-USE: $mainLang"
$templates = @{}
foreach ($c in $firstOfClass.Keys) {
    $objName = $firstOfClass[$c].Split('.')[1]
    $dirName = ($sections | Where-Object { $_[1] -eq $c })[2]
    $f = Join-Path $pdump "$dirName\$objName.xml"
    if (-not (Test-Path $f)) { "FATAL TEMPLATE-MISSING: $c ($f)"; exit 1 }
    $x = [IO.File]::ReadAllText($f)
    $tpl = @()
    foreach ($mm in [regex]::Matches($x, '<xr:GeneratedType name="([^".]+)\.([^".]+)" category="([^"]+)"')) {
        if ($mm.Groups[2].Value -eq $objName) { $tpl += ,@($mm.Groups[1].Value, $mm.Groups[3].Value) }
    }
    if ($tpl.Count -eq 0) { "FATAL TEMPLATE-EMPTY: $c"; exit 1 }
    $templates[$c] = $tpl
    "TEMPLATE $c : $($tpl.Count) типов"
}

# 4. файлы расширения
$root = Join-Path $env:TEMP "AIReadOnly-src"
Remove-Item $root -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$root\Roles\$RoleName\Ext" | Out-Null
New-Item -ItemType Directory -Force "$root\Languages" | Out-Null
New-Item -ItemType Directory -Force "$root\HTTPServices\AISetup\Ext" | Out-Null
$NS = 'xmlns="http://v8.1c.ru/8.3/MDClasses" xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config" xmlns:v8="http://v8.1c.ru/8.1/data/core" xmlns:xr="http://v8.1c.ru/8.3/xcf/readable" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" version="2.20"'
function Write-Utf8Bom($path, $text) {
    [IO.File]::WriteAllBytes($path, [byte[]](0xEF,0xBB,0xBF) + [Text.Encoding]::UTF8.GetBytes($text))
}

# заимствованные объекты
$childLines = New-Object System.Text.StringBuilder
foreach ($o in $objects) {
    $cls, $nm = $o.Split('.')
    $dirName = ($sections | Where-Object { $_[1] -eq $cls })[2]
    $dir = Join-Path $root $dirName
    New-Item -ItemType Directory -Force $dir | Out-Null
    $gt = New-Object System.Text.StringBuilder
    if ($cls -eq "ExchangePlan") {  # планам обмена нужен ThisNode в InternalInfo (замер 10.08)
        [void]$gt.Append("`t`t`t<xr:ThisNode>$([guid]::NewGuid())</xr:ThisNode>`n")
    }
    foreach ($pr in $templates[$cls]) {
        [void]$gt.Append("`t`t`t<xr:GeneratedType name=`"$($pr[0]).$nm`" category=`"$($pr[1])`"><xr:TypeId>$([guid]::NewGuid())</xr:TypeId><xr:ValueId>$([guid]::NewGuid())</xr:ValueId></xr:GeneratedType>`n")
    }
    $u1 = [guid]::NewGuid().ToString()
    if (-not $idMap.ContainsKey($o)) { "FATAL: нет реального UUID для $o (ConfigDumpInfo)"; exit 1 }
    $u2 = $idMap[$o]
    $co = "`t`t<ChildObjects/>`n"
    if ($cls -eq "Constant") { $co = "" }  # у константы элемента ChildObjects нет (замер 10.08)
    $stub = "<?xml version=`"1.0`" encoding=`"UTF-8`"?>`n<MetaDataObject $NS>`n`t<$cls uuid=`"$u1`">`n`t`t<InternalInfo>`n" + $gt.ToString() + "`t`t</InternalInfo>`n`t`t<Properties>`n`t`t`t<ObjectBelonging>Adopted</ObjectBelonging>`n`t`t`t<Name>$nm</Name>`n`t`t`t<Comment/>`n`t`t`t<ExtendedConfigurationObject>$u2</ExtendedConfigurationObject>`n`t`t</Properties>`n" + $co + "`t</$cls>`n</MetaDataObject>`n"
    Write-Utf8Bom (Join-Path $dir "$nm.xml") $stub
    [void]$childLines.Append("`t`t`t<$cls>$nm</$cls>`n")
}

$ii = @"
		<InternalInfo>
			<xr:ContainedObject><xr:ClassId>9cd510cd-abfc-11d4-9434-004095e12fc7</xr:ClassId><xr:ObjectId>225193c1-ba53-407d-b373-f46f8b16de81</xr:ObjectId></xr:ContainedObject>
			<xr:ContainedObject><xr:ClassId>9fcd25a0-4822-11d4-9414-008048da11f9</xr:ClassId><xr:ObjectId>68c5be0d-7692-460d-b3d8-942921fdddb3</xr:ObjectId></xr:ContainedObject>
			<xr:ContainedObject><xr:ClassId>e3687481-0a87-462c-a166-9f34594f9bba</xr:ClassId><xr:ObjectId>7de0ba5c-c840-4e2f-b384-9483b995473f</xr:ObjectId></xr:ContainedObject>
			<xr:ContainedObject><xr:ClassId>9de14907-ec23-4a07-96f0-85521cb6b53b</xr:ClassId><xr:ObjectId>57643625-714a-461b-899f-01768c815857</xr:ObjectId></xr:ContainedObject>
			<xr:ContainedObject><xr:ClassId>51f2d5d8-ea4d-4064-8892-82951750031e</xr:ClassId><xr:ObjectId>6233e9db-de73-47b0-9b06-4698526302c9</xr:ObjectId></xr:ContainedObject>
			<xr:ContainedObject><xr:ClassId>e68182ea-4237-4383-967f-90c1e3370bc7</xr:ClassId><xr:ObjectId>48e8699d-b0ea-4d9f-8b85-200e6c8ac7d7</xr:ObjectId></xr:ContainedObject>
			<xr:ContainedObject><xr:ClassId>fb282519-d103-4dd3-bc12-cb271d631dfc</xr:ClassId><xr:ObjectId>20301740-cf02-4bee-bfa3-5f679eaf9ae0</xr:ObjectId></xr:ContainedObject>
		</InternalInfo>
"@
$cfg = @"
<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject $NS>
	<Configuration uuid="a433a1ba-1111-4111-8111-26612e947f96">
$ii		<Properties>
			<ObjectBelonging>Adopted</ObjectBelonging>
			<Name>$ExtName</Name>
			<Synonym><v8:item><v8:lang>ru</v8:lang><v8:content>$ExtName</v8:content></v8:item></Synonym>
			<Comment/>
			<ConfigurationExtensionPurpose>AddOn</ConfigurationExtensionPurpose>
			<KeepMappingToExtendedConfigurationObjectsByIDs>true</KeepMappingToExtendedConfigurationObjectsByIDs>
			<NamePrefix>AI</NamePrefix>
			<ConfigurationExtensionCompatibilityMode>$compat</ConfigurationExtensionCompatibilityMode>
			<DefaultRunMode>ManagedApplication</DefaultRunMode>
			<ScriptVariant>Russian</ScriptVariant>
			<Version>1.0.0</Version>
			<DefaultLanguage>Language.$mainLang</DefaultLanguage>
		</Properties>
		<ChildObjects>
			<Language>$mainLang</Language>
			<Role>$RoleName</Role>
			<HTTPService>AISetup</HTTPService>
$($childLines.ToString())		</ChildObjects>
	</Configuration>
</MetaDataObject>
"@
Write-Utf8Bom "$root\Configuration.xml" $cfg
$langIdKey = "Language.$mainLang"
if (-not $idMap.ContainsKey($langIdKey)) { "FATAL: нет реального UUID для $langIdKey"; exit 1 }
$langId = $idMap[$langIdKey]
$lang = @"
<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject $NS>
	<Language uuid="ed1506c0-2222-4222-8222-945bab8ed3fd">
		<InternalInfo/>
		<Properties>
			<ObjectBelonging>Adopted</ObjectBelonging>
			<Name>$mainLang</Name>
			<Comment/>
			<ExtendedConfigurationObject>$langId</ExtendedConfigurationObject>
			<LanguageCode>ru</LanguageCode>
		</Properties>
	</Language>
</MetaDataObject>
"@
Write-Utf8Bom "$root\Languages\$mainLang.xml" $lang
$role = @"
<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject $NS>
	<Role uuid="a7181713-3333-4333-8333-ab9998503308">
		<Properties><Name>$RoleName</Name><Synonym/><Comment/></Properties>
	</Role>
</MetaDataObject>
"@
Write-Utf8Bom "$root\Roles\$RoleName.xml" $role
$sb = New-Object System.Text.StringBuilder
[void]$sb.Append('<?xml version="1.0" encoding="UTF-8"?>' + "`n" + '<Rights xmlns="http://v8.1c.ru/8.2/roles" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">' + "`n")
foreach ($o in $objects) {
    [void]$sb.Append("`t<object><name>$o</name><right><name>Read</name><value>true</value></right><right><name>View</name><value>true</value></right></object>`n")
}
[void]$sb.Append('</Rights>')
Write-Utf8Bom "$root\Roles\$RoleName\Ext\Rights.xml" $sb.ToString()

# HTTP-сервис самоназначения: сеанс HTTP-сервиса применяет расширение — роль
# видна и записывается читателю (COM-сеанс расширение не применяет, замер 10.08).
# Заодно снимает БезопасныйРежим с расширения и отвечает на ?check=РегистрСведений.Х
# диагностикой ПравоДоступа.
$svc = @"
<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject $NS>
	<HTTPService uuid="93b52b96-1872-4900-931f-30f172dcdeed">
		<Properties>
			<Name>AISetup</Name>
			<Synonym/>
			<Comment/>
			<RootURL>ai-setup</RootURL>
			<ReuseSessions>DontUse</ReuseSessions>
			<SessionMaxAge>20</SessionMaxAge>
		</Properties>
		<ChildObjects>
			<URLTemplate uuid="4959a157-4c22-4802-b76b-d4ba8ff3752f">
				<Properties>
					<Name>Setup</Name>
					<Synonym/>
					<Comment/>
					<Template>/setup</Template>
				</Properties>
				<ChildObjects>
					<Method uuid="dfc323e9-33e4-49a0-b3f5-7264cb26003d">
						<Properties>
							<Name>GET</Name>
							<Synonym/>
							<Comment/>
							<HTTPMethod>GET</HTTPMethod>
							<Handler>SetupGET</Handler>
						</Properties>
					</Method>
				</ChildObjects>
			</URLTemplate>
		</ChildObjects>
	</HTTPService>
</MetaDataObject>
"@
Write-Utf8Bom "$root\HTTPServices\AISetup.xml" $svc
$module = @'
Функция SetupGET(Запрос)
	Ответ = Новый HTTPСервисОтвет(200);
	Попытка
		Роль = Метаданные.Роли.Найти("AIReadAll");
		Если Роль = Неопределено Тогда
			Ответ.УстановитьТелоИзСтроки("FAIL: роль AIReadAll не найдена в метаданных сеанса");
			Возврат Ответ;
		КонецЕсли;
		П = ПользователиИнформационнойБазы.НайтиПоИмени("ai_reader");
		Если П = Неопределено Тогда
			Ответ.УстановитьТелоИзСтроки("FAIL: пользователь ai_reader не найден");
			Возврат Ответ;
		КонецЕсли;
		Если НЕ П.Роли.Содержит(Роль) Тогда
			П.Роли.Добавить(Роль);
			П.Записать();
		КонецЕсли;
		ИмяПров = Запрос.ПараметрыЗапроса.Получить("check");
		Если ИмяПров <> Неопределено Тогда
			Мд = Метаданные.НайтиПоПолномуИмени(ИмяПров);
			Если Мд = Неопределено Тогда
				Ответ.УстановитьТелоИзСтроки("OK role=assigned; FAIL: объект " + ИмяПров + " не найден");
			Иначе
				Чт = ПравоДоступа("Чтение", Мд, П);
				Изм = ПравоДоступа("Изменение", Мд, П);
				Ответ.УстановитьТелоИзСтроки("OK role=assigned; check=" + ИмяПров + "; read=" + Чт + "; write=" + Изм);
			КонецЕсли;
		Иначе
			Ответ.УстановитьТелоИзСтроки("OK role=assigned");
		КонецЕсли;
	Исключение
		Ответ.УстановитьТелоИзСтроки("FAIL: " + ОписаниеОшибки());
	КонецПопытки;
	Возврат Ответ;
КонецФункции
'@
Write-Utf8Bom "$root\HTTPServices\AISetup\Ext\Module.bsl" $module
"FILES-WRITTEN: $root"

# 5. загрузка расширения
$a = 'DESIGNER',"/F$BASE","/N`"$U`"","/P`"$P`"",'/LoadConfigFromFiles',$root,'-Extension',$ExtName,'/Out',"$env:TEMP\aiext-load.log",'/DisableStartupDialogs','/DisableStartupMessages'
$p1 = Start-Process -FilePath $platformExe -ArgumentList $a -Wait -PassThru
"LOAD-EXIT=$($p1.ExitCode)"
if ($p1.ExitCode -ne 0) {
    $log = [IO.File]::ReadAllText("$env:TEMP\aiext-load.log")
    "LOAD-LOG: " + $log.Substring(0, [Math]::Min(900, $log.Length))
    exit 1
}

# 5.5 применение расширения к конфигурации БД (без этого /LoadConfigFromFiles
# расширение хранится, но не применено — HTTP-сервис даёт 404; ресерч 10.08)
$aU = 'DESIGNER',"/F$BASE","/N`"$U`"","/P`"$P`"",'/UpdateDBCfg','-Extension',$ExtName,'/Out',"$env:TEMP\aiext-upd.log",'/DisableStartupDialogs','/DisableStartupMessages'
$pU = Start-Process -FilePath $platformExe -ArgumentList $aU -Wait -PassThru
"UPDATEDB-EXIT=$($pU.ExitCode)"
if ($pU.ExitCode -ne 0) {
    $lg = [IO.File]::ReadAllText("$env:TEMP\aiext-upd.log")
    "UPDATEDB-LOG: " + $lg.Substring(0, [Math]::Min(900, $lg.Length))
    "FATAL: расширение не применено к конфигурации БД"
    exit 1
}

# 5.6 снятие БезопасныйРежим + предупреждений защиты: без этого права от роли
# расширения не действуют (ресерч гл. 3.6: на файловой базе вариант работает
# только при БезопасныйРежим=Ложь). Порядок важен: сначала выключаем
# предупреждение защиты, иначе Записать требует интерактивного подтверждения.
$flagsOk = $false
try {
    $mgrE = [__ComObject].InvokeMember("РасширенияКонфигурации", $GP, $null, $ib, @())
    $exts = [__ComObject].InvokeMember("Получить", $IM, $null, $mgrE, @())
    foreach ($e in $exts) {
        $nm = [__ComObject].InvokeMember("Имя", $GP, $null, $e, @())
        if ($nm -ne $ExtName) { continue }
        $prot = [__ComObject].InvokeMember("ЗащитаОтОпасныхДействий", $GP, $null, $e, @())
        [__ComObject].InvokeMember("ПредупреждатьОбОпасныхДействиях", $SP, $null, $prot, @($false)) | Out-Null
        [__ComObject].InvokeMember("БезопасныйРежим", $SP, $null, $e, @($false)) | Out-Null
        [__ComObject].InvokeMember("Записать", $IM, $null, $e, @()) | Out-Null
        $flagsOk = $true
    }
} catch { "EXT-FLAGS FAIL: " + $_.Exception.Message.Substring(0, [Math]::Min(200, $_.Exception.Message.Length)) }
if ($flagsOk) { "EXT-FLAGS: БезопасныйРежим=Ложь, предупреждения=Ложь" } else { "EXT-FLAGS: НЕ ЗАПИСАНЫ"; $script:hadFail = $true }

# 6. публикация HTTP-сервисов расширений в default.vrd + рецикл пула
$vrd = "C:\inetpub\1c\default.vrd"
if ($VRD) { $vrd = $VRD }
if (-not (Test-Path $vrd)) {
    $cand = Get-ChildItem 'C:\inetpub' -Recurse -Filter '*.vrd' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cand) { $vrd = $cand.FullName; "VRD-FOUND-BY-SEARCH: $vrd" }
}
if (Test-Path $vrd) {
    $txt = [IO.File]::ReadAllText($vrd)
    if ($txt -notmatch "httpServices") {
        $txt = $txt -replace "</point>", ('<httpServices publishByDefault="true" publishExtensionsByDefault="true"/>' + "`n</point>")
        [IO.File]::WriteAllBytes($vrd, [byte[]](0xEF,0xBB,0xBF) + [Text.Encoding]::UTF8.GetBytes($txt))
        "VRD-PATCHED"
    } else { "VRD-ALREADY" }
    $appcmd = "$env:SystemRoot\system32\inetsrv\appcmd.exe"
    if (Test-Path $appcmd) {
        & $appcmd list apppool $POOL 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { & $appcmd recycle apppool $POOL | Out-Null; "POOL-RECYCLED" } else { "POOL-$POOL-НЕ-НАЙДЕН" }
    }
    Start-Sleep -Seconds 8
} else { "VRD-NOT-FOUND: $vrd (веб-публикации нет — endpoint пропускаем)"; $script:hadFail = $true }

# 7. самоназначение роли + проверка ПравоДоступа из сеанса с расширением
if (Test-Path $vrd) {
    $secAdmin = New-Object SecureString; foreach ($ch in $P.ToCharArray()) { $secAdmin.AppendChar($ch) }
    $credAdmin = New-Object PSCredential($U, $secAdmin)
    $checkRu = ""
    $checkSrc = $null
    if ($before401.Count -gt 0) { $checkSrc = $before401[0] } elseif ($probeObjs.Count -gt 0) { $checkSrc = $probeObjs[0] }
    if ($checkSrc) {
        $ccls, $cnm = $checkSrc.Split('.')
        $ruCls = ($sections | Where-Object { $_[1] -eq $ccls })[3]
        $checkRu = "$ruCls.$cnm"
    }
    $url = "http://localhost/$ALIAS/hs/ai-setup/setup"
    if ($checkRu) { $url += "?check=" + [uri]::EscapeDataString($checkRu) }
    try {
        $resp = Invoke-WebRequest -Uri $url -Credential $credAdmin -UseBasicParsing -TimeoutSec 120
        $body = $resp.Content
        if ($body -is [byte[]]) { $body = [Text.Encoding]::UTF8.GetString($body) }
        "SETUP-ENDPOINT: " + $body
        if ($body -notmatch "role=assigned") { $script:hadFail = $true }
    } catch {
        $script:hadFail = $true
        $r = $_.Exception.Response
        if ($r) { "SETUP-ENDPOINT HTTP " + [int]$r.StatusCode } else { "SETUP-ENDPOINT ERR: " + $_.Exception.Message.Substring(0, [Math]::Min(120, $_.Exception.Message.Length)) }
    }
}

# 8. пробы ПОСЛЕ
foreach ($o in $probeObjs) {
    $e = $o.Replace(".", "_")
    "AFTER $e -> " + (Odata-Probe $e)
}
if ($script:hadFail) { "RESULT: FAIL"; exit 2 }
"RESULT: OK"
"DONE"
