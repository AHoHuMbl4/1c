# 1C read-only gateway (Ubuntu-сторона)

Вся защита read-only — на Ubuntu. На Винде ничего кастомного: штатный MCP Toolkit на `127.0.0.1:6003` + SSH (оба уже есть).

## Топология (соединение по IP, без туннеля — проверено на живой системе 2026-07-22)

```
Windows (stock): 1C + MCP Toolkit → слушает сетевой интерфейс :6003 (под админом; Bearer-токен)
Роутер 192.168.56.1: проброс :6003 → Windows-тулкит (настраивает владелец на своей железке)

Ubuntu LXC 192.168.56.42 (наш контроль):
  1c-gateway.service  gateway.py :6010  →  http://192.168.56.1:6003  (deny-by-default, только execute_query+read)
  «второй мозг»       ходит на 127.0.0.1:6010, зовёт только execute_query
```

## Три слоя защиты (все на нашей стороне)
1. **Сеть.** 6003 доступен только внутри доверенной сети LXC через роутер `.1`; наружу не торчит. Bearer-токен обязателен (без него тулкит отдаёт 401 — проверено).
2. **Gateway.** `gateway.py` — deny-by-default allowlist: пропускает `initialize`/`tools/list`/`ping` и `tools/call` ТОЛЬКО для read-инструментов (`execute_query`, `get_metadata`, …). `execute_code` и всё прочее отбивается до 1С.
3. **Фундамент.** Язык запросов 1С не имеет DML — `execute_query` физически не пишет.

## Развёртывание (по команде владельца; на серверах ничего не меняем без неё)

```bash
# 1. Разложить код и конфиг
install -D gateway.py /opt/1c-gateway/gateway.py
cat > /etc/1c-gateway.env <<EOF
GW_TOOLKIT_TOKEN=<Bearer тулкита из credentials/mcp-toolkit.env>
GW_UPSTREAM=http://192.168.56.1:6003
EOF
chmod 600 /etc/1c-gateway.env

# 2. systemd
cp systemd/1c-gateway.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now 1c-gateway

# 3. Проверка
curl -s http://127.0.0.1:6010/health                       # {"status":"gateway-ok"}
# execute_query проходит; execute_code режется на прокси (не доходит до 1С).
```

## Конфиг (env)
| Переменная | Дефолт | Смысл |
|---|---|---|
| `GW_LISTEN_HOST/PORT` | `127.0.0.1:6010` | где слушает прокси (для мозга) |
| `GW_UPSTREAM` | `http://192.168.56.1:6003` | адрес тулкита (проброс на роутере .1) |
| `GW_TOOLKIT_TOKEN` | — | Bearer тулкита (обязателен) |
| `GW_GATEWAY_TOKEN` | пусто | если задан — мозг обязан предъявить этот Bearer прокси |
| allowlist методов/инструментов | в коде | deny-by-default; правится в `gateway.py` |

## Проверка whitelist (после запуска)
- `tools/call execute_query` → данные ✅
- `tools/call execute_code` → `{"error":{"message":"tool not allowed (read-only gateway): execute_code"}}`, до 1С не ушло ✅
- любой метод вне списка → отказ ✅
