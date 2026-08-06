#!/bin/sh
# Поднимает WireGuard-мост Ubuntu (этот сервер) ↔ FreeBSD 201.34.130.46.
# Запускать ОТ ROOT на этом сервере:
#   sudo sh ubuntu/wireguard/setup-ubuntu-wg.sh
# Приватный ключ Ubuntu НЕ в git — читается из файла (по умолчанию
# /home/claudedev/.ssh-bridge/wg-ubuntu-private.key, можно передать путь аргументом).
set -eu

KEY_SRC="${1:-/home/claudedev/.ssh-bridge/wg-ubuntu-private.key}"
[ -f "$KEY_SRC" ] || { echo "НЕТ файла приватного ключа: $KEY_SRC" >&2; exit 1; }

if ! command -v wg >/dev/null 2>&1; then
    apt-get update
    apt-get install -y wireguard-tools
fi

install -d -m 700 /etc/wireguard
PRIV=$(tr -d '[:space:]' < "$KEY_SRC")
cat > /etc/wireguard/wg0.conf <<EOF
[Interface]
PrivateKey = $PRIV
Address = 10.77.0.2/24

[Peer]
# FreeBSD 201.34.130.46 (msk-1-vm-uqv5) — сторона с белым IP, слушает 51820/udp
PublicKey = I4aSAqchQjUW7O4IC6ffrsN289r43U6Sjnfl5lKNB0E=
Endpoint = 201.34.130.46:51820
AllowedIPs = 10.77.0.0/24
PersistentKeepalive = 25
EOF
chmod 600 /etc/wireguard/wg0.conf

systemctl enable --now wg-quick@wg0
sleep 2
wg show
echo "--- ping по туннелю:"
ping -c 3 -W 2 10.77.0.1
