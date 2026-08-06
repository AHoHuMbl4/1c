# Канал Ubuntu ↔ FreeBSD: приёмник `1c-gate.timpul.ru`

Связь этого сервера (витрина, SereneDB, packet_server) с FreeBSD `201.34.130.46`
(`msk-1-vm-uqv5`, FreeBSD 16.0-CURRENT) — опорным узлом с белым IP и доменом
приёмника пакетного транспорта (`docs/PLAN_MVP_PACKET_TRANSPORT.md`).

## Транспорт: SSH reverse-туннель (TCP). 🔴 WireGuard замерен нерабочим 06.08

`[замер 06.08]` **возвратный UDP от FreeBSD до этого сервера не доходит вовсе** —
ни WireGuard-хендшейки (инициации приходят, ответы уходят с FreeBSD и не доезжают),
ни обычный UDP-эхо-ответ (проба plain-text: запрос дошёл, ответ нет, 2 порта).
Исходящий UDP Ubuntu→FreeBSD при этом ходит (3/3), DNS-ответы от 8.8.8.8 доезжают —
то есть режется именно путь «Европа → РФ-сервер» для UDP (гипотеза владельца с
первого сообщения — подтвердилась). TCP по тому же пути чистый в обе стороны
(SSH и HTTPS замерены). Вывод: WireGuard/AmneziaWG/udp2raw-in-UDP здесь мёртвы —
обфускация не лечит потерю ВСЕХ возвратных UDP-дейтаграмм. Конфиги WG сохранены
(`freebsd/wg0.conf.sample`, `setup-ubuntu-wg.sh`) на случай разблокировки; на
FreeBSD `wireguard_enable=NO`, юнит `wg-quick@wg0` на Ubuntu можно остановить.

**Рабочая схема (замерена 06.08 end-to-end, HTTP 200, 0,34 с):**

```
Windows (TLS) → https://1c-gate.timpul.ru:443  [DNS → 201.34.130.46]
  → HAProxy на FreeBSD — TLS-терминация (Let's Encrypt, lego)
  → 127.0.0.1:6022 — SSH reverse-туннель (ssh -R, инициатор Ubuntu, TCP/22)
  → packet_server на Ubuntu 127.0.0.1:6090 (наружу не светит)
```

Входящих портов ни на Ubuntu, ни на Windows не нужно: обе стороны только
инициируют исходящие соединения. Клиентский IP доезжает `X-Forwarded-For`
(замер: `xff=167.235.37.94` в ответе пробного бэкенда). Плечо FreeBSD→Ubuntu
шифрует SSH, плечо Windows→FreeBSD — TLS; сквозная шифрованность сохраняется.

🔴 **Порт приёмника — 6090, не 6021:** `127.0.0.1:6021` занят шлюзом второй базы
(`1c-odata-gateway@ut`, его `/health` отвечает `odata-gateway-ok`). При выкате
`packet_server` задавать `PACKET_LISTEN=127.0.0.1:6090` (дефолт в коде —
соседняя сессия).

## Состояние сторон

**FreeBSD — ✅ поднята целиком (06.08):**
- HAProxy 3.4: `:443` TLS → `127.0.0.1:6022` (`httpchk GET /health` ждёт 200);
  `:80` — ACME HTTP-01 (webroot через `acmewww` на 127.0.0.1:8402) + редирект.
  Пока туннель/приёмник не подняты — 503, это ожидаемое состояние.
- Сертификат LE `CN=1c-gate.timpul.ru` выпущен (`lego`); продление —
  `periodic weekly 604.lego` + `deploy-certs.sh` (pem → `haproxy reload`).
- Юзер `gate-tunnel` (nologin): ssh-ключ с `restrict,port-forwarding,
  permitlisten="127.0.0.1:6022"` — ключ только для проброса, шелла нет.
- Автозапуск: `rc.conf` — `haproxy_enable`, `acmewww_enable` (wireguard — NO).
- Конфиги версионируются в [`freebsd/`](freebsd/): `haproxy.conf`, `lego.yml`,
  `lego.sh`, `deploy-certs.sh`, `rc.d/acmewww`, сниппеты, `wg0.conf.sample`
  (без ключей — ключи только на серверах).

**Ubuntu — root-шаг владельца (постоянный туннель):**
```
sudo sh ubuntu/wireguard/setup-ubuntu-tunnel.sh
```
Ставит `/etc/ssh/gate-tunnel.ed25519` (600) + юнит `1c-gate-tunnel.service`
(ssh -R, `Restart=always`), гасит ручной туннель пробы, включает и стартует.
После этого сессия может перезапускать юнит сама (`systemctl restart
1c-gate-tunnel` — правило polkit на `1c-*`).

Затем — выкат `packet_server` с `PACKET_LISTEN=127.0.0.1:6090` (компонент
соседней сессии): health-чек HAProxy позеленеет, цепочка замкнётся.

## Замеры 06.08

| Проверка | Итог |
|---|---|
| UDP Ubuntu → FreeBSD 51820 | 3/3 дошли |
| UDP FreeBSD → Ubuntu (NAT) | 0/3 — нет прямого входа |
| WG-хендшейк | инициации доходят, ответы уходят с FreeBSD и НЕ доезжают |
| UDP-эхо (plain text, 2 порта) | запрос дошёл, ответ не дошёл — возвратный UDP мёртв |
| TCP Ubuntu ↔ FreeBSD | чист в обе стороны (SSH, HTTPS) |
| Сквозная цепочка домен → HAProxy → туннель → :6090 | **HTTP 200, 0,34 с**, `X-Forwarded-For` доезжает |

## Ловушки (замеры 06.08)

- `service … start` по ssh без редиректа держит канал (daemon наследует stdout) —
  звать с `</dev/null >/dev/null 2>&1 &`.
- HAProxy без `daemon` в конфиге — foreground: pidfile не пишется, rc-status врёт.
- `redirect` в HAProxy обрабатывается РАНЬШЕ `use_backend` — ACME-путь чинится
  условием `if !acme`, иначе HTTP-01 никогда не дойдёт до webroot.
- `pkill -f <строка>` убивает и саму команду, если строка есть в её тексте —
  паттерн писать так, чтобы не совпадал с собственной командной строкой, или
  убивать по pid (`HOW_NOT_TO`).

## Доступ сессии

- FreeBSD root: ssh-ключ `~/.ssh-bridge/fbsd_ed25519` (пароль удалён 06.08).
- Ключ туннеля: `~/.ssh-bridge/gate-tunnel.ed25519` → `/etc/ssh/` (скриптом);
  на FreeBSD — только `permitlisten 127.0.0.1:6022`.
- Приватный WG-ключ Ubuntu: `~/.ssh-bridge/wg-ubuntu-private.key` — лежит на
  случай разблокировки UDP; `setup-ubuntu-wg.sh` поднимал `wg-quick@wg0`
  (10.77.0.2, работает только исходящее плечо).
