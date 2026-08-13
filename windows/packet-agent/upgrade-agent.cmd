@echo off
setlocal
chcp 65001 >nul 2>&1
rem =====================================================================
rem  Обновление агента пакетного транспорта НА МЕСТЕ (без переустановки).
rem  Меняется ТОЛЬКО packet-agent.exe: комплект, сертификат, agent.ini,
rem  задачи планировщика и накопленные данные (data\) не трогаются.
rem  ЗАПУСКАТЬ ОТ ИМЕНИ АДМИНИСТРАТОРА.
rem
rem  Использование:
rem    upgrade-agent.cmd                     — каталог C:\1c\packet, exe с S3
rem    upgrade-agent.cmd D:\мой\каталог      — нестандартный каталог агента
rem    upgrade-agent.cmd C:\1c\packet <url>  — свой адрес нового exe
rem
rem  Порядок продуман: сначала скачиваем и ПРОВЕРЯЕМ новый exe, и только
rem  потом останавливаем работающего агента — если сети нет, ничего не
rem  трогаем. Старый exe остаётся рядом (.bak): откат = переименовать назад.
rem =====================================================================

set "DIR=%~1"
if "%DIR%"=="" set "DIR=C:\1c\packet"
set "URL=%~2"
if "%URL%"=="" set "URL=https://s3.twcstorage.ru/cf8b6108-f9c9-4606-a329-07c466992020/installers/packet-agent/packet-agent.exe"

if not exist "%DIR%\packet-agent.exe" (
  echo [ОШИБКА] агент не найден: %DIR%\packet-agent.exe
  echo          укажите каталог параметром: upgrade-agent.cmd "D:\путь\к\агенту"
  exit /b 2
)

echo == 1/5 текущая версия:
"%DIR%\packet-agent.exe" --version

echo == 2/5 скачиваю новый агент
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%URL%' -OutFile '%DIR%\packet-agent.new.exe'"
if errorlevel 1 goto :fail_download
"%DIR%\packet-agent.new.exe" --version
if errorlevel 1 goto :fail_download

echo == 3/5 останавливаю демона и сторожа
schtasks /Change /TN "1C Packet Agent Watchdog" /DISABLE >nul 2>&1
schtasks /End /TN "1C Packet Agent" >nul 2>&1
taskkill /f /im packet-agent.exe >nul 2>&1
rem процесс умирает не мгновенно — mutex и файл освобождаются с задержкой
ping -n 6 127.0.0.1 >nul & rem пауза: timeout /t не работает в неинтерактивной консоли (замер 13.08)
taskkill /f /im packet-agent.exe >nul 2>&1
ping -n 3 127.0.0.1 >nul

echo == 4/5 подмена exe (старый останется рядом: packet-agent.exe.bak)
move /y "%DIR%\packet-agent.exe" "%DIR%\packet-agent.exe.bak" >nul
if errorlevel 1 goto :fail_swap
move /y "%DIR%\packet-agent.new.exe" "%DIR%\packet-agent.exe" >nul
if errorlevel 1 goto :restore
"%DIR%\packet-agent.exe" --version
if errorlevel 1 goto :restore

echo == 5/5 включаю автозапуск обратно
schtasks /Change /TN "1C Packet Agent Watchdog" /ENABLE >nul 2>&1
schtasks /Run /TN "1C Packet Agent" >nul 2>&1
echo.
echo [OK] Агент обновлён и запущен. Прежний exe: %DIR%\packet-agent.exe.bak
echo      Первый такт начнётся сразу; ход виден в C:\1c\logs\packet-agent.log
exit /b 0

:fail_download
del /q "%DIR%\packet-agent.new.exe" >nul 2>&1
echo [ОШИБКА] новый агент не скачался или не запускается — НИЧЕГО НЕ ИЗМЕНЕНО.
echo          Проверьте исходящий доступ 443/TCP и повторите.
exit /b 1

:fail_swap
del /q "%DIR%\packet-agent.new.exe" >nul 2>&1
echo [ОШИБКА] не удалось отложить старый exe (занят?) — НИЧЕГО НЕ ИЗМЕНЕНО.
echo          Убедитесь, что окно запущено от имени администратора, и повторите.
schtasks /Change /TN "1C Packet Agent Watchdog" /ENABLE >nul 2>&1
schtasks /Run /TN "1C Packet Agent" >nul 2>&1
exit /b 1

:restore
echo [ОШИБКА] новый exe не встал — ВОЗВРАЩАЮ ПРЕЖНИЙ.
move /y "%DIR%\packet-agent.exe.bak" "%DIR%\packet-agent.exe" >nul
del /q "%DIR%\packet-agent.new.exe" >nul 2>&1
schtasks /Change /TN "1C Packet Agent Watchdog" /ENABLE >nul 2>&1
schtasks /Run /TN "1C Packet Agent" >nul 2>&1
"%DIR%\packet-agent.exe" --version
exit /b 1
