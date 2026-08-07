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

echo "== CA клиентских сертификатов (mTLS, контракт §8) — один раз"
if [ ! -f /etc/1c-packet-ca.key ]; then
  openssl genrsa -out /etc/1c-packet-ca.key 2048
  chown root:1c-secrets /etc/1c-packet-ca.key && chmod 640 /etc/1c-packet-ca.key
  openssl req -x509 -new -key /etc/1c-packet-ca.key -days 3650 -sha256 \
    -subj "/CN=1c-packet-ca" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -out /etc/1c-packet-ca.crt
  chmod 644 /etc/1c-packet-ca.crt
fi
install -d -m 755 "$REPO/work/packet/ca"
install -m 644 /etc/1c-packet-ca.crt "$REPO/work/packet/ca/1c-packet-ca.crt"
echo "   CA-гриф для FreeBSD: $REPO/work/packet/ca/1c-packet-ca.crt"

echo "== комплект $BASE с клиентским сертификатом (после CA)"
su - claudedev -c "cd $REPO && \
  PACKET_AGE_BIN=/opt/1c-packet/bin/age PACKET_AGE_KEYGEN_BIN=/opt/1c-packet/bin/age-keygen \
  python3 ubuntu/packet/packet_kit.py $BASE \
  --dsn 'host=127.0.0.1 port=7890 user=postgres dbname=ut_test'"

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
if curl -s --max-time 15 https://1c-gate.timpul.ru/health; then echo; else
  echo "   (соединение отвергнуто без клиентского сертификата — так и задумано при mTLS)"
fi
if [ -f "$REPO/work/packet/kit/$BASE/client.crt" ]; then
  echo "-- сквозная с клиентским сертификатом $BASE:"
  curl -s --max-time 15 --cert "$REPO/work/packet/kit/$BASE/client.crt" \
       --key "$REPO/work/packet/kit/$BASE/client-key.pem" \
       https://1c-gate.timpul.ru/health && echo || \
  echo "   (отказ — mTLS на релее ещё не включён: задание сессии FreeBSD)"
fi
echo "== готово. Комплект для Windows: $REPO/work/packet/kit/$BASE/packet-setup.json"
