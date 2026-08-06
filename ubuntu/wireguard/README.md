# WireGuard-мост Ubuntu ↔ FreeBSD

Мост между этим сервером (витрина, SereneDB) и FreeBSD `201.34.130.46`
(`msk-1-vm-uqv5`, FreeBSD 16.0-CURRENT) — опорный узел с белым IP для будущего
канала с Windows на проде (план `docs/PLAN_MVP_PACKET_TRANSPORT.md`).

## Топология (замерено 06.08)

- **FreeBSD** — белый IP прямо на `vtnet0`, файрволов нет. Сторона с
  `ListenPort = 51820/udp`. Адрес в туннеле: **10.77.0.1**.
- **Ubuntu (этот сервер)** — белого IP НЕТ: `eth0` = `192.168.56.42/24`,
  исходящий NAT провайдера (`167.235.37.94`). Поэтому Ubuntu — всегда
  инициатор, `PersistentKeepalive = 25` держит NAT-отображение.
  Адрес в туннеле: **10.77.0.2**.
- Туннельная подсеть: **10.77.0.0/24** (не пересекается с `192.168.56.0/24`).

## Проверка «не режет ли провайдер UDP» [замер 06.08]

- Ubuntu → FreeBSD `51820/udp`: **3 пакета из 3 дошли** (nc-слушатель).
- FreeBSD → Ubuntu `167.235.37.94:51820/udp`: **0 из 3** — входящий UDP на
  NAT-провайдера не транслируется. UDP сам по себе не блокируется ни одной
  стороной; заблокирован именно вход на этот сервер.
- Вывод: WireGuard рабочий, но только с инициацией от Ubuntu. Это же значит,
  что предположение плана «белый IP только у Ubuntu» неверно — белый IP есть
  у FreeBSD, и для Windows за NAT узлом встречи будет именно он.

## Состояние сторон

**FreeBSD — ✅ поднято (06.08):**
- `wireguard-tools` из pkg; конфиг `/usr/local/etc/wireguard/wg0.conf` (600);
- автозапуск: `rc.conf` → `wireguard_enable=YES`, `wireguard_interfaces=wg0`;
- ключи в `/usr/local/etc/wireguard/` (600), публичный:
  `I4aSAqchQjUW7O4IC6ffrsN289r43U6Sjnfl5lKNB0E=`.

**Ubuntu — ждёт root-шаг владельца:**
```
sudo sh ubuntu/wireguard/setup-ubuntu-wg.sh
```
Скрипт ставит `wireguard-tools`, пишет `/etc/wireguard/wg0.conf` (приватный
ключ из `/home/claudedev/.ssh-bridge/wg-ubuntu-private.key`, в git его нет),
включает `wg-quick@wg0` и пингует `10.77.0.1`.

Доступ сессии к FreeBSD: ssh-ключ `~/.ssh-bridge/fbsd_ed25519`
(парольный вход после установки ключа не нужен).

## Релей `1c-gate.timpul.ru` (поднят 06.08, вторая половина дня)

`[решение]` владельца: домен приёмника смотрит на FreeBSD; FreeBSD — **бесшовный
мост**: Windows в установщике знает только `https://1c-gate.timpul.ru`, а принимает
соединения Ubuntu. Цепочка:

```
Windows (TLS) → 1c-gate.timpul.ru:443 [DNS → 201.34.130.46]
  → HAProxy на FreeBSD — TLS-терминация (Let's Encrypt, lego)
  → по туннелю wg0 → packet_server на Ubuntu 10.77.0.2:6021 (наружу не светит)
```

- **TLS терминируется на FreeBSD** (LE-сертификат, `lego` + webroot HTTP-01 через
  тот же HAProxy :80; продление — `periodic weekly 604.lego`, deploy-hook собирает
  pem и делает `service haproxy reload`). Плечо FreeBSD→Ubuntu шифрует сам
  WireGuard, поэтому сквозная шифрованность пути сохраняется.
- **Клиентский IP доезжает** заголовком `X-Forwarded-For` (`option forwardfor`) —
  замер 06.08: проба вернула реальный адрес клиента.
- **Бэкенд с проверкой живости**: `httpchk GET /health` на `10.77.0.2:6021`
  (ждёт 200; `/health` у packet_server без авторизации). Пока Ubuntu-сторона не
  поднята, релей отвечает **503 — это замеренное ожидаемое состояние**, не дефект.
- Таймауты 300 с под чанки до 64 МБ (контракт К8).
- Конфиги FreeBSD версионируются в [`freebsd/`](freebsd/): `haproxy.conf`,
  `lego.yml`, `lego.sh`, `deploy-certs.sh`, `rc.d/acmewww` (webroot-сервер
  HTTP-01 на 127.0.0.1:8402), сниппеты `rc.conf`/`periodic.conf`, `wg0.conf.sample`
  (без ключей — ключи только на серверах).
- Автозапуск на FreeBSD: `rc.conf` — `wireguard_enable`, `haproxy_enable`,
  `acmewww_enable`; продление серта — `periodic.conf` (сниппеты в `freebsd/`).
- ⚠️ Ловушка ssh: `service … start` без редиректа держит канал открытым
  (daemon наследует stdout) — сессия виснет. Звать с `</dev/null >/dev/null 2>&1 &`.
  Две причины починены: `daemon` в haproxy.conf (без него foreground, pidfile не
  пишется, rc-status врёт) и `redirect … if !acme` (redirect обрабатывается РАНЬШЕ
  use_backend — ACME-запросы улетали на https и HTTP-01 бы не прошёл).
