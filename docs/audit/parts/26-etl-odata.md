# 26. etl-odata

## Зачем участок нужен
`windows/odata-setup` настраивает на Windows публикацию базы 1С в IIS с интерфейсом OData (только чтение) и при наличии комплекта ставит агент пакетной выгрузки. `ubuntu/1c-etl/oc_etl.py` по GET к OData-шлюзу выгружает справочники/документы в markdown и пушит их в git-репозиторий KB. Участок не отвечает на вопросы бота и не пишет в SereneDB.

## Входы
**oc_etl.py:** env `ETL_ODATA_BASE`, `ETL_KB_REPO` (обязателен), `ETL_KB_DIR`, `ETL_KB_SUBDIR`, `ETL_INCLUDE`, `ETL_EXCLUDE`, `ETL_TOP`, `ETL_SKIP_EMPTY`, `ETL_SELECTED_FILE`, `ETL_GIT_NAME`, `ETL_GIT_EMAIL`, `ETL_TIMEOUT`, `ODG_GATEWAY_TOKEN` (`ubuntu/1c-etl/oc_etl.py:60-71`, `:54-57`). systemd: `EnvironmentFile=/etc/1c-etl.env`, `ExecStart=…/oc_etl.py` (`ubuntu/1c-etl/systemd/1c-etl.service:11-12`); таймер `OnCalendar=*-*-* 03:00:00` (`1c-etl.timer:5`).

**setup-1c-odata:** CLI/`--config` ini — `--base`/`--connstr`, `--alias` (default `1c`), `--dir`, `--site`, `--admin-*`, `--reader-*`, `--scope` (default `default`), `--app-pool`, `--platform-*`, `--backup-dir`, `--no-backup`, `--ubuntu-host`/`--port`, `--open-firewall`, `--verify-url`, `--external-url`, `--force`, `--check`, `--unattended`, `--skip-scope`, `--skip-packet`, `--packet-*`, `--remove-logcfg`, `--log` (`Program.cs:1256-1330`, `Opts` `:13-44`). Пароли из `--*-password-env` читаются из env (`:1292-1295`).

## Порядок работы
**A. ETL (`main`, `oc_etl.py:232-301`)**
1. Нет `ETL_KB_REPO` → `sys.exit` (`:233-234`).
2. `ensure_repo`: clone/fetch/reset `origin/main`, git user (`:217-225`, `:236`).
3. Список сущностей: `ETL_INCLUDE` → иначе файл `ETL_SELECTED_FILE` → иначе `GET ?$format=json`, префиксы `Catalog`/`Document` с ровно одним `_` (`:114-130`, `:238`).
4. Фильтр `ETL_EXCLUDE` (`:228-229`, `:238`).
5. На сущность: при `SKIP_EMPTY` — `GET …/$count`, skip если 0 (`:244-247`); `GET …?$top&$skip` пачками до 1000, лимит `TOP` (`:140-154`).
6. Карта `Ref_Key` → представление (`:256-259`); markdown в `{KB}/{SUBDIR}/catalogs|documents/*.md` + `_index.md`; старые `.md` в этих каталогах удаляются (`:263-289`).
7. `git add/commit/push origin HEAD:main`; нет изменений — выход; push fail — exit 1 (`:291-301`).

**B. setup-1c-odata (`Run`, `Program.cs:119-900`) — 14 шагов**
1–3: admin, платформа (web/COM), база (file/CS). 4–5: IIS + W3SVC. 6: `webinst -publish` или запись `default.vrd`/`web.config` (`Steps.cs:570-649`). 7: `standardOdata enable=true` в vrd (`:915-978`). 8–10: пул, ISAPI, ACL. 11: zip-бэкап файловой базы перед составом. 12: COM `SetOdataComposition` (+ валидатор исключений). Затем опц. `manifest-gen.ps1` → `metadata.xml`. 13: HTTP-пробы корня/`$metadata`/данных. 14: `ai-ext.ps1` (роль `AIReadAll`) — внутри блока пакета до автозапуска агента, иначе после (`Program.cs:867-896`). Блок 2 `PacketSteps.Run`: комплект → mTLS → проба OData → `agent.ini` → `--smoke` → schtasks (`Packet.cs:157-520`).

## Выходы
- ETL: markdown в git KB (`KB_DIR/KB_SUBDIR`); потребители в этом участке не вызываются (комментарий в шапке `oc_etl.py:8-9` указывает на внешний индекс KB).
- setup: публикация IIS `…/<alias>/odata/standard.odata/`; файл `1c-odata-connection.txt` с `ODG_UPSTREAM`/`ODG_USER` при отсутствии пакета (`Program.cs:1094-1138`); при пакете — `C:\1c\packet\agent.ini` (`odata_url`, user/password) и демон `packet-agent.exe` (`Packet.cs:986-1009`); опц. `metadata.xml`, расширение `AIReadOnly`.

## Обращения наружу
| Что | Где | Назначение |
|---|---|---|
| HTTP GET OData (+ Bearer) | `oc_etl.py:105-111`, `:123`, `:135`, `:144` | список сущностей, `$count`, выгрузка |
| git clone/fetch/commit/push | `oc_etl.py:213-225`, `:291-297` | KB-репо |
| webinst / appcmd / netsh / schtasks | `Steps.cs:570+`, `Packet.cs:1057+` | IIS, firewall, автозапуск |
| COM через PowerShell | `Steps.SetOdataComposition` `:1944-1945`; `ValidateOdataComposition` `:2090`; `manifest-gen.ps1`; `ai-ext.ps1` | состав OData, манифест, расширение |
| HTTP GET OData Basic | `Steps.Probe` `:2297`; `ProbeDataRead` `:2406-2448` | проверка публикации |
| HTTPS GET `{receiver}/health` mTLS | `Packet.cs:713-766` | префлайт приёмника |
| `packet-agent.exe --smoke` | `Packet.cs:1114-1118` | пробная доставка |
| HTTP GET OData / Designer /hs/ai-setup | `ai-ext.ps1:98-105`, `:439-445`, `:504-510` | пробы и установка расширения |

Языковых моделей в участке нет.

## Переключатели
| Имя | Default | Чтение |
|---|---|---|
| `ETL_ODATA_BASE` | `http://127.0.0.1:6011` | `oc_etl.py:60` |
| `ETL_KB_REPO` | `""` (обязателен) | `:61` |
| `ETL_KB_DIR` / `ETL_KB_SUBDIR` | `/opt/1c-etl/kb` / `1c` | `:62-63` |
| `ETL_TOP` | `5000` | `:64` |
| `ETL_SKIP_EMPTY` | `1` (ложь: `0`/`false`/`no`/`""`) | `:65` |
| `ETL_INCLUDE` / `ETL_EXCLUDE` | пусто | `:66-67` |
| `ETL_SELECTED_FILE` | `/etc/1c-etl-selected.txt` | `:68` |
| `ETL_TIMEOUT` | `120` | `:71` |
| `ODG_GATEWAY_TOKEN` | `""` (заголовок только если непуст) | `:54-57` |
| `--scope` | `default` → все ключи `ScopeMap` | `Steps.cs:1197-1202` |
| `--check` | DryRun | `Program.cs:1275` |
| `--skip-scope` / `--skip-packet` / `--no-backup` / `--force` | false | `:1278-1283` |
| `OC1C_*` для ps1 | см. скрипты | `manifest-gen.ps1:23-27`, `ai-ext.ps1:19-32` |

## Развилки
- ETL: источник списка INCLUDE / selected-файл / discover; skip пустых; ошибка fetch → строка в `_index` «Пропущено»; нет diff → без commit (`oc_etl.py:114-122`, `:244-251`, `:292-294`).
- setup: нет admin → EXIT_NOTADMIN; RAM < 256 МБ → EXIT_PREREQ; нет web-модуля → EXIT_PREREQ; IIS needs reboot → EXIT_REBOOT (`Program.cs:128-160`, `:209-223`, `:414-423`).
- `--skip-scope` / compat≤8.3.4: состав не пишется (`:543-547`, `:568-592`).
- Корень/`$metadata` HTTP 500 + живые сущности → успех по `ProbeDataRead` + манифест (`:800-810`).
- Нет `packet-setup.json` / `--skip-packet` → агент не ставится, EXIT_OK (`Packet.cs:162-180`).
- Smoke `stale_seq` → считается успехом канала (`Packet.cs:1149-1152`).
- Фейл ai-ext не валит установку (`Steps.cs:2569`).

## Чего здесь нет
- Записи в SereneDB / витрину / корпус индекса бота.
- Вызова LLM.
- Непрерывной выгрузки из ETL кроме таймера 03:00 и oneshot-юнита.
- Регистров в ETL (`TOP_PREFIXES` только Catalog/Document, `oc_etl.py:76`).
- Создания пользователя-читателя в основном потоке без блока пакета (инструкция в Report; автосоздание — в `PacketSteps`).
- Кода самого `packet-agent` / приёмника Ubuntu / шлюза ODG — только установка и пробы.
