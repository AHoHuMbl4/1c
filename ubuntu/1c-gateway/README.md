# 1C read-only gateway (Ubuntu-сторона)

Вся защита read-only — на Ubuntu. На Винде ничего кастомного: штатный MCP Toolkit на `127.0.0.1:6003` + SSH (оба уже есть).

## Топология

```
Windows 10.8.0.58 (stock):
  1C + MCP Toolkit  →  127.0.0.1:6003   (под админом; Bearer-токен; localhost-only)
  OpenSSH-сервер                          (уже стоит)

Ubuntu LXC 192.168.56.42 (наш контроль):
  1c-tunnel.service   ssh -L 127.0.0.1:16003 → win:6003   (порт 6003 наружу не торчит)
  1c-gateway.service  gateway.py :6010  → deny-by-default, только execute_query + read
  «второй мозг»       ходит на 127.0.0.1:6010, зовёт только execute_query
```

## Три слоя защиты (все на нашей стороне)
1. **Сеть.** 6003 на Винде — только localhost; достижим лишь через SSH-туннель (аутентификация по ключу). Из сети execute_code не вызвать — порт закрыт.
2. **Gateway.** `gateway.py` — deny-by-default allowlist: пропускает `initialize`/`tools/list`/`ping` и `tools/call` ТОЛЬКО для read-инструментов (`execute_query`, `get_metadata`, …). `execute_code` и всё прочее отбивается до 1С.
3. **Фундамент.** Язык запросов 1С не имеет DML — `execute_query` физически не пишет.

## Развёртывание (по команде владельца; на серверах ничего не меняем без неё)

```bash
# 1. Ключ Ubuntu → Windows (один раз): сгенерить на LXC, публичную часть добавить
#    в C:\ProgramData\ssh\administrators_authorized_keys на Винде.
ssh-keygen -t ed25519 -f /root/.ssh/id_1c_windows -N "" -C "lxc-1c-gateway"

# 2. Разложить код и конфиг
install -D gateway.py /opt/1c-gateway/gateway.py
printf 'GW_TOOLKIT_TOKEN=<Bearer тулкита из credentials/mcp-toolkit.env>\n' > /etc/1c-gateway.env
chmod 600 /etc/1c-gateway.env

# 3. systemd
cp systemd/1c-tunnel.service systemd/1c-gateway.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now 1c-tunnel 1c-gateway

# 4. Проверка
curl -s http://127.0.0.1:6010/health                       # {"status":"gateway-ok"}
# execute_query проходит; execute_code режется на прокси (не доходит до 1С).
```

## Конфиг (env)
| Переменная | Дефолт | Смысл |
|---|---|---|
| `GW_LISTEN_HOST/PORT` | `127.0.0.1:6010` | где слушает прокси (для мозга) |
| `GW_UPSTREAM` | `http://127.0.0.1:16003` | локальный конец SSH-туннеля к тулкиту |
| `GW_TOOLKIT_TOKEN` | — | Bearer тулкита (обязателен) |
| `GW_GATEWAY_TOKEN` | пусто | если задан — мозг обязан предъявить этот Bearer прокси |
| allowlist методов/инструментов | в коде | deny-by-default; правится в `gateway.py` |

## Проверка whitelist (после запуска)
- `tools/call execute_query` → данные ✅
- `tools/call execute_code` → `{"error":{"message":"tool not allowed (read-only gateway): execute_code"}}`, до 1С не ушло ✅
- любой метод вне списка → отказ ✅
