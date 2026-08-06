#!/bin/sh
# Развёртывание приёмника пакетного транспорта на Ubuntu. Запуск ВЛАДЕЛЬЦЕМ:
#   sudo sh /srv/1c/work/packet/setup-receiver.sh
# Идемпотентно. Делает только root-часть: каталоги, /etc, юниты; код раскладывает
# deploy_packet.sh. Основание портов — ubuntu/wireguard/README.md (6090, не 6021).
set -eu

REPO=/srv/1c
BASE=ut

echo "== каталоги"
install -d -m 775 -o root -g 1c-secrets /opt/1c-packet
install -d -m 755 -o root -g root /opt/1c-packet/bin
install -d -m 755 -o root -g root /var/lib/1c-packet
install -d -m 755 -o serenedb -g serenedb /var/lib/serenedb/packet-meta
install -d -m 755 -o serenedb -g serenedb "/var/lib/serenedb/packet-meta/$BASE"

echo "== бинари age (официальный релиз v1.1.1, проверка версии)"
install -m 755 "$REPO/work/packet/bin/age/age" /opt/1c-packet/bin/age
install -m 755 "$REPO/work/packet/bin/age/age-keygen" /opt/1c-packet/bin/age-keygen
/opt/1c-packet/bin/age --version

echo "== identity и файл баз"
install -m 640 -o root -g 1c-secrets "$REPO/work/packet/kit/$BASE/age.key" "/etc/1c-packet-age-$BASE.key"
python3 - "$REPO/work/packet/kit/$BASE/bases-entry.json" << 'EOF'
import json, sys
doc = json.load(open(sys.argv[1], encoding='utf-8'))
for base, rec in doc.items():
    rec['identity'] = f'/etc/1c-packet-age-{base}.key'
with open('/etc/1c-packet-bases.json', 'w', encoding='utf-8') as f:
    json.dump(doc, f, ensure_ascii=False, indent=2)
EOF
chown root:1c-secrets /etc/1c-packet-bases.json && chmod 640 /etc/1c-packet-bases.json

echo "== /etc/1c-packet.env"
cat > /etc/1c-packet.env << 'EOF'
PACKET_ROOT=/var/lib/1c-packet
PACKET_LISTEN=127.0.0.1:6090
PACKET_BASES=/etc/1c-packet-bases.json
PACKET_AGE_BIN=/opt/1c-packet/bin/age
PACKET_AGE_KEYGEN_BIN=/opt/1c-packet/bin/age-keygen
SERENEDB_DSN=host=127.0.0.1 port=7890 user=postgres dbname=ut_test
EOF
chown root:1c-secrets /etc/1c-packet.env && chmod 640 /etc/1c-packet.env

echo "== раскладка кода"
su - claudedev -c "cd $REPO && bash ubuntu/packet/deploy_packet.sh"

echo "== юниты"
install -m 644 "$REPO/ubuntu/packet/systemd/1c-packet-server.service" /etc/systemd/system/
install -m 644 "$REPO/ubuntu/packet/systemd/1c-packet-apply.service" /etc/systemd/system/
install -m 644 "$REPO/ubuntu/packet/systemd/1c-packet-apply.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now 1c-packet-server
systemctl enable --now 1c-packet-apply.timer

echo "== проверка"
sleep 2
systemctl is-active 1c-packet-server
curl -s --max-time 5 http://127.0.0.1:6090/health && echo
echo "-- сквозная (домен → HAProxy → туннель → приёмник):"
curl -s --max-time 15 https://1c-gate.timpul.ru/health && echo
echo "== готово. Комплект для Windows: $REPO/work/packet/kit/$BASE/packet-setup.json"
