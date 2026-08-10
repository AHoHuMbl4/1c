@echo off
rem =====================================================================
rem  Сборка setup-1c-odata.exe
rem  БЕЗ сторонних зависимостей: компилятор входит в состав .NET Framework,
rem  который есть на любой современной Windows. Ничего ставить не нужно.
rem =====================================================================
setlocal
chcp 65001 >nul 2>&1

set "CSC=%windir%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=%windir%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if not exist "%CSC%" (
  echo [ОШИБКА] Не найден компилятор C^# ^(csc.exe^) из .NET Framework 4.
  echo          Установите .NET Framework 4.8 и повторите.
  exit /b 1
)

rem Сборка кладётся в build\ (в .gitignore): чтобы локальная сборка НИКОГДА не конфликтовала
rem с готовым dist\setup-1c-odata.exe из репозитория при git pull.
if not exist "%~dp0build" mkdir "%~dp0build"
set "OUT=%~dp0build\setup-1c-odata.exe"

echo Компилятор: %CSC%
echo Выход:      %OUT%
echo.

rem Вшивание бинарей комплекта (один exe на новую машину): если рядом есть
rem каталог embed\ с packet-agent.exe/age.exe/age-keygen.exe/zstd.exe — они
rem кладутся ресурсами внутрь exe, и установщик извлечёт их сам (Packet.cs).
rem Нет embed\ — прежнее поведение: файлы должны лежать рядом с exe.
set "RES="
if exist "%~dp0embed\packet-agent.exe" set "RES=%RES% /resource:""%~dp0embed\packet-agent.exe"",packet-agent.exe"
if exist "%~dp0embed\age.exe" set "RES=%RES% /resource:""%~dp0embed\age.exe"",age.exe"
if exist "%~dp0embed\age-keygen.exe" set "RES=%RES% /resource:""%~dp0embed\age-keygen.exe"",age-keygen.exe"
if exist "%~dp0embed\zstd.exe" set "RES=%RES% /resource:""%~dp0embed\zstd.exe"",zstd.exe"
if defined RES echo Вшиваются ресурсы из embed\: %RES%

rem Скрипт расширения чтения (шаг 14) вшивается безусловно — он всегда в репозитории.
rem Через -EncodedCommand он не влезает в лимит командной строки, поэтому ресурсом,
rem а при выполнении извлекается во временный файл (Steps.InstallAiExtension).
set "RES=%RES% /resource:""%~dp0src\ai-ext.ps1"",ai-ext.ps1"

"%CSC%" /nologo /target:exe /platform:anycpu /optimize+ /langversion:5 ^
  /win32manifest:"%~dp0src\app.manifest" ^
  /out:"%OUT%" ^
  /reference:System.dll ^
  /reference:System.Core.dll ^
  /reference:System.Xml.dll ^
  /reference:System.Xml.Linq.dll ^
  /reference:System.IO.Compression.dll ^
  /reference:System.IO.Compression.FileSystem.dll ^
  /reference:System.Web.Extensions.dll ^
  %RES% ^
  "%~dp0src\Sys.cs" "%~dp0src\Steps.cs" "%~dp0src\Packet.cs" "%~dp0src\Payload.cs" "%~dp0src\Program.cs"

if errorlevel 1 (
  echo.
  echo [ОШИБКА] Сборка не удалась.
  exit /b 1
)

echo.
echo [OK] Собрано: %OUT%
for %%F in ("%OUT%") do echo      размер: %%~zF байт
certutil -hashfile "%OUT%" SHA256 2>nul | findstr /r "^[0-9a-f]"
echo.
echo Проверить, ничего не меняя:  "%OUT%" --check
echo Справка:                     "%OUT%" --help
endlocal
