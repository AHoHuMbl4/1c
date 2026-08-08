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

**Ubuntu-релей `89.23.101.22` — ✅ В БОЮ с 08.08 (DNS переключён, FreeBSD выведен):**
- `[замер 08.08]` боевая проверка по публичному DNS (с FreeBSD, свежий резолв):
  health с сертом `ut` → **200 `packet-server-ok`**, без серта — обрыв TLS;
  ACME-проба через домен (файл из webroot по HTTP) — отвечает, продление lego
  будет работать. Туннель — юнит `1c-gate-tunnel-ubuntu.service` (active).
- Ubuntu 26.04, 2 vCPU / 2 ГБ; HAProxy 3.2.9 + lego + fail2ban 1.1.0 из apt.
- Конфиги версионируются в [`relay/`](relay/) — порт FreeBSD-версии: `haproxy.cfg`
  (`:443` TLS+mTLS → `127.0.0.1:6022`, `:80` ACME/редирект), `acmewww.service`
  (webroot на 127.0.0.1:8402), `lego.yml` + `lego-renew.{sh,service,timer}` +
  `deploy-certs.sh` (pem → `systemctl reload haproxy`), `jail.local`.
- Сертификат LE и аккаунт скопированы с FreeBSD — TLS жил до переключения DNS.
- Юзер `gate-tunnel` (nologin), тот же ключ с `restrict,port-forwarding,
  permitlisten="127.0.0.1:6022"`.
- fail2ban: стоковый фильтр Ubuntu рабочий (замер 08.08: бан брутфорсера
  подтверждён); в `ignoreip` внесены свои IP (NAT основного сервера, FreeBSD) —
  иначе jail отсекает наш же туннель (проверено на себе: 4 неудачных входа при
  разведке → бан основного NAT-IP, чинилось ProxyJump через FreeBSD).
- Зона `Europe/Moscow`, timesyncd синхронизирован.
- Приватная сеть хостера: у релея `10.1.1.4` (решение владельца 08.08 — позже
  туда же подключат основной сервер; транспорт можно будет перевести на неё).

**FreeBSD `201.34.130.46` — ⛔ ВЫВЕДЕНА из контура 08.08** (DNS ушёл на
Ubuntu-релей, туннельный юнит `1c-gate-tunnel.service` на основном сервере
остановлен; VM удаляется владельцем). Исторически (06.08–08.08) держала:
HAProxy 3.4 TLS → `127.0.0.1:6022`, lego, юзер `gate-tunnel`, fail2ban+pf,
зону MSK/ntpd. Конфиги остаются в [`freebsd/`](freebsd/) как образец порта.

**Ubuntu — ✅ туннель в бою (06.08, юнит `1c-gate-tunnel.service`):**
`active` + `enabled`, `Restart=always`. `[замер]` сквозная проба через туннель
ЮНИТА (пробный бэкенд на :6090): `https://1c-gate.timpul.ru/health` → HTTP 200,
`xff` клиента на месте. Строки `connect_to 127.0.0.1 port 6090: failed` в журнале
юнита — health-чеки HAProxy, дошедшие по туннелю: пока приёмник не выкачен,
это норма (снаружи — 502/503). Запуск — `setup-ubuntu-tunnel.sh` (выполнен
владельцем 06.08); перезапуск — `systemctl restart 1c-gate-tunnel` (polkit `1c-*`).

Остался выкат `packet_server` с `PACKET_LISTEN=127.0.0.1:6090` (компонент
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
| **Задержка пути (07.08)** | ping 30/30, 0 % потерь, avg 46,5 мс, джиттер 7 мс |
| **Пропускная сырого пути (07.08)** | Ubuntu→FreeBSD **~260 Мбит/с**, FreeBSD→Ubuntu **~62 Мбит/с** (асимметрия провайдера) |
| **Пропускная туннеля (07.08)** | **~37 Мбит/с** (100 МБ через 6022→6090): чанк 32 МБ ≈ 7 с, гигабайтная посылка ≈ 3,5 мин |
| **Живучесть (07.08)** | `systemctl restart` → юнит поднялся за ~6 с, 6022 на FreeBSD вернулся сам; юнит прожил 16+ ч до этого без вмешательств |

**Как проверять в эксплуатации:** `systemctl status 1c-gate-tunnel` (жив ли туннель) ·
`ssh root@201.34.130.46 'sockstat -4 -l | grep 6022'` (удалённый конец) ·
`curl -w '%{http_code} %{time_total}s' https://1c-gate.timpul.ru/health` (200 = вся цепочка,
502/503 = туннель жив, приёмник не выкачен; недоступность = смотреть туннель и HAProxy).

## Ловушки (замеры 06.08)

- `service … start` по ssh без редиректа держит канал (daemon наследует stdout) —
  звать с `</dev/null >/dev/null 2>&1 &`.
- HAProxy без `daemon` в конфиге — foreground: pidfile не пишется, rc-status врёт.
- `redirect` в HAProxy обрабатывается РАНЬШЕ `use_backend` — ACME-путь чинится
  условием `if !acme`, иначе HTTP-01 никогда не дойдёт до webroot.
- `pkill -f <строка>` убивает и саму команду, если строка есть в её тексте —
  паттерн писать так, чтобы не совпадал с собственной командной строкой, или
  убивать по pid (`HOW_NOT_TO`).

## mTLS на приёме (включён 07.08, контракт §8)

Приём пакетов — **два фактора**: клиентский сертификат + Bearer-токен базы.

- `bind :443 ssl crt … verify required ca-file /usr/local/etc/haproxy/1c-packet-ca.crt`:
  без клиентского сертификата, подписанного проектным CA (`CN=1c-packet-ca`),
  TLS-рукопожатие обрывается. `[замер 07.08]`: `curl` без серта → код 56 (обрыв),
  `openssl s_client` показывает `Acceptable client CA: CN=1c-packet-ca` (запрос
  сертификата идёт); с сертом базы (`CN=ut`) — handshake проходит.
- CN клиентского сертификата уходит бэкенду заголовком `X-SSL-Client-CN`
  (`%[ssl_c_s_dn(cn)]`) — приёмник сверяет его с базой.
- CA-гриф на FreeBSD: `/usr/local/etc/haproxy/1c-packet-ca.crt` (644);
  источник — `/etc/1c-packet-ca.crt` на Ubuntu (копия в `work/packet/ca/`),
  выдаёт компонент пакетов (`packet_kit.py`). Клиентские серты баз —
  `work/packet/kit/<base>/`.
- Порт 80 не тронут: ACME/редирект Let's Encrypt работает как раньше.
- 🔴 Внешние проверки домена теперь требуют сертификат: без него домен молчит
  (обрыв TLS) — это норма. Проверка в эксплуатации:
  `curl --cert work/packet/kit/<base>/client.crt --key …/client-key.pem
  https://1c-gate.timpul.ru/health` → `packet-server-ok`.

## Защита узла: fail2ban (поднят 06.08)

- `py312-fail2ban` + **pf** (был не загружен): `/etc/pf.conf` = `anchor "f2b/*"` +
  `pass all` (фильтрации кроме банов нет, локаута быть не может по построению).
- Jail `sshd` → `/var/log/auth.log`, бан в таблицу pf `f2b-sshd` (1h/10m/5).
- 🔴 **Ловушка FreeBSD 16** `[замер]`: OpenSSH ≥9.8 логирует как `sshd-session`,
  стоковый фильтр (`_daemon = sshd`) не матчил **0 из 7706 строк** — fail2ban
  работал вхолостую. Чинится `filter.d/sshd.local` с `_daemon = sshd(?:-session)?`
  (после правки 3833 совпадения). Проверено живьём: свежий фейл засчитывается
  (`Currently failed: 1`), бан/анбан в pf-таблице ходит (`banip 203.0.113.7`).
- Автозапуск: `pf_enable`, `fail2ban_enable` в `rc.conf`. Конфиги —
  [`freebsd/fail2ban/`](freebsd/fail2ban/) + `freebsd/pf.conf`.

## Доступ сессии

- FreeBSD root: ssh-ключ `~/.ssh-bridge/fbsd_ed25519` (пароль удалён 06.08).
- Ключ туннеля: `~/.ssh-bridge/gate-tunnel.ed25519` → `/etc/ssh/` (скриптом);
  на FreeBSD — только `permitlisten 127.0.0.1:6022`.
- Приватный WG-ключ Ubuntu: `~/.ssh-bridge/wg-ubuntu-private.key` — лежит на
  случай разблокировки UDP; `setup-ubuntu-wg.sh` поднимал `wg-quick@wg0`
  (10.77.0.2, работает только исходящее плечо).
